import json

import pymupdf

from src.extraction.financial_v2 import extract_financial, validate_financial
from src.extraction.source_v2 import capture_pdf


def page(*paragraphs):
    texts = [{'text': p[0], 'label': p[1]} if isinstance(p, tuple) else {'text': p, 'label': 'text'} for p in paragraphs]
    return {'texts': texts, 'body': {'children': [{'$ref': f'#/texts/{i}'} for i in range(len(texts))]}}


def run_notes(tmp_path, pages, fail_page=None):
    source = tmp_path / 'notes.pdf'
    with pymupdf.open() as pdf:
        for _ in pages:
            pdf.new_page()
        pdf.save(source)
    def reader(path, number):
        if number == fail_page:
            raise RuntimeError('OCR failure')
        return {'status': 'processed', 'document': pages[number - 1], 'markdown': 'notes'}
    work = capture_pdf(source, tmp_path / 'out', company_id='BSR', report_type='financial_statements', report_year=2025,
                       page_reader=reader, retries=0, profile={'engine': 'test-notes'})
    output = extract_financial(work)
    result = json.loads(output.read_text(encoding='utf-8'))
    notes = [r for r in result['records'] if r['record_type'] == 'financial_context']
    return work, result, notes


def test_policy_without_numbers_keeps_exact_text_and_missing_fields(tmp_path):
    raw = 'Doanh thu được ghi nhận khi  nghĩa vụ thực hiện\nđã hoàn thành.'
    _, result, notes = run_notes(tmp_path, [page(('THUYẾT MINH BÁO CÁO TÀI CHÍNH RIÊNG', 'section_header'),
                                               ('3. Chính sách kế toán', 'section_header'), raw)])
    assert len(notes) == 1
    record = notes[0]
    assert record['original_text'] == raw
    assert record['payload']['statement'] == raw
    assert record['payload']['context_type_candidates'] == ['accounting_policy']
    assert record['payload']['section_heading_raw'] == '3. Chính sách kế toán'
    assert record['payload']['statement_scope'] == 'separate'
    assert record['payload']['effective_date'] is None
    assert '/payload/effective_date' in record['missing_fields']
    assert record['content_period'] is None
    assert record['classification']['pillar'] == 'unknown'
    assert record['boundary']['included_entities'] is None
    assert record['review']['status'] == 'needs_review'
    assert result['validation']['valid']


def test_notes_context_continues_across_pages_with_heading_source(tmp_path):
    pages = [page(('Notes to the consolidated financial statements', 'section_header'), ('6. Borrowings', 'section_header')),
             page('The loan is secured by inventories and matures in 2027.')]
    work, result, notes = run_notes(tmp_path, pages)
    assert len(notes) == 1
    record = notes[0]
    assert record['payload']['context_type'] == 'general_note'
    assert record['field_sources']['/payload/section_heading_raw'][0]['pdf_page'] == 1
    assert record['field_sources']['/payload/statement'][0]['pdf_page'] == 2
    assert record['content_period'] is None
    assert record['payload']['statement_scope'] == 'consolidated'
    before = [r['record_id'] for r in notes]
    rerun = json.loads(extract_financial(work).read_text(encoding='utf-8'))
    assert before == [r['record_id'] for r in rerun['records'] if r['record_type'] == 'financial_context']


def test_gap_blocks_heading_inheritance_but_retains_keyword_candidate(tmp_path):
    pages = [page(('Thuyết minh báo cáo tài chính riêng', 'section_header'), ('4. Rủi ro', 'section_header')),
             {}, page('Rủi ro tỷ giá có thể ảnh hưởng chi phí.')]
    _, result, notes = run_notes(tmp_path, pages, fail_page=2)
    assert len(notes) == 1
    assert notes[0]['payload']['notes_title_raw'] is None
    assert notes[0]['payload']['section_heading_raw'] is None
    assert '/payload/notes_title_raw' in notes[0]['missing_fields']
    assert result['source_capture_coverage']['counts']['failed'] == 1


def test_statement_footer_and_unit_not_falsely_extracted_as_notes(tmp_path):
    _, result, notes = run_notes(tmp_path, [page(('Bảng cân đối kế toán', 'section_header'),
                                               'Các thuyết minh kèm theo là bộ phận của báo cáo tài chính riêng này.',
                                               'Đơn vị: VND', ('9', 'page_footer'))])
    assert notes == []
    assert len(result['notes_coverage']) == 4
    assert any(c['disposition'] == 'statement_footer_retained_in_source' for c in result['notes_coverage'])


def test_financial_esg_mentions_stay_candidates_not_esg_verdict(tmp_path):
    raw = 'Không phát sinh nghĩa vụ tiềm tàng về môi trường; công ty có cam kết đầu tư.'
    _, result, notes = run_notes(tmp_path, [page(raw)])
    assert len(notes) == 1
    record = notes[0]
    assert set(record['payload']['context_type_candidates']) == {'contingency', 'financial_esg_context', 'commitment'}
    assert record['record_type'] == 'financial_context'
    assert record['classification']['pillar'] == 'unknown'
    assert record['payload']['target_year'] is None
    assert record['payload']['baseline_value'] is None
    assert not result['graph_ready']
    assert any(i['code'] == 'NOTE_CLASSIFICATION_CANDIDATE' for i in result['issues'])


def test_unreachable_text_retained_and_flagged(tmp_path):
    native = page('A paragraph about accounting policy.')
    native['body']['children'] = []
    _, result, notes = run_notes(tmp_path, [native])
    assert notes == []
    assert result['notes_coverage'][0]['disposition'] == 'reading_order_unknown'
    assert any(i['code'] == 'NOTE_READING_ORDER_UNKNOWN' for i in result['issues'])


def test_statement_heading_stops_notes_context(tmp_path):
    _, result, notes = run_notes(tmp_path, [page(('Thuyết minh báo cáo tài chính', 'section_header'),
                                               'Một nội dung thuyết minh không có số.',
                                               ('Báo cáo lưu chuyển tiền tệ', 'section_header'),
                                               'Một đoạn ngoài phần thuyết minh.')])
    assert len(notes) == 1
    assert result['notes_coverage'][-1]['disposition'] == 'outside_notes_or_context_unknown'


def test_nested_reading_order_and_numeric_leading_paragraph(tmp_path):
    native = page(('Thuyết minh báo cáo tài chính', 'section_header'), '5 năm là thời gian sử dụng tài sản.')
    native['groups'] = [{'children': [{'$ref': '#/texts/0'}, {'$ref': '#/texts/1'}]}]
    native['body']['children'] = [{'$ref': '#/groups/0'}]
    _, _, notes = run_notes(tmp_path, [native])
    assert len(notes) == 1
    assert notes[0]['original_text'].startswith('5 năm')


def test_notes_coverage_missing_entry_rejected(tmp_path):
    work, result, _ = run_notes(tmp_path, [page('Accounting policy for depreciation is disclosed here.')])
    result['notes_coverage'] = []
    assert 'Not all text blocks have a note disposition.' in validate_financial(result, work)
