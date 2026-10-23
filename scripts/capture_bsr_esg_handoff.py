"""Capture three supplied BSR ESG PDFs with Docling, native text/OCR fallback.

No legacy generated ESG JSON is used as evidence. New page checkpoints and
results are durable and discoverable in extraction history.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.extraction.source_v2 import capture_pdf, default_profile, atomic_json, now
from src.extraction.esg_v2 import extract_esg
from src.extraction.isolated_page_reader import IsolatedPageReader


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pdf_directory', type=Path)
    parser.add_argument('--page-timeout', type=float, default=120, help='Docling conversion deadline per page, seconds')
    args = parser.parse_args()
    if args.page_timeout <= 0:
        parser.error('--page-timeout must be positive')
    paths = [(year, args.pdf_directory / f'BSR_{year}.pdf') for year in (2023, 2024, 2025)]
    if not all(p.is_file() for _, p in paths):
        parser.error('Supply a folder containing BSR_2023.pdf, BSR_2024.pdf and BSR_2025.pdf')
    job_id = uuid.uuid4().hex
    folder = ROOT / 'data/processed/extraction_jobs' / job_id
    folder.mkdir(parents=True)
    atomic_json(folder / 'runtime_settings.json', {'docling_page_timeout_seconds': args.page_timeout, 'retries': 0})
    run = ROOT / 'data/processed/uploads_v2' / job_id
    run.mkdir(parents=True)
    documents, failures = [], []
    profile = default_profile()
    profile['page_read_policy'] = 'native_text_ge40_characters_then_docling_without_ocr_else_configured_ocr_v1'
    print(json.dumps({'job_id': job_id}), flush=True)
    for index, (year, source) in enumerate(paths):
        def progress(event):
            event.update(document_index=index + 1, document_total=3, filename=source.name)
            atomic_json(folder / 'status.json', {'status': 'running', 'worker_pid': os.getpid(),
                                                 'progress': event, 'updated_at': now()})
            print(json.dumps(event), flush=True)
        isolated = IsolatedPageReader(folder / 'page_workers', profile['ocr'], timeout=args.page_timeout, mode='native_auto')
        try:
            work = capture_pdf(source, ROOT / 'data/processed/capture_v2/bsr_esg_delivery', company_id='BSR',
                               report_type='ESG', report_year=year, profile=profile, page_reader=isolated,
                               progress_callback=progress, retries=0)
            path = extract_esg(work)
            output = json.loads(path.read_text(encoding='utf-8'))
            bundle = json.loads((work / 'canonical.json').read_text(encoding='utf-8'))
            documents.append({'document_index': index, 'filename': source.name, 'workspace': str(work),
                              'output_path': str(path), 'capture_status': bundle['batch']['capture_status'],
                              'coverage': bundle['coverage'], 'output': output})
        except Exception as exc:
            failures.append({'document_index': index, 'filename': source.name, 'error': str(exc)})
        finally:
            isolated.close()
        manifest = {'pipeline': 'source-typed-v2', 'created_at': now(), 'document_count': 3,
                    'processed_documents': len(documents), 'documents': [{k:v for k,v in d.items() if k != 'output'} for d in documents],
                    'failures': failures, 'graph_ready': False}
        atomic_json(run / 'run_manifest.json', manifest)
    result = {'status': 'completed', 'pipeline': 'source-typed-v2', 'manifest': manifest,
              'documents': documents, 'run_directory': str(run), 'graph_ready': False, 'semantic_status': 'partial'}
    atomic_json(folder / 'result.json', result)
    atomic_json(folder / 'status.json', {'status': 'completed', 'updated_at': now()})
    print(json.dumps({'job_id': job_id, 'documents': len(documents), 'failures': failures}), flush=True)


if __name__ == '__main__':
    main()
