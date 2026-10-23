import json

import pymupdf
import pytest

from scripts.export_financial_handoff import export
from src.extraction.source_v2 import capture_pdf, file_hash
from src.extraction.financial_v2 import validate_financial
from tests.test_financial_v2 import fixture


def test_portable_package_has_resolvable_sources_and_refuses_overwrite(tmp_path):
    source = tmp_path / 'BCTC_example.pdf'
    with pymupdf.open() as pdf:
        pdf.new_page()
        pdf.save(source)
    b, _, _ = fixture()
    native = {'texts': [{'text': 'Đơn vị: VND', 'label': 'text'}],
              'tables': [{'data': {'table_cells': b['original_cells']}, 'label': 'table'}],
              'body': {'children': [{'$ref': '#/texts/0'}, {'$ref': '#/tables/0'}]}}
    work = capture_pdf(source, tmp_path / 'capture', report_type='financial_statements',
        page_reader=lambda *a: {'status': 'processed', 'document': native, 'markdown': 'table'}, profile={'engine': 'test'})
    package = export([work], tmp_path / 'delivery')
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf8'))
    doc = manifest['documents'][0]
    path = package / doc['json_path']
    output = json.loads(path.read_text(encoding='utf8'))
    assert file_hash(path) == doc['json_sha256']
    assert file_hash(package / doc['source_pdf_path']) == file_hash(source)
    assert validate_financial(output, path.parent) == []
    assert output['semantic_status'] == 'partial'
    with pytest.raises(FileExistsError):
        export([work], package)
    output['metadata']['company_name'].update(value='Not supported', sources=[])
    assert any('Metadata value has no source' in e for e in validate_financial(output, path.parent))
