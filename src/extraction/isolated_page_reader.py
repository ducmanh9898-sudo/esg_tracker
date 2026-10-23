"""A persistent Docling subprocess with an enforceable per-page deadline.

Control/results are atomic JSON files; library stdout is only a private log.
Timeout terminates only this reader's owned process tree, never other apps.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from src.extraction.source_v2 import atomic_json

ROOT = Path(__file__).resolve().parents[2]


class IsolatedPageReader:
    def __init__(self, folder, ocr, timeout=120, *, worker_script=None, startup_timeout=180, mode='configured'):
        if timeout <= 0:
            raise ValueError('Page timeout must be positive')
        self.folder = Path(folder)
        self.ocr = ocr
        self.mode = mode
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self.script = Path(worker_script or ROOT / 'scripts/docling_page_worker.py')
        self.worker = None
        self.seq = 0
        self.log = None

    def _read(self, name):
        try:
            return json.loads((self.runtime / name).read_text(encoding='utf-8'))
        except (OSError, ValueError):
            return None

    def _start(self):
        self.runtime = self.folder / uuid.uuid4().hex
        self.runtime.mkdir(parents=True)
        atomic_json(self.runtime / 'settings.json', {'ocr': self.ocr, 'page_timeout': self.timeout, 'mode': self.mode})
        self.log = (self.runtime / 'worker.log').open('ab')
        self.worker = subprocess.Popen([sys.executable, '-u', str(self.script), str(self.runtime / 'settings.json')],
            cwd=ROOT, stdout=self.log, stderr=subprocess.STDOUT,
            env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        deadline = time.monotonic() + self.startup_timeout
        while not self._read('ready.json'):
            if self.worker.poll() is not None:
                raise RuntimeError(f'Page worker startup failed; see {self.runtime / "worker.log"}')
            if time.monotonic() > deadline:
                self.close()
                raise TimeoutError('Page worker startup deadline exceeded')
            time.sleep(.1)

    def __call__(self, path, number):
        if self.worker is None or self.worker.poll() is not None:
            self.close()
            self._start()
        self.seq += 1
        atomic_json(self.runtime / 'request.json', {'seq': self.seq, 'pdf': str(path), 'page': number})
        deadline = time.monotonic() + self.timeout
        while True:
            reply = self._read('reply.json')
            if reply and reply.get('seq') == self.seq:
                if reply.get('error'):
                    self.close()
                    raise RuntimeError(reply['error'])
                return reply['result']
            if self.worker.poll() is not None:
                code = self.worker.returncode
                self.close()
                raise RuntimeError(f'Page worker exited ({code}); page {number} not confirmed.')
            if time.monotonic() > deadline:
                self.close()
                raise TimeoutError(f'PAGE_DEADLINE_EXCEEDED: page {number}, {self.timeout}s; owned worker tree stopped, later pages may continue.')
            time.sleep(.1)

    def close(self):
        if self.worker and self.worker.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(self.worker.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            else:
                self.worker.terminate()
            try:
                self.worker.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.worker.kill()
                self.worker.wait(timeout=5)
        self.worker = None
        if self.log:
            self.log.close()
            self.log = None
