import json
import pymupdf
import pytest

from src.extraction.native_pdf_fallback import read_native_page
from src.extraction.source_v2 import capture_pdf
from src.extraction.esg_v2 import extract_esg
from src.extraction.corporate_handoff import convert_document


def test_literal_fallback_table_is_partial_and_reaches_contract_with_source(tmp_path):
    path = tmp_path / 'BSR_2025.pdf'
    with pymupdf.open() as pdf:
        page = pdf.new_page(width=400, height=250)
        page.insert_text((30, 35), 'Native source for table test. Values copied only from real cells.', fontsize=9)
        for x in (30, 200, 280, 370):
            page.draw_line((x, 80), (x, 150))
        for y in (80, 115, 150):
            page.draw_line((30, y), (370, y))
        for y, row in ((100, ['Indicator', 'Unit', '2025']), (135, ['Total employees', 'people', '1594'])):
            for x, text in zip((40, 210, 290), row):
                page.insert_text((x, y), text, fontsize=9)
        pdf.save(path)
    native = read_native_page(path, 1)
    assert native['status'] == 'partial'
    assert native['read_method'] == 'pymupdf_native_text_and_tables_fallback'
    cells = native['document']['tables'][0]['data']['table_cells']
    assert any(c['text'] == '1594' and c['start_col_offset_idx'] == 2 for c in cells)
    work = capture_pdf(path, tmp_path / 'capture', company_id='BSR', report_type='ESG', report_year=2025,
                       profile={'engine': 'native-fallback-test'}, page_reader=read_native_page, retries=0)
    output = json.loads(extract_esg(work).read_text(encoding='utf-8'))
    coverage = json.loads((work / 'canonical.json').read_text(encoding='utf-8'))['coverage']
    h = convert_document({'filename': path.name, 'workspace': str(work), 'output': output, 'coverage': coverage})
    r = next(r for r in h['records'] if r['record_type'] == 'measurement')
    assert r['value']['normalized_value'] == 1594 and r['period']['observation_year'] == 2025
    assert r['quality']['review_status'] == 'pending_human_review'
    assert r['evidence'][0]['physical_page'] == 1


def test_blank_or_image_only_native_page_is_not_claimed_read(tmp_path):
    path = tmp_path / 'blank.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(path)
    with pytest.raises(ValueError, match='needs OCR'):
        read_native_page(path, 1)
