from copy import deepcopy
import json

import pymupdf
import pytest

from src.extraction.financial_v2 import extract_table, extract_financial, validate_financial
from src.extraction.source_v2 import capture_pdf, file_hash
from tests.test_financial_v2 import cell, fixture


def box(left, right):
    return {'l': left, 'r': right, 't': 10, 'b': 20, 'coord_origin': 'TOPLEFT'}


def merged_header_fixture():
    b, context, report = fixture(headers=('Năm nay', 'Năm trước'))
    cells = [cell('Chỉ tiêu', 0, 0, True), cell('Mã số Thuyết minh', 0, 2, True),
             cell('Năm nay', 0, 3, True), cell('Năm trước', 0, 4, True)]
    cells[1]['bbox'] = box(100, 180)
    cells[2]['bbox'] = box(240, 290)
    cells[3]['bbox'] = box(340, 390)
    for row in range(1, 4):
        items = [cell('Chỉ tiêu bất kỳ', row, 0), cell(f'{row:02} ', row, 1),
                 cell('8', row, 2), cell('1.234.567.890 9.876.543.210 ', row, 4)]
        items[1]['bbox'] = box(105, 125)
        items[2]['bbox'] = box(155, 165)
        items[3]['bbox'] = box(200, 395)
        cells += items
    b['original_cells'] = cells
    return b, context, report


def test_misindexed_merged_code_header_and_amount_pair_are_source_grounded():
    b, context, report = merged_header_fixture()
    original = deepcopy(b)
    records, links, issues = extract_table(b, context, report, number_format='vi')
    measurements = [r for r in records if r['record_type'] == 'measurement']
    assert b == original
    assert len(measurements) == len(links) == 6
    assert [r['payload']['item_code_raw'] for r in measurements] == ['01 ', '01 ', '02 ', '02 ', '03 ', '03 ']
    assert [r['payload']['parsed_value'] for r in measurements[:2]] == ['1234567890', '9876543210']
    assert [r['payload']['column_headers_raw'] for r in measurements[:2]] == [['Năm nay'], ['Năm trước']]
    assert not any(i['code'] in ('MERGED_VALUE_CELL', 'VALUE_CELL_NOT_DETECTED') for i in issues)
    for r in measurements:
        source = r['field_sources']['/payload/raw_value'][0]
        lo, hi = source['text_span']
        assert source['raw_text'][lo:hi] == r['payload']['raw_value']
        assert source['bbox'] == box(200, 395)  # Whole cell, not a made-up token box.
        assert r['original_cells'][-1]['text'] == source['raw_text']
        assert len(r['field_sources']['/payload/item_code_raw']) == 2


@pytest.mark.parametrize('change', ['no_geometry', 'one_row', 'damaged_codes'])
def test_ambiguous_code_mapping_abstains(change):
    b, context, report = merged_header_fixture()
    if change == 'no_geometry':
        b['original_cells'][1].pop('bbox')
        # Keep the ambiguity explicit: a merged code/note header has no usable geometry.
    elif change == 'one_row':
        b['original_cells'] = [c for c in b['original_cells'] if c['start_row_offset_idx'] <= 1]
    else:
        for c in b['original_cells']:
            if not c['column_header'] and c['start_col_offset_idx'] == 1:
                c['text'] = 'OCR?'
    records, _, _ = extract_table(b, context, report)
    assert all(r['payload']['item_code_raw'] is None for r in records)
    assert all('/payload/item_code_raw' in r['missing_fields'] for r in records)
    assert all(r['payload']['column_index'] in (3, 4) for r in records if r['record_type'] == 'measurement')


@pytest.mark.parametrize('raw', ['1 234', '123 456', '12.345 67.890', '1.234.567 8.765.432 9.876.543'])
def test_spaced_integer_or_multiple_tokens_not_guessed(raw):
    b, context, report = merged_header_fixture()
    for c in b['original_cells']:
        if not c['column_header'] and c['start_col_offset_idx'] == 4:
            c['text'] = raw
    records, _, _ = extract_table(b, context, report)
    assert not any('text_span' in s for r in records for s in r['field_sources'].get('/payload/raw_value', []))


def test_same_column_vertical_contamination_not_split():
    b, context, report = merged_header_fixture()
    for c in b['original_cells']:
        if not c['column_header'] and c['start_col_offset_idx'] == 4:
            c['bbox'] = box(320, 395)
    records, _, _ = extract_table(b, context, report, number_format='vi')
    amounts = [r for r in records if r['record_type'] == 'measurement']
    assert len(amounts) == 3
    assert all(r['payload']['parsed_value'] is None for r in amounts)


def test_reversed_period_columns_follow_headers_not_assumed_order():
    b, context, report = merged_header_fixture()
    b['original_cells'][2]['text'] = 'Năm trước'
    b['original_cells'][3]['text'] = 'Năm nay'
    records, _, _ = extract_table(b, context, report, number_format='vi')
    amounts = [r for r in records if r['record_type'] == 'measurement']
    assert [r['payload']['column_headers_raw'] for r in amounts[:2]] == [['Năm trước'], ['Năm nay']]
    assert [r['payload']['parsed_value'] for r in amounts[:2]] == ['1234567890', '9876543210']


def test_separate_current_year_cell_is_not_excluded_as_metadata():
    records, _, _ = extract_table(*fixture(headers=('Năm nay', 'Năm trước')), number_format='vi')
    amounts = [r for r in records if r['record_type'] == 'measurement']
    assert len(amounts) == 2
    assert amounts[0]['payload']['period_role'] == 'current_flow'
    assert amounts[0]['payload']['column_index'] == 3


def test_substring_sources_validate_and_tampering_is_rejected(tmp_path):
    pdf = tmp_path / 'report.pdf'
    with pymupdf.open() as doc:
        doc.new_page()
        doc.save(pdf)
    b, _, _ = merged_header_fixture()
    native = {'texts': [{'text': 'Đơn vị: VND', 'label': 'text'}],
              'tables': [{'data': {'table_cells': b['original_cells']}, 'label': 'table'}],
              'body': {'children': [{'$ref': '#/texts/0'}, {'$ref': '#/tables/0'}]}}
    work = capture_pdf(pdf, tmp_path / 'capture', company_id='OTHER', report_type='financial_statements',
        profile={'engine': 'test'}, page_reader=lambda *a: {'status': 'processed', 'document': native, 'markdown': 'table'})
    checkpoint = work / 'pages/0001.json'
    before = file_hash(checkpoint)
    path = extract_financial(work, number_format='vi')
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['parser_version'] == 7
    assert not validate_financial(data, work)
    measurement = next(r for r in data['records'] if r['record_type'] == 'measurement')
    measurement['field_sources']['/payload/raw_value'][0]['text_span'] = [-1, 4]
    assert 'Invalid measurement source substring span.' in validate_financial(data, work)
    assert file_hash(checkpoint) == before
