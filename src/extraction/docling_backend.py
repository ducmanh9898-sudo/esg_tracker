"""Docling conversion with full native JSON and explicit table coordinates."""
import re
import threading
import shutil
import os
from contextlib import contextmanager
from pathlib import Path

import pymupdf

CONVERSION_LOCK = threading.Lock()


def table_rows(table):
    """Keep all cells, including empty and merged cells, without guessing years."""
    data = table.get('data', {})
    cells = data.get('table_cells', [])
    rows = []
    for row_index in range(data.get('num_rows', 0)):
        row_cells = [cell for cell in cells
                     if cell.get('start_row_offset_idx', -1) <= row_index < cell.get('end_row_offset_idx', -1)]
        rows.append({'row_index': row_index,
                     'cells': sorted(row_cells, key=lambda cell: cell.get('start_col_offset_idx', 0))})
    return rows


def ocr_profile():
    """Prefer installed Vietnamese Tesseract; no downloads or silent fallback."""
    root = Path(__file__).resolve().parents[2]
    command = shutil.which('tesseract')
    windows = Path('C:/Program Files/Tesseract-OCR/tesseract.exe')
    if not command and windows.is_file():
        command = str(windows)
    local = root / 'data/models/tesseract'
    if command and all((local / f'{lang}.traineddata').is_file() for lang in ('vie', 'eng')):
        from hashlib import sha256
        return {'backend': 'tesseract_pdf', 'lang': ['vie', 'eng'], 'scale': 4.0,
                'tesseract_cmd': command, 'path': str(local), 'force_full_page_ocr': True,
                'orientation': 'pdf_render_orientation_no_osd_guess',
                'tsv_config_sha256': sha256((local / 'configs/tsv').read_bytes()).hexdigest() if (local / 'configs/tsv').is_file() else None,
                'model_sha256': {lang: sha256((local / f'{lang}.traineddata').read_bytes()).hexdigest() for lang in ('vie', 'eng')}}
    return {'backend': 'rapidocr', 'lang': ['vi'], 'force_full_page_ocr': True}


@contextmanager
def ocr_environment(ocr):
    """Docling's language discovery omits options.path; scope the workaround.

    Call only while holding CONVERSION_LOCK. Restore any existing user setting.
    """
    previous = os.environ.get('TESSDATA_PREFIX')
    active = ocr and ocr.get('backend') == 'tesseract_cli'
    if active:
        os.environ['TESSDATA_PREFIX'] = ocr['path']
    try:
        yield
    finally:
        if active:
            if previous is None:
                os.environ.pop('TESSDATA_PREFIX', None)
            else:
                os.environ['TESSDATA_PREFIX'] = previous


def create_converter(ocr=None):
    """Shared local Docling profile; importing this module does not load models."""
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.backend.pypdfium2_backend import PyPdfiumDocumentBackend
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, TableFormerMode
    except ImportError as exc:
        raise RuntimeError('Docling chưa sẵn sàng. Chạy pip install -r requirements.txt trong môi trường dự án.') from exc
    options = PdfPipelineOptions()
    options.do_ocr = True
    options.do_table_structure = True
    ocr = ocr or ocr_profile()
    if ocr.get('document_timeout_seconds') is not None:
        options.document_timeout = float(ocr['document_timeout_seconds'])
    if ocr['backend'] in ('tesseract_pdf', 'native_text'):
        options.do_ocr = False
    elif ocr['backend'] == 'tesseract_cli':
        from docling.datamodel.pipeline_options import TesseractCliOcrOptions, OcrMode
        options.ocr_options = TesseractCliOcrOptions(lang=ocr['lang'], scale=ocr['scale'],
            tesseract_cmd=ocr['tesseract_cmd'], path=ocr['path'], mode=OcrMode.FULL_PAGE)
    else:
        options.ocr_options = RapidOcrOptions(lang=['vi'], force_full_page_ocr=True)
    options.table_structure_options.mode = TableFormerMode.ACCURATE
    options.table_structure_options.do_cell_matching = True
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(
        pipeline_options=options, backend=PyPdfiumDocumentBackend)})


def convert_pdf(source: Path, max_pages=None, progress_callback=None, start_page=1):
    with pymupdf.open(source) as pdf:
        total = len(pdf)
    end_page = min(total, start_page + max_pages - 1) if max_pages else total
    limit = end_page - start_page + 1
    pages, native_pages, tables = [], [], []
    # The model can use substantial RAM; serialize conversions within the app.
    with CONVERSION_LOCK, ocr_environment(ocr_profile()):
        converter = create_converter({'backend': 'rapidocr'})
        for offset, page_number in enumerate(range(start_page, end_page + 1)):
            if progress_callback:
                progress_callback({'stage': 'docling', 'page': page_number, 'page_total': limit,
                                   'completed_pages': offset})
            result = converter.convert(str(source), page_range=(page_number, page_number), raises_on_error=True)
            native = result.document.export_to_dict()
            native_pages.append({'pdf_page': page_number, 'conversion_status': str(result.status), 'document': native})
            text = result.document.export_to_markdown()
            pages.append({'page_number': page_number, 'text': text, 'character_count': len(text),
                          'extraction_method': 'docling', 'extraction_status': 'available' if text else 'ocr_pending',
                          'confidence': 0.70})
            for table in native.get('tables', []):
                tables.append({'table_id': f'P{page_number:03d}-T{len(tables)+1:04d}',
                               'pdf_page': page_number, 'native_table': table, 'rows': table_rows(table),
                               'review_status': 'unreviewed'})
            if progress_callback:
                progress_callback({'stage': 'docling', 'page': page_number, 'page_total': limit,
                                   'completed_pages': offset + 1})
    full = {'engine': 'docling', 'schema_version': '1.0', 'pdf_page_count': total,
            'processed_page_count': limit, 'table_count': len(tables), 'tables': tables,
            'native_page_documents': native_pages,
            'all_fields_verified': False,
            'review_note': 'All detected tables and cells are retained. OCR and table structure require source verification. Unrecognized or missing cells are not inferred.'}
    metadata = {'pdf_page_count': total, 'processed_page_count': limit,
                'method_counts': {'docling': limit}, 'table_count': len(tables)}
    return pages, metadata, full


def all_table_claims(spec, full, boundary):
    records = []
    for table in full['tables']:
        for row in table['rows']:
            text = ' | '.join(cell.get('text', '') for cell in row['cells'])
            if not re.search(r'\d', text):
                continue
            records.append({'record_id': f'{spec.document_key}-{table["table_id"]}-R{row["row_index"]:03d}',
                            'company_id': spec.company_id, 'company_name': spec.company_name,
                            'report_year': spec.report_year, 'report_type': spec.report_type,
                            'source_file': spec.source_path.name, 'source_page': table['pdf_page'],
                            'table_id': table['table_id'], 'row_index': row['row_index'],
                            'claim_text': text, 'original_text': text, 'cells': row['cells'],
                            'dimension': 'X', 'metric_code': None, 'value': None, 'unit': None,
                            'boundary': boundary, 'extraction_method': 'docling_table',
                            'extraction_status': 'available', 'review_status': 'unreviewed',
                            'confidence': .70, 'period_mapping': None})
    return records
