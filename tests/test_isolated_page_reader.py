from pathlib import Path
import time

import pytest

from src.extraction.isolated_page_reader import IsolatedPageReader

STUB = Path(__file__).parent / 'fixtures/page_worker_stub.py'


def test_persistent_worker_reuses_process_for_multiple_pages(tmp_path):
    reader = IsolatedPageReader(tmp_path, {'backend': 'stub'}, timeout=2, worker_script=STUB)
    try:
        assert reader('not-read-by-stub.pdf', 1)['page'] == 1
        pid = reader.worker.pid
        assert reader('not-read-by-stub.pdf', 2)['page'] == 2
        assert reader.worker.pid == pid
    finally:
        reader.close()
    assert reader.worker is None


def test_hard_deadline_stops_owned_worker_and_later_page_can_continue(tmp_path):
    reader = IsolatedPageReader(tmp_path, {'backend': 'hang_first'}, timeout=.5, worker_script=STUB)
    try:
        start = time.monotonic()
        with pytest.raises(TimeoutError, match='PAGE_DEADLINE_EXCEEDED'):
            reader('not-read-by-stub.pdf', 1)
        assert time.monotonic() - start < 12
        assert reader.worker is None
        assert reader('not-read-by-stub.pdf', 2)['status'] == 'processed'
    finally:
        reader.close()
