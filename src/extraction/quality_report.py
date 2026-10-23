"""Extraction coverage and grounding diagnostics, not factual accuracy or gold."""
from collections import Counter


def extraction_quality(handoffs, natives=()):
    native_index = {n['reports'][0]['report_version_id']: n for n in natives}
    documents = []
    for h in handoffs:
        d = h['document']
        native = native_index.get(d['document_id'], {})
        exported = {r['record_id'] for r in h['records']}
        excluded = [{'record_id': r['record_id'], 'record_type': r['record_type'],
                     'reason': 'See handoff issue_log; original retained in notes/native.'}
                    for r in native.get('records', [])
                    if r['record_type'] != 'metric' and r['record_id'] not in exported]
        rows = []
        for r in h['records']:
            quantitative = r['record_type'] in ('measurement', 'financial_measurement', 'target')
            blockers = []
            if quantitative:
                if r['value']['status'] != 'available':
                    blockers.append('numeric_value_or_unit_unresolved')
                if r['period']['observation_year'] is None or r['period']['year_basis'] == 'unknown':
                    blockers.append('observation_year_ungrounded')
                if r['period']['period_type'] == 'unknown':
                    blockers.append('observation_period_type_unknown')
                if r['metric_id'] is None:
                    blockers.append('metric_unmapped')
                if r['boundary']['consolidation'] == 'unknown':
                    blockers.append('entity_boundary_unknown')
                if r['statement']['assertion_kind'] != 'reported_result':
                    blockers.append('not_reported_actual')
            rows.append({'record_id': r['record_id'], 'quantitative': quantitative,
                         'dimension': r['dimension'], 'metric_id': r['metric_id'],
                         'blockers': blockers, 'review_status': r['quality']['review_status'],
                         'physical_pages': sorted({e['physical_page'] for e in r['evidence']}),
                         'semantic_verified': False})
        dimensions = {}
        for dimension in sorted({r['dimension'] for r in rows}):
            group = [r for r in rows if r['dimension'] == dimension]
            dimensions[dimension] = {
                'records_exported': len(group),
                'quantitative_records': sum(r['quantitative'] for r in group),
                'quantitative_without_mechanical_blockers': sum(
                    r['quantitative'] and not r['blockers'] for r in group),
                'metric_ids': sorted({r['metric_id'] for r in group if r['metric_id']}),
            }
        documents.append({
            'document_id': d['document_id'], 'source_sha256': d['source']['sha256'],
            'report_year': d['report_year'], 'source_document_type': d['source_document_type'],
            'source_page_count': d['source']['page_count'], 'coverage': h['coverage'],
            'records_exported': len(rows), 'quantitative_records': sum(r['quantitative'] for r in rows),
            'dimensions': dimensions,
            'blocking_reason_counts': dict(Counter(b for r in rows for b in r['blockers'])),
            'excluded_native_records': excluded, 'records': rows})
    return {'schema_version': 'extraction-quality/1.0', 'documents': documents,
            'evaluation_status': 'pending_adjudication', 'precision': None, 'recall': None,
            'note': 'Counts measure extraction/grounding coverage only. Dimension counts are not completeness, accuracy or semantic comparability. No disclosure absence inferred.'}
