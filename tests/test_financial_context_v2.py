import json

import pymupdf
import pytest

from src.extraction.financial_context_v2 import scope_candidate
from src.extraction.financial_v2 import extract_financial
from src.extraction.source_v2 import capture_pdf


def cell(text, row, col, header=False):
    return {'text': text, 'start_row_offset_idx': row, 'end_row_offset_idx': row + 1,
            'start_col_offset_idx': col, 'end_col_offset_idx': col + 1,
            'column_header': header, 'row_span': 1, 'col_span': 1}


def native_page(title, *, headers=True, unit=None, scope=None, years=('2025', '2024')):
    cells = ([cell('Chỉ tiêu', 0, 0, True), cell(years[0], 0, 1, True), cell(years[1], 0, 2, True)] if headers else [])
    cells += [cell('Tiền mặt', 1, 0), cell('1000000', 1, 1), cell('2000000', 1, 2)]
    texts = [{'text': title, 'label': 'section_header'}]
    if unit:
        texts.append({'text': unit, 'label': 'text'})
    children = [{'$ref': f'#/texts/{i}'} for i in range(len(texts))] + [{'$ref': '#/tables/0'}]
    if scope:
        children.append({'$ref': f'#/texts/{len(texts)}'})
        texts.append({'text': scope, 'label': 'text'})
    return {'texts': texts, 'tables': [{'label': 'table', 'data': {'table_cells': cells}}],
            'body': {'children': children}}


def run_pages(tmp_path, pages, failed_page=None):
    source = tmp_path / 'BCTC_hop_nhat_filename_not_evidence.pdf'
    with pymupdf.open() as pdf:
        for _ in pages:
            pdf.new_page()
        pdf.save(source)
    def reader(path, number):
        if number == failed_page:
            raise RuntimeError('scan failure')
        return {'status': 'processed', 'document': pages[number - 1], 'markdown': 'table'}
    work = capture_pdf(source, tmp_path / 'out', company_id='BSR', report_type='financial_statements',
                       page_reader=reader, retries=0, profile={'engine': 'fixture'})
    result_path = extract_financial(work)
    return work, json.loads(result_path.read_text(encoding='utf-8'))


def measurements(result, page):
    anchors = {b['block_id'] for b in result['source_blocks'] if b['source']['pdf_page'] == page}
    return [r for r in result['records'] if r['record_type'] == 'measurement' and r['payload']['table_anchor_id'] in anchors]


def test_explicit_continuation_inherits_headers_unit_and_scope_with_sources(tmp_path):
    pages = [native_page('Bảng cân đối kế toán', unit='Đơn vị: triệu đồng',
                         scope='Các thuyết minh là bộ phận của bộ báo cáo tài chính riêng này.'),
             native_page('Bảng cân đối kế toán (tiếp theo)', headers=False)]
    work, result = run_pages(tmp_path, pages)
    second = measurements(result, 2)
    assert result['table_continuations'][0]['status'] == 'rule_matched'
    assert len(second) == 2
    assert [r['content_period']['year'] for r in second] == [2025, 2024]
    assert all(r['payload']['currency'] == 'VND' and r['payload']['scale'] == '1000000' for r in second)
    assert all(r['payload']['statement_scope'] == 'separate' for r in second)
    assert second[0]['field_sources']['/content_period'][0]['pdf_page'] == 1
    assert second[0]['field_sources']['/payload/unit'][0]['pdf_page'] == 1
    assert second[0]['field_sources']['/payload/raw_value'][0]['pdf_page'] == 2
    assert second[0]['field_sources']['/payload/statement_scope'][0]['pdf_page'] == 1
    assert '/payload/statement_scope' not in second[0]['missing_fields']
    assert second[0]['boundary']['included_entities'] is None
    assert 'included_entities' in second[0]['boundary']['missing_fields']
    assert result['validation']['valid']
    ids = [r['record_id'] for r in result['records']]
    rerun = json.loads(extract_financial(work).read_text(encoding='utf-8'))
    assert ids == [r['record_id'] for r in rerun['records']]


@pytest.mark.parametrize('change,reason', [
    ('title', 'explicit_matching_continuation_title_required'),
    ('year', 'header_mapping_conflict'),
    ('unit', 'unit_or_scale_conflict'),
    ('scope', 'statement_scope_conflict'),
])
def test_reject_continuation_conflicts_without_inheriting(tmp_path, change, reason):
    first = native_page('Bảng cân đối kế toán', unit='Đơn vị: VND', scope='Báo cáo tài chính riêng')
    second = native_page('Bảng cân đối kế toán (tiếp theo)', headers=False)
    if change == 'title':
        second['texts'][0]['text'] = 'Bảng cân đối kế toán'
    if change == 'year':
        second = native_page('Bảng cân đối kế toán (tiếp theo)', years=('2026', '2025'))
    if change == 'unit':
        second = native_page('Bảng cân đối kế toán (tiếp theo)', headers=False, unit='Đơn vị: USD')
    if change == 'scope':
        second = native_page('Bảng cân đối kế toán (tiếp theo)', headers=False, scope='Báo cáo tài chính hợp nhất')
    _, result = run_pages(tmp_path, [first, second])
    assert result['table_continuations'][0]['status'] == 'rejected'
    assert reason in result['table_continuations'][0]['reasons']
    if change != 'year':
        assert all(r['content_period'] is None for r in measurements(result, 2))
    if change == 'title':
        assert all(r['payload']['unit'] is None for r in measurements(result, 2))


def test_do_not_inherit_across_failed_page(tmp_path):
    pages = [native_page('Bảng cân đối kế toán', unit='Đơn vị: VND'), {},
             native_page('Bảng cân đối kế toán (tiếp theo)', headers=False)]
    _, result = run_pages(tmp_path, pages, failed_page=2)
    assert result['source_capture_coverage']['counts']['failed'] == 1
    assert result['table_continuations'][0]['status'] == 'rejected'
    assert 'not_adjacent_page_edge_tables' in result['table_continuations'][0]['reasons']
    assert all(r['payload']['unit'] is None for r in measurements(result, 3))


def test_three_page_chain_keeps_original_header_provenance(tmp_path):
    pages = [native_page('Bảng cân đối kế toán', unit='Đơn vị: VND'),
             native_page('Bảng cân đối kế toán (tiếp theo)', headers=False),
             native_page('Bảng cân đối kế toán (tiếp theo)', headers=False)]
    _, result = run_pages(tmp_path, pages)
    assert [c['status'] for c in result['table_continuations']] == ['rule_matched', 'rule_matched']
    assert measurements(result, 3)[0]['field_sources']['/content_period'][0]['pdf_page'] == 1
    assert len({r['payload']['logical_table_id'] for r in result['records']}) == 1


def test_conflicting_scope_stays_null_and_missing(tmp_path):
    page = native_page('Báo cáo tài chính riêng', scope='Báo cáo tài chính hợp nhất')
    _, result = run_pages(tmp_path, [page])
    record = measurements(result, 1)[0]
    assert record['payload']['statement_scope'] is None
    assert record['field_status']['/payload/statement_scope']['status'] == 'ambiguous'
    assert '/payload/statement_scope' in record['missing_fields']
    assert any(i['code'] == 'STATEMENT_SCOPE_CONFLICT' for i in result['issues'])


def test_filename_and_general_reference_do_not_establish_scope(tmp_path):
    page = native_page('Bảng cân đối kế toán', scope='Công ty con lập báo cáo tài chính riêng cho hoạt động của mình.')
    _, result = run_pages(tmp_path, [page])
    assert all(r['payload']['statement_scope'] is None for r in result['records'])


@pytest.mark.parametrize('text,value', [
    ('Báo cáo tài chính hợp nhất cho năm kết thúc ngày 31/12/2025', 'consolidated'),
    ('Separate financial statements', 'separate'),
    ('Notes to the consolidated financial statements', 'consolidated'),
    ('Bảng cân đối kế toán riêng', 'separate'),
    ('Báo cáo tài chính không hợp nhất', None),
    ('So sánh báo cáo tài chính riêng và hợp nhất', None),
])
def test_scope_labels(text, value):
    block = {'block_id': 'text', 'original_text': text, 'source': {'pdf_page': 1}}
    result = scope_candidate(block)
    assert (result['scope'] if result else None) == value
