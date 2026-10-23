"""Revise a corporate delivery non-destructively; never overwrite its source."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extraction.corporate_handoff import convert_document
from src.extraction.corporate_review import enrich_records, recover_headcounts, build_review_queue, VERSION
from src.extraction.source_v2 import atomic_json, file_hash, now, stable_id


def build(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(source) or source == destination:
        raise ValueError('Destination must be a NEW directory outside the source delivery.')
    # Preflight before any copy; no source/PDF substitution.
    manifest = json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    for row in manifest['files']:
        if row['status'] == 'unavailable':
            continue
        for field, digest in (('pdf_path','pdf_sha256'), ('json_path','json_sha256')):
            p = (source / row[field]).resolve()
            if not p.is_relative_to(source) or file_hash(p) != row[digest]:
                raise ValueError('Invalid source delivery path or hash: ' + field)
    shutil.copytree(source, destination)
    # Old validation output is historical, not evidence of validation of V2.
    for name in ('report.json', 'extra_checks.json'):
        p = destination/'validation'/name
        if p.exists():
            p.rename(destination/'notes'/('parent_' + name))
    handoffs, ledger = [], []
    for row in manifest['files']:
        if row['status'] == 'unavailable':
            continue
        path = destination / row['json_path']
        h = json.loads(path.read_text(encoding='utf-8'))
        old = deepcopy(h)
        native = json.loads((destination/'notes/native'/(row['pdf_sha256']+'.json')).read_text(encoding='utf-8'))
        # Recover only bounded, source-anchored ESG economic observations omitted
        # by the earlier E/S/G classifier. Their original native IDs are retained.
        if h['document']['report_type'] == 'ESG':
            wrapper = {'output': native, 'filename': h['document']['source']['file_name'],
                       'coverage': {'pages': [{'pdf_page': n, 'status': 'processed'} for n in h['coverage']['pages_checked']] +
                                     [{'pdf_page': n, 'status': 'failed'} for n in h['coverage']['pages_unreadable']]}}
            recovered = convert_document(wrapper, {'url': h['document']['source']['url']})
            present = {r['record_id'] for r in h['records']}
            new_records = [r for r in recovered['records'] if r['record_id'] not in present]
            h['records'].extend(new_records)
            new_ids = {r['record_id'] for r in new_records}
            h['issue_log'].extend(i for i in recovered['issue_log'] if i['record_id'] in new_ids)
            ledger.extend({'document_id': row['document_id'], 'record_id': r['record_id'], 'kind': 'recovered_native_economic_measurement'} for r in new_records)
        updates = enrich_records(h, native) + recover_headcounts(h, native)
        ledger.extend(dict(x, document_id=row['document_id']) for x in updates)
        original_ids = {r['record_id']: r for r in old['records']}
        for r in h['records']:
            if r['record_id'] in original_ids:
                prior = original_ids[r['record_id']]
                assert r['statement']['original_quote'] == prior['statement']['original_quote']
                assert r['value']['original_value'] == prior['value']['original_value']
                assert r['period']['observation_year'] == prior['period']['observation_year']
                assert [e['evidence_id'] for e in r['evidence']] == [e['evidence_id'] for e in prior['evidence']]
                assert [e['element_id'] for e in r['evidence']] == [e['element_id'] for e in prior['evidence']]
            assert r['quality']['review_status'] == 'pending_human_review'
            assert not r['boundary']['verified']
        assert original_ids.keys() <= {r['record_id'] for r in h['records']}
        # Original coverage/issues retained, including unresolved OCR/parse/search.
        atomic_json(path, h)
        row['json_sha256'] = file_hash(path)
        row['status'] = 'partial'
        row['reason'] = 'Source-bound V2 enrichment; original PDF unchanged. Candidate semantic review, methods, boundary and restatement remain pending.'
        handoffs.append(h)
    manifest['batch_id'] = stable_id('batch_v2', manifest['batch_id'], [(x['document_id'],x['json_sha256']) for x in manifest['files']])
    atomic_json(destination/'manifest.json', manifest)
    atomic_json(destination/'notes/demo_review_queue.json', build_review_queue(handoffs))
    atomic_json(destination/'notes/record_enrichment.json', {'version': VERSION, 'created_at': now(), 'parent_manifest_sha256': file_hash(source/'manifest.json'),
                'original_records_preserved': True, 'original_pdf_bytes_preserved': True,
                'historical_issues': 'Parent issue_log entries are retained as extraction history; latest structured fields and new review issues describe current state.',
                'changes': ledger})
    for filename in ('audit_corporate_handoff.py', 'validate_corporate_review.py'):
        shutil.copyfile(ROOT/'scripts'/filename, destination/'validation'/filename)
    shutil.copyfile(ROOT/'docs/ESG_EXTRACT_V2.md', destination/'README_V2.md')
    print(json.dumps({'destination': str(destination), 'files': len(handoffs), 'records': sum(len(h['records']) for h in handoffs), 'changes': len(ledger)}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    args = parser.parse_args()
    build(args.source, args.destination)
