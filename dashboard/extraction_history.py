"""Discover durable local extraction results, including pre-history upload runs."""
from pathlib import Path
from functools import lru_cache
import re

from dashboard.extraction_worker import load_job, read_json
from src.extraction.source_v2 import atomic_json


@lru_cache(maxsize=128)
def _job_summary(path, modified, size):
    index = Path(path).parent / 'history_summary.json'
    cached = read_json(index, {})
    if (isinstance(cached, dict) and cached.get('result_mtime_ns') == modified
            and cached.get('result_size') == size and isinstance(cached.get('summary'), dict)):
        return cached['summary']
    result = read_json(path)
    if not isinstance(result, dict) or result.get('status') != 'completed':
        return None
    summary = {'manifest': result.get('manifest', {}), 'run_directory': result.get('run_directory'),
               'documents': [{'filename': d.get('filename', 'PDF')} for d in result.get('documents', [])]}
    try:
        atomic_json(index, {'result_mtime_ns': modified, 'result_size': size, 'summary': summary})
    except OSError:
        pass  # Read-only storage can still show history; cache is optional.
    return summary


def load_saved_result(root, saved_id):
    if not isinstance(saved_id, str):
        return None
    if not saved_id.startswith('run:'):
        return load_job(root, saved_id)
    run_id = saved_id[4:]
    if not re.fullmatch(r'[a-f0-9]{32}', run_id):
        return None
    base = Path(root).resolve()
    run = base / 'data/processed/uploads_v2' / run_id
    manifest = read_json(run / 'run_manifest.json')
    if not isinstance(manifest, dict):
        return None
    documents = []
    for doc in manifest.get('documents', []):
        path = Path(doc.get('output_path', '')).resolve()
        # Never follow a manifest outside this installation's processed storage.
        if not path.is_relative_to(base / 'data/processed'):
            return None
        output = read_json(path)
        if not isinstance(output, dict):
            return None
        documents.append({**doc, 'output': output})
    return {'status': 'completed', 'manifest': manifest, 'documents': documents,
            'pipeline': manifest.get('pipeline'), 'run_directory': str(run),
            'semantic_status': 'partial', 'graph_ready': False}


def history_options(root):
    base = Path(root).resolve() / 'data/processed'
    entries, covered_runs = [], set()
    for path in (base / 'extraction_jobs').glob('*/result.json'):
        if not re.fullmatch(r'[a-f0-9]{32}', path.parent.name):
            continue
        stat = path.stat()
        result = _job_summary(str(path), stat.st_mtime_ns, stat.st_size)
        if result is None:
            continue
        run = result.get('run_directory')
        if run:
            covered_runs.add(Path(run).resolve())
        entries.append((path.stat().st_mtime, path.parent.name, result))
    for path in (base / 'uploads_v2').glob('*/run_manifest.json'):
        if path.parent.resolve() in covered_runs:
            continue
        manifest = read_json(path)
        if not isinstance(manifest, dict) or not manifest.get('documents'):
            continue
        entries.append((path.stat().st_mtime, 'run:' + path.parent.name,
                        {'manifest': manifest, 'documents': manifest['documents']}))
    options = []
    for _, saved_id, result in sorted(entries, key=lambda item: item[0], reverse=True):
        manifest = result.get('manifest', {})
        names = [d.get('filename', 'PDF') for d in result.get('documents', [])]
        if not names:
            continue
        date = manifest.get('created_at', '')
        errors = len(manifest.get('failures', []))
        suffix = f' · {errors} file lỗi' if errors else ''
        options.append({'value': saved_id, 'label': f"{date} · {', '.join(names)}{suffix}"})
    return options
