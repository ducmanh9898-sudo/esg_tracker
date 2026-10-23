"""Isolated OCR worker supervision, durable status, and crash diagnostics.

Only the child imports/runs conversion. The Dash process keeps serving if a
native PDF/OCR library terminates the child. Worker stdout is a private log,
never a JSON protocol (third-party libraries may print arbitrary messages).
"""
import ctypes
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

from src.extraction.source_v2 import atomic_json, now

WORKER_SLOT = threading.Semaphore(1)
CODE_ROOT = Path(__file__).resolve().parents[1]


def job_folder(root, job_id):
    if not isinstance(job_id, str) or not re.fullmatch(r'[a-f0-9]{32}', job_id):
        raise ValueError('Invalid extraction job ID')
    return Path(root).resolve() / 'data/processed/extraction_jobs' / job_id


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default


def pid_alive(pid):
    if not isinstance(pid, int) or pid <= 0:
        return False
    if os.name == 'nt':
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        kernel.OpenProcess.restype = ctypes.c_void_p
        kernel.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def load_job(root, job_id):
    try:
        folder = job_folder(root, job_id)
    except ValueError:
        return None
    state = read_json(folder / 'status.json')
    if not state:
        return None
    result = read_json(folder / 'result.json')
    if result and result.get('status') in ('completed', 'failed'):
        return result
    if state['status'] == 'running':
        owner = state.get('worker_pid') or state.get('supervisor_pid')
        if owner and not pid_alive(owner):
            return {'status': 'failed', 'recoverable': True, 'progress': state.get('progress', {}),
                'error': 'Worker đã dừng bất thường. Trang đã lưu vẫn còn. Tải lại cùng PDF và giữ metadata để tiếp tục checkpoint cùng profile.',
                'log_path': str(folder / 'worker.log')}
    return state


def run_isolated_upload(root, job_id, contents, filenames, company=None, year=None,
                        report_type=None, progress_callback=None, number_format='auto', *, worker_script=None):
    folder = job_folder(root, job_id)
    folder.mkdir(parents=True, exist_ok=False)
    request = {'root': str(Path(root).resolve()), 'contents': contents, 'filenames': filenames,
               'company': company, 'year': year, 'report_type': report_type, 'number_format': number_format}
    atomic_json(folder / 'request.json', request)
    atomic_json(folder / 'status.json', {'status': 'running', 'supervisor_pid': os.getpid(),
        'progress': {'stage': 'queued'}, 'updated_at': now()})
    if progress_callback:
        progress_callback({'stage': 'queued'})
    with WORKER_SLOT:
        script = Path(worker_script or CODE_ROOT / 'scripts/upload_worker.py').resolve()
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8'}
        try:
            with (folder / 'worker.log').open('ab') as log:
                worker = subprocess.Popen([sys.executable, '-u', str(script), str(folder / 'request.json')],
                    cwd=CODE_ROOT, stdout=log, stderr=subprocess.STDOUT, env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                previous = None
                while worker.poll() is None:
                    state = read_json(folder / 'status.json', {})
                    progress = state.get('progress')
                    if progress and progress != previous:
                        previous = progress
                        if progress_callback:
                            progress_callback(progress)
                    time.sleep(.3)
            result = read_json(folder / 'result.json')
            if worker.returncode == 0 and result and result.get('status') in ('completed', 'failed'):
                return result
            code = worker.returncode & 0xFFFFFFFF
            state = read_json(folder / 'status.json', {})
            result = {'status': 'failed', 'recoverable': True, 'exit_code': worker.returncode,
                'exit_code_hex': f'0x{code:08X}', 'progress': state.get('progress', {}),
                'log_path': str(folder / 'worker.log'),
                'error': f'Worker trích xuất bị dừng (0x{code:08X}). Giao diện vẫn hoạt động. Trang đã lưu được giữ; tải lại cùng PDF để tiếp tục checkpoint cùng profile.'}
        except OSError as exc:
            result = {'status': 'failed', 'recoverable': True, 'error': f'Không khởi động được worker: {exc}'}
        atomic_json(folder / 'result.json', result)
        atomic_json(folder / 'status.json', {**result, 'updated_at': now()})
        return result
