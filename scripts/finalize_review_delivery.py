"""Re-run all mechanical gates and publish a NEW validation/report.json for V2."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.extraction.corporate_review import build_review_queue


def finalize(folder):
    def read(path):
        return json.loads(path.read_text(encoding='utf-8'))
    manifest=read(folder/'manifest.json')
    handoffs=[read(folder/row['json_path']) for row in manifest['files'] if row['status']!='unavailable']
    (folder/'notes/demo_review_queue.json').write_text(json.dumps(build_review_queue(handoffs),ensure_ascii=False,indent=2),encoding='utf-8')
    priority_doc=next(h for h in handoffs if h['document']['report_year']==2024 and h['document']['report_type']=='Financial' and h['document']['financial_scope']=='Separate')
    priority={'document_id':priority_doc['document']['document_id'],'json_path':'json/'+priority_doc['document']['source']['sha256']+'.json',
              'record_ids':[r['record_id'] for r in priority_doc['records'] if r['metric_id']],
              'review_status':'pending_human_review','note':'Start with these mapped records; other candidates are retained, not automatically confirmed.'}
    (folder/'notes/priority_bctc_separate_2024.json').write_text(json.dumps(priority,ensure_ascii=False,indent=2),encoding='utf-8')
    old_status=folder/'DELIVERY_STATUS_VI.md'
    if old_status.exists() and not (folder/'notes/parent_DELIVERY_STATUS_VI.md').exists():
        old_status.rename(folder/'notes/parent_DELIVERY_STATUS_VI.md')
    checks = []
    for script, args in [('validate.py',['--manifest',str(folder/'manifest.json'),'--pdf-dir',str(folder/'pdf')]),
                         ('audit_corporate_handoff.py',[str(folder),'--bsr-nine','--pending-only']),
                         ('validate_corporate_review.py',[str(folder)])]:
        result=subprocess.run([sys.executable,str(folder/'validation'/script),*args],capture_output=True,text=True,encoding='utf-8')
        checks.append({'script':script,'passed':result.returncode==0,'stdout':result.stdout,'stderr':result.stderr})
        print(result.stdout,flush=True)
    manifest=read(folder/'manifest.json')
    extra=read(folder/'validation/extra_checks.json')
    review=read(folder/'validation/review_checks.json')
    counts={}
    pending=0
    for row in manifest['files']:
        if row['status']=='unavailable':
            continue
        h=read(folder/row['json_path'])
        counts[row['document_id']]=len(h['records'])
        pending += sum(r['quality']['review_status']=='pending_human_review' for r in h['records'])
    report={'created_at':datetime.now(timezone.utc).isoformat(),'delivery_version':'ESG_extract_V2',
            'mechanical_valid':all(x['passed'] for x in checks),'manifest_valid':checks[0]['passed'],
            'validator_output':checks[0]['stdout'].strip(),'complete_handoff':False,
            'human_review_pending':True,'record_counts':counts,'total_records':sum(counts.values()),
            'pending_human_review_records':pending,'partial_documents':sum(x['status']=='partial' for x in manifest['files']),
            'unavailable_slots':sum(x['status']=='unavailable' for x in manifest['files']),
            'candidate_pairs':review['candidate_pairs'],'financially_verified_claims':0,
            'source_integrity':'PDF and JSON SHA-256 validated against current manifest; original PDF bytes retained.',
            'manifest_sha256':hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(),
            'source_quote_audit':{k:extra[k] for k in ('passed','normalized_values_recomputed','native_quotes_checked','native_checkpoint_hashes_checked')},
            'graph_import':review['graph_import'],
            'errors':[x['script'] for x in checks if not x['passed']], 'checks':checks}
    (folder/'validation/report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report['mechanical_valid']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('delivery',type=Path)
    args=parser.parse_args()
    raise SystemExit(0 if finalize(args.delivery.resolve()) else 1)
