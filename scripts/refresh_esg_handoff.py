"""Reparse retained ESG checkpoints with the current parser, without OCR.

Creates a new history job. Old result.json and parser-version outputs stay intact.
"""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dashboard.extraction_history import load_saved_result
from src.extraction.esg_v2 import extract_esg
from src.extraction.source_v2 import atomic_json, now


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('saved_id')
    parser.add_argument('--vi-years', type=int, nargs='*', default=[], help='Explicitly checked Vietnamese numeric format, by report year; other years stay auto')
    args = parser.parse_args()
    result = load_saved_result(ROOT, args.saved_id)
    if not result or result.get('status') != 'completed':
        parser.error('Source job has not completed')
    result = deepcopy(result)
    for doc in result['documents']:
        report = doc['output']['reports'][0]
        if report['report_type'] not in ('ESG', 'annual_report'):
            parser.error('Only ESG/annual source jobs are accepted')
        path = extract_esg(doc['workspace'], number_format='vi' if report['reporting_year'] in args.vi_years else 'auto')
        doc.update(output_path=str(path), output=json.loads(path.read_text(encoding='utf-8')))
    job_id = uuid.uuid4().hex
    folder = ROOT / 'data/processed/extraction_jobs' / job_id
    run = ROOT / 'data/processed/uploads_v2' / job_id
    folder.mkdir(parents=True)
    run.mkdir(parents=True)
    manifest = {**result['manifest'], 'created_at': now(),
                'documents': [{k:v for k,v in d.items() if k != 'output'} for d in result['documents']]}
    result.update(manifest=manifest, run_directory=str(run))
    atomic_json(run / 'run_manifest.json', manifest)
    atomic_json(folder / 'result.json', result)
    atomic_json(folder / 'status.json', {'status': 'completed', 'updated_at': now()})
    print(json.dumps({'job_id': job_id, 'documents': len(result['documents'])}))


if __name__ == '__main__':
    main()
