import base64
import copy
from pathlib import Path

import pymupdf
import pytest

from dashboard import upload_v2 as upload
from src.extraction.source_v2 import capture_pdf

ROOT = Path(__file__).resolve().parents[1]


def test_download_filename_uses_pdf_metadata_and_scope_not_source_filename():
    output = {'reports': [{'company_id': 'INPUT', 'reporting_year': 2025, 'report_type': 'financial_statements'}],
              'metadata': {'ticker_from_pdf': {'status': 'available', 'value': 'BSR'},
                           'reporting_year': {'status': 'available', 'value': 2024},
                           'statement_scope': {'status': 'available', 'value': 'consolidated'}}}
    result = {'documents': [{'filename': 'rieng.pdf', 'output': output}], 'manifest': {'document_count': 1}}
    name = upload.download_filename(result, timestamp='20261010_101530', token='abc12345')
    assert name == 'BSR_BCTC_2024_HOPNHAT_extract_v2_20261010_101530_ABC12345.json'
    output['metadata']['statement_scope']['status'] = 'ambiguous'
    assert '_PHAMVI_UNKNOWN_' in upload.download_filename(result)


def test_download_filename_handles_batch_partial_and_unsafe_components():
    def doc(company, kind, year):
        return {'output': {'reports': [{'company_id': company, 'report_type': kind, 'reporting_year': year}]}}
    result = {'documents': [doc('BSR', 'financial_statements', 2024), doc('PLX', 'ESG', 2025)],
              'manifest': {'document_count': 2}}
    assert upload.download_filename(result).startswith('MULTI_MIXED_MULTI_BATCH02_extract_v2_')
    result['documents'] = [doc('../../C:\\Bình Sơn?:*', 'annual_report', None)]
    name = upload.download_filename(result, timestamp='20261010_101530', token='abc')
    assert name.startswith('C_BINH_SON_BCTN_UNKNOWN_BATCH02_')
    assert all(c not in name for c in '<>:"/\\|?*')
    assert len(name) < 255


def test_download_filename_does_not_invent_missing_company_or_year():
    result = {'documents': [{'output': {'reports': [{'report_type': 'ESG'}]}}]}
    assert upload.download_filename(result).startswith('UNKNOWN_ESG_UNKNOWN_extract_v2_')
    assert upload.download_filename(result) != upload.download_filename(result)


def pdf_upload():
    with pymupdf.open() as pdf:
        pdf.new_page()
        raw = pdf.tobytes()
    return 'data:application/pdf;base64,' + base64.b64encode(raw).decode()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / 'repo'
    # Read-only config lookup in production root, isolate generated files.
    original_load = upload.load_yaml
    monkeypatch.setattr(upload, 'load_yaml', lambda path: original_load(ROOT / 'config' / path.name))
    def capture(source, output_root, **kwargs):
        cells = []
        for row, items in enumerate([['Chỉ tiêu', '2025'], ['Phát thải trực tiếp', '25']]):
            for col, raw in enumerate(items):
                cells.append({'text': raw, 'column_header': row == 0,
                              'start_row_offset_idx': row, 'end_row_offset_idx': row + 1,
                              'start_col_offset_idx': col, 'end_col_offset_idx': col + 1})
        def reader(path, number):
            return {'status': 'processed', 'document': {'texts': [{'text': 'Chính sách giảm phát thải trực tiếp.', 'label': 'text'}],
                    'tables': [{'data': {'table_cells': cells}}],
                    'body': {'children': [{'$ref': '#/texts/0'}, {'$ref': '#/tables/0'}]}}, 'markdown': 'source'}
        return capture_pdf(source, output_root, **kwargs, page_reader=reader, profile={'engine': 'test-upload'})
    monkeypatch.setattr(upload, 'capture_pdf', capture)
    return root


def test_upload_v2_routes_mixed_batch_and_exports_portable_sources(workspace):
    events = []
    result = upload.process_upload_v2(workspace, [pdf_upload(), pdf_upload()],
              ['BSR_2025.pdf', '20260326 - BSR - BCTC rieng 2025.pdf'], progress_callback=events.append)
    assert result['pipeline'] == 'source-typed-v2'
    assert len(result['documents']) == 2 and not result['manifest']['failures']
    assert result['documents'][0]['output']['schema_version'] == 'esg-candidates/2.1.0'
    assert result['documents'][1]['output']['schema_version'] == 'esg-financial-candidates/2.3.0'
    assert any(e.get('completed_pages') == 1 and e['stage'] == 'source_v2' for e in events)
    assert events[-1]['stage'] == 'export'
    exported = upload.export_result(result)
    assert len(exported['documents'][0]['native_artifacts']) == 1
    assert 'workspace' not in str(exported.keys())
    rows = upload.record_rows(result)
    measurement = next(row for row in rows if row['type'] == 'measurement')
    assert measurement['value'] == '25' and measurement['indicator'] == 'Phát thải trực tiếp'
    selected = upload.selected_source(result, measurement['id'])
    assert selected['record']['original_text'] == '25' and selected['source_blocks']
    assert upload.selected_source(result, 'invalid') is None


@pytest.mark.parametrize('contents,names', [([], []), (['bad'], ['x.pdf']),
    (['data:application/pdf;base64,AAAA'], ['x.pdf']), ([pdf_upload()], ['x.txt']),
    ([pdf_upload()], ['a.pdf', 'b.pdf'])])
def test_invalid_batch_has_no_writes(workspace, contents, names):
    with pytest.raises(ValueError):
        upload.process_upload_v2(workspace, contents, names)
    assert not (workspace / 'data').exists()


def test_partial_batch_keeps_success_and_explicit_failure(workspace, monkeypatch):
    original = upload.capture_pdf
    def sometimes(source, output_root, **kwargs):
        if source.name.startswith('PLX'):
            raise RuntimeError('conversion failed')
        return original(source, output_root, **kwargs)
    monkeypatch.setattr(upload, 'capture_pdf', sometimes)
    result = upload.process_upload_v2(workspace, [pdf_upload(), pdf_upload()], ['BSR_2025.pdf', 'PLX_2025.pdf'])
    assert len(result['documents']) == 1
    assert result['manifest']['document_count'] == 2
    assert result['manifest']['failures'][0]['filename'] == 'PLX_2025.pdf'


def test_export_rejects_tampered_artifact_and_unsafe_path(workspace):
    result = upload.process_upload_v2(workspace, [pdf_upload()], ['BSR_2025.pdf'])
    changed = copy.deepcopy(result)
    changed['documents'][0]['output']['source_artifacts'][0]['path'] = '../../outside.pdf'
    with pytest.raises(ValueError, match='an toàn'):
        upload.export_result(changed)
    doc = result['documents'][0]
    artifact = next(a for a in doc['output']['source_artifacts'] if a['kind'] == 'page_checkpoint')
    (Path(doc['workspace']) / artifact['path']).write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='thay đổi'):
        upload.export_result(result)


def test_same_company_year_type_isolated_and_path_sanitized(workspace):
    result = upload.process_upload_v2(workspace, [pdf_upload(), pdf_upload()],
                                     ['../../BSR_2025.pdf', 'BSR_2025.pdf'])
    assert len(result['documents']) == 2
    assert result['documents'][0]['workspace'] != result['documents'][1]['workspace']
    assert result['documents'][0]['filename'] == 'BSR_2025.pdf'
    assert len({r['id'] for r in upload.record_rows(result)}) == len(upload.record_rows(result))


def make_ui():
    from dash import Dash
    from dashboard import upload_analysis as ui
    app = Dash(__name__)
    app.layout = ui.upload_panel()
    ui.register_upload_callbacks(app, ROOT)
    return app, ui


def callback(app, fragment):
    return next(value['callback'].__wrapped__ for key, value in app.callback_map.items() if fragment in key)


def test_ui_callbacks_progress_source_and_json_download(workspace):
    app, ui = make_ui()
    result = upload.process_upload_v2(workspace, [pdf_upload()], ['BSR_2025.pdf'])
    key = 'test-ui-v2'
    ui.JOBS[key] = result
    job = {'id': key}
    try:
        poll = callback(app, 'analysis-status.children')
        response = poll(1, job)
        assert response[2] and response[4] is False and response[5] is False and response[6] is True
        row_id = response[2][0]['id']
        detail, index = callback(app, 'analysis-source-detail.children')([row_id], job)
        assert detail and index == 0
        href, hidden, disabled = callback(app, 'analysis-source-link.href')(0, job, [row_id])
        assert href == '/extract-source/test-ui-v2/0#page=1' and not hidden and not disabled
        data, message = callback(app, 'analysis-download.data')(1, job)
        assert data['filename'].startswith('BSR_ESG_2025_extract_v2_')
        assert data['filename'].endswith('.json')
        assert 'native_artifacts' in data['content'] and message
        ui.JOBS[key] = {'status': 'running', 'progress': {'stage': 'source_v2', 'page_total': 5, 'completed_pages': 2}}
        response = poll(2, job)
        assert response[4] is True and response[5] is True and response[6] is False
        ui.JOBS[key] = {'status': 'failed', 'error': 'test failure'}
        response = poll(3, job)
        assert response[0] == 'test failure' and response[5] is False
    finally:
        ui.JOBS.pop(key, None)


def test_pdf_route_has_no_filesystem_input_and_checks_hash(workspace):
    app, ui = make_ui()
    result = upload.process_upload_v2(workspace, [pdf_upload()], ['BSR_2025.pdf'])
    key = 'test-route-v2'
    ui.JOBS[key] = result
    try:
        with app.server.test_client() as client:
            assert client.get('/_dash-layout').status_code == 200
            assert client.get('/extract-source/missing/0').status_code == 404
            assert client.get(f'/extract-source/{key}/99').status_code == 404
            response = client.get(f'/extract-source/{key}/0')
            assert response.status_code == 200 and response.data.startswith(b'%PDF-')
            assert response.headers['Cache-Control'] == 'no-store'
            doc = result['documents'][0]
            (Path(doc['workspace']) / 'source.pdf').write_bytes(b'changed')
            assert client.get(f'/extract-source/{key}/0').status_code == 409
    finally:
        ui.JOBS.pop(key, None)


def test_upload_exposes_partial_page_capture(workspace, monkeypatch):
    def partial(source, output_root, **kwargs):
        return capture_pdf(source, output_root, **kwargs,
            page_reader=lambda p, n: {'status': 'partial', 'document': {'texts': [{'text': 'Chính sách ESG', 'label': 'text'}]}, 'markdown': ''},
            profile={'engine': 'partial'})
    monkeypatch.setattr(upload, 'capture_pdf', partial)
    result = upload.process_upload_v2(workspace, [pdf_upload()], ['BSR_2025.pdf'])
    assert result['documents'][0]['capture_status'] == 'partial'
    assert result['documents'][0]['coverage']['counts'] == {'partial': 1}
    assert result['documents'][0]['output']['validation']['valid']


def test_annual_report_with_date_prefix_uses_annual_metadata(workspace):
    result = upload.process_upload_v2(workspace, [pdf_upload()], ['20260326 - BSR - BCTN 2025.pdf'])
    assert result['documents'][0]['output']['reports'][0]['report_type'] == 'annual_report'


def test_reupload_same_pdf_reuses_checkpoint_across_jobs(workspace):
    contents = pdf_upload()
    first = upload.process_upload_v2(workspace, [contents], ['BSR_2025.pdf'])
    from src.extraction.source_v2 import file_hash
    before = first['documents'][0]
    checkpoint = Path(before['workspace']) / 'pages/0001.json'
    digest = file_hash(checkpoint)
    second = upload.process_upload_v2(workspace, [contents], ['BSR_2025.pdf'])
    after = second['documents'][0]
    assert first['run_directory'] != second['run_directory']
    assert before['workspace'] == after['workspace']
    assert file_hash(checkpoint) == digest
    assert [r['record_id'] for r in before['output']['records']] == [r['record_id'] for r in after['output']['records']]
