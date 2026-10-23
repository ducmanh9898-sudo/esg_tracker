"""Review-only ESG text and table candidates. Separate from financial extraction.

Unparsed tables/charts retain explicit pending coverage, not silently omitted.
Keyword classifications are provisional, not factual validation or scoring.
"""
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re

import yaml

from src.extraction.financial_context_v2 import normalized
from src.extraction.financial_notes_v2 import ordered_blocks
from src.extraction.esg_tables_v2 import extract_esg_table, candidate_links
from src.extraction.source_v2 import atomic_json, file_hash, new_record, now, stable_id, sync_missing_fields, validate_source_bundle

ROOT = Path(__file__).resolve().parents[2]


def unique_year(text, pattern):
    years = {int(value) for value in re.findall(pattern, normalized(text))}
    return next(iter(years)) if len(years) == 1 else None, 'available' if len(years) == 1 else 'ambiguous' if years else 'unknown'


def explicit_fields(kind, raw):
    values, states = {}, {}
    if kind == 'target':
        values = dict.fromkeys(('target_value', 'unit', 'target_year', 'deadline', 'baseline_year', 'baseline_value'))
        values['target_year'], states['target_year'] = unique_year(raw, r'(?:den nam|vao nam|truoc nam|by(?: the year)?|before)\s+((?:19|20)\d{2})\b')
        values['baseline_year'], states['baseline_year'] = unique_year(raw, r'(?:nam co so|nam goc|baseline(?: year)?)\s*[:=]?\s*((?:19|20)\d{2})\b')
        # Only percentages immediately bound to an explicit target verb, not
        # an arbitrary actual/comparative number elsewhere in the paragraph.
        percentages = re.findall(r'(?:muc tieu|cam ket|targets?|commitments?)\s+(?:giam|tang|dat|reduce|increase|achieve)\s+(\d+(?:[.,]\d{1,2})?)\s*%', normalized(raw))
        if len(set(percentages)) == 1:
            values['target_value'] = percentages[0].replace(',', '.')
            values['unit'] = '%'
            states.update({'target_value': 'available', 'unit': 'available'})
        elif percentages:
            states['target_value'] = 'ambiguous'
    elif kind == 'policy':
        values = {'policy_text': raw, 'applicable_scope': None, 'effective_date': None}
        dates = re.findall(r'(?:có hiệu lực từ(?: ngày)?|effective (?:from|on))\s+(\d{1,2})[/.](\d{1,2})[/.]((?:19|20)\d{2})', raw, re.I)
        valid = set()
        for day, month, year in dates:
            try:
                valid.add(date(int(year), int(month), int(day)).isoformat())
            except ValueError:
                pass
        if len(valid) == 1 and len(dates) == 1:
            values['effective_date'] = next(iter(valid))
            states['effective_date'] = 'available'
        elif dates:
            states['effective_date'] = 'ambiguous'
    elif kind == 'action':
        values = {'activity': raw, 'beneficiaries': None, 'time': None, 'disclosed_results': None}
    elif kind == 'governance':
        values = dict.fromkeys(('responsible_body', 'responsible_person', 'role', 'oversight_mechanism', 'reporting_frequency'))
        bodies = list(dict.fromkeys(re.findall(r'\b(?:Hội đồng quản trị|HĐQT|Hội đồng thành viên|HĐTV|Board of Directors|Audit Committee)\b', raw, re.I)))
        values['responsible_body'] = bodies[0] if len(bodies) == 1 else None
        states['responsible_body'] = 'available' if len(bodies) == 1 else 'ambiguous' if bodies else 'unknown'
        values['responsible_body_candidates'] = bodies
        frequencies = set(re.findall(r'(?:báo cáo|reports?)\s+(?:định kỳ\s+)?(hàng quý|hàng tháng|hàng năm|quarterly|monthly|annually)\b', raw, re.I))
        if len(frequencies) == 1:
            values['reporting_frequency'] = next(iter(frequencies))
            states['reporting_frequency'] = 'available'
        elif frequencies:
            states['reporting_frequency'] = 'ambiguous'
    elif kind == 'claim':
        values = {'actor': None, 'action': None, 'object': None, 'qualifier': None}
    else:
        values = {'reason': 'No configured ESG type or topic signal; source retained for review.'}
    for field, value in values.items():
        if field not in states:
            states[field] = 'available' if value is not None else 'unknown'
    return values, states


def build_candidates(block, section, report, config):
    raw = block['original_text']
    inputs = [block] + ([section] if section else [])
    type_sources = {kind: [b for b in inputs if re.search(pattern, normalized(b['original_text'] or ''))]
                    for kind, pattern in config['types'].items()}
    kinds = [kind for kind, sources in type_sources.items() if sources]
    topics = []
    for code, rule in config['topics'].items():
        matched = [b for b in inputs if re.search(rule['pattern'], normalized(b['original_text'] or ''))]
        if matched:
            topics.append({'topic_id': code, 'pillar': rule['pillar'], 'status': 'candidate',
                           'source_refs': [b['block_id'] for b in matched]})
    if kinds or topics or re.search(config['claim_pattern'], normalized(raw)):
        kinds = ['claim'] + kinds
    else:
        kinds = ['unknown']
    pillars = {t['pillar'] for t in topics}
    records, issues = [], []
    for kind in kinds:
        record = new_record(report['report_version_id'], block['block_id'], kind, 'paragraph')
        payload, states = explicit_fields(kind, raw)
        payload.update({'statement': raw, 'section_heading_raw': section['original_text'] if section else None,
                        'classification_method': config['version'], 'assertion_status': 'unverified',
                        'negation_cue': bool(re.search(r'\b(?:khong|chua|not|no|without)\b', normalized(raw)))})
        record.update({'company_id': report['company_id'], 'record_type': kind, 'domain': 'esg',
                       'original_text': raw, 'original_cells': [], 'payload': payload,
                       'classification': {'pillar': next(iter(pillars)) if len(pillars) == 1 else 'unknown',
                                          'topic_candidates': topics, 'codebook_version': config['version'], 'status': 'candidate'},
                       'data_status': 'available' if kind != 'unknown' else 'unknown',
                       'type_candidates': [{'record_type': k, 'status': 'candidate'} for k in kinds],
                       'field_sources': {'/payload/statement': [block['source']],
                                         '/payload/section_heading_raw': [section['source']] if section else [],
                                         '/record_type': [b['source'] for b in type_sources.get(kind, [])] or [block['source']]}})
        record['source_refs'] = [block['block_id']] + ([section['block_id']] if section else [])
        record['field_status']['/company_id']['status'] = 'available' if report['company_id'] else 'unknown'
        record['field_status']['/content_period'] = {'status': 'unknown', 'reason': 'Reporting year not used as content period.'}
        record['field_status']['/payload/section_heading_raw'] = {'status': 'available' if section else 'unknown', 'reason': 'Only observed source headings may be inherited.'}
        for field, status in states.items():
            pointer = '/payload/' + field
            record['field_status'][pointer] = {'status': status, 'reason': 'Explicit source phrase only; no inferred values.'}
            if status == 'available':
                record['field_sources'][pointer] = [block['source']]
        record['review']['status'] = 'needs_review'
        sync_missing_fields(record)
        records.append(record)
        for pointer in record['missing_fields']:
            issues.append({'issue_id': stable_id('issue', record['record_id'], pointer), 'record_id': record['record_id'],
                           'field': pointer, 'source_refs': [block['block_id']], 'pdf_page': block['source']['pdf_page'],
                           'code': 'ESG_FIELD_UNRESOLVED', 'status': 'open', 'details': record['field_status'][pointer]['reason']})
        issues.append({'issue_id': stable_id('issue', record['record_id'], 'classification'), 'record_id': record['record_id'],
                       'field': '/record_type', 'source_refs': record['source_refs'], 'pdf_page': block['source']['pdf_page'],
                       'code': 'ESG_CANDIDATE_REVIEW', 'status': 'open',
                       'details': 'Keyword/context candidate. Negation, role, completeness and factual meaning require review.'})
        if payload['negation_cue']:
            issues.append({'issue_id': stable_id('issue', record['record_id'], 'negation'), 'record_id': record['record_id'],
                           'field': '/payload/negation_cue', 'source_refs': [block['block_id']], 'pdf_page': block['source']['pdf_page'],
                           'code': 'ESG_NEGATION_REVIEW', 'status': 'open',
                           'details': 'Negation word detected; candidate type is not confirmation of a positive assertion.'})
    return records, issues


def extract_esg(work, config_path=None, number_format='auto'):
    if number_format not in ('auto', 'vi', 'en'):
        raise ValueError('Unsupported number format.')
    work = Path(work).resolve()
    bundle = json.loads((work / 'canonical.json').read_text(encoding='utf-8'))
    errors = validate_source_bundle(bundle, work)
    if errors:
        raise ValueError('Invalid source capture: ' + '; '.join(errors))
    report = bundle['reports'][0]
    if report['report_type'] not in ('ESG', 'annual_report'):
        raise ValueError('ESG branch requires ESG or annual_report; financial statements use the financial branch.')
    config_path = Path(config_path or ROOT / 'config/esg_v2.yml')
    config = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    config_hash = file_hash(config_path)
    metrics_path = ROOT / 'config/metrics.yml'
    metrics = yaml.safe_load(metrics_path.read_text(encoding='utf-8'))['metrics']
    metrics_hash = file_hash(metrics_path)
    ordered, unreachable_texts = ordered_blocks(bundle, work)
    visited = set()
    section = previous_page = None
    page_status = {p['pdf_page']: p['status'] for p in bundle['coverage']['pages']}
    records, evidence, issues, coverage = [], [], [], []
    # Unreachable blocks are still retained, but cannot inherit heading context.
    missing_order = {b['block_id'] for b in unreachable_texts}
    remaining = [b for b in bundle['source_blocks'] if b['block_id'] not in {o['block_id'] for o in ordered}]
    for block in ordered + remaining:
        if block['block_id'] in visited:
            continue
        visited.add(block['block_id'])
        page = block['source']['pdf_page']
        if previous_page is not None and page != previous_page and (page != previous_page + 1 or any(page_status.get(p) != 'processed' for p in (previous_page, page))):
            section = None
        previous_page = page
        if block['block_id'] in missing_order:
            section = None
        entry = {'block_id': block['block_id'], 'pdf_page': page, 'record_ids': []}
        if block['kind'] != 'texts':
            entry['disposition'] = 'pending_table_extraction' if block['kind'] == 'tables' else 'pending_nontext_review'
            issues.append({'issue_id': stable_id('issue', block['block_id'], 'esg_pending'), 'record_id': None,
                           'field': '/coverage', 'source_refs': [block['block_id']], 'pdf_page': page,
                           'code': 'ESG_BLOCK_PENDING', 'status': 'open', 'details': 'Source retained; unparsed cells/charts and table completeness require review.'})
            if block['kind'] == 'tables':
                found, ev, flagged = extract_esg_table(block, bundle, work, config, metrics, number_format)
                records.extend(found)
                evidence.extend(ev)
                issues.extend(flagged)
                if found:
                    entry.update(disposition='table_candidates_needs_completeness_review',
                                 record_ids=[r['record_id'] for r in found])
        elif not (block['original_text'] or '').strip():
            entry['disposition'] = 'empty_source'
        elif block.get('label') in ('page_header', 'page_footer', 'caption') or re.fullmatch(r'\d+', block['original_text'].strip()):
            entry['disposition'] = 'layout_retained_in_source'
        elif block.get('label') in ('section_header', 'title') and block['block_id'] not in missing_order:
            section = block
            entry['disposition'] = 'section_heading_context'
        else:
            found, flagged = build_candidates(block, section, report, config)
            records.extend(found)
            issues.extend(flagged)
            entry.update({'disposition': 'reading_order_unknown_candidates' if block['block_id'] in missing_order else 'text_candidates',
                          'record_ids': [r['record_id'] for r in found]})
            if block['block_id'] in missing_order:
                issues.append({'issue_id': stable_id('issue', block['block_id'], 'order'), 'record_id': None,
                               'field': '/coverage', 'source_refs': [block['block_id']], 'pdf_page': page,
                               'code': 'ESG_READING_ORDER_UNKNOWN', 'status': 'open', 'details': 'No section inherited for unreachable text.'})
        coverage.append(entry)
    from src.extraction.esg_cards_v2 import extract_cards
    card_records, card_evidence, card_issues = extract_cards(bundle, config, number_format)
    records.extend(card_records)
    evidence.extend(card_evidence)
    issues.extend(card_issues)
    coverage_by_block = {row['block_id']: row for row in coverage}
    for record in card_records:
        for anchor in record['source_refs']:
            ids = coverage_by_block[anchor]['record_ids']
            if record['record_id'] not in ids:
                ids.append(record['record_id'])
    output = {'schema_version': 'esg-candidates/2.1.0', 'parser_version': 5, 'created_at': now(),
              'config': {'version': config['version'], 'sha256': config_hash, 'taxonomy_status': config['taxonomy_status']},
              'source_capture_sha256': file_hash(work / 'canonical.json'), 'reports': bundle['reports'],
              'source_artifacts': bundle['source_artifacts'], 'source_blocks': bundle['source_blocks'],
              'metrics_config_sha256': metrics_hash, 'number_format': number_format,
              'records': records, 'evidence': evidence, 'links': candidate_links(records, evidence, metrics), 'issues': bundle['issues'] + issues,
              'coverage': {'source_pages': bundle['coverage'], 'blocks': coverage},
              'counts': dict(Counter(r['record_type'] for r in records)), 'graph_ready': False, 'semantic_status': 'partial',
              'pending': ['table_completeness_review', 'cross_page_esg_tables', 'chart_extraction', 'semantic_field_interpretation', 'evidence_link_review', 'graph_adapter', 'review_ui']}
    errors = validate_esg(output, work)
    from jsonschema import Draft202012Validator
    schema = json.loads((ROOT / 'contracts/esg_v2.schema.json').read_text(encoding='utf-8'))
    errors.extend(e.message for e in Draft202012Validator(schema).iter_errors(output))
    output['validation'] = {'valid': not errors, 'errors': errors, 'scope': 'structure_and_source_not_factual_accuracy'}
    path = work / ('e5_' + stable_id('parser', 5, config_hash, metrics_hash, number_format).split('_', 1)[1][:12]) / 'r.json'
    atomic_json(path, output)
    if errors:
        raise ValueError('ESG validation failed: ' + '; '.join(errors))
    return path


def validate_esg(output, work):
    errors = []
    blocks = {b['block_id']: b for b in output['source_blocks']}
    artifacts = {a['artifact_id']: a for a in output['source_artifacts']}
    records = output['records']
    ids = {r['record_id'] for r in records}
    if len(ids) != len(records):
        errors.append('Duplicate record IDs.')
    coverage = output['coverage']['blocks']
    if len(coverage) != len(blocks) or {c['block_id'] for c in coverage} != set(blocks):
        errors.append('Block coverage mismatch.')
    if dict(Counter(r['record_type'] for r in records)) != output['counts']:
        errors.append('Record counts mismatch.')
    documents = {}
    for record in records:
        if not record['source_refs'] or not set(record['source_refs']) <= set(blocks):
            errors.append('Unresolved record source.')
        if record['review']['status'] != 'needs_review' or record['review']['verified_fields']:
            errors.append('Automatic candidates cannot be verified.')
        before = (list(record['missing_fields']), list(record['boundary']['missing_fields']))
        sync_missing_fields(record)
        if before != (record['missing_fields'], record['boundary']['missing_fields']):
            errors.append('Missing fields out of sync.')
        for field, sources in record['field_sources'].items():
            for source in sources:
                try:
                    aid = source['artifact_id']
                    if source['artifact_sha256'] != artifacts[aid]['sha256']:
                        errors.append('Field source hash mismatch.')
                    if aid not in documents:
                        documents[aid] = json.loads((work / artifacts[aid]['path']).read_text(encoding='utf-8'))
                    target = documents[aid]
                    for token in source['native_json_pointer'].lstrip('/').split('/'):
                        target = target[int(token)] if isinstance(target, list) else target[token]
                    if field == '/payload/statement' and (record['original_text'] != target.get('text') or record['payload']['statement'] != target.get('text')):
                        errors.append('Original text differs from source.')
                    if field == '/payload/section_heading_raw' and record['payload']['section_heading_raw'] != target.get('text'):
                        errors.append('Heading text differs from source.')
                    if field == '/original_text' and record['original_text'] != target.get('text'):
                        errors.append('Original cell differs from source.')
                    if source.get('raw_text') is not None and source['raw_text'] != target.get('text'):
                        errors.append('Cell source text differs from source.')
                except (KeyError, IndexError, TypeError, ValueError):
                    errors.append('Unresolved field source pointer.')
    for entry in coverage:
        if not set(entry['record_ids']) <= ids:
            errors.append('Unresolved coverage record.')
    by_id = {r['record_id']: r for r in records}
    evidence_ids = {e['evidence_id'] for e in output['evidence']}
    if len(evidence_ids) != len(output['evidence']):
        errors.append('Duplicate evidence IDs.')
    for record in records:
        if record['record_type'] == 'measurement' and by_id.get(record['payload'].get('metric_id'), {}).get('record_type') != 'metric':
            errors.append('Unresolved measurement metric.')
    for ev in output['evidence']:
        rec = by_id.get(ev['record_id'])
        if not rec or rec['record_type'] != 'measurement':
            errors.append('Unresolved evidence measurement.')
        elif ev['original_text'] != rec['original_text'] or ev['source'] != rec['field_sources']['/original_text'][0] or ev['metric_id'] != rec['payload']['metric_id']:
            errors.append('Evidence source mismatch.')
        if ev['status'] != 'candidate' or ev['boundary_verified']:
            errors.append('Automatic evidence cannot be verified.')
    if len({link['link_id'] for link in output['links']}) != len(output['links']):
        errors.append('Duplicate link IDs.')
    for link in output['links']:
        if by_id.get(link['claim_id'], {}).get('record_type') not in ('claim', 'target') or link['evidence_id'] not in evidence_ids:
            errors.append('Unresolved candidate link.')
        if link['relation'] != 'candidate_context' or link['comparability']['eligible'] or link['status'] != 'needs_review':
            errors.append('Automatic links cannot assert support or comparability.')
    return errors
