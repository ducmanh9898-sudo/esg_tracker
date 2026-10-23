"""Source-preserving note paragraphs with deterministic, review-only tags.

No financial/ESG judgment, no inferred periods or KPI entities, no OCR repair.
Paragraphs remain separate records; section context can cross processed pages.
"""
import json
import re

from src.extraction.financial_context_v2 import normalized, resolve_scope
from src.extraction.source_v2 import new_record, stable_id, sync_missing_fields

NOTE_TITLE = re.compile(r'^(?:cac )?thuyet minh (?:cho )?(?:bao cao tai chinh|bctc)\b|^notes to (?:the )?(?:separate |consolidated )?financial statements\b')
STATEMENT_TITLE = re.compile(r'^(?:bang can doi ke toan|bao cao ket qua hoat dong kinh doanh|bao cao luu chuyen tien te|balance sheet|statement of (?:cash flows|financial position|profit))\b')
TAG_RULES = {
    'accounting_policy': r'chinh sach ke toan|accounting polic(?:y|ies)|ghi nhan doanh thu|doanh thu.{0,80}ghi nhan|revenue recognition|khau hao|depreciation',
    'risk_disclosure': r'rui ro|\brisk\b|risks\b',
    'commitment': r'cam ket|commitments?\b',
    'contingency': r'no tiem tang|contingent|nghia vu tiem tang',
    'related_party': r'ben lien quan|related part(?:y|ies)',
    'estimate_judgment': r'uoc tinh|xet doan|estimat(?:e|es|ion)|judg(?:e)?ment',
    'financial_esg_context': r'moi truong|phat thai|khi nha kinh|an toan lao dong|environmental|emissions?|greenhouse|occupational safety',
}


def ordered_blocks(bundle, work):
    """Native body ordering, including nested groups; flag unreachable text blocks."""
    artifacts = {a['artifact_id']: a for a in bundle['source_artifacts']}
    by_artifact = {}
    for block in bundle['source_blocks']:
        by_artifact.setdefault(block['source']['artifact_id'], []).append(block)
    result, unreachable = [], []
    for artifact_id, blocks in sorted(by_artifact.items(), key=lambda pair: pair[1][0]['source']['pdf_page']):
        native = json.loads((work / artifacts[artifact_id]['path']).read_text(encoding='utf-8'))['document']
        lookup = {'#' + b['source']['native_json_pointer'].removeprefix('/document'): b for b in blocks}
        visited = set()
        def visit(ref):
            if ref in visited:
                return
            visited.add(ref)
            try:
                target = native
                for token in ref.removeprefix('#/').split('/'):
                    target = target[int(token)] if isinstance(target, list) else target[token]
            except (KeyError, IndexError, ValueError, TypeError):
                return
            if ref in lookup:
                result.append(lookup[ref])
            for child in target.get('children', []):
                visit(child.get('$ref', ''))
        for child in native.get('body', {}).get('children', []):
            visit(child.get('$ref', ''))
        unreachable.extend(b for ref, b in lookup.items() if ref not in visited and b['kind'] == 'texts')
    return result, unreachable


def extract_notes(bundle, work):
    report = bundle['reports'][0]
    blocks, unreachable = ordered_blocks(bundle, work)
    statuses = {p['pdf_page']: p['status'] for p in bundle['coverage']['pages']}
    notes_title = section = None
    previous_page = None
    records, issues, coverage = [], [], []
    def disposition(block, status, record_id=None):
        coverage.append({'block_id': block['block_id'], 'pdf_page': block['source']['pdf_page'],
                         'disposition': status, 'record_id': record_id})
    for block in blocks:
        page = block['source']['pdf_page']
        if previous_page is not None and page != previous_page:
            if page != previous_page + 1 or any(statuses.get(p) != 'processed' for p in (previous_page, page)):
                notes_title = section = None
        previous_page = page
        if block['kind'] != 'texts':
            continue
        raw = block['original_text']
        text = normalized(raw or '')
        if not text:
            disposition(block, 'empty_source')
            continue
        if block.get('label') in ('page_header', 'page_footer', 'caption') or re.fullmatch(r'\d+', text):
            disposition(block, 'layout_text_retained_in_source')
            continue
        if re.match(r'^(?:don vi(?: tinh)?|unit)\s*[:：]', text):
            disposition(block, 'unit_label_retained_in_source')
            continue
        # Standard statement footer is not a note or accounting policy paragraph.
        if re.match(r'^cac thuyet minh kem theo\b|^the accompanying notes\b', text):
            disposition(block, 'statement_footer_retained_in_source')
            continue
        if NOTE_TITLE.search(text):
            notes_title = section = block
            disposition(block, 'notes_heading_context')
            continue
        if STATEMENT_TITLE.search(text):
            notes_title = section = None
            disposition(block, 'statement_heading_outside_notes')
            continue
        if notes_title and (block.get('label') in ('section_header', 'title') or re.match(r'^\d+(?:\.\d+)*[.)]\s+[^\d]', text)):
            section = block
            disposition(block, 'section_heading_context')
            continue
        tag_sources = {}
        for tag, pattern in TAG_RULES.items():
            evidence = [b for b in (block, section) if b and re.search(pattern, normalized(b['original_text'] or ''))]
            if evidence:
                tag_sources[tag] = [b['source'] for b in evidence]
        tags = list(tag_sources)
        if not notes_title and not tags:
            disposition(block, 'outside_notes_or_context_unknown')
            continue
        record = new_record(report['report_version_id'], block['block_id'], 'financial_context', 'paragraph')
        scope = resolve_scope(block, bundle)
        record.update({'company_id': report['company_id'], 'domain': 'financial', 'original_text': raw,
                       'original_cells': [], 'data_status': 'available',
                       'payload': {'statement': raw, 'context_type': tags[0] if len(tags) == 1 else 'general_note',
                                   'context_type_candidates': tags, 'classifier': 'keyword_candidates/1',
                                   'notes_title_raw': notes_title['original_text'] if notes_title else None,
                                   'section_heading_raw': section['original_text'] if section else None,
                                   'statement_scope': scope['value'], 'financial_record_ids': []},
                       'field_sources': {'/payload/statement': [block['source']],
                                         '/payload/statement_scope': scope['sources'],
                                         '/payload/notes_title_raw': [notes_title['source']] if notes_title else [],
                                         '/payload/section_heading_raw': [section['source']] if section else [],
                                         '/payload/context_type_candidates': [src for sources in tag_sources.values() for src in sources]}})
        record['source_refs'] = list(dict.fromkeys([block['block_id']] + scope['anchor_ids'] +
                                    ([notes_title['block_id']] if notes_title else []) +
                                    ([section['block_id']] if section else [])))
        record['field_status']['/company_id']['status'] = 'available' if report['company_id'] else 'unknown'
        record['field_status']['/content_period'] = {'status': 'unknown', 'reason': 'Narrative time not parsed; report year is not substituted.'}
        record['field_status']['/payload/statement_scope'] = {'status': scope['status'], 'reason': 'Explicit statement label only; KPI boundary unverified.'}
        for field in ('notes_title_raw', 'section_heading_raw'):
            record['field_status']['/payload/' + field] = {'status': 'available' if record['payload'][field] else 'unknown',
                                                         'reason': 'Only headings observed in source reading order are used.'}
        if 'accounting_policy' in tags:
            record['payload']['effective_date'] = None
            record['field_status']['/payload/effective_date'] = {'status': 'unknown', 'reason': 'Not parsed from policy narrative.'}
        if 'commitment' in tags:
            for field in ('target_value', 'target_year', 'baseline_year', 'baseline_value'):
                record['payload'][field] = None
                record['field_status']['/payload/' + field] = {'status': 'unknown', 'reason': 'Financial commitment is not automatically an ESG target.'}
        record['review']['status'] = 'needs_review'
        sync_missing_fields(record)
        records.append(record)
        disposition(block, 'financial_context_candidate', record['record_id'])
        for pointer in record['missing_fields']:
            issues.append({'issue_id': stable_id('issue', record['record_id'], pointer, 'note_field'),
                           'record_id': record['record_id'], 'field': pointer, 'code': 'NOTE_FIELD_UNKNOWN',
                           'pdf_page': page, 'status': 'open',
                           'details': record['field_status'][pointer]['reason']})
        if tags:
            issues.append({'issue_id': stable_id('issue', record['record_id'], 'tags'),
                           'record_id': record['record_id'], 'field': '/payload/context_type_candidates',
                           'code': 'NOTE_CLASSIFICATION_CANDIDATE', 'pdf_page': page, 'status': 'open',
                           'details': 'Keyword-based candidates; negation, completeness and ESG relevance require review.'})
    for block in unreachable:
        disposition(block, 'reading_order_unknown')
        issues.append({'issue_id': stable_id('issue', block['block_id'], 'reading_order'),
                       'record_id': None, 'field': '/notes_coverage', 'code': 'NOTE_READING_ORDER_UNKNOWN',
                       'pdf_page': block['source']['pdf_page'], 'status': 'open',
                       'details': 'Text preserved in source but not reachable from native body; no section inferred.'})
    return records, issues, coverage
