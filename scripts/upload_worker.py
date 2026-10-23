"""Child process entry point. Native crashes cannot terminate the Dash parent."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extraction.source_v2 import atomic_json, now
from dashboard.upload_v2 import process_upload_v2


def main():
    request_path = Path(sys.argv[1]).resolve()
    folder = request_path.parent
    request = json.loads(request_path.read_text(encoding='utf-8'))

    def progress(event):
        atomic_json(folder / 'status.json', {'status': 'running', 'worker_pid': os.getpid(),
            'progress': event, 'updated_at': now()})
    progress({'stage': 'preparing'})
    try:
        result = process_upload_v2(**request, progress_callback=progress)
    except Exception as exc:
        result = {'status': 'failed', 'error': f'{type(exc).__name__}: {exc}'}
    atomic_json(folder / 'result.json', result)
    atomic_json(folder / 'status.json', {'status': result['status'], 'worker_pid': os.getpid(),
        'updated_at': now(), 'error': result.get('error')})


if __name__ == '__main__':
    main()
