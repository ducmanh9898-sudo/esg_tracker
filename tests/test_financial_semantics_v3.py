from src.extraction.financial_semantics_v3 import resolved_period, metadata, formula_terms, section_contexts
from src.extraction.financial_v2 import extract_table
from src.extraction.financial_layout_recovery import recover_statement_table
from tests.test_financial_v2 import fixture, cell


def meta(start='2024-01-01', end='2024-12-31'):
    return {'period_start': {'value': start, 'sources': []}, 'period_end': {'value': end, 'sources': []}}


def test_contents_page_numbers_are_not_measurements():
    b, context, report = fixture()
    b['original_cells'] = [cell('NỘI DUNG', 0, 0, True), cell('TRANG', 0, 1, True),
                           cell('Báo cáo Ban Tổng Giám đốc', 1, 0), cell('1–2', 1, 1)]
    records, links, issues = extract_table(b, context, report)
    assert not records and not links
    assert issues[0]['code'] == 'CONTENTS_TABLE_EXCLUDED'


def test_relative_columns_use_pdf_period_not_input_year():
    closing, _ = resolved_period('Số cuối năm', 'Tài sản', 'balance_sheet', meta())
    opening, _ = resolved_period('Số đầu năm', 'Tài sản', 'balance_sheet', meta())
    previous, _ = resolved_period('Năm trước', 'Doanh thu', 'income_statement', meta())
    assert closing['as_of_date'] == '2024-12-31'
    assert opening['as_of_date'] == '2023-12-31'
    assert previous['start_date'] == '2023-01-01'
    assert previous['end_date'] == '2023-12-31'
    assert resolved_period('Năm nay', '', 'cash_flow', meta(end=None))[0] is None


def test_opening_cash_in_flow_table_is_instant():
    p, _ = resolved_period('Năm trước', 'Tiền đầu năm', 'cash_flow', meta())
    assert p['as_of_date'] == '2022-12-31'
    assert p['period_type'] == 'instant'


def test_multiple_year_headers_are_not_collapsed():
    assert resolved_period('2024 và 2023', '', 'note_table', meta())[0] is None
    assert resolved_period('31/12/2024 và 31/12/2023', '', 'note_table', meta())[0] is None
    assert resolved_period('Quý 1 năm 2024', '', 'note_table', meta())[0] is None
    p, _ = resolved_period('Từ 01/01/2024 đến 30/06/2024', '', 'note_table', meta())
    assert p['start_date'] == '2024-01-01' and p['end_date'] == '2024-06-30'


def test_nested_formula_and_unsafe_formula():
    assert formula_terms('20+(21-22)-(25+26)') == [('+', '20'), ('+', '21'), ('-', '22'), ('-', '25'), ('-', '26')]
    assert formula_terms('01') == [('+', '01')]
    assert formula_terms('__import__("os")') == []
    assert formula_terms('10*20') == []


def test_metadata_start_excludes_subsidiary_control_dates():
    def block(text, page):
        return {'kind': 'texts', 'original_text': text, 'block_id': str(page) + text,
                'source': {'pdf_page': page, 'artifact_id': 'a', 'native_json_pointer': '/x'}}
    bundle = {'reports': [{'source_filename': 'x.pdf', 'source_sha256': 'h', 'pdf_page_count': 20}],
              'source_artifacts': [{'kind': 'pdf', 'path': 'source.pdf', 'artifact_id': 'a'}],
              'source_blocks': [block('Cho năm tài chính kết thúc ngày 31 tháng 12 năm 2024', 1),
                                block('Năm tài chính của Công ty bắt đầu từ ngày 01 tháng 01 và kết thúc ngày 31 tháng 12.', 14),
                                block('Công ty hợp nhất từ ngày 27 tháng 5 năm 2024 vào báo cáo cho năm tài chính này', 15),
                                block('Cổ phiếu với mã chứng khoán là BSR.', 12)]}
    result = metadata(bundle)
    assert result['period_start']['value'] == '2024-01-01'
    assert result['ticker_from_pdf']['value'] == 'BSR'
    assert result['statement_scope']['value'] is None


def test_layout_recovery_is_not_generic_numeric_text_table():
    assert recover_statement_table({'texts': [{'text': 'MỤC LỤC'}]}, [], 800) is False
    assert recover_statement_table({'texts': [], 'tables': [{}]}, [], 800) is False


def test_asset_class_headers_are_values_not_row_labels():
    b, context, report = fixture()
    b['original_cells'] = [cell('Tài sản cố định hữu hình khác VND', 0, 1, True),
                           cell('Tổng VND', 0, 2, True), cell('NGUYÊN GIÁ', 1, 0),
                           cell('Số dư đầu năm', 2, 0), cell('1.234.567', 2, 1), cell('2.234.567', 2, 2)]
    records, _, _ = extract_table(b, context, report)
    assert len(records) == 3
    assert records[0]['payload']['original_name'] == 'Số dư đầu năm'
    assert records[0]['payload']['row_group_raw'] == 'NGUYÊN GIÁ'


def test_damaged_code_header_still_excludes_code_values():
    b, context, report = fixture()
    b['original_cells'][1]['text'] = 'Mã s "_x O'
    records, _, _ = extract_table(b, context, report)
    assert len(records) == 3
    assert records[0]['payload']['item_code_raw'] == '270'


def test_missing_statement_table_recovered_from_word_alignment():
    texts = [{'text': 'BÁO CÁO LƯU CHUYỂN TIỀN TỆ HỢP NHẤT'}]
    for label, left, right in [('CHỈ TIÊU', 50, 100), ('Mã số', 300, 320),
                               ('Năm nay', 400, 430), ('Năm trước', 500, 540)]:
        texts.append({'text': label, 'prov': [{'bbox': {'l': left, 'r': right, 't': 100, 'b': 110, 'coord_origin': 'TOPLEFT'}}]})
    words = []
    for n in range(3):
        y = 130 + n * 30
        words.extend([(50, y, 200, y + 10, 'Khoản mục'), (305, y, 315, y + 10, str(30 + n)),
                      (380, y, 430, y + 10, '1.234.567'), (490, y, 540, y + 10, '(2.345.678)')])
    document = {'texts': texts, 'body': {'children': []}}
    assert recover_statement_table(document, words, 800)
    cells = document['tables'][0]['data']['table_cells']
    assert len(cells) == 16
    assert cells[-1]['text'] == '(2.345.678)'
    assert document['texts'] == texts
    assert document['tables'][0]['layout_recovery']['status'] == 'needs_review'


def test_missing_note_number_never_inherits_previous_number(monkeypatch):
    blocks = [{'block_id': 'first', 'kind': 'texts', 'label': 'section_header',
               'original_text': '1. THÔNG TIN KHÁI QUÁT', 'source': {'pdf_page': 12}},
              {'block_id': 'next', 'kind': 'texts', 'label': 'section_header',
               'original_text': 'TÓM TẮT CÁC CHÍNH SÁCH KẾ TOÁN CHỦ YẾU', 'source': {'pdf_page': 13}},
              {'block_id': 'body', 'kind': 'texts', 'label': 'text',
               'original_text': 'Chính sách kế toán...', 'source': {'pdf_page': 13}}]
    monkeypatch.setattr('src.extraction.financial_semantics_v3.ordered_blocks', lambda *a: (blocks, []))
    mapping = section_contexts({'coverage': {'pages': [{'pdf_page': p, 'status': 'processed'} for p in [12, 13]]}}, None)
    assert mapping['first']['number'] == '1'
    assert mapping['body']['number'] is None
    assert mapping['body']['raw'] == blocks[1]['original_text']
