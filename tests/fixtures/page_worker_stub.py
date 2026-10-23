import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from src.extraction.source_v2 import atomic_json

folder = Path(sys.argv[1]).parent
settings = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
atomic_json(folder / 'ready.json', {'ready': True})
seq = None
while True:
    try:
        request = json.loads((folder / 'request.json').read_text(encoding='utf-8'))
    except (OSError, ValueError):
        time.sleep(.05)
        continue
    if request['seq'] == seq:
        time.sleep(.05)
        continue
    seq = request['seq']
    if settings['ocr'].get('backend') == 'hang_first' and request['page'] == 1:
        time.sleep(3600)
    atomic_json(folder / 'reply.json', {'seq': seq, 'result': {'status': 'processed', 'page': request['page']}})
