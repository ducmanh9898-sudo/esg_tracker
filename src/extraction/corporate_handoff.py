"""Conservative, source-bound corporate-extract-1.0 delivery adapter.

This is an export boundary, not another OCR engine or a verification engine.
Unknown fields stay unknown. Native records/checkpoints remain separate review
artifacts; no candidate alias becomes a cross-report metric identity.
"""
from decimal import Decimal, InvalidOperation, localcontext
import importlib.util
import json
from pathlib import Path
import re
import shutil
import zipfile
from urllib.parse import urlparse

from jsonschema import Draft202012Validator

from src.extraction.financial_context_v2 import normalized, resolve_scope
from src.extraction.financial_v2 import parse_number
from src.extraction.source_v2 import atomic_json, file_hash, now, stable_id
from src.extraction.corporate_review import identify, enrich_records, recover_headcounts, build_review_queue

CONTRACT = Path(__file__).resolve().parents[2] / 'contracts/corporate_extract_v1'
SCOPES = {'separate': 'Separate', 'consolidated': 'Consolidated',
          'Separate': 'Separate', 'Consolidated': 'Consolidated'}
TYPES = {'claim': 'claim', 'measurement': 'measurement', 'target': 'target',
         'policy': 'policy', 'governance': 'governance_evidence', 'action': 'claim'}
TOPICS = ('emissions', 'workforce', 'board', 'financial_esg_notes')
TOPIC_PATTERNS = {
    'emissions': r'phat thai|khi nha kinh|\bscope\s*[12]\b|greenhouse|emissions?',
    'workforce': r'lao dong|nhan vien|nhan su|employees?|workforce|headcount',
    'board': r'hoi dong quan tri|\bhdqt\b|board of directors',
    'financial_esg_notes': r'chi phi.{0,50}moi truong|du phong.{0,50}moi truong|environmental (?:cost|provision|liabilit)',
}


def validator_module():
    spec = importlib.util.spec_from_file_location('corporate_contract_validator', CONTRACT / 'validate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _meta(output, name):
    field = output.get('metadata', {}).get(name, {})
    return field.get('value') if field.get('status') == 'available' else None


def _source_bytes_checked(info, digest):
    verification = info.get('verification') or {}
    if verification.get('method') != 'windows_https_download_and_sha256_match':
        return False
    publisher_hosts = info.get('official_domains') or ('bsr.com.vn', 'www.bsr.com.vn')
    parsed = urlparse(info.get('url') or '')
    if (not isinstance(publisher_hosts, (list, tuple, set)) or
            parsed.scheme != 'https' or parsed.hostname not in publisher_hosts):
        return False
    path = Path(verification.get('downloaded_pdf') or '')
    if not path.is_absolute():
        path = CONTRACT.parents[1] / path
    return path.is_file() and file_hash(path) == digest


def _bbox(value):
    if isinstance(value, dict) and all(k in value for k in ('l', 't', 'r', 'b')):
        value = [value[k] for k in ('l', 't', 'r', 'b')]
    if not isinstance(value, list) or len(value) != 4:
        return None
    if not all(isinstance(n, (int, float)) for n in value) or value[0] == value[2] or value[1] == value[3]:
        return None
    return value


def _number(value):
    """Do not silently round exact decimals through an IEEE float."""
    number = Decimal(str(value))
    if not number.is_finite():
        raise ValueError('Non-finite decimal')
    if number == number.to_integral_value():
        return int(number)
    floating = float(number)
    if Decimal(str(floating)) != number:
        raise ValueError('Decimal cannot round-trip through JSON number')
    return floating


def _sources(record):
    return [ref for refs in record.get('field_sources', {}).values() for ref in refs]


def _unit(raw, observed):
    """Return literal unit + base unit/factor only for supported, observed units."""
    if not raw:
        return None, None, None, None
    if raw not in observed:
        return None, None, None, None
    key = normalized(raw).replace('³', '3')
    currency = re.search(r'\b(vnd|dong|usd|eur)\b', key)
    if currency:
        scales = [('ty', 10**9), ('trieu', 10**6), ('nghin', 1000), ('ngan', 1000),
                  ('billion', 10**9), ('million', 10**6), ('thousand', 1000)]
        scale = next(((word, factor) for word, factor in scales if re.search(r'\b' + word + r'\b', key)), None)
        literal = re.sub(r'^\s*(?:đơn vị(?: tính)?|unit)\s*[:：]\s*', '', raw, flags=re.I).strip()
        raw_scale = re.search(r'triệu|tỷ|nghìn|ngàn|million|billion|thousand', raw, re.I)
        return literal, {'dong': 'VND'}.get(currency[1], currency[1].upper()), Decimal(scale[1] if scale else 1), raw_scale[0] if raw_scale else None
    known = {'%': ('%', '1'), 'tco2e': ('tCO2e', '1'), 'kgco2e': ('tCO2e', '.001'),
             'gj': ('GJ', '1'), 'mwh': ('GJ', '3.6'), 'kwh': ('GJ', '.0036'),
             'm3': ('m3', '1'), 'tan': ('t', '1'), 'ton': ('t', '1'), 'tons': ('t', '1'),
             'kg': ('t', '.001'), 'nguoi': ('people', '1'), 'people': ('people', '1'),
             'gio': ('hours', '1'), 'hours': ('hours', '1'), 'lan': ('count', '1'),
             'shares': ('shares', '1'), 'co phieu': ('shares', '1')}
    if key not in known:
        # Intensity, ratios and compound units must not be simplified blindly.
        return raw, None, None, None
    base, factor = known[key]
    return raw, base, Decimal(factor), None


def _value(record, context, uncertainties, number_format='auto'):
    p = record.get('payload', {})
    raw = p.get('raw_value', p.get('value_raw'))
    parsed = p.get('parsed_value', p.get('value'))
    if record['record_type'] == 'target':
        parsed = p.get('target_value')
        raw = str(parsed) if parsed is not None and str(parsed) in context else None
    raw_unit = p.get('unit')
    # Prefer an observed scale-bearing label to a normalized currency token.
    labels = p.get('unit_source_labels_raw', [])
    scale_labels = [s for s in labels if s in context and re.search(r'\b(?:trieu|ty|nghin|ngan|million|billion|thousand)\b', normalized(s))]
    scale_conflict = len({(_unit(label, context)[1], _unit(label, context)[2]) for label in scale_labels}) > 1
    if scale_labels:
        raw_unit = scale_labels[0]
    original_unit, unit, factor, scale = _unit(raw_unit, context)
    if scale_conflict:
        unit = factor = scale = None
        uncertainties.append('conflicting_observed_scale_labels')
    if factor is not None and p.get('scale') and record.get('domain') == 'financial':
        if Decimal(str(p['scale'])) != factor:
            factor = None  # No observed scale label: don't invent a literal unit.
            uncertainties.append('scale_source_label_missing_or_conflicting')
    quantitative = record['record_type'] in ('measurement', 'target')
    status = 'not_applicable' if not quantitative else 'unknown'
    normalized_value = None
    source_status = record.get('data_status', 'unknown')
    if quantitative and raw is not None and parsed is not None:
        reparsed, read_status = parse_number(raw, p.get('number_format') or number_format)
        if read_status != 'available' or reparsed is None or Decimal(reparsed) != Decimal(str(parsed)):
            parsed = None
            source_status = 'ambiguous'
            uncertainties.append('native_parsed_value_does_not_match_unambiguous_source_amount')
    if quantitative and raw is not None and parsed is not None and raw in context:
        if source_status in ('ambiguous', 'missing'):
            status = source_status
        elif unit is not None and factor is not None:
            try:
                with localcontext() as ctx:
                    ctx.prec = max(64, len(str(parsed)) + len(str(factor)) + 8)
                    normalized_value = _number(Decimal(str(parsed)) * factor)
                status = 'available'
            except (InvalidOperation, ValueError, OverflowError):
                status = 'ambiguous'
                uncertainties.append('normalization_or_numeric_precision_unresolved')
        else:
            uncertainties.append('normalization_unit_or_factor_unknown')
    elif quantitative:
        status = source_status if source_status in ('missing', 'ambiguous') else 'unknown'
        uncertainties.append('numeric_value_not_resolved_from_source')
    return {'status': status, 'original_value': raw, 'original_unit': original_unit,
            'original_scale': scale, 'normalized_value': normalized_value,
            'normalized_unit': unit, 'normalization_factor': _number(factor) if factor is not None else None,
            'normalization_note': 'Base value = parsed source amount × normalization_factor, exactly once.'
            if status == 'available' else 'No normalized amount asserted; see uncertainty and native record.' if quantitative else None}


def _period(record, headers, quote, uncertainties, column, source_page=None):
    native = record.get('content_period') or {}
    year = native.get('year')
    basis = 'unknown'
    if year is not None:
        if (isinstance(column, int) and not isinstance(column, bool)
                and any(h['role'] == 'year' and h['column'] == column
                        and set(re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', h['text'])) == {str(year)}
                        for h in headers)):
            basis = 'table_header'
        elif (record['record_type'] == 'measurement' and
              native.get('mapping_basis') == 'column_label_plus_pdf_reporting_period' and
              record.get('payload', {}).get('period_role') == 'current_flow' and
              native.get('end_date') == f'{year}-12-31' and
              isinstance(column, int) and not isinstance(column, bool) and
              isinstance(source_page, int) and not isinstance(source_page, bool)):
            same_column_current = any(
                h['role'] == 'year' and h.get('physical_page') == source_page and
                h['column'] == column and normalized(h['text']) == 'nam nay'
                for h in headers)
            title_years = set()
            for header in headers:
                if header.get('physical_page') != source_page or header['role'] == 'year':
                    continue
                title = re.search(r'\bcho nam tai chinh.{0,60}\b31 thang 12 nam ((?:19|20)\d{2})\b',
                                  normalized(header['text']))
                if title:
                    title_years.add(int(title.group(1)))
            if same_column_current and title_years == {year}:
                basis = 'same_page_title_and_column'
                uncertainties.append('ocr_title_and_current_column_year_needs_human_review')
        elif record['record_type'] != 'measurement' and str(year) in quote:
            basis = 'explicit_quote'
        if basis == 'unknown':
            uncertainties.append('period_derived_from_context_requires_human_review')
    p = record.get('payload', {})
    row_label = p.get('row_label_raw') or ''
    # E.g. "Chia cổ tức năm 2022" in a 2024 roll-forward describes the dividend,
    # not necessarily when the cash movement was measured. Preserve native data,
    # but don't export that year as an observation without a genuine period row.
    if year and str(year) in row_label and basis != 'table_header' and not re.match(
            r'^(?:nam(?: tai chinh)?|tai ngay|so (?:du|dau|cuoi)|cuoi nam|dau nam|opening|closing|balance)\b', normalized(row_label)):
        uncertainties.append('row_reference_year_is_not_established_observation_period')
        native = {}
        year = None
    # A native period candidate can come from an OCR repaired title or a
    # document-level end date. Without a same-column header/quote anchor it is
    # not a Graph-ready observation period; retain it in the native artifact.
    if basis == 'unknown':
        year = None
        native = {}
    period_type = {'instant': 'at_date', 'duration': 'range', 'annual': 'annual',
                   'quarter': 'quarter', 'half_year': 'half_year', 'range': 'range'}.get(native.get('period_type'), 'unknown')
    start, end = native.get('start_date'), native.get('end_date')
    if period_type == 'range' and start and end and start[5:] == '01-01' and end[5:] == '12-31' and start[:4] == end[:4]:
        period_type = 'annual'
    return {'observation_year': year, 'observation_start': start, 'observation_end': end,
            'measurement_date': native.get('as_of_date'), 'period_type': period_type,
            'year_basis': basis, 'baseline_year': p.get('baseline_year'), 'target_deadline': p.get('deadline')}


def _financial_workforce_note(block, source_text, checked, digest, scope, page_methods):
    """Queue one explicitly dated headcount from a source note paragraph.

    The rule is intentionally narrow: a company-and-subsidiaries sentence, a
    31 December date, and the amount immediately after `la` must co-occur in
    the same source text block. A comparative amount later in parentheses is
    never interpreted as the current observation.
    """
    quote = block.get('original_text') or ''
    folded = normalized(quote)
    match = re.search(r'\bnhan vien\b.{0,55}\bcong ty va cong ty con\b.{0,35}'
                      r'\bngay 31 thang 12 nam ((?:19|20)\d{2}) la (\d{1,3}(?:\.\d{3})+)', folded)
    if not match:
        return None
    year, raw_value = int(match.group(1)), match.group(2)
    number, status = parse_number(raw_value, 'vi')
    if status != 'available' or number is None:
        return None
    unit_match = re.search(r'nhân viên|nhan vien', quote, re.I)
    if not unit_match:
        return None
    ref = block['source']
    page = ref.get('pdf_page')
    anchor = source_text.get((ref.get('artifact_id'), ref.get('native_json_pointer')))
    if page not in checked or not anchor or quote not in anchor:
        return None
    # Keep the OCR wording as the label; no spelling repair enters evidence.
    label_match = re.search(r'(?i)^.{0,90}?(?:nhân viên|nhan vien).{0,70}?(?:công ty con|cong ty con)', quote)
    label = label_match.group(0) if label_match else quote
    read_method = page_methods.get(str(page), {}).get('read_method')
    uncertainty = ['pending_human_source_review', 'ocr_transcription_needs_review',
                   'workforce_population_and_definition_not_verified',
                   'restatement_not_fully_searched']
    if read_method == 'pymupdf_native_text_and_tables_fallback':
        uncertainty.append('native_fallback_layout_needs_review')
    source_record_id = stable_id('record', block['block_id'], 'current_workforce_note', year)
    return {'record_id': source_record_id, 'dimension': 'X',
            'record_type': 'financial_measurement', 'topic': 'workforce',
            'metric_id': None, 'metric_label': label, 'metric_definition': None,
            'statement': {'original_quote': quote, 'interpretation': None,
                          'assertion_kind': 'reported_result'},
            'value': {'status': 'available', 'original_value': raw_value,
                      'original_unit': unit_match.group(0), 'original_scale': None,
                      'normalized_value': int(Decimal(number)), 'normalized_unit': 'people',
                      'normalization_factor': 1,
                      'normalization_note': 'Observed headcount token; one person per employee.'},
            'period': {'observation_year': year, 'observation_start': None,
                       'observation_end': None, 'measurement_date': f'{year}-12-31',
                       'period_type': 'at_date', 'year_basis': 'explicit_quote',
                       'baseline_year': None, 'target_deadline': None},
            'boundary': {'reporting_entity': None, 'consolidation': scope or 'unknown',
                         'scope': None, 'population': None, 'counting_method': None,
                         'calculation_method': None, 'verified': False},
            'restatement': {'status': 'unknown', 'note': None},
            'evidence': [{'evidence_id': stable_id('handoff_evidence', source_record_id, digest,
                                                  page, ref.get('native_json_pointer'), quote),
                          'source_sha256': digest, 'physical_page': page, 'printed_page': None,
                          'exact_quote': quote, 'context_text': anchor,
                          'section': None,
                          'element_id': ref.get('native_json_pointer'), 'char_start': None,
                          'char_end': None, 'bbox': None, 'table_id': None,
                          'row': None, 'column': None, 'headers': [], 'footnotes': []}],
            'quality': {'extraction_method': 'rule',
                        'parser_name': f"{read_method or 'source-bound parser'} + workforce-note/1",
                        'model_id': None, 'prompt_version': None,
                        'uncertainty': uncertainty, 'review_status': 'pending_human_review',
                        'reviewer': None, 'reviewed_at_utc': None, 'review_basis': None},
            'comparison_group_id': None}


def convert_document(document, source_info=None):
    """Return one strict handoff; unresolved document scope blocks Financial export."""
    info = source_info or {}
    output = document['output']
    report = output['reports'][0]
    financial = output.get('schema_version', '').startswith('esg-financial-')
    scope = SCOPES.get(_meta(output, 'statement_scope')) if financial else None
    if financial and scope is None and output.get('source_blocks'):
        resolved = resolve_scope(output['source_blocks'][0], output)
        if resolved['status'] == 'available':
            scope = SCOPES.get(resolved['value'])
    if financial and scope is None:
        raise ValueError('FINANCIAL_SCOPE_UNRESOLVED: Separate/Consolidated must be established from PDF evidence.')
    if not financial and report.get('report_type') == 'financial_statements':
        raise ValueError('REPORT_TYPE_CONFLICT: financial PDF metadata routed to ESG parser.')
    document_id = report['report_version_id']
    digest = report['source_sha256']
    blocks = {b['block_id']: b for b in output.get('source_blocks', [])}
    source_text = {(b['source'].get('artifact_id'), b['source'].get('native_json_pointer')): b.get('original_text')
                   for b in blocks.values() if b.get('original_text')}
    cover_text = ' '.join(normalized(b.get('original_text') or '') for b in blocks.values()
                          if b['source']['pdf_page'] <= 3 and b.get('kind') == 'texts')
    if not financial and re.search(r'bao cao tai chinh (?:rieng|hop nhat)|bao cao tai chinh.{0,20}cong ty me', cover_text):
        raise ValueError('REPORT_TYPE_CONFLICT: Financial title in PDF was processed by ESG parser; re-extract as BCTC.')
    by_id = {r['record_id']: r for r in output['records']}
    if len(by_id) != len(output['records']):
        raise ValueError('DUPLICATE_NATIVE_RECORD_ID: refusing ambiguous mapping')
    issues, records, exported_ids = [], [], set()

    def issue(code, message, pages=(), record_id=None):
        if not isinstance(message, str):
            message = json.dumps(message, ensure_ascii=False)
        issues.append({'issue_id': stable_id('handoff_issue', document_id, code, record_id, message),
                       'code': code, 'message': message, 'source_pages': sorted(set(p for p in pages if p)),
                       'record_id': record_id, 'status': 'needs_review'})

    page_coverage = document.get('coverage') or output.get('source_capture_coverage') or output.get('coverage', {}).get('source_pages', {})
    page_rows = page_coverage.get('pages', [])
    checked = {r['pdf_page'] for r in page_rows if r['status'] in ('processed', 'partial')}
    unreadable = sorted(r['pdf_page'] for r in page_rows if r['status'] == 'failed')
    for record in output['records']:
        kind = record['record_type']
        if kind == 'metric':
            continue  # A row definition is not a second quantitative observation.
        if financial and kind != 'measurement' or not financial and kind not in TYPES:
            issue('NATIVE_RECORD_NOT_MAPPED', f"Native record {record['record_id']} ({kind}) retained in notes/native; no invented contract type.")
            continue
        dimension = 'X' if financial else record.get('classification', {}).get('pillar')
        # Explicit economic table rows are governance/economic disclosures.
        # Never promote unrelated unknown narrative or index-reference cells.
        metric_candidate = by_id.get(record.get('payload', {}).get('metric_id'), {})
        if not financial and kind == 'measurement' and dimension not in ('E', 'S', 'G'):
            economic_key = identify(metric_candidate.get('original_text') or '')
            if economic_key in ('profit_after_tax', 'net_sales_revenue', 'profit_before_tax', 'total_assets', 'owners_equity') and record.get('original_cells'):
                dimension = 'G'
        if dimension not in ('E', 'S', 'G', 'X') or not financial and dimension == 'X':
            issue('DIMENSION_UNRESOLVED', f"Native record {record['record_id']} retained; E/S/G not unambiguously established.")
            continue
        refs = _sources(record)
        primary = next((record.get('field_sources', {}).get(k, []) for k in
                        ('/payload/raw_value', '/original_text', '/payload/statement')
                        if record.get('field_sources', {}).get(k)), refs[:1])
        quote = record.get('original_text') or ''
        if not primary or not quote.strip() or primary[0].get('pdf_page') not in checked:
            issue('SOURCE_ANCHOR_UNRESOLVED', f"Native record {record['record_id']} has no usable quote/page; retained in notes/native.")
            continue
        anchor_raw = primary[0].get('raw_text') or source_text.get((primary[0].get('artifact_id'), primary[0].get('native_json_pointer')))
        if not anchor_raw or quote not in anchor_raw:
            issue('QUOTE_NOT_IN_SOURCE_ANCHOR', f"Native record {record['record_id']} quote not resolved in its source anchor; retained for review, not inserted into evidence context.", [primary[0]['pdf_page']])
            continue
        metric = by_id.get(record.get('payload', {}).get('metric_record_id') or record.get('payload', {}).get('metric_id'), {})
        all_refs = refs + _sources(metric)
        texts = [anchor_raw] + [r.get('raw_text') for r in all_refs if r.get('raw_text')]
        texts += [blocks[a].get('original_text') for a in record.get('source_refs', []) if a in blocks and blocks[a].get('original_text')]
        context = '\n'.join(dict.fromkeys(texts))
        headers = []
        for field, sources in record.get('field_sources', {}).items():
            role = 'year' if field == '/content_period' else 'unit' if field == '/payload/unit' else None
            if role:
                for ref in sources:
                    raw = ref.get('raw_text')
                    if not raw:
                        raw = source_text.get((ref.get('artifact_id'), ref.get('native_json_pointer')))
                    if raw and ref.get('pdf_page') in checked:
                        actual_role = role
                        if role == 'year' and (ref.get('pdf_page') != primary[0].get('pdf_page') or ref.get('column_index') is None or ref.get('column_index') != primary[0].get('column_index')):
                            actual_role = 'other'
                        headers.append({'role': actual_role, 'text': raw, 'physical_page': ref['pdf_page'],
                                        'row': ref.get('row_index'), 'column': ref.get('column_index'), 'bbox': _bbox(ref.get('bbox'))})
                        if raw not in context:
                            context += '\n' + raw
        for ref in _sources(metric):
            if ref.get('raw_text'):
                headers.append({'role': 'row_label', 'text': ref['raw_text'], 'physical_page': ref['pdf_page'],
                                'row': ref.get('row_index'), 'column': ref.get('column_index'), 'bbox': _bbox(ref.get('bbox'))})
        ref = primary[0]
        uncertainty = ['pending_human_source_review', 'metric_definition_not_verified',
                       'reporting_boundary_not_verified', 'footnote_completeness_not_verified', 'restatement_not_fully_searched']
        page_method = document.get('page_methods', {}).get(str(ref['pdf_page']), {})
        read_method = page_method.get('read_method')
        if read_method == 'pymupdf_native_text_and_tables_fallback':
            uncertainty.append('native_fallback_layout_needs_review')
        if read_method and 'ocr' in read_method:
            uncertainty.append('ocr_transcription_needs_review')
        if page_method.get('fallback_reason'):
            uncertainty.append(page_method['fallback_reason'])
        p = record.get('payload', {})
        label = p.get('row_label_raw') or metric.get('original_text') or p.get('name_raw') or p.get('section_heading_raw') or quote
        topics = record.get('classification', {}).get('topic_candidates', [])
        topic = p.get('statement_type') if financial else topics[0].get('topic_id') if len(topics) == 1 else None
        evidence = [{'evidence_id': stable_id('handoff_evidence', record['record_id'], digest, ref['pdf_page'], ref.get('native_json_pointer'), quote),
                     'source_sha256': digest, 'physical_page': ref['pdf_page'], 'printed_page': None,
                     'exact_quote': quote, 'context_text': context, 'section': p.get('section_heading_raw'),
                     'element_id': ref.get('native_json_pointer'), 'char_start': None, 'char_end': None,
                     'bbox': _bbox(ref.get('bbox')), 'table_id': p.get('table_anchor_id') or next((a for a in record.get('source_refs', []) if blocks.get(a, {}).get('kind') == 'tables'), None),
                     'row': ref.get('row_index'), 'column': ref.get('column_index'), 'headers': headers, 'footnotes': []}]
        value = _value(record, context, uncertainty, output.get('number_format', 'auto'))
        period = _period(record, headers, quote, uncertainty, ref.get('column_index'), ref['pdf_page'])
        record_scope = SCOPES.get(p.get('statement_scope')) if financial else None
        restatement_note = '\n'.join(h['text'] for h in headers if re.search(r'trinh bay lai|dieu chinh|restated|adjusted', normalized(h['text']))) or None
        restatement_status = ('restated' if restatement_note and re.search(r'trinh bay lai|restated', normalized(restatement_note))
                              else 'ambiguous' if restatement_note else 'unknown')
        handoff = {'record_id': record['record_id'], 'dimension': dimension,
                   'record_type': 'financial_measurement' if financial else TYPES[kind],
                   'topic': topic or ('financial_unclassified' if financial else 'esg_unclassified'),
                   'metric_id': None, 'metric_label': label, 'metric_definition': None,
                   'statement': {'original_quote': quote,
                                 'interpretation': '\n'.join(record.get('interpretation_notes', [])) or None,
                                 'assertion_kind': 'target' if kind == 'target' else 'policy' if kind == 'policy' else p.get('assertion_kind', 'reported_result') if kind == 'measurement' else 'unknown'},
                   'value': value, 'period': period,
                   'boundary': {'reporting_entity': record.get('reported_entity'), 'consolidation': record_scope or 'unknown',
                                'scope': None, 'population': None, 'counting_method': None, 'calculation_method': None, 'verified': False},
                   'restatement': {'status': restatement_status, 'note': restatement_note},
                   'evidence': evidence,
                   'quality': {'extraction_method': 'rule', 'parser_name': f"{read_method or 'source-bound parser (see checkpoint)'} + {output['schema_version']} + corporate-handoff/1.2",
                               'model_id': None, 'prompt_version': None, 'uncertainty': sorted(set(uncertainty)),
                               'review_status': 'pending_human_review', 'reviewer': None, 'reviewed_at_utc': None, 'review_basis': None},
                   'comparison_group_id': None}
        records.append(handoff)
        exported_ids.add(record['record_id'])
        issue('RECORD_REQUIRES_REVIEW', '; '.join(handoff['quality']['uncertainty']), [ref['pdf_page']], record['record_id'])
    if financial:
        for block in blocks.values():
            if block['kind'] != 'texts':
                continue
            workforce = _financial_workforce_note(block, source_text, checked, digest,
                                                  scope, document.get('page_methods', {}))
            if workforce:
                records.append(workforce)
                exported_ids.add(workforce['record_id'])
                issue('WORKFORCE_NOTE_REQUIRES_REVIEW',
                      'Source-bound workforce note candidate; OCR, population and counting basis need review.',
                      [workforce['evidence'][0]['physical_page']], workforce['record_id'])
    for item in output.get('issues', []):
        issue(item.get('code', 'NATIVE_ISSUE'), item.get('details') or item.get('reason') or 'See native output.',
              [item.get('pdf_page')], item.get('record_id') if item.get('record_id') in exported_ids else None)
    if not _source_bytes_checked(info, digest):
        issue('SOURCE_PROVENANCE_UNCONFIRMED' if not info.get('url') else 'SOURCE_URL_NOT_INDEPENDENTLY_VERIFIED',
          'Source URL absent; uploaded PDF not independently verified against official publication.' if not info.get('url')
              else 'URL is supplied provenance, not a claim that official bytes have been independently verified.')
    issue('DOCUMENT_METADATA_REQUIRES_REVIEW', 'Company/year/type supplied metadata must be checked against PDF. No cover-to-KPI boundary inheritance.')
    if not financial and any(b.get('label') in ('page_header', 'page_footer') and
                             normalized(b.get('original_text') or '').startswith('bao cao thuong nien') for b in blocks.values()):
        issue('PHYSICAL_DOCUMENT_TYPE_REQUIRES_REVIEW', 'Annual-report running headers occur in supplied ESG PDF. Check the official original and whether this is an annual-report chapter; do not assert independent sustainability publication.')
    outcomes, searched = [], []
    for topic in TOPICS:
        hits = sorted({b['source']['pdf_page'] for b in blocks.values() if b['source']['pdf_page'] in checked
                       and re.search(TOPIC_PATTERNS[topic], normalized(b.get('original_text') or ' '.join(c.get('text', '') for c in b.get('original_cells') or [])))})
        if hits:
            searched.append(topic)
            outcomes.append({'topic': topic, 'status': 'found', 'pages': hits,
                             'reason': 'Bounded keyword occurrence in retained source, not confirmed KPI completeness or comparability.'})
        else:
            outcomes.append({'topic': topic, 'status': 'parse_failure' if unreadable else 'not_searched',
                             'pages': unreadable if unreadable else [],
                             'reason': 'Unreadable pages prevent a completeness claim.' if unreadable else
                             'No confirmed topic search completion; missing keyword alone is not disclosure absence.'})
    issue('SEARCH_COVERAGE_NOT_ADJUDICATED', 'Found means a source keyword occurrence only. No topic absence or semantic search completeness asserted.')
    year = _meta(output, 'reporting_year') or report.get('reporting_year')
    result = {'schema_version': 'corporate-extract-1.0',
              'document': {'document_id': document_id, 'company_id': _meta(output, 'ticker_from_pdf') or report['company_id'],
                           'report_type': 'Financial' if financial else 'ESG',
                           'source_document_type': 'financial_statement' if financial else 'annual_report' if report.get('report_type') == 'annual_report' or 'bao cao thuong nien' in cover_text else 'sustainability_report',
                           'report_year': year, 'financial_scope': scope, 'reporting_entity': _meta(output, 'company_name'),
                           'reporting_period_start': _meta(output, 'period_start'), 'reporting_period_end': _meta(output, 'period_end'),
                           'publication_date': _meta(output, 'publication_date'),
                           'source': {'source_id': stable_id('source', digest), 'file_name': document['filename'], 'url': info.get('url'),
                                      'downloaded_at_utc': info.get('downloaded_at_utc'), 'sha256': digest,
                                      'page_count': report['pdf_page_count'], 'page_system': 'physical_pdf_page_1_based'}},
              'coverage': {'status': 'partial', 'scope_description': 'Candidate extraction over retained page checkpoints; semantic completeness, topic search and human review pending.',
                           'search_status': 'partial_search' if searched else 'search_failed' if unreadable else 'not_searched',
                           'pages_checked': sorted(checked), 'pages_unreadable': unreadable,
                           'topics_searched': searched, 'search_outcomes': outcomes},
              'records': records, 'issue_log': issues}
    enrich_records(result, output)
    recover_headcounts(result, output)
    schema = json.loads((CONTRACT / 'schema.json').read_text(encoding='utf-8'))
    errors = list(Draft202012Validator(schema).iter_errors(result))
    if errors:
        raise ValueError('Contract schema error: ' + '; '.join(e.message for e in errors[:8]))
    return result


def build_delivery(result, destination, *, source_info=None, expected_bsr=False):
    """Create a new immutable delivery directory; partial is never certified complete."""
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    for name in ('pdf', 'json', 'notes/native', 'validation'):
        (destination / name).mkdir(parents=True)
    entries, slots, seen, blocked, handoffs, record_counts, source_verified = [], set(), set(), [], [], {}, []
    v = validator_module()
    schema = v.load_json(CONTRACT / 'schema.json')
    for doc in result.get('documents', []):
        out = doc['output']
        report = out['reports'][0]
        digest = report['source_sha256']
        if digest in seen:
            continue
        seen.add(digest)
        work = Path(doc['workspace']).resolve()
        artifact = next(a for a in out['source_artifacts'] if a['kind'] == 'pdf')
        pdf = (work / artifact['path']).resolve()
        if not pdf.is_relative_to(work) or file_hash(pdf) != digest:
            raise ValueError('Source PDF missing, unsafe or hash changed; delivery stopped.')
        pdf_name = Path(doc['filename']).name
        if (destination / 'pdf' / pdf_name).exists():
            pdf_name = digest[:12] + '_' + pdf_name
        shutil.copyfile(pdf, destination / 'pdf' / pdf_name)
        atomic_json(destination / 'notes/native' / (digest + '.json'), out)
        # Keep parser-native page checkpoints so JSON pointers remain resolvable.
        native_dir = destination / 'notes/native' / digest
        for a in out['source_artifacts']:
            if a['kind'] == 'page_checkpoint':
                source = (work / a['path']).resolve()
                if not source.is_relative_to(work) or file_hash(source) != a['sha256']:
                    raise ValueError('Native source hash changed; delivery stopped.')
                target = native_dir / source.relative_to(work)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        try:
            handoff = convert_document(doc, (source_info or {}).get(digest))
            handoff['document']['source']['file_name'] = pdf_name
            filename = digest + '.json'
            target = destination / 'json' / filename
            atomic_json(target, handoff)
            _, errors = v.validate_handoff(target, schema, destination / 'pdf')
            if errors:
                raise ValueError('; '.join(errors[:8]))
            document = handoff['document']
            source_verified.append(_source_bytes_checked((source_info or {}).get(digest, {}), digest))
            record_counts[document['document_id']] = len(handoff['records'])
            handoffs.append(handoff)
            entries.append({'document_id': document['document_id'], 'report_year': document['report_year'],
                            'report_type': document['report_type'], 'financial_scope': document['financial_scope'],
                            'pdf_path': 'pdf/' + pdf_name, 'pdf_sha256': digest, 'json_path': 'json/' + filename,
                            'json_sha256': file_hash(target), 'status': 'partial',
                            'reason': 'Mechanical checks passed; source provenance, semantic completeness and human review pending.'})
            if document['company_id'].upper() == 'BSR':
                slots.add((document['report_year'], document['report_type'], document['financial_scope']))
        except (ValueError, KeyError) as exc:
            # Do not put a mechanically invalid candidate in delivery/json.
            path = destination / 'json' / (digest + '.json')
            if path.exists():
                path.rename(destination / 'notes' / (digest + '.invalid.json'))
            blocked.append({'filename': pdf_name, 'source_sha256': digest, 'error': str(exc)})
    if expected_bsr:
        for year in (2023, 2024, 2025):
            for kind, scope in (('ESG', None), ('Financial', 'Separate'), ('Financial', 'Consolidated')):
                if (year, kind, scope) not in slots:
                    entries.append({'document_id': f'BSR-{year}-{kind}-{scope or "ESG"}-UNAVAILABLE',
                                    'report_year': year, 'report_type': kind, 'financial_scope': scope,
                                    'pdf_path': None, 'pdf_sha256': None, 'json_path': None, 'json_sha256': None,
                                    'status': 'unavailable', 'reason': 'No contract-ready source/result supplied for this slot. Not a finding that BSR did not publish it; see blocked documents in notes.'})
    if not entries:
        atomic_json(destination / 'notes/blocked_documents.json', blocked)
        raise ValueError(f'No contract-ready documents. Review {destination / "notes/blocked_documents.json"}.')
    manifest = {'schema_version': 'corporate-extract-manifest-1.0',
                'batch_id': stable_id('batch', sorted(e['document_id'] for e in entries)), 'files': entries}
    atomic_json(destination / 'manifest.json', manifest)
    _, errors = v.validate_manifest(destination / 'manifest.json', v.load_json(CONTRACT / 'manifest_schema.json'))
    atomic_json(destination / 'notes/blocked_documents.json', blocked)
    atomic_json(destination / 'notes/source_provenance.json', source_info or {})
    atomic_json(destination / 'notes/source_selection.json', result.get('excluded_source_versions', []))
    atomic_json(destination / 'notes/demo_review_queue.json', build_review_queue(handoffs))
    from src.extraction.quality_report import extraction_quality
    atomic_json(destination / 'notes/extraction_quality.json', extraction_quality(handoffs, [d['output'] for d in result.get('documents', [])]))
    candidates = CONTRACT.parents[1] / 'config/bsr_source_candidates_20261016.json'
    if expected_bsr and candidates.is_file():
        shutil.copyfile(candidates, destination / 'notes/source_url_candidates.json')
    validation = {'created_at': now(), 'mechanical_valid': not errors and any(e['status'] == 'partial' for e in entries),
                  'manifest_valid': not errors,
                  'complete_handoff': False, 'human_review_pending': True,
                  'official_source_verification': 'sha256_matched_downloaded_official_sources' if source_verified and all(source_verified) else 'pending',
                  'source_pdf_bytes_verified': sum(source_verified), 'record_counts': record_counts,
                  'partial_documents': sum(e['status'] == 'partial' for e in entries),
                  'unavailable_slots': sum(e['status'] == 'unavailable' for e in entries),
                  'blocked_documents': len(blocked), 'errors': errors}
    atomic_json(destination / 'validation/report.json', validation)
    for name in ('schema.json', 'manifest_schema.json', 'validate.py', 'requirements.txt'):
        shutil.copyfile(CONTRACT / name, destination / 'validation' / name)
    # Ship the reference graph/review validator with UI/CLI exports too. Partial
    # uploads may have no pairs or an incomplete nine-slot corpus; report that
    # honestly rather than claiming an external Graph import succeeded.
    review_script = CONTRACT.parents[1] / 'scripts/validate_corporate_review.py'
    shutil.copyfile(review_script, destination / 'validation/validate_corporate_review.py')
    spec = importlib.util.spec_from_file_location('delivery_review_validator', review_script)
    review_validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(review_validator)
    review_report = review_validator.validate(destination, require_complete=False, require_pairs=False)
    validation['graph_import'] = review_report['graph_import']
    validation['candidate_pairs'] = review_report['candidate_pairs']
    if not review_report['passed']:
        validation['errors'].extend(review_report['errors'])
        validation['mechanical_valid'] = False
    atomic_json(destination / 'validation/report.json', validation)
    shutil.copyfile(CONTRACT / 'DELIVERY_README.md', destination / 'README.md')
    if errors:
        raise ValueError('Manifest validation failed: ' + '; '.join(errors))
    return validation


def zip_delivery(folder, archive=None):
    folder = Path(folder)
    archive = Path(archive) if archive is not None else folder.with_suffix('.zip')
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for path in folder.rglob('*'):
            if path.is_file():
                z.write(path, path.relative_to(folder).as_posix())
    return archive
