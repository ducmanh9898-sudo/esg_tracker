"""Private persistent page reader; never writes a source capture checkpoint."""
import json
from pathlib import Path
import sys
import time
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import pymupdf
from src.extraction.source_v2 import atomic_json, _docling_page, _ocr_docling_page
from src.extraction.docling_backend import create_converter


def needs_ocr(page, text):
    if len(text.strip()) < 40 or text.count('\ufffd') > max(1, len(text) // 100):
        return True
    if len(text.strip()) >= 500:
        return False
    area = page.rect.get_area()
    if not area:
        return False
    images = [rect for image in page.get_images(full=True)
              for rect in page.get_image_rects(image[0])]
    if any(rect.get_area() / area >= .7 for rect in images):
        return True
    # Scanned BCTC pages may consist of dozens of horizontal image strips
    # behind one selectable footer stamp. Count spatial coverage, not the
    # largest single image or the sum of overlapping image areas.
    if not images:
        return False
    covered = sum(any(rect.contains(pymupdf.Point(
        page.rect.x0 + (column + .5) * page.rect.width / 16,
        page.rect.y0 + (row + .5) * page.rect.height / 16))
        for rect in images) for row in range(16) for column in range(16))
    return covered >= 180  # ~70% of the physical page


def main():
    settings_path = Path(sys.argv[1])
    folder = settings_path.parent
    settings = json.loads(settings_path.read_text(encoding='utf-8'))
    native_auto = settings.get('mode', 'native_auto') == 'native_auto'
    options = {'backend': 'native_text'} if native_auto else dict(settings['ocr'])
    options['document_timeout_seconds'] = settings['page_timeout']
    converter = create_converter(options)
    ocr_converter = None
    atomic_json(folder / 'ready.json', {'ready': True})
    seq = None
    while True:
        try:
            request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
        except (OSError, ValueError):
            time.sleep(.1)
            continue
        if request['seq'] == seq:
            time.sleep(.1)
            continue
        seq = request['seq']
        try:
            path, number = request['pdf'], request['page']
            text = ''
            scan = False
            if native_auto:
                with pymupdf.open(path) as pdf:
                    page = pdf[number - 1]
                    text = page.get_text()
                    scan = needs_ocr(page, text)
            if native_auto and not scan:
                # Process a one-page native proxy, not the whole multi-page
                # resource tree. Original PDF bytes are never modified. This
                # also avoids mixed page-size provenance clamping in Docling.
                with tempfile.TemporaryDirectory(prefix='esg_native_page_') as temporary:
                    proxy = Path(temporary) / 'page.pdf'
                    with pymupdf.open(path) as source, pymupdf.open() as single:
                        single.insert_pdf(source, from_page=number-1, to_page=number-1)
                        single.save(proxy, garbage=4, deflate=True)
                    result = _docling_page(proxy, 1, converter)
                result['read_method'] = 'isolated_docling_single_native_page'
                result['original_pdf_page'] = number
            elif settings['ocr']['backend'] == 'tesseract_pdf':
                result = _ocr_docling_page(path, number, converter, settings['ocr'])
                result['read_method'] = 'isolated_tesseract_pdf_then_docling'
            elif native_auto:
                # The page may contain a small selectable stamp over a scanned
                # financial statement. OCR that physical page with the configured
                # local engine; never treat the stamp as complete page content.
                if ocr_converter is None:
                    ocr_options = dict(settings['ocr'])
                    ocr_options['document_timeout_seconds'] = settings['page_timeout']
                    ocr_converter = create_converter(ocr_options)
                with tempfile.TemporaryDirectory(prefix='esg_scanned_page_') as temporary:
                    proxy = Path(temporary) / 'page.pdf'
                    with pymupdf.open(path) as source, pymupdf.open() as single:
                        single.insert_pdf(source, from_page=number-1, to_page=number-1)
                        single.save(proxy, garbage=4, deflate=True)
                    result = _docling_page(proxy, 1, ocr_converter)
                result['read_method'] = 'isolated_configured_ocr_single_scanned_page'
                result['original_pdf_page'] = number
            else:
                result = _docling_page(path, number, converter)
                result['read_method'] = 'isolated_configured_docling_ocr'
            atomic_json(folder / 'reply.json', {'seq': seq, 'result': result})
        except Exception as exc:
            atomic_json(folder / 'reply.json', {'seq': seq, 'error': f'{type(exc).__name__}: {exc}'})


if __name__ == '__main__':
    main()
