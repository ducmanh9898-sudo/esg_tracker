"""Test-only process: simulate hard native exit without loading OCR models."""
import ctypes
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.extraction.source_v2 import atomic_json

folder = Path(sys.argv[1]).parent
request = json.loads(Path(sys.argv[1]).read_text(encoding='utf8'))
atomic_json(folder / 'status.json', {'status': 'running', 'worker_pid': os.getpid(),
    'progress': {'stage': 'source_v2', 'page': 21, 'completed_pages': 20, 'page_total': 45}})
if request['number_format'] == 'en':
    print('Simulated native worker termination', flush=True)
    if os.name == 'nt':
        ctypes.WinDLL('kernel32').ExitProcess(ctypes.c_uint(0xC0000005))
    os._exit(77)
atomic_json(folder / 'result.json', {'status': 'completed', 'documents': [],
    'manifest': {'document_count': 0, 'failures': []}, 'graph_ready': False})
