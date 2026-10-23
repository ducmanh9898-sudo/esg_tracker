import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import pytest

import pymupdf
from dash import Dash

from dashboard.extraction_worker import run_isolated_upload, load_job, job_folder
from src.extraction.source_v2 import capture_pdf, file_hash, atomic_json, default_profile, workspace_lock

STUB = Path(__file__).parent / 'fixtures/isolated_worker_stub.py'


def test_worker_hard_crash_is_reported_and_parent_survives(tmp_path):
    job = uuid.uuid4().hex
    result = run_isolated_upload(tmp_path, job, ['dummy'], ['sample.pdf'],
                                 number_format='en', worker_script=STUB)
    assert result['status'] == 'failed' and result['recoverable']
    assert result['exit_code_hex'] == ('0xC0000005' if os.name == 'nt' else '0x0000004D')
    assert result['progress']['completed_pages'] == 20
    assert Path(result['log_path']).exists()
    assert load_job(tmp_path, job) == result


def test_result_survives_memory_loss_and_invalid_ids_are_rejected(tmp_path):
    job = uuid.uuid4().hex
    result = run_isolated_upload(tmp_path, job, [], [], worker_script=STUB)
    assert result['status'] == 'completed'
    assert load_job(tmp_path, job) == result
    assert load_job(tmp_path, '../outside') is None
    interrupted = uuid.uuid4().hex
    folder = job_folder(tmp_path, interrupted)
    atomic_json(folder / 'status.json', {'status': 'running', 'worker_pid': 2147483647})
    assert load_job(tmp_path, interrupted)['recoverable']


def test_os_lock_and_saved_pages_survive_hard_exit(tmp_path):
    source = tmp_path / 'scan.pdf'
    with pymupdf.open() as pdf:
        for _ in range(3):
            pdf.new_page()
        pdf.save(source)
    script = Path(__file__).parent / 'fixtures/capture_crash_worker.py'
    child = subprocess.run([sys.executable, str(script), str(source), str(tmp_path / 'capture')], timeout=30)
    assert child.returncode == 77
    checkpoint = next((tmp_path / 'capture').rglob('pages/0001.json'))
    digest = file_hash(checkpoint)
    calls = []
    def reader(path, page):
        calls.append(page)
        return {'status': 'processed', 'document': {'texts': [{'text': 'next', 'label': 'text'}]}, 'markdown': 'next'}
    work = capture_pdf(source, tmp_path / 'capture', page_reader=reader, profile={'engine': 'test-native-crash'})
    assert calls == [2, 3]
    assert file_hash(checkpoint) == digest
    assert not (work / '.writer.lock').exists()
    assert json.loads((work / 'canonical.json').read_text(encoding='utf8'))['coverage']['counts'] == {'processed': 3}


def test_ui_remains_usable_after_child_native_failure(tmp_path, monkeypatch):
    from dashboard import upload_analysis as ui
    monkeypatch.setattr(ui, 'run_isolated_upload', lambda *a, **kw: run_isolated_upload(*a, **kw, worker_script=STUB))
    app = Dash(__name__)
    app.layout = ui.upload_panel()
    ui.register_upload_callbacks(app, tmp_path)
    def callback(fragment):
        return next(v['callback'].__wrapped__ for k, v in app.callback_map.items() if fragment in k)
    job = callback('analysis-job.data')(1, ['dummy'], ['sample.pdf'], None, None, 'auto', 'en')
    try:
        deadline = time.monotonic() + 15
        while ui.job_result(job)['status'] == 'running' and time.monotonic() < deadline:
            time.sleep(.1)
        assert ui.job_result(job)['status'] == 'failed'
        assert '0x' in callback('analysis-status.children')(1, job)[0]
        with app.server.test_client() as client:
            assert client.get('/_dash-layout').status_code == 200
        ui.JOBS.pop(job['id'])
        assert ui.job_result(job, tmp_path)['recoverable']
    finally:
        ui.JOBS.pop(job['id'], None)


def test_profile_records_alternative_backend():
    profile = default_profile()
    assert profile['pdf_backend'] == 'pypdfium2'
    assert 'pypdfium2' in profile['packages']


def test_active_os_lock_cannot_be_reclaimed(tmp_path):
    with workspace_lock(tmp_path):
        with pytest.raises(RuntimeError, match='Workspace is in use'):
            with workspace_lock(tmp_path):
                raise AssertionError('Concurrent writer acquired active lock')


@pytest.mark.skipif(os.name != 'nt', reason='Windows atomic replacement retry')
def test_atomic_json_retries_transient_sharing_violation(tmp_path, monkeypatch):
    import src.extraction.source_v2 as source
    original = source.os.replace
    calls = []
    def replace(before, after):
        calls.append(after)
        if len(calls) < 3:
            error = PermissionError('File is briefly open in another process')
            error.winerror = 32
            raise error
        return original(before, after)
    monkeypatch.setattr(source.os, 'replace', replace)
    atomic_json(tmp_path / 'state.json', {'status': 'running'})
    assert len(calls) == 3
    assert json.loads((tmp_path / 'state.json').read_text())['status'] == 'running'
