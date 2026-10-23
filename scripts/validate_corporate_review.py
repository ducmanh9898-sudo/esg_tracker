"""Standalone review-pair and reference property-graph importer/validator.

Does not write to an external Graph service or produce a verification verdict.
Run the supplied validate.py first for schema/PDF/manifest integrity.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def graph_import(graph):
    """Materialize nodes/edges into a local reference graph and check all FKs."""
    nodes = {}
    for n in graph['nodes']:
        if n['id'] in nodes:
            raise ValueError('Duplicate graph node: ' + n['id'])
        nodes[n['id']] = n
    adjacency = {key: [] for key in nodes}
    for edge in graph['edges']:
        if edge['source'] not in nodes or edge['target'] not in nodes:
            raise ValueError('Dangling graph relationship')
        adjacency[edge['source']].append((edge['type'],edge['target']))
    expected = {(y,k,s) for y in (2023,2024,2025) for k,s in [('ESG',None),('Financial','Separate'),('Financial','Consolidated')]}
    actual = {(n['report_year'], n['report_type'], n['financial_scope']) for n in nodes.values() if n['type']=='Report' and n['company_id']=='BSR'}
    return {'import_target': 'local_reference_property_graph', 'external_graph_service_tested': False,
            'missing_expected_reports': len(expected-actual), 'missing_slots': sorted([str(t) for t in expected-actual]),
            'nodes_loaded': len(nodes), 'edges_loaded': sum(map(len,adjacency.values())),
            'candidate_pairs_loaded': sum(n['type']=='CandidatePair' for n in nodes.values()),
            'human_review_pending': True}


def validate(folder, *, require_complete=True, require_pairs=True):
    manifest = load(folder/'manifest.json')
    queue = load(folder/'notes/demo_review_queue.json')
    records, documents, errors, nodes, edges = {}, {}, [], [], []
    for row in manifest['files']:
        if row['status']=='unavailable':
            continue
        h = load(folder/row['json_path'])
        d = h['document']
        documents[d['document_id']] = d
        nodes.append(dict(id=d['document_id'],type='Report', **{k:d[k] for k in ('company_id','report_year','report_type','financial_scope')}))
        for r in h['records']:
            if r['record_id'] in records:
                errors.append('duplicate_record_id')
            records[r['record_id']] = (d,r)
            if r['quality']['review_status'] != 'pending_human_review' or r['boundary']['verified']:
                errors.append('automatic_review_forbidden:' + r['record_id'])
            nodes.append({'id':r['record_id'],'type':'Record','metric_id':r['metric_id'],'review_status':'pending_human_review'})
            edges.append({'source':d['document_id'],'type':'HAS_RECORD','target':r['record_id']})
            for e in r['evidence']:
                nodes.append({'id':e['evidence_id'],'type':'Evidence','source_sha256':e['source_sha256'],
                              'physical_page':e['physical_page'],'exact_quote':e['exact_quote'],'element_id':e['element_id']})
                edges.append({'source':r['record_id'],'type':'SUPPORTED_BY','target':e['evidence_id']})
    for ref in queue['priority_records'] + queue['excluded_from_headcount_pairing']:
        try:
            d,r = records[ref['record_id']]
            assert ref['document_id']==d['document_id']
            assert set(ref['evidence_ids']) <= {e['evidence_id'] for e in r['evidence']} and ref['evidence_ids']
            if 'money' in r['topic']:
                assert not any(t in ref['topics'] for t in ('workforce','workforce_headcount'))
        except (KeyError, AssertionError):
            errors.append('invalid_priority_reference:' + ref['record_id'])
    pairs_seen = set()
    for pair in queue['candidate_pairs']:
        try:
            assert pair['pair_id'] not in pairs_seen
            pairs_seen.add(pair['pair_id'])
            de,e = records[pair['esg']['record_id']]
            df,f = records[pair['financial']['record_id']]
            assert de['report_type']=='ESG' and df['report_type']=='Financial'
            assert de['company_id']==df['company_id']
            assert e['metric_id'] and e['metric_id']==f['metric_id']==pair['metric_id']
            assert e['period']['observation_year']==f['period']['observation_year']==pair['observation_year']
            assert e['value']['normalized_unit']==f['value']['normalized_unit']
            se,sf=e['boundary']['consolidation'],f['boundary']['consolidation']
            assert se not in ('Separate','Consolidated') or se==sf
            for side,r,d in [('esg',e,de),('financial',f,df)]:
                assert pair[side]['document_id']==d['document_id']
                assert pair[side]['evidence_ids'] and set(pair[side]['evidence_ids']) <= {x['evidence_id'] for x in r['evidence']}
                if 'headcount' in pair['metric_id']:
                    assert r['value']['normalized_unit']=='people' and 'money' not in r['topic']
            assert pair['status']=='NeedsReview' and pair['verdict'] is None
            assert pair['review_status']=='pending_human_review'
            assert pair['eligible_for_numeric_comparison'] is False and pair['blockers']
            assert pair['check_type']=='ESG_FINANCIAL'
            nodes.append({'id':pair['pair_id'],'type':'CandidatePair','status':'NeedsReview','verdict':None,'eligible_for_numeric_comparison':False})
            edges.extend([{'source':pair['pair_id'],'type':'ESG_SIDE','target':e['record_id']},
                          {'source':pair['pair_id'],'type':'FINANCIAL_SIDE','target':f['record_id']}])
        except (KeyError, AssertionError):
            errors.append('invalid_pair:' + pair.get('pair_id','?'))
    graph = {'schema_version':'corporate-review-property-graph/1.0','nodes':nodes,'edges':edges}
    try:
        graph_report = graph_import(graph)
        if (require_complete and graph_report['missing_expected_reports']) or (require_pairs and not graph_report['candidate_pairs_loaded']):
            errors.append('reference_graph_missing_reports_or_candidates')
    except ValueError as exc:
        graph_report = {'error':str(exc)}
        errors.append('reference_graph_integrity_failure')
    report = {'created_at':datetime.now(timezone.utc).isoformat(), 'passed':not errors,'errors':errors,
              'complete_bsr_matrix_required':require_complete,'candidate_pairs_required':require_pairs,
              'candidate_pairs':len(queue['candidate_pairs']), 'pair_status_counts':dict(Counter(p['status'] for p in queue['candidate_pairs'])),
              'financially_verified_claims':0,'graph_import':graph_report,'human_semantic_review_pending':True}
    write(folder/'notes/graph_review.json', graph)
    write(folder/'validation/graph_load_report.json', graph_report)
    write(folder/'validation/review_checks.json', report)
    return report


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('delivery',type=Path)
    args=parser.parse_args()
    report=validate(args.delivery.resolve())
    print(json.dumps(report,ensure_ascii=False,indent=2))
    raise SystemExit(0 if report['passed'] else 1)
