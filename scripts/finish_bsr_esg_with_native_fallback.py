"""Finish supplied BSR ESG sources, preserving successful Docling captures.

New hybrid profile, new anchors; original checkpoints/JSON are not overwritten.
Every fallback page remains partial, not successful Docling extraction.
"""
from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid
import argparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extraction.source_v2 import capture_pdf, default_profile, file_hash, stable_id, atomic_json, now
from src.extraction.native_pdf_fallback import read_native_page
from src.extraction.esg_v2 import extract_esg


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_dir', type=Path)
    parser.add_argument('--years', nargs='+', type=int, choices=(2023, 2024, 2025), default=[2023, 2024, 2025])
    args = parser.parse_args()
    source_dir = args.source_dir
    job_id = uuid.uuid4().hex
    folder = ROOT / 'data/processed/extraction_jobs' / job_id
    run = ROOT / 'data/processed/uploads_v2' / job_id
    folder.mkdir(parents=True)
    run.mkdir(parents=True)
    documents = []
    print(json.dumps({'job_id': job_id}), flush=True)
    for index, year in enumerate(args.years):
        source = source_dir / f'BSR_{year}.pdf'
        digest = file_hash(source)
        report_id = 'report_' + digest
        base = ROOT / 'data/processed/capture_v2/bsr_esg_delivery' / report_id
        candidates = []
        for path in base.glob('*/canonical.json'):
            b = json.loads(path.read_text(encoding='utf-8'))
            candidates.append((b['coverage']['counts'].get('processed', 0), path.parent))
        previous = max(candidates, key=lambda x: x[0])[1] if candidates else None
        profile = default_profile()
        profile.update(capture_policy='reuse_successful_docling_then_native_pdf_fallback/2', fallback_backend='pymupdf',
                       parent_profile_id=previous.name if previous else None)
        profile_id = stable_id('profile', profile)
        work = ROOT / 'data/processed/capture_v2/bsr_esg_hybrid' / report_id / profile_id
        if previous:
            for path in (previous / 'pages').glob('*.json'):
                raw = json.loads(path.read_text(encoding='utf-8'))
                if raw.get('status') != 'processed':
                    continue
                reused = deepcopy(raw)
                reused.update(profile_id=profile_id, reused_from={'profile_id': raw['profile_id'],
                              'checkpoint_sha256': file_hash(path), 'reason': 'Unchanged native source observation, explicit new hybrid profile lineage.'})
                atomic_json(work / 'pages' / path.name, reused)
        def progress(event):
            event.update(document_index=index+1, document_total=len(args.years), filename=source.name)
            atomic_json(folder / 'status.json', {'status': 'running', 'progress': event, 'updated_at': now()})
            print(json.dumps(event), flush=True)
        work = capture_pdf(source, ROOT / 'data/processed/capture_v2/bsr_esg_hybrid', company_id='BSR',
                           report_type='ESG', report_year=year, profile=profile, page_reader=read_native_page,
                           retries=0, progress_callback=progress)
        # Vietnamese separators confirmed visually on the 2025 workforce table.
        output_path = extract_esg(work, number_format='vi' if year == 2025 else 'auto')
        output = json.loads(output_path.read_text(encoding='utf-8'))
        bundle = json.loads((work / 'canonical.json').read_text(encoding='utf-8'))
        documents.append({'document_index': index, 'filename': source.name, 'workspace': str(work),
                          'output_path': str(output_path), 'capture_status': bundle['batch']['capture_status'],
                          'coverage': bundle['coverage'], 'output': output})
    manifest = {'pipeline': 'source-typed-v2', 'created_at': now(), 'document_count': len(args.years),
                'processed_documents': len(documents), 'documents': [{k:v for k,v in d.items() if k != 'output'} for d in documents],
                'failures': [], 'graph_ready': False}
    atomic_json(run / 'run_manifest.json', manifest)
    result = {'status': 'completed', 'pipeline': 'source-typed-v2', 'manifest': manifest,
              'documents': documents, 'run_directory': str(run), 'graph_ready': False, 'semantic_status': 'partial'}
    atomic_json(folder / 'result.json', result)
    atomic_json(folder / 'status.json', {'status': 'completed', 'updated_at': now()})
    print(json.dumps({'completed_job_id': job_id}), flush=True)


if __name__ == '__main__':
    main()
