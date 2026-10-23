import json

import pymupdf
import pytest

from src.extraction.financial_v2 import extract_financial, extract_table, parse_number, parse_period
from src.extraction.source_v2 import capture_pdf


def cell(text, row, col, header=False):
    return {'text': text, 'start_row_offset_idx': row, 'end_row_offset_idx': row + 1,
            'start_col_offset_idx': col, 'end_col_offset_idx': col + 1,
            'column_header': header, 'row_span': 1, 'col_span': 1}


def fixture(headers=('2025', '2024'), values=('85.004.418.533.771', '88.352.140.328.065')):
    cells = [cell('Chỉ tiêu', 0, 0, True), cell('Mã số', 0, 1, True),
             cell('Thuyết minh', 0, 2, True), cell(headers[0], 0, 3, True), cell(headers[1], 0, 4, True),
             cell('Tổng cộng tài sản', 1, 0), cell('270', 1, 1), cell('5', 1, 2),
             cell(values[0], 1, 3), cell(values[1], 1, 4)]
    block = {'block_id': 'table', 'original_cells': cells,
             'source': {'artifact_id': 'artifact', 'artifact_sha256': 'hash',
                        'native_json_pointer': '/document/tables/0', 'pdf_page': 9}}
    context = [{'original_text': 'Đơn vị: VND', 'source': {'pdf_page': 9, 'native_json_pointer': '/document/texts/0'}}]
    report = {'report_version_id': 'report', 'company_id': 'BSR', 'reporting_year': 2026}
    return block, context, report


def test_two_columns_are_two_measurements_not_code_or_note():
    records, links, issues = extract_table(*fixture())
    metric, *measurements = records
    assert metric['original_text'] == 'Tổng cộng tài sản'
    assert len(measurements) == 2
    assert len(links) == 2
    assert [r['payload']['parsed_value'] for r in measurements] == ['85004418533771', '88352140328065']
    assert [r['content_period']['year'] for r in measurements] == [2025, 2024]
    assert all(r['payload']['currency'] == 'VND' for r in measurements)
    assert measurements[0]['original_text'] == '85.004.418.533.771'
    assert measurements[0]['payload']['column_headers_raw'] == ['2025']
    assert all(r['payload']['statement_scope'] is None for r in measurements)
    assert all(r['review']['status'] == 'needs_review' for r in records)
    assert all(r['classification']['pillar'] == 'unknown' for r in records)


@pytest.mark.parametrize('raw,expected,status', [
    ('(1.234.567)', '-1234567', 'available'), ('0', '0', 'available'),
    ('-', None, 'missing'), ('', None, 'missing'), ('1.234', None, 'ambiguous'),
    ('12,5', '12.5', 'available'), ('12O.000', None, 'ambiguous'),
    ('1,234.56', None, 'ambiguous'), ('1.234.56', None, 'ambiguous'),
    ('(-1)', None, 'ambiguous'), ('1 2', None, 'ambiguous'), ('1 234', '1234', 'available'),
])
def test_numeric_parser_preserves_ambiguity(raw, expected, status):
    assert parse_number(raw) == (expected, status)


def test_explicit_formats_and_exact_large_integer_normalization():
    assert parse_number('1.234,56', 'vi') == ('1234.56', 'available')
    assert parse_number('1,234.56', 'en') == ('1234.56', 'available')
    block, context, report = fixture(values=('123456789012345678901234567890123', '0'))
    context[0]['original_text'] = 'Đơn vị tính: triệu đồng'
    records, _, _ = extract_table(block, context, report)
    assert records[1]['payload']['normalized_value'] == '123456789012345678901234567890123000000'
    assert records[2]['payload']['normalized_value'] == '0'


def test_unknown_period_not_report_year_and_missing_lists():
    records, _, issues = extract_table(*fixture(headers=('Số cuối năm', 'Số đầu năm')))
    assert records[1]['content_period'] is None
    assert records[1]['payload']['period_role'] == 'current'
    assert records[2]['payload']['period_role'] == 'opening_balance'
    assert '/content_period' in records[1]['missing_fields']
    assert '/boundary/included_entities' in records[1]['missing_fields']
    assert 'included_entities' in records[1]['boundary']['missing_fields']
    assert sum(i['code'] == 'PERIOD_UNKNOWN' for i in issues) == 2


def test_missing_unit_and_blank_zero_distinct():
    block, _, report = fixture(values=('-', '0'))
    records, _, _ = extract_table(block, [], report)
    assert records[1]['payload']['parsed_value'] is None
    assert records[1]['data_status'] == 'missing'
    assert records[2]['payload']['parsed_value'] == '0'
    assert records[2]['payload']['currency'] is None
    assert records[2]['payload']['normalized_value'] is None


def test_merged_value_not_silently_assigned():
    block, context, report = fixture()
    block['original_cells'][-1]['col_span'] = 2
    block['original_cells'][-1]['end_col_offset_idx'] = 6
    records, _, issues = extract_table(block, context, report)
    assert records[-1]['data_status'] == 'ambiguous'
    assert records[-1]['payload']['parsed_value'] is None
    assert any(i['code'] == 'MERGED_VALUE_CELL' for i in issues)


def test_absent_source_cell_is_logged_not_synthesized():
    block, context, report = fixture()
    block['original_cells'].pop()
    records, _, issues = extract_table(block, context, report)
    assert len(records) == 2
    assert any(i['code'] == 'VALUE_CELL_NOT_DETECTED' for i in issues)


def test_english_currency_scale_and_unrelated_context_not_inherited():
    block, context, report = fixture()
    context[0]['original_text'] = 'Unit: million USD'
    records, _, _ = extract_table(block, context, report)
    assert records[1]['payload']['scale'] == '1000000'
    context[0]['original_text'] = 'Investment was 10 million USD'
    records, _, _ = extract_table(block, context, report)
    assert records[1]['payload']['currency'] is None


def test_date_and_quarter_not_guessed():
    assert parse_period('31/12/2025')['as_of_date'] == '2025-12-31'
    assert parse_period('31/02/2025') is None
    assert parse_period('Quý 1 năm 2025') is None
    assert parse_period('2025 và 2024') is None


def test_end_to_end_source_context_export_and_stable_ids(tmp_path):
    source = tmp_path / 'report.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(source)
    block, _, _ = fixture()
    native = {'texts': [{'text': 'Đơn vị: VND', 'label': 'text'}],
              'tables': [{'data': {'table_cells': block['original_cells']}, 'label': 'table'}],
              'body': {'children': [{'$ref': '#/texts/0'}, {'$ref': '#/tables/0'}]}}
    work = capture_pdf(source, tmp_path / 'out', report_type='financial_statements', company_id='BSR',
                       page_reader=lambda *a: {'status': 'processed', 'document': native, 'markdown': 'table'},
                       profile={'engine': 'test'})
    output = extract_financial(work)
    first = json.loads(output.read_text(encoding='utf-8'))
    assert first['counts'] == {'metrics': 1, 'measurements': 2, 'tables_seen': 1, 'financial_contexts': 0}
    assert first['records'][1]['payload']['currency'] == 'VND'
    assert first['validation']['valid']
    assert not first['graph_ready']
    assert first['semantic_status'] == 'partial'
    assert first['records'][1]['field_sources']['/payload/raw_value'][0]['native_json_pointer'].endswith('/table_cells/8')
    extract_financial(work)
    second = json.loads(output.read_text(encoding='utf-8'))
    assert [r['record_id'] for r in first['records']] == [r['record_id'] for r in second['records']]
    assert json.loads((work / 'canonical.json').read_text(encoding='utf-8'))['records'] == []


def test_esg_rejected_by_financial_parser(tmp_path):
    source = tmp_path / 'report.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(source)
    work = capture_pdf(source, tmp_path / 'out', report_type='ESG',
                       page_reader=lambda *a: {'status': 'processed', 'document': {}, 'markdown': 'policy'},
                       profile={'engine': 'test'})
    with pytest.raises(ValueError, match='separate branch'):
        extract_financial(work)
