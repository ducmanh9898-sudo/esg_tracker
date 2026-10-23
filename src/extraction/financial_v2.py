"""Conservative financial table candidates from the immutable v2 source ledger.

No metric whitelist, no guessed years, no boundary verification, no OCR repair.
Qualitative notes remain pending; explicit continuations are reviewable rules.
"""
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import json
from pathlib import Path
import re
import unicodedata

from src.extraction.source_v2 import (
    atomic_json, file_hash, new_record, now, stable_id, sync_missing_fields,
    validate_source_bundle,
)
from src.extraction.financial_context_v2 import resolve_scope, title_context, continuation_decision
from src.extraction.financial_notes_v2 import extract_notes
from src.extraction.financial_semantics_v3 import table_class, augment
from src.extraction.financial_column_mapping import code_header, resolve_code_columns, split_amount_pair


def fold(text):
    text = unicodedata.normalize('NFD', text.lower().replace('đ', 'd'))
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


def parse_number(raw, number_format='auto'):
    """Return decimal string and status. Blank/dash are never converted to zero."""
    raw = raw.replace('\u2212', '-').replace('\u00a0', ' ').strip()
    if re.search(r'\d\s+\d', raw) and not re.fullmatch(r'\(?[+-]?\d{1,3}(?:\s\d{3})+(?:[.,]\d+)?\)?%?', raw):
        return None, 'ambiguous'
    text = re.sub(r'\s+', '', raw)
    if text in ('', '-', '–', '—'):
        return None, 'missing'
    text = text.removesuffix('%')
    negative = text.startswith('(') and text.endswith(')')
    if negative:
        text = text[1:-1]
        if text.startswith(('-', '+')):
            return None, 'ambiguous'
    if not re.fullmatch(r'[+-]?\d[\d.,]*', text):
        return None, 'ambiguous'
    if number_format == 'vi':
        if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?', text):
            return None, 'ambiguous'
        text = text.replace('.', '').replace(',', '.')
    elif number_format == 'en':
        if not re.fullmatch(r'[+-]?(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?', text):
            return None, 'ambiguous'
        text = text.replace(',', '')
    elif ',' in text and '.' in text:
        # Mixed separators need an explicit format; currency is not a locale.
        return None, 'ambiguous'
    elif ',' in text or '.' in text:
        separator = ',' if ',' in text else '.'
        if text.count(separator) > 1 and re.fullmatch(r'[+-]?\d{1,3}(?:[.,]\d{3})+', text):
            text = text.replace(separator, '')
        elif text.count(separator) == 1 and len(text.split(separator)[1]) != 3:
            text = text.replace(separator, '.')
        else:
            return None, 'ambiguous'
    try:
        value = Decimal(text)
        if negative:
            value = value.copy_negate()
        return format(value, 'f'), 'available'
    except InvalidOperation:
        return None, 'ambiguous'


def parse_period(header):
    """Only parse explicit header dates/years; never default to report year."""
    normalized = fold(header)
    dates = re.findall(r'\b(\d{1,2})[/.\-](\d{1,2})[/.\-]((?:19|20)\d{2})\b', normalized)
    years = set(re.findall(r'\b(?:19|20)\d{2}\b', normalized))
    if len(dates) == 1:
        day, month, year = map(int, dates[0])
        try:
            day_iso = date(year, month, day).isoformat()
        except ValueError:
            return None
        return {'raw_text': header, 'year': year, 'as_of_date': day_iso,
                'start_date': None, 'end_date': None, 'period_type': 'date_label'}
    if not dates and len(years) == 1 and not re.search(r'\bquy\b|quarter|\bthang\b|month', normalized):
        return {'raw_text': header, 'year': int(next(iter(years))), 'as_of_date': None,
                'start_date': None, 'end_date': None, 'period_type': 'year_label'}
    return None


def period_role(header):
    text = fold(header)
    if re.search(r'cuoi nam|cuoi ky|closing|current', text):
        return 'current'
    if re.search(r'dau nam|dau ky|opening', text):
        return 'opening_balance'
    if re.search(r'nam truoc|comparative|previous', text):
        return 'comparative'
    if re.search(r'nam nay|trong nam|current year', text):
        return 'current_flow'
    return None


def _cell_source(block, index, cell):
    native = cell.get('_native_cell', cell)
    source = {**block['source'], 'native_json_pointer': block['source']['native_json_pointer'] + f'/data/table_cells/{index}',
            'row_index': cell['start_row_offset_idx'], 'column_index': cell['start_col_offset_idx'],
            'bbox': native.get('bbox'), 'raw_text': native.get('text', '')}
    if '_text_span' in cell:
        source.update(text_span=cell['_text_span'], mapping_basis=cell['_mapping_basis'],
                      native_column_index=native['start_col_offset_idx'])
    return source


def _preceding_texts(block, bundle, work):
    """Read table context by native body order, not texts/tables array order."""
    artifact = next(a for a in bundle['source_artifacts'] if a['artifact_id'] == block['source']['artifact_id'])
    native = json.loads((work / artifact['path']).read_text(encoding='utf-8'))['document']
    table_ref = '#' + block['source']['native_json_pointer'].removeprefix('/document')
    order = []
    visited = set()
    def visit(ref):
        if ref in visited:
            return
        visited.add(ref)
        try:
            item = native
            for token in ref.removeprefix('#/').split('/'):
                item = item[int(token)] if isinstance(item, list) else item[token]
        except (KeyError, IndexError, ValueError, TypeError):
            return
        order.append(ref)
        for child in item.get('children', []):
            visit(child.get('$ref', ''))
    for child in native.get('body', {}).get('children', []):
        visit(child.get('$ref', ''))
    if table_ref not in order:
        return []
    position = order.index(table_ref)
    # Never inherit across another table without a verified continuation.
    start = max((i + 1 for i, ref in enumerate(order[:position]) if ref.startswith('#/tables/')), default=0)
    refs = {ref: index for index, ref in enumerate(order[start:position])}
    found = [b for b in bundle['source_blocks'] if b['source']['artifact_id'] == block['source']['artifact_id']
             and b['kind'] == 'texts' and '#' + b['source']['native_json_pointer'].removeprefix('/document') in refs]
    return sorted(found, key=lambda b: refs['#' + b['source']['native_json_pointer'].removeprefix('/document')])


def unit_context(context, headers):
    candidates = []
    for raw, source in headers + context:
        text = fold(raw)
        if (raw, source) in context and not re.match(r'^\s*(?:(?:don vi(?: tinh)?|unit)\s*[:：]?\s*)?(?:(?:nghin|ngan|trieu|ty|thousand|million|billion)\s*)?(?:vnd|usd|eur|dong)\s*[.)]?\s*$', text) and not re.match(r'^\s*(?:nam nay|so cuoi nam)\s+(?:don vi(?: tinh)?|unit)\s*[:：]\s*(?:vnd|usd|eur)\s*$', text):
            continue
        currencies = set(re.findall(r'\b(VND|USD|EUR)\b', raw.upper()))
        if re.search(r'\bdong\b', text):
            currencies.add('VND')
        if not currencies:
            continue
        scales = [(word, value) for word, value in [('nghin', '1000'), ('ngan', '1000'), ('trieu', '1000000'), ('ty', '1000000000'),
                                                   ('thousand', '1000'), ('million', '1000000'), ('billion', '1000000000')]
                  if re.search(r'\b' + word + r'\b', text)]
        # Currency alone means base currency only for a short unit label.
        if len(currencies) == 1 and len({v for _, v in scales}) <= 1 and len(raw) < 100:
            candidates.append((next(iter(currencies)), scales[0][1] if scales else '1', source))
    unique = {(currency, scale) for currency, scale, _ in candidates}
    if len(unique) == 1:
        currency, scale = next(iter(unique))
        return currency, scale, [src for _, _, src in candidates]
    return None, None, []


def normalized_decimal(value, scale):
    with localcontext() as ctx:
        ctx.prec = max(64, len(value) + len(scale) + 4)
        return format(Decimal(value) * Decimal(scale), 'f')


def extract_table(block, context, inventory, number_format='auto', inherited_headers=None, scope=None):
    if table_class(block, context) == 'table_of_contents':
        return [], [], [{'issue_id': stable_id('issue', block['block_id'], 'contents'),
            'record_id': None, 'field': '/source_blocks', 'code': 'CONTENTS_TABLE_EXCLUDED',
            'severity': 'info', 'pdf_page': block['source']['pdf_page'], 'source_refs': [block['block_id']],
            'status': 'resolved', 'details': 'Page-reference column is navigation, not financial measurements. Original source table retained.'}]
    cells = block['original_cells'] or []
    indexed = list(enumerate(cells))
    headers = [(i, c) for i, c in indexed if c.get('column_header')]
    inherited = {-(i + 1): item for i, item in enumerate(inherited_headers or [])}
    if not headers:
        headers = [(index, item['cell']) for index, item in inherited.items()]
    def header_source(index, cell):
        return inherited[index]['source'] if index < 0 else _cell_source(block, index, cell)
    rows = defaultdict(list)
    for i, cell in indexed:
        if not cell.get('column_header'):
            rows[cell['start_row_offset_idx']].append((i, cell))
    header_columns = defaultdict(list)
    excluded = set()
    code_columns = set()
    label_column = None
    for i, cell in headers:
        text = fold(cell.get('text', ''))
        for col in range(cell['start_col_offset_idx'], cell['end_col_offset_idx']):
            header_columns[col].append((i, cell))
            if re.search(r'^ma\s+s\b|ma s[oő]|\bcode\b|thuyet|minh|notes?|\bstt\b', text):
                excluded.add(col)
            if re.search(r'^ma\s+s\b|ma s[oő]|\bcode\b', text):
                code_columns.add(col)
            if re.fullmatch(r'\s*(?:chi tieu|tai san|nguon von|items?|description)\s*', text):
                label_column = col
    if label_column is None:
        text_columns = defaultdict(int)
        for _, cell in indexed:
            if not cell.get('column_header') and re.search(r'[^\W\d_]', cell.get('text', ''), re.UNICODE):
                text_columns[cell['start_col_offset_idx']] += 1
        if text_columns:
            label_column = max(text_columns, key=text_columns.get)
    code_columns = resolve_code_columns(headers, indexed, label_column)
    excluded.update(code_columns)
    # Ambiguous metadata columns must not become financial amounts merely
    # because the code header's grid index is wrong or mapping abstained.
    value_header_cols = [col for col, pairs in header_columns.items()
                         if any(period_role(c.get('text', '')) or parse_period(c.get('text', '')) for _, c in pairs)]
    if label_column is not None and value_header_cols and any(code_header(c.get('text', '')) for _, c in headers):
        excluded.update(range(label_column + 1, min(value_header_cols)))
    records, links, issues = [], [], []
    def issue(record, field, code, reason):
        record['field_status'][field] = {'status': 'unknown', 'reason': reason}
        issues.append({'issue_id': stable_id('issue', record['record_id'], field, code),
                       'record_id': record['record_id'], 'field': field, 'code': code,
                       'pdf_page': block['source']['pdf_page'], 'status': 'open', 'details': reason})
    row_group = None
    for row_index, row in sorted(rows.items()):
        row.sort(key=lambda pair: pair[1]['start_col_offset_idx'])
        label_pair = next(((i, c) for i, c in row if c['start_col_offset_idx'] == label_column), None)
        label = label_pair[1].get('text', '') if label_pair else None
        candidates = [(i, c) for i, c in row if c['start_col_offset_idx'] not in excluded
                      and (label_column is None or c['start_col_offset_idx'] > label_column)
                      and (re.search(r'\d', c.get('text', '')) or c.get('text', '').strip() in ('', '-', '–', '—'))]
        candidates = [pair for i, c in candidates for pair in split_amount_pair(i, c, row, headers)]
        if not candidates:
            if label and label.isupper() and re.search(r'[^\W\d_]', label, re.UNICODE):
                row_group = label_pair
            continue
        metric = new_record(inventory['report_version_id'], block['block_id'], 'metric', f'row:{row_index}')
        metric.update({'company_id': inventory['company_id'], 'domain': 'financial', 'original_text': label,
                       'original_cells': [c for _, c in row],
                       'payload': {'original_name': label, 'code_candidates': [], 'definition': None, 'methodology': None,
                                   'item_code_raw': next((c.get('text') for _, c in row if c['start_col_offset_idx'] in code_columns), None)},
                       'field_sources': {'/payload/original_name': [_cell_source(block, *label_pair)] if label_pair else []},
                       'data_status': 'available' if label else 'unknown'})
        code_pair = next(((i, c) for i, c in row if c['start_col_offset_idx'] in code_columns), None)
        metric['payload']['row_group_raw'] = row_group[1].get('text') if row_group else None
        if row_group:
            metric['field_sources']['/payload/row_group_raw'] = [_cell_source(block, *row_group)]
        if code_pair:
            metric['field_sources']['/payload/item_code_raw'] = [_cell_source(block, *code_pair)] + [
                header_source(i, c) for i, c in headers if code_header(c.get('text', ''))]
        metric['field_status']['/payload/item_code_raw'] = {
            'status': 'available' if code_pair and re.fullmatch(r'\d{2,3}', code_pair[1].get('text', '').strip()) else 'ambiguous' if code_pair else 'unknown',
            'reason': 'Observed row cell under explicit code header; physical header alignment used when grid is misindexed. Raw OCR not repaired.'}
        metric['field_status']['/company_id']['status'] = 'available' if inventory['company_id'] else 'unknown'
        if not label:
            issue(metric, '/payload/original_name', 'ROW_LABEL_UNKNOWN', 'No unambiguous row label detected.')
        for field in ('definition', 'methodology'):
            metric['field_status']['/payload/' + field] = {'status': 'unknown', 'reason': 'Not extracted from financial notes yet.'}
        sync_missing_fields(metric)
        metric['review']['status'] = 'needs_review'
        records.append(metric)
        expected_columns = {col for col in header_columns if col not in excluded and label_column is not None and col > label_column}
        observed_columns = {c['start_col_offset_idx'] for _, c in row} | {c['start_col_offset_idx'] for _, c in candidates}
        for absent in sorted(expected_columns - observed_columns):
            issues.append({'issue_id': stable_id('issue', metric['record_id'], absent, 'absent_cell'),
                           'record_id': metric['record_id'], 'field': '/original_cells', 'code': 'VALUE_CELL_NOT_DETECTED',
                           'pdf_page': block['source']['pdf_page'], 'status': 'open',
                           'details': f'No detected source cell in column {absent}; no value or zero synthesized.'})
        for cell_index, cell in candidates:
            col = cell['start_col_offset_idx']
            matching_headers = sorted(header_columns[col], key=lambda pair: pair[1]['start_row_offset_idx'])
            # Repeated headers inside a table define a new band, not additional
            # tiers of every previous row's column header.
            preceding = [(i, c) for i, c in matching_headers if i < 0 or c['start_row_offset_idx'] < row_index]
            bands = []
            for pair in preceding:
                if not bands or pair[1]['start_row_offset_idx'] > bands[-1][-1][1]['end_row_offset_idx']:
                    bands.append([])
                bands[-1].append(pair)
            matching_headers = bands[-1] if bands else []
            header_texts = [c.get('text', '') for _, c in matching_headers]
            header_display = ' | '.join(header_texts)
            context_sources = [(b['original_text'] or '', b['source']) for b in context]
            context_sources += [(c.get('text', ''), header_source(i, c)) for i, c in headers
                                if re.search(r'(?:don vi(?: tinh)?|unit)\s*[:：]', fold(c.get('text', '')))]
            header_sources = [(c.get('text', ''), header_source(i, c)) for i, c in matching_headers]
            currency, scale, unit_sources = unit_context(context_sources, header_sources)
            raw = cell.get('text', '')
            value, status = parse_number(raw, number_format)
            period = parse_period(header_display)
            percentage = raw.strip().endswith('%') or any('%' in text for text in header_texts)
            slot = f'cell:{cell_index}' + (f":span:{cell['_text_span'][0]}:{cell['_text_span'][1]}" if '_text_span' in cell else '')
            record = new_record(inventory['report_version_id'], block['block_id'], 'measurement', slot)
            record.update({'company_id': inventory['company_id'], 'domain': 'financial', 'original_text': raw,
                           'original_cells': [c for _, c in matching_headers] + ([label_pair[1]] if label_pair else []) + [cell.get('_native_cell', cell)],
                           'content_period': period,
                           'field_sources': {'/payload/raw_value': [_cell_source(block, cell_index, cell)],
                                             '/content_period': [src for _, src in header_sources],
                                             '/payload/unit': unit_sources if not percentage else [_cell_source(block, cell_index, cell)] + [src for _, src in header_sources]},
                           'payload': {'metric_record_id': metric['record_id'], 'row_label_raw': label,
                                       'column_headers_raw': header_texts, 'raw_value': raw, 'parsed_value': value,
                                       'unit': '%' if percentage else currency, 'currency': None if percentage else currency,
                                       'scale': '1' if percentage else scale,
                                       'unit_source_labels_raw': [raw_label for raw_label, src in context_sources + header_sources if src in unit_sources],
                                       'normalized_value': normalized_decimal(value, scale) if value is not None and scale and not percentage else None,
                                       'period_role': period_role(header_display), 'statement_scope': None,
                                       'item_code_raw': metric['payload']['item_code_raw'],
                                       'row_index': row_index, 'column_index': col, 'table_anchor_id': block['block_id'],
                                       'number_format': number_format}, 'data_status': status})
            if code_pair:
                record['field_sources']['/payload/item_code_raw'] = metric['field_sources']['/payload/item_code_raw']
            record['field_status']['/payload/item_code_raw'] = dict(metric['field_status']['/payload/item_code_raw'])
            if '_text_span' in cell:
                record['interpretation_notes'].append('Rule-mapped two observed amount tokens to explicit period columns; full native cell and substring span retained. Needs review.')
            record['field_status']['/company_id']['status'] = 'available' if inventory['company_id'] else 'unknown'
            record['field_status']['/content_period']['status'] = 'available' if period else 'unknown'
            for field in ('parsed_value', 'unit', 'scale', 'statement_scope', 'period_role'):
                if record['payload'][field] is None:
                    issue(record, '/payload/' + field, field.upper() + '_UNKNOWN', 'Not unambiguously established from source context.')
            if period is None:
                issue(record, '/content_period', 'PERIOD_UNKNOWN', 'Header has no unambiguous explicit year/date; report year not substituted.')
            if not matching_headers:
                issue(record, '/payload/column_headers_raw', 'COLUMN_ROLE_UNCONFIRMED', 'Numeric cell retained as a candidate; no value-column header found.')
            # Ambiguous numeric values remain ambiguous rather than simply unknown.
            if value is None:
                record['field_status']['/payload/parsed_value']['status'] = status
            if cell.get('col_span', 1) > 1 or cell.get('row_span', 1) > 1 or cell['end_col_offset_idx'] - col > 1 or cell['end_row_offset_idx'] - row_index > 1:
                record['data_status'] = 'ambiguous'
                issue(record, '/payload/parsed_value', 'MERGED_VALUE_CELL', 'Value spans multiple rows/columns; mapping requires review.')
                record['payload']['parsed_value'] = None
                record['payload']['normalized_value'] = None
                record['field_status']['/payload/parsed_value']['status'] = 'ambiguous'
            sync_missing_fields(record)
            record['review']['status'] = 'needs_review'
            records.append(record)
            links.append({'link_id': stable_id('link', metric['record_id'], record['record_id']),
                          'from_id': metric['record_id'], 'to_id': record['record_id'],
                          'relation_type': 'metric_measurement', 'status': 'candidate'})
    if scope:
        for record in records:
            record['payload']['statement_scope'] = scope['value']
            record['field_sources']['/payload/statement_scope'] = scope['sources']
            record['source_refs'] = list(dict.fromkeys(record['source_refs'] + scope['anchor_ids']))
            record['field_status']['/payload/statement_scope'] = {
                'status': scope['status'], 'reason': 'Explicit financial statement label; not KPI legal-entity boundary.',
                'basis': scope['basis']}
            sync_missing_fields(record)
        if scope['value']:
            issues = [i for i in issues if i['code'] != 'STATEMENT_SCOPE_UNKNOWN']
        elif scope['status'] == 'ambiguous':
            for issue_item in issues:
                if issue_item['code'] == 'STATEMENT_SCOPE_UNKNOWN':
                    issue_item.update({'code': 'STATEMENT_SCOPE_CONFLICT', 'details': 'Conflicting explicit statement scope labels; no scope selected.'})
    return records, links, issues


def _table_contexts(bundle, work):
    tables = sorted([b for b in bundle['source_blocks'] if b['kind'] == 'tables'], key=lambda b: b['source']['pdf_page'])
    page_tables = defaultdict(list)
    for block in tables:
        page_tables[block['source']['pdf_page']].append(block['block_id'])
    page_statuses = {p['pdf_page']: p['status'] for p in bundle['coverage']['pages']}
    result, decisions, issues = [], [], []
    for block in tables:
        context = _preceding_texts(block, bundle, work)
        current = {'block': block, 'context': context, 'title': title_context(context),
                   'scope': resolve_scope(block, bundle),
                   'headers': [{'cell': cell, 'source': _cell_source(block, i, cell)}
                               for i, cell in enumerate(block['original_cells'] or []) if cell.get('column_header')],
                   'inherited_headers': [], 'logical_table_id': stable_id('logical_table', block['block_id'])}
        current['statement_type'] = table_class(block, context)
        if result:
            previous = result[-1]
            decision = continuation_decision(previous, current, page_statuses,
                page_tables[block['source']['pdf_page']][0] == block['block_id'],
                page_tables[previous['block']['source']['pdf_page']][-1] == previous['block']['block_id'], unit_context)
            if decision:
                decisions.append(decision)
                if decision['status'] == 'rule_matched':
                    current['logical_table_id'] = previous['logical_table_id']
                    if not current['headers']:
                        current['inherited_headers'] = previous['headers']
                        current['headers'] = previous['headers']
                    current['context'] = previous['context'] + current['context']
                    if current['scope']['status'] == 'unknown' and previous['scope']['value']:
                        current['scope'] = {**previous['scope'], 'basis': 'logical_table_continuation'}
                else:
                    issues.append({'issue_id': stable_id('issue', decision['continuation_id']),
                                   'record_id': None, 'field': '/table_continuations', 'code': 'TABLE_CONTINUATION_UNCONFIRMED',
                                   'pdf_page': block['source']['pdf_page'], 'status': 'open', 'details': decision['reasons']})
        result.append(current)
    return result, decisions, issues


def extract_financial(work, *, number_format='auto'):
    if number_format not in ('auto', 'vi', 'en'):
        raise ValueError('Number format must be auto, vi or en.')
    work = Path(work).resolve()
    bundle = json.loads((work / 'canonical.json').read_text(encoding='utf-8'))
    errors = validate_source_bundle(bundle, work)
    if errors:
        raise ValueError('Invalid source capture: ' + '; '.join(errors))
    inventory = bundle['reports'][0]
    if inventory.get('report_type') != 'financial_statements':
        raise ValueError('Financial parser requires report_type=financial_statements. ESG is a separate branch.')
    contexts, continuations, issues = _table_contexts(bundle, work)
    records, links = [], []
    table_count = 0
    for item in contexts:
        block = item['block']
        table_count += 1
        result, linked, flagged = extract_table(block, item['context'], inventory, number_format,
                                               inherited_headers=item['inherited_headers'], scope=item['scope'])
        for record in result:
            record['payload']['logical_table_id'] = item['logical_table_id']
        records.extend(result)
        links.extend(linked)
        issues.extend(flagged)
        if not result and item['statement_type'] != 'table_of_contents':
            issues.append({'issue_id': stable_id('issue', block['block_id'], 'unparsed_table'),
                           'record_id': None, 'field': '/source_blocks', 'code': 'TABLE_NOT_PARSED',
                           'pdf_page': block['source']['pdf_page'], 'status': 'open',
                           'details': 'Table retained in source capture; no candidate rows mapped.'})
    if not table_count:
        issues.append({'issue_id': stable_id('issue', inventory['report_version_id'], 'no_tables'),
                       'record_id': None, 'field': '/source_blocks', 'code': 'NO_TABLES_DETECTED',
                       'pdf_page': None, 'status': 'open', 'details': 'No detected tables; not evidence of absent financial disclosure.'})
    note_records, note_issues, notes_coverage = extract_notes(bundle, work)
    records.extend(note_records)
    issues.extend(note_issues)
    output = {'schema_version': 'esg-financial-candidates/2.3.0', 'parser_version': 7,
              'source_capture_sha256': file_hash(work / 'canonical.json'),
              'created_at': now(), 'number_format': number_format, 'graph_ready': False,
              'semantic_status': 'partial', 'source_capture_coverage': bundle['coverage'],
              'reports': bundle['reports'], 'source_artifacts': bundle['source_artifacts'],
              'source_blocks': bundle['source_blocks'], 'records': records, 'links': links,
              'table_continuations': continuations,
              'notes_coverage': notes_coverage,
              'issues': bundle['issues'] + issues,
              'counts': {'metrics': sum(r['record_type'] == 'metric' for r in records),
                         'measurements': sum(r['record_type'] == 'measurement' for r in records),
                         'tables_seen': table_count, 'financial_contexts': len(note_records)},
              'pending': ['narrative_field_interpretation', 'unconfirmed_continuations_and_scope', 'unmapped_cells_and_ocr_review', 'graph_adapter']}
    augment(output, bundle, contexts, work)
    validation_errors = validate_financial(output, work)
    from jsonschema import Draft202012Validator
    schema = json.loads((Path(__file__).resolve().parents[2] / 'contracts/financial_v2.schema.json').read_text(encoding='utf-8'))
    validation_errors.extend(e.message for e in Draft202012Validator(schema).iter_errors(output))
    output['validation'] = {'valid': not validation_errors, 'errors': validation_errors, 'scope': 'structure_and_references_not_factual_accuracy'}
    destination = work / ('f7_' + stable_id('parser', 7, number_format).split('_', 1)[1][:12])
    atomic_json(destination / 'r.json', output)
    if validation_errors:
        raise ValueError('Financial candidate validation failed: ' + '; '.join(validation_errors))
    return destination / 'r.json'


def validate_financial(output, work=None):
    errors = []
    records = output['records']
    ids = {r['record_id'] for r in records}
    if len(ids) != len(records):
        errors.append('Duplicate record IDs.')
    anchors = {b['block_id'] for b in output['source_blocks']}
    artifacts = {a['artifact_id']: a for a in output['source_artifacts']}
    documents = {}
    for record in records:
        if not set(record['source_refs']) <= anchors:
            errors.append('Unknown source anchor.')
        if record['review']['status'] == 'verified':
            errors.append('Automatic extraction must not mark records verified.')
        before = list(record['missing_fields'])
        boundary_before = list(record['boundary']['missing_fields'])
        sync_missing_fields(record)
        if before != record['missing_fields'] or boundary_before != record['boundary']['missing_fields']:
            errors.append('Missing fields out of sync.')
        if record['record_type'] == 'measurement' and record['payload']['metric_record_id'] not in ids:
            errors.append('Unknown metric reference.')
        if record['record_type'] == 'measurement':
            payload = record['payload']
            period = record['content_period']
            if period and period.get('start_date') and period.get('end_date') and period['start_date'] > period['end_date']:
                errors.append('Period start exceeds end.')
            if period and not record['field_sources'].get('/content_period'):
                errors.append('Period has no source evidence.')
            if payload.get('unit') and not record['field_sources'].get('/payload/unit'):
                errors.append('Unit has no source evidence.')
            if payload['parsed_value'] is None and payload['normalized_value'] is not None:
                errors.append('Normalized value exists without parsed value.')
        if record['payload'].get('statement_scope') and not record.get('field_sources', {}).get('/payload/statement_scope'):
            errors.append('Statement scope has no source evidence.')
        if work is not None:
            for field, sources in record.get('field_sources', {}).items():
                for source in sources:
                    try:
                        artifact_id = source['artifact_id']
                        if artifact_id not in documents:
                            documents[artifact_id] = json.loads((work / artifacts[artifact_id]['path']).read_text(encoding='utf-8'))
                        if source.get('artifact_sha256') != artifacts[artifact_id]['sha256']:
                            errors.append('Field source artifact hash mismatch.')
                        target = documents[artifact_id]
                        for token in source['native_json_pointer'].lstrip('/').split('/'):
                            target = target[int(token)] if isinstance(target, list) else target[token]
                        if 'raw_text' in source and source['raw_text'] != target.get('text'):
                            errors.append('Field source raw text mismatch.')
                        if field == '/payload/raw_value':
                            raw = target.get('text', '')
                            span = source.get('text_span')
                            if span is not None:
                                if (not isinstance(span, list) or len(span) != 2
                                    or any(type(n) is not int for n in span)
                                    or not 0 <= span[0] < span[1] <= len(raw)):
                                    errors.append('Invalid measurement source substring span.')
                                    continue
                                raw = raw[span[0]:span[1]]
                            if record['payload']['raw_value'] != raw:
                                errors.append('Measurement raw value differs from source cell or selected substring.')
                        if field == '/payload/statement' and record['original_text'] != target.get('text'):
                            errors.append('Narrative original text differs from source paragraph.')
                        if field in ('/payload/statement', '/payload/notes_title_raw', '/payload/section_heading_raw') and record['payload'][field.rsplit('/', 1)[-1]] != target.get('text'):
                            errors.append('Narrative payload differs from source text.')
                    except (KeyError, IndexError, ValueError, TypeError):
                        errors.append('Unresolved field source pointer.')
    for link in output['links']:
        if link['from_id'] not in ids or link['to_id'] not in ids:
            errors.append('Unresolved link.')
    tables = {b['block_id']: b for b in output['source_blocks'] if b['kind'] == 'tables'}
    continuation_ids = set()
    page_statuses = {p['pdf_page']: p['status'] for p in output['source_capture_coverage']['pages']}
    for item in output.get('table_continuations', []):
        if item['continuation_id'] in continuation_ids:
            errors.append('Duplicate continuation ID.')
        continuation_ids.add(item['continuation_id'])
        left, right = tables.get(item['from_table_anchor']), tables.get(item['to_table_anchor'])
        if not left or not right:
            errors.append('Unresolved table continuation anchor.')
        elif item['status'] == 'rule_matched':
            before, after = left['source']['pdf_page'], right['source']['pdf_page']
            if after != before + 1 or any(page_statuses.get(p) != 'processed' for p in (before, after)) or item['reasons']:
                errors.append('Invalid accepted continuation coverage.')
    text_anchors = {b['block_id'] for b in output['source_blocks'] if b['kind'] == 'texts'}
    note_coverage = output.get('notes_coverage', [])
    if len({item['block_id'] for item in note_coverage}) != len(note_coverage):
        errors.append('Duplicate note coverage entry.')
    if {item['block_id'] for item in note_coverage} != text_anchors:
        errors.append('Not all text blocks have a note disposition.')
    if any(item.get('record_id') and item['record_id'] not in ids for item in note_coverage):
        errors.append('Unresolved note coverage record.')
    for name, field in output.get('metadata', {}).items():
        if not isinstance(field, dict) or 'status' not in field:
            continue
        if field.get('value') is not None and not field.get('sources'):
            errors.append('Metadata value has no source evidence: ' + name)
        for source in field.get('sources', []):
            if source.get('artifact_id') not in artifacts:
                errors.append('Unknown metadata source artifact.')
                continue
            if source.get('artifact_sha256') != artifacts[source['artifact_id']]['sha256']:
                errors.append('Metadata source hash mismatch.')
            if work is not None:
                try:
                    artifact_id = source['artifact_id']
                    if artifact_id not in documents:
                        documents[artifact_id] = json.loads((work / artifacts[artifact_id]['path']).read_text(encoding='utf-8'))
                    target = documents[artifact_id]
                    for token in source['native_json_pointer'].lstrip('/').split('/'):
                        target = target[int(token)] if isinstance(target, list) else target[token]
                    if 'raw_text' in source and source['raw_text'] != target.get('text'):
                        errors.append('Metadata source raw text mismatch.')
                except (KeyError, IndexError, ValueError, TypeError):
                    errors.append('Unresolved metadata source pointer.')
    for check in output.get('arithmetic_checks', []):
        if check['total_record_id'] not in ids or not set(check['operand_record_ids']) <= ids:
            errors.append('Unresolved arithmetic check reference.')
    for edge in output.get('hierarchy_relationships', []):
        if edge['parent_metric_id'] not in ids or edge['child_metric_id'] not in ids:
            errors.append('Unresolved hierarchy reference.')
    return errors
