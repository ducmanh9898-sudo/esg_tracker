"""Evidence-backed report metadata, periods, semantic coverage and checks.

This layer never overwrites raw OCR cells or equates source coverage with
semantic completeness. Rules are candidates; no automated audit verdict.
"""
from collections import Counter, defaultdict
import ast
from datetime import date, timedelta
from decimal import Decimal, localcontext
import re

from src.extraction.financial_context_v2 import normalized, resolve_scope
from src.extraction.financial_notes_v2 import ordered_blocks, NOTE_TITLE, STATEMENT_TITLE
from src.extraction.source_v2 import stable_id, sync_missing_fields


def source_evidence(block):
    return {**block['source'], 'block_id': block['block_id'], 'raw_text': block.get('original_text')}


def dates_in(raw):
    text = normalized(raw)
    matches = re.findall(r'\b(\d{1,2})(?:\s+thang\s+|[/.\-])(\d{1,2})(?:\s+nam\s+|[/.\-])((?:19|20)\d{2})\b', text)
    found = []
    for day, month, year in matches:
        try:
            found.append(date(int(year), int(month), int(day)).isoformat())
        except ValueError:
            pass
    return found


def metadata(bundle):
    blocks = [b for b in bundle['source_blocks'] if b['kind'] == 'texts' and b.get('original_text')]
    report = bundle['reports'][0]
    fields = {}

    def put(name, candidates, method='explicit_source'):
        distinct = {str(value) for value, _ in candidates}
        fields[name] = {'value': candidates[0][0] if len(distinct) == 1 else None,
                        'status': 'available' if len(distinct) == 1 else 'ambiguous' if candidates else 'not_found_in_checked_scope',
                        'sources': [source_evidence(block) for _, block in candidates],
                        'method': method, 'verification_status': 'needs_review'}

    titles = [b for b in blocks if b['source']['pdf_page'] <= 2 and re.match(r'^(?:bo )?bao cao tai chinh\b', normalized(b['original_text']))]
    put('report_title', [(b['original_text'], b) for b in titles[:1]])
    put('report_type', [('financial_statements', b) for b in titles])
    put('company_name', [(b['original_text'], b) for b in blocks if b['source']['pdf_page'] == 1 and re.match(r'^(?:cong ty|tong cong ty|tap doan)\b', normalized(b['original_text']))][:1])
    tickers = [(m.group(1).upper(), b) for b in blocks for m in [re.search(r'(?:ma (?:chung khoan|co phieu)|ticker)\s*(?:[:：]|la\b)?\s*([A-Za-z]{2,10})\b', normalized(b['original_text']))] if m]
    put('ticker_from_pdf', tickers)
    scope = resolve_scope(blocks[0], bundle) if blocks else {'value': None, 'sources': [], 'status': 'unknown'}
    fields['statement_scope'] = {'value': scope['value'], 'status': scope['status'], 'sources': scope['sources'],
                                 'method': 'explicit_statement_labels_not_filename', 'verification_status': 'needs_review'}
    ends = [(d, b) for b in blocks if b['source']['pdf_page'] <= 12
            and re.match(r'^(?:cho )?nam tai chinh.{0,90}(?:ket|kt) thuc|^tai ngay', normalized(b['original_text']))
            for d in dates_in(b['original_text'])]
    put('period_end', ends)
    end = fields['period_end']['value']
    starts = [(d, b) for b in blocks if re.match(r'^(?:nam tai chinh|nien do|ky ke toan)', normalized(b['original_text'])) and re.search(r'bat dau|tu ngay|beginning|starting', normalized(b['original_text']))
              for d in dates_in(b['original_text']) if end and d[:4] == end[:4] and d < end]
    # Recurring calendar accounting year requires a source policy, not the
    # user-supplied report year or an assumption based only on a cover date.
    calendar = [b for b in blocks if re.match(r'^(?:nam tai chinh|nien do|ky ke toan)', normalized(b['original_text']))
                and re.search(r'(?:01|1)\s+thang\s+(?:01|1)\b|01/01', normalized(b['original_text']))
                and re.search(r'31\s+thang\s+12\b|31/12', normalized(b['original_text']))]
    if not starts and end and calendar:
        starts = [(end[:4] + '-01-01', b) for b in calendar]
    put('period_start', starts, 'explicit_date_or_calendar_policy_plus_source_year')
    put('reporting_year', [(int(end[:4]), b) for _, b in ends] if end else [])
    currencies = [(currency, b) for b in blocks
                  if re.search(r'don vi(?: tinh)?\s*[:：]|don vi tien te|dong tien', normalized(b['original_text']))
                  for currency in re.findall(r'\b(?:VND|USD|EUR)\b', b['original_text'])]
    put('presentation_currency', currencies)
    put('presentation_unit_raw', [(b['original_text'], b) for b in blocks
                                  if re.match(r'^don vi(?: tinh)?\s*[:：]', normalized(b['original_text']))][:1])
    audited = [b for b in blocks if b['source']['pdf_page'] <= 8 and re.search(r'bao cao kiem toan doc lap|da duoc kiem toan|chung toi da kiem toan', normalized(b['original_text']))]
    put('audit_status', [('audited', b) for b in audited])
    auditors = [b for b in blocks if b['source']['pdf_page'] <= 8 and re.match(r'^cong ty (?:tnhh|trach nhiem huu han).{0,30}kiem toan', normalized(b['original_text'])) and len(b['original_text']) < 180]
    put('auditor_name', [(b['original_text'], b) for b in auditors[:1]])
    opinion = [b for b in blocks if b['source']['pdf_page'] <= 8 and re.search(r'^theo y kien cua chung toi', normalized(b['original_text']))]
    opinion_types = []
    for b in opinion:
        text = normalized(b['original_text'])
        if 'ngoai tru' in text:
            opinion_types.append(('qualified', b))
        elif re.search(r'khong phan anh|khong trinh bay trung thuc', text):
            opinion_types.append(('adverse', b))
        elif 'phan anh trung thuc va hop ly' in text:
            opinion_types.append(('unmodified_candidate', b))
    put('audit_opinion', opinion_types, 'explicit_opinion_phrase_candidate_not_independent_audit')
    put('emphasis_of_matter', [(True, b) for b in blocks if b['source']['pdf_page'] <= 8 and re.search(r'cac van de can nhan manh|emphasis of matter', normalized(b['original_text']))])
    signature_dates = [(d, b) for b in blocks if b['source']['pdf_page'] <= 11 and re.match(r'^ngay\s+\d', normalized(b['original_text'])) for d in dates_in(b['original_text'])]
    put('signature_date', signature_dates)
    put('publication_date', [])  # Signature is not publication.
    fields['supplied_metadata'] = {key: {'value': report.get(key), 'origin': report.get('metadata_origin'),
                                       'status': 'unverified_input_not_pdf_evidence'}
                                   for key in ('company_id', 'reporting_year', 'report_type')}
    pdf = next(a for a in bundle['source_artifacts'] if a['kind'] == 'pdf')
    fields['source_pdf'] = {'filename': report['source_filename'], 'sha256': report['source_sha256'],
                             'page_count': report['pdf_page_count'], 'path': pdf['path'], 'artifact_id': pdf['artifact_id']}
    return fields


def table_class(block, context):
    headers = ' '.join(c.get('text', '') for c in block.get('original_cells') or [] if c.get('column_header'))
    text = normalized(headers)
    ctx = ' '.join(normalized(b.get('original_text') or '') for b in context)
    if re.search(r'\btrang\b|\bpages?\b', text) and not re.search(r'vnd|usd|eur|nam nay|cuoi nam', text):
        return 'table_of_contents'
    if re.search(r'^muc luc\b|\btable of contents\b', ctx) and re.search(r'\btrang\b', text):
        return 'table_of_contents'
    if any(NOTE_TITLE.search(normalized(b.get('original_text') or '')) for b in context):
        return 'note_table'
    for code, pattern in [('balance_sheet', r'bang can doi ke toan|bao cao tinh hinh tai chinh|balance sheet'),
                           ('income_statement', r'bao cao ket qua hoat dong kinh doanh|profit or loss'),
                           ('cash_flow', r'bao cao luu chuyen tien te|cash flows')]:
        if any(re.match(r'^(?:' + pattern + r')\b', normalized(b.get('original_text') or '')) for b in context):
            return code
    return 'note_table'


def relative_role(raw):
    text = normalized(raw)
    if re.search(r'dau nam truoc|opening.{0,10}previous', text):
        return 'previous_opening'
    if re.search(r'cuoi nam truoc', text):
        return 'previous_closing'
    if re.search(r'dau nam|dau ky|opening', text):
        return 'opening_balance'
    if re.search(r'cuoi nam|cuoi ky|closing', text):
        return 'current'
    if re.search(r'nam truoc|previous|comparative', text):
        return 'comparative'
    if re.search(r'nam nay|trong nam|current year', text):
        return 'current_flow'
    return None


def resolved_period(header, row_label, section_type, meta, existing=None):
    """Relative columns resolve from PDF period evidence, never supplied year."""
    dates = dates_in(header)
    end = meta['period_end']['value']
    start = meta['period_start']['value']
    role = relative_role(header)
    row_role = relative_role(row_label)
    sources = meta['period_end']['sources'] + meta['period_start']['sources']
    if len(dates) == 2 and re.search(r'\btu\b.{0,100}\bden\b|\bfrom\b.{0,100}\bto\b', normalized(header)) and dates[0] <= dates[1]:
        return {'raw_text': header, 'year': int(dates[1][:4]), 'as_of_date': None,
                'start_date': dates[0], 'end_date': dates[1], 'period_type': 'duration',
                'mapping_basis': 'explicit_header_date_range'}, []
    if re.search(r'\bquy\b|\bquarter\b|\bmonths?\b|\bthang\b', normalized(header)) and not dates:
        return existing, []
    if len(set(dates)) == 1:
        d = dates[0]
        return {'raw_text': header, 'year': int(d[:4]), 'as_of_date': d, 'start_date': None,
                'end_date': None, 'period_type': 'instant', 'mapping_basis': 'explicit_column_date'}, []
    if len(set(dates)) > 1:
        return None, []
    explicit_years = set(re.findall(r'\b(?:19|20)\d{2}\b', header))
    if len(explicit_years) > 1:
        return None, []
    year = int(next(iter(explicit_years))) if len(explicit_years) == 1 else int(end[:4]) if end and role else None
    if year is None:
        return existing, []
    if role in ('comparative', 'previous_closing', 'previous_opening') and not explicit_years:
        year -= 1
    temporal = 'instant' if section_type == 'balance_sheet' or role in ('opening_balance', 'current', 'previous_opening', 'previous_closing') or row_role in ('opening_balance', 'current', 'previous_opening', 'previous_closing') else 'duration'
    if row_role in ('previous_opening', 'previous_closing') and not role:
        year -= 1
    if not end:
        return existing, []
    try:
        period_end = date(year, int(end[5:7]), int(end[8:10]))
        period_start = date(year, int(start[5:7]), int(start[8:10])) if start else None
    except ValueError:
        return None, []
    opening = role in ('opening_balance', 'previous_opening') or row_role in ('opening_balance', 'previous_opening')
    if temporal == 'instant':
        if opening and not period_start:
            return None, []
        as_of = (period_start - timedelta(days=1)) if opening else period_end
        return {'raw_text': header, 'year': as_of.year, 'as_of_date': as_of.isoformat(), 'start_date': None,
                'end_date': None, 'period_type': 'instant', 'mapping_basis': 'relative_label_plus_pdf_period'}, sources
    return {'raw_text': header, 'year': year, 'as_of_date': None,
            'start_date': period_start.isoformat() if period_start else None, 'end_date': period_end.isoformat(),
            'period_type': 'duration', 'mapping_basis': 'column_label_plus_pdf_reporting_period'}, sources


def augment(output, bundle, contexts, work):
    meta = metadata(bundle)
    output['metadata'] = meta
    # Printed page labels come from observed footers only; no constant offset.
    printed = defaultdict(list)
    for b in bundle['source_blocks']:
        if b['kind'] == 'texts' and b.get('label') == 'page_footer' and re.fullmatch(r'\d+', (b.get('original_text') or '').strip()):
            printed[b['source']['pdf_page']].append(b['original_text'].strip())
    printed = {p: labels[0] for p, labels in printed.items() if len(set(labels)) == 1}
    contexts_by_id = {item['block']['block_id']: item for item in contexts}
    section_map = section_contexts(bundle, work)
    by_id = {r['record_id']: r for r in output['records']}
    for record in output['records']:
        anchor = record['payload'].get('table_anchor_id') or record['source_refs'][0]
        context = contexts_by_id.get(anchor)
        section = section_map.get(anchor, {})
        payload = record['payload']
        payload.update({'statement_type': context.get('statement_type') if context else 'notes',
                        'table_title_raw': context['title']['raw'] if context and context.get('title') else None,
                        'note_number': section.get('number'), 'note_heading_raw': section.get('raw')})
        if section.get('block'):
            record['field_sources']['/payload/note_number'] = [section['block']['source']]
            record['source_refs'] = list(dict.fromkeys(record['source_refs'] + [section['block']['block_id']]))
        if record['record_type'] == 'metric':
            payload['normalized_name'] = normalized(payload.get('original_name') or '') or None
            payload['normalization_method'] = 'unicode_accent_case_whitespace_only_no_ocr_repair'
            cells = context['block']['original_cells'] if context else []
            # The original label source identifies the row even for row 0.
            label_source = record['field_sources'].get('/payload/original_name', [])
            row = label_source[0].get('row_index') if label_source else None
            note_cols = {c['start_col_offset_idx'] for c in cells if c.get('column_header') and re.search(r'thuyet|minh|notes?', normalized(c.get('text', '')))}
            note_cells = [(i, c) for i, c in enumerate(cells) if c['start_row_offset_idx'] == row and c['start_col_offset_idx'] in note_cols and not c.get('column_header')]
            payload['note_reference_raw'] = note_cells[0][1].get('text') if len(note_cells) == 1 else None
            if len(note_cells) == 1:
                i, cell = note_cells[0]
                block = context['block']
                record['field_sources']['/payload/note_reference_raw'] = [{**block['source'],
                    'native_json_pointer': block['source']['native_json_pointer'] + f'/data/table_cells/{i}',
                    'bbox': cell.get('bbox'), 'raw_text': cell.get('text'),
                    'row_index': cell['start_row_offset_idx'], 'column_index': cell['start_col_offset_idx']}]
            payload['parent_metric_id'] = None
            payload['hierarchy_status'] = 'not_checked_without_explicit_formula'
        if record['record_type'] == 'measurement':
            header = ' | '.join(payload['column_headers_raw'])
            row_label = payload.get('row_label_raw') or ''
            # Some roll-forwards encode the period in rows rather than columns.
            period_row = bool(re.match(r'^(?:nam(?: tai chinh)?|tai ngay|so (?:du|dau|cuoi)|cuoi nam|dau nam|opening|closing|balance)\b', normalized(row_label)))
            period_header = header if relative_role(header) or re.search(r'\b(?:19|20)\d{2}\b', header) else row_label if period_row or relative_role(row_label) else header
            period, sources = resolved_period(period_header, row_label, payload['statement_type'], meta, record['content_period'])
            record['content_period'] = period
            if sources:
                record['field_sources']['/content_period'] += sources
            if period_header == row_label:
                metric = by_id[payload['metric_record_id']]
                record['field_sources']['/content_period'] += metric['field_sources'].get('/payload/original_name', [])
            record['field_status']['/content_period'] = {'status': 'available' if period else 'unknown',
                                                        'reason': 'Column/row label + PDF period evidence only; supplied year not used.'}
            payload['period_role'] = relative_role(header) or relative_role(row_label)
            payload['time_type'] = period['period_type'] if period else None
            payload['restatement_status'] = 'restated' if re.search(r'trinh bay lai|dieu chinh|restated|adjusted', normalized(header)) else 'not_labelled'
            # A currency in the row is more specific than a generic table unit.
            row_currency = re.findall(r'\b(VND|USD|EUR)\b', row_label)
            if len(set(row_currency)) == 1:
                payload.update(currency=row_currency[0], unit=row_currency[0], scale='1')
                metric = by_id[payload['metric_record_id']]
                record['field_sources']['/payload/unit'] = metric['field_sources'].get('/payload/original_name', [])
            # Share counts must not inherit a table's generic VND context.
            if re.search(r'co phieu|shares', normalized(row_label)) and not re.search(r'lai|loi nhuan|thu nhap|\(vnd\)|earnings', normalized(row_label)):
                payload.update(currency=None, unit='shares', scale='1')
                metric = by_id[payload['metric_record_id']]
                record['field_sources']['/payload/unit'] = metric['field_sources'].get('/payload/original_name', [])
            if payload['parsed_value'] is not None and payload['scale'] and payload['unit'] != '%':
                with localcontext() as ctx:
                    ctx.prec = max(50, len(payload['parsed_value']) + len(payload['scale']) + 5)
                    payload['normalized_value'] = format(Decimal(payload['parsed_value']) * Decimal(payload['scale']), 'f')
            for name in ('unit', 'scale', 'period_role'):
                record['field_status']['/payload/' + name] = {'status': 'available' if payload.get(name) is not None else 'unknown', 'reason': 'Source-specific semantic mapping.'}
            payload['read_status'] = record['data_status']
            payload['verification_status'] = 'needs_review'
        for refs in record['field_sources'].values():
            for source in refs:
                source['printed_page'] = printed.get(source['pdf_page'])
        for name in ('statement_type', 'table_title_raw', 'note_number', 'note_heading_raw'):
            record['field_status']['/payload/' + name] = {'status': 'available' if payload.get(name) is not None else 'unknown', 'reason': 'Observed table or note heading; missing is not inferred.'}
        sync_missing_fields(record)
    # Remove old unresolved issues only when the affected field is resolved.
    output['issues'] = [i for i in output['issues'] if not (i.get('record_id') in by_id and i.get('field')
        and by_id[i['record_id']]['field_status'].get(i['field'], {}).get('status') == 'available'
        and (i['code'].endswith('_UNKNOWN') or i['code'] == 'PERIOD_UNKNOWN'))]
    checks, hierarchy = arithmetic_checks(output['records'])
    output['arithmetic_checks'], output['hierarchy_relationships'] = checks, hierarchy
    parents = defaultdict(set)
    for edge in hierarchy:
        parents[edge['child_metric_id']].add(edge['parent_metric_id'])
    for child, candidates in parents.items():
        by_id[child]['payload']['parent_metric_id'] = next(iter(candidates)) if len(candidates) == 1 else None
        by_id[child]['payload']['hierarchy_status'] = 'explicit_formula_candidate' if len(candidates) == 1 else 'multiple_explicit_parents'
    for check in checks:
        if check['status'] == 'mismatch':
            output['issues'].append({'issue_id': stable_id('issue', check['check_id']), 'code': 'ARITHMETIC_MISMATCH',
                'severity': 'warning', 'status': 'open', 'record_id': check['total_record_id'], 'field': '/payload/parsed_value',
                'pdf_page': check['pdf_page'], 'source_refs': check['source_refs'], 'details': check})
    output['semantic_coverage'] = semantic_coverage(bundle, output, contexts)
    periods = {}
    for record in output['records']:
        period = record.get('content_period')
        if record['record_type'] == 'measurement' and period:
            key = tuple(period.get(k) for k in ('year', 'as_of_date', 'start_date', 'end_date', 'period_type'))
            periods.setdefault(key, {'period': {k: period.get(k) for k in ('year', 'as_of_date', 'start_date', 'end_date', 'period_type')}, 'record_ids': []})['record_ids'].append(record['record_id'])
    meta['observed_measurement_periods'] = list(periods.values())
    output['esg_relevant_disclosures'] = esg_search(output, bundle)
    for issue in output['issues']:
        issue.setdefault('severity', 'warning')
        issue.setdefault('source_refs', by_id.get(issue.get('record_id'), {}).get('source_refs', []))
        issue.setdefault('affected_field', issue.get('field'))
        issue.setdefault('reason', issue.get('details'))
    for record in output['records']:
        if record['record_type'] == 'metric':
            code = record['payload'].get('item_code_raw')
            if code and not re.fullmatch(r'\d{2,3}', code.strip()):
                output['issues'].append({'issue_id': stable_id('issue', record['record_id'], 'unreadable_code'),
                    'record_id': record['record_id'], 'field': '/payload/item_code_raw', 'affected_field': '/payload/item_code_raw',
                    'code': 'ITEM_CODE_NEEDS_REVIEW', 'severity': 'warning', 'status': 'open',
                    'pdf_page': record['field_sources']['/payload/item_code_raw'][0]['pdf_page'],
                    'source_refs': record['source_refs'], 'reason': 'Observed item code is not a plain 2–3 digit statement code; raw OCR retained, not repaired.'})
    for name, field in meta.items():
        if isinstance(field, dict) and 'status' in field and field.get('value') is None:
            output['issues'].append({'issue_id': stable_id('issue', bundle['reports'][0]['report_version_id'], 'metadata', name),
                'record_id': None, 'field': '/metadata/' + name, 'code': 'METADATA_UNRESOLVED', 'severity': 'warning',
                'status': 'open', 'pdf_page': None, 'source_refs': [], 'details': field['status']})
    for issue in output['issues']:
        issue.setdefault('affected_field', issue.get('field'))
        issue.setdefault('reason', issue.get('details'))
    return output


def section_contexts(bundle, work):
    blocks, _ = ordered_blocks(bundle, work)
    active = None
    sections = {}
    previous_page = None
    statuses = {p['pdf_page']: p['status'] for p in bundle['coverage']['pages']}
    for block in blocks:
        page = block['source']['pdf_page']
        if previous_page is not None and page != previous_page and (page != previous_page + 1 or statuses.get(previous_page) != 'processed' or statuses.get(page) != 'processed'):
            active = None
        previous_page = page
        raw = block.get('original_text') or ''
        text = normalized(raw)
        # Notes numbered headings only; policy subsection numbers remain separate.
        if block['kind'] == 'texts' and block.get('label') in ('section_header', 'title'):
            match = re.match(r'^(\d{1,2})(?:[.),;]\s*|\s+)([^\d\s].+)', text)
            if match and not re.match(r'(?:nam|thang)\s+\d', match.group(2)):
                active = {'number': match.group(1), 'raw': raw, 'block': block}
            elif raw.isupper() and len(raw.split()) >= 3 and not re.match(r'^(?:cong ty|tong cong ty|tap doan|mau so|thuyet minh|bao cao|bang can doi)', text):
                # A new major heading with a missing/damaged number must not
                # silently inherit the previous note's number.
                active = {'number': None, 'raw': raw, 'block': block}
        if active:
            sections[block['block_id']] = active
    return sections


def arithmetic_checks(records):
    metrics = {r['record_id']: r for r in records if r['record_type'] == 'metric'}
    measurements = [r for r in records if r['record_type'] == 'measurement']
    by_code = defaultdict(list)
    for metric in metrics.values():
        code = metric['payload'].get('item_code_raw')
        if code:
            by_code[(metric['payload'].get('statement_type'), code.strip())].append(metric)
    checks, hierarchy = [], []
    for metric in metrics.values():
        raw = metric['original_text'] or ''
        match = re.search(r'\((\d{2,3})\s*=\s*([0-9+\-()\s]+)\)', raw)
        if not match:
            continue
        terms = formula_terms(match.group(2))
        if not terms:
            continue
        children = []
        for sign, code in terms:
            candidates = by_code[(metric['payload'].get('statement_type'), code)]
            if len(candidates) != 1:
                children = []
                break
            children.append((sign or '+', candidates[0]))
        if not children:
            continue
        for _, child in children:
            hierarchy.append({'relationship_id': stable_id('hierarchy', metric['record_id'], child['record_id']),
                'parent_metric_id': metric['record_id'], 'child_metric_id': child['record_id'], 'basis': 'explicit_formula',
                'formula_raw': match.group(0), 'source_refs': metric['source_refs'], 'status': 'candidate'})
        for total in [r for r in measurements if r['payload']['metric_record_id'] == metric['record_id']]:
            operands = []
            for sign, child in children:
                candidates = [r for r in measurements if r['payload']['metric_record_id'] == child['record_id']
                              and compatible_check_period(total, r) and r['payload']['unit'] == total['payload']['unit']
                              and r['payload']['scale'] == total['payload']['scale']
                              and r['payload']['statement_scope'] == total['payload']['statement_scope']]
                if len(candidates) != 1 or candidates[0]['payload']['parsed_value'] is None:
                    operands = []
                    break
                operands.append((sign, candidates[0]))
            actual = total['payload']['parsed_value']
            expected = sum((Decimal(r['payload']['parsed_value']) * (-1 if sign == '-' else 1) for sign, r in operands), Decimal(0)) if operands else None
            difference = Decimal(actual) - expected if actual is not None and expected is not None else None
            tolerance = Decimal(len(operands) + 1) / 2
            checks.append({'check_id': stable_id('check', total['record_id'], match.group(0)),
                'total_record_id': total['record_id'], 'operand_record_ids': [r['record_id'] for _, r in operands],
                'formula_raw': match.group(0), 'difference': str(difference) if difference is not None else None,
                'rounding_tolerance_in_presentation_unit': str(tolerance),
                'status': 'not_checked' if difference is None or not total['content_period'] or not total['payload']['unit'] or not total['payload']['scale'] or not total['payload']['statement_scope'] else 'pass' if abs(difference) <= tolerance else 'mismatch',
                'pdf_page': next(iter(total['field_sources']['/payload/raw_value']))['pdf_page'],
                'source_refs': list(dict.fromkeys(total['source_refs'] + [a for _, r in operands for a in r['source_refs']])),
                'note': 'Arithmetic consistency only; no source value corrected or audit assurance implied.'})
    return checks, hierarchy


def compatible_check_period(total, operand):
    left, right = total['content_period'], operand['content_period']
    if not left or not right:
        return False
    fields = ('as_of_date', 'start_date', 'end_date', 'period_type')
    if any(left.get(k) for k in ('as_of_date', 'end_date')) and all(left.get(k) == right.get(k) for k in fields):
        return True
    # A cash-flow closing bridge explicitly adds annual movements to opening
    # cash. Preserve each component's correct instant/duration classification.
    if total['payload'].get('statement_type') == 'cash_flow' and relative_role(total['payload'].get('row_label_raw') or '') == 'current' and left.get('as_of_date'):
        ending = date.fromisoformat(left['as_of_date'])
        if right.get('period_type') == 'duration' and right.get('end_date') == ending.isoformat():
            return True
        if relative_role(operand['payload'].get('row_label_raw') or '') == 'opening_balance' and right.get('as_of_date'):
            # Only accept an observed calendar-year policy, not assumed fiscal year.
            return right['as_of_date'] == date(ending.year - 1, 12, 31).isoformat() and ending.month == 12 and ending.day == 31
    return False


def formula_terms(expression):
    """Parse only item-code additions/subtractions; never execute source text."""
    expression = re.sub(r'\b(\d{2,3})\b', r'c\1', expression)
    try:
        node = ast.parse(expression.strip(), mode='eval').body
        result = []

        def walk(item, sign=1):
            if isinstance(item, ast.Name) and re.fullmatch(r'c\d{2,3}', item.id):
                result.append(('+' if sign == 1 else '-', item.id[1:]))
            elif isinstance(item, ast.BinOp) and isinstance(item.op, (ast.Add, ast.Sub)):
                walk(item.left, sign)
                walk(item.right, sign * (-1 if isinstance(item.op, ast.Sub) else 1))
            else:
                raise ValueError('Unsupported formula')
        walk(node)
        return result
    except (SyntaxError, ValueError):
        return []


def semantic_coverage(bundle, output, contexts):
    blocks = {b['block_id']: b for b in bundle['source_blocks']}
    table_records = defaultdict(list)
    for r in output['records']:
        if r['record_type'] in ('metric', 'measurement'):
            table_records[r['payload'].get('table_anchor_id') or r['source_refs'][0]].append(r)
    tables = []
    for item in contexts:
        block = item['block']
        records = table_records[block['block_id']]
        ms = [r for r in records if r['record_type'] == 'measurement']
        mapped = sum(r['content_period'] is not None and r['payload']['unit'] is not None and r['payload']['row_label_raw'] is not None and r['payload']['parsed_value'] is not None for r in ms)
        used = {source['native_json_pointer'] for r in records for refs in r['field_sources'].values() for source in refs if source.get('native_json_pointer', '').startswith(block['source']['native_json_pointer'] + '/data/table_cells/')}
        unmapped = [{'cell_index': i, 'row': c['start_row_offset_idx'], 'column': c['start_col_offset_idx'], 'raw_text': c.get('text')}
                    for i, c in enumerate(block['original_cells'] or []) if not c.get('column_header')
                    and re.search(r'\d', c.get('text', '')) and block['source']['native_json_pointer'] + f'/data/table_cells/{i}' not in used]
        tables.append({'block_id': block['block_id'], 'pdf_page': block['source']['pdf_page'],
                       'statement_type': item['statement_type'], 'capture_status': 'retained_in_source',
                       'semantic_status': 'not_applicable' if item['statement_type'] == 'table_of_contents' else 'partial' if ms else 'needs_review',
                       'record_ids': [r['record_id'] for r in records], 'measurement_count': len(ms),
                       'mapped_measurement_count': mapped, 'unmapped_numeric_cells': unmapped,
                       'review_status': 'needs_review', 'source': block['source']})
    pages = []
    for p in bundle['coverage']['pages']:
        page_tables = [t for t in tables if t['pdf_page'] == p['pdf_page']]
        note_items = [n for n in output['notes_coverage'] if n['pdf_page'] == p['pdf_page']]
        pages.append({**p, 'capture_status': p['status'], 'semantic_status': 'failed' if p['status'] == 'failed' else 'partial' if page_tables or any(n.get('record_id') for n in note_items) else 'needs_review',
                      'table_ids': [t['block_id'] for t in page_tables], 'note_record_count': sum(bool(n.get('record_id')) for n in note_items)})
    return {'pages': pages, 'tables': tables, 'notes': output['notes_coverage'],
            'status': 'partial', 'definition': 'Mapped means label + value + period + unit candidates; not verified extraction or full table coverage.',
            'measurement_mapping_counts': {'total': sum(t['measurement_count'] for t in tables), 'mapped': sum(t['mapped_measurement_count'] for t in tables)}}


def esg_search(output, bundle):
    rules = {'environment': r'moi truong|environment', 'restoration_decommissioning': r'phuc hoi|thao do|hoan nguyen|decommission',
             'personnel': r'nhan cong|nhan vien|nguoi lao dong|personnel', 'commitments': r'cam ket|commitments?'}
    result = []
    for category, pattern in rules.items():
        matched = [r for r in output['records'] if re.search(pattern, normalized(r.get('original_text') or ''))]
        result.append({'category': category, 'status': 'candidate_disclosures_found' if matched else 'not_found_in_checked_scope',
                       'record_ids': [r['record_id'] for r in matched], 'capture_pages_checked': [p['pdf_page'] for p in bundle['coverage']['pages'] if p['status'] == 'processed'],
                       'search_method': 'keyword_scan_over_extracted_records', 'limitations': 'Not a claim of company absence; OCR gaps/unmapped source and semantic interpretation remain. Ordinary assets/costs are not classified as environmental.'})
    return result
