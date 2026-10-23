from src.extraction.corporate_handoff import _financial_workforce_note


def test_explicit_current_workforce_date_excludes_comparative_amount():
    quote = ('Tồng s nhân viên ca Công ty và công ty con ti ngày 31 tháng 12 năm 2025 '
             'là 1.946 (ti ngày 31 tháng12 năm 2024: là 1.891).')
    source = {'artifact_id': 'artifact', 'native_json_pointer': '/document/texts/0',
              'pdf_page': 14}
    block = {'block_id': 'block', 'kind': 'texts', 'source': source,
             'original_text': quote}
    text = {('artifact', '/document/texts/0'): quote}
    result = _financial_workforce_note(block, text, {14}, 'a' * 64, 'Consolidated',
                                       {'14': {'read_method': 'isolated_configured_ocr_single_scanned_page'}})
    assert result['value']['normalized_value'] == 1946
    assert result['value']['original_value'] == '1.946'
    assert result['period']['observation_year'] == 2025
    assert result['period']['measurement_date'] == '2025-12-31'
    assert result['period']['year_basis'] == 'explicit_quote'
    assert result['boundary']['verified'] is False
    assert result['evidence'][0]['exact_quote'] == quote
    assert _financial_workforce_note(block, {}, {14}, 'a' * 64, 'Consolidated', {}) is None
    block['original_text'] = quote.replace('công ty con', 'đơn vị khác')
    assert _financial_workforce_note(block, text, {14}, 'a' * 64, 'Consolidated', {}) is None
