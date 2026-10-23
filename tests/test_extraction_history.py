import json
import uuid

from dash import Dash, no_update

from dashboard import upload_analysis as ui
from dashboard.extraction_history import history_options, load_saved_result
from dashboard.upload_v2 import export_result
from src.extraction.source_v2 import atomic_json


def save_run(root):
    run_id = uuid.uuid4().hex
    work = root / 'data/processed/capture_v2' / run_id
    output = {'reports': [{'company_id': 'BSR', 'reporting_year': 2024, 'report_type': 'ESG'}],
              'records': [], 'source_artifacts': [], 'source_blocks': [], 'issues': []}
    path = work / 'esg_records.json'
    atomic_json(path, output)
    doc = {'document_index': 0, 'filename': 'BSR_2024.pdf', 'workspace': str(work),
           'output_path': str(path), 'capture_status': 'completed',
           'coverage': {'counts': {'processed': 1}, 'total_pages': 1}}
    run = root / 'data/processed/uploads_v2' / run_id
    manifest = {'created_at': '2026-10-15 12:00 UTC', 'document_count': 1,
                'documents': [doc], 'failures': [], 'pipeline': 'source-typed-v2'}
    atomic_json(run / 'run_manifest.json', manifest)
    return run_id, {'status': 'completed', 'run_directory': str(run), 'manifest': manifest,
                    'documents': [{**doc, 'output': output}]}


def test_old_runs_are_discovered_reopened_and_exported_without_ocr(tmp_path):
    run_id, original = save_run(tmp_path)
    options = history_options(tmp_path)
    assert options[0]['value'] == 'run:' + run_id
    assert 'BSR_2024.pdf' in options[0]['label']
    restored = load_saved_result(tmp_path, options[0]['value'])
    assert restored['documents'] == original['documents']
    assert export_result(restored)['documents'][0]['output'] == original['documents'][0]['output']


def test_jobs_survive_restart_and_do_not_duplicate_underlying_run(tmp_path):
    run_id, result = save_run(tmp_path)
    job_id = uuid.uuid4().hex
    folder = tmp_path / 'data/processed/extraction_jobs' / job_id
    atomic_json(folder / 'status.json', {'status': 'completed'})
    atomic_json(folder / 'result.json', result)
    assert history_options(tmp_path)[0]['value'] == job_id
    assert len(history_options(tmp_path)) == 1
    assert load_saved_result(tmp_path, job_id) == result


def test_small_history_index_survives_restart_and_invalidates_on_result_change(tmp_path, monkeypatch):
    from dashboard import extraction_history as history
    _, result = save_run(tmp_path)
    folder = tmp_path / 'data/processed/extraction_jobs' / uuid.uuid4().hex
    atomic_json(folder / 'result.json', result)
    atomic_json(folder / 'status.json', {'status': 'completed'})
    assert history.history_options(tmp_path)
    assert (folder / 'history_summary.json').is_file()
    history._job_summary.cache_clear()
    original = history.read_json
    reads = []
    def track(path, *args):
        reads.append(str(path))
        return original(path, *args)
    monkeypatch.setattr(history, 'read_json', track)
    history.history_options(tmp_path)
    assert not any(path.endswith('result.json') for path in reads)
    result['documents'][0]['filename'] = 'BSR_2024_updated.pdf'
    atomic_json(folder / 'result.json', result)
    assert 'updated' in history.history_options(tmp_path)[0]['label']
    assert any(path.endswith('result.json') for path in reads)


def test_invalid_corrupt_or_missing_history_does_not_open(tmp_path):
    assert load_saved_result(tmp_path, 'run:../../outside') is None
    assert load_saved_result(tmp_path, None) is None
    run_id, result = save_run(tmp_path)
    path = tmp_path / 'data/processed/uploads_v2' / run_id / 'run_manifest.json'
    result['manifest']['documents'][0]['output_path'] = str(tmp_path / 'outside.json')
    atomic_json(path, result['manifest'])
    assert load_saved_result(tmp_path, 'run:' + run_id) is None
    atomic_json(path, [])
    assert history_options(tmp_path) == []


def test_history_callback_restores_after_memory_loss_and_blocks_switch_while_running(tmp_path):
    run_id, result = save_run(tmp_path)
    app = Dash(__name__)
    app.layout = ui.upload_panel()
    ui.register_upload_callbacks(app, tmp_path)
    callback = next(v['callback'].__wrapped__ for k, v in app.callback_map.items()
                    if 'analysis-history-feedback.children' in k)
    saved_id = 'run:' + run_id
    job, note = callback(1, saved_id, None)
    assert job['id'] == saved_id
    assert ui.job_result(job, tmp_path)['documents'] == result['documents']
    assert 'không chạy lại OCR' in note
    running = uuid.uuid4().hex
    ui.JOBS[running] = {'status': 'running'}
    try:
        blocked, note = callback(1, saved_id, {'id': running})
        assert blocked is no_update and 'Đang trích xuất' in note
    finally:
        ui.JOBS.pop(running)
