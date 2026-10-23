"""Test OS lock recovery after a process dies during page 2."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.extraction.source_v2 import capture_pdf


def read(path, page):
    if page == 2:
        os._exit(77)
    return {'status': 'processed', 'document': {'texts': [{'text': 'saved', 'label': 'text'}]}, 'markdown': 'saved'}


capture_pdf(sys.argv[1], sys.argv[2], page_reader=read, profile={'engine': 'test-native-crash'})
