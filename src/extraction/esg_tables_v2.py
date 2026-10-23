"""Source-bound ESG table candidates; never a finding or verified boundary."""
from collections import defaultdict
import re

from src.extraction.financial_context_v2 import normalized
from src.extraction.financial_v2 import _cell_source, _preceding_texts, parse_number, parse_period
from src.extraction.source_v2 import new_record, stable_id, sync_missing_fields


def metric_candidates(text, metrics):
    folded = normalized(text)
    return [code for code, spec in metrics.items()
            if any(re.search(r'(?<!\w)' + re.escape(normalized(alias)) + r'(?!\w)', folded)
                   for alias in spec.get('variants', []))]


def explicit_unit(raw):
    """Accept a complete unit label, not a substring of an intensity unit."""
    value = re.sub(r'^(?:đơn vị(?: tính)?|unit)\s*[:：]?\s*', '', raw.strip(), flags=re.I)
    value = value.strip('() ')
    if re.fullmatch(r'(?:%|tCO2e|kgCO2e|GJ|MWh|kWh|m[³3]|tấn|tons?|kg|người|people|giờ|hours?|lần|VND|USD|EUR|đồng|(?:triệu|tỷ|nghìn|ngàn|million|billion|thousand)\s+(?:đồng|VND|USD|EUR))(?:\s*/\s*[^\n]+)?', value, re.I):
        return value
    return None


def extract_esg_table(block, bundle, work, config, metrics, number_format):
    cells = block['original_cells'] or []
    indexed = list(enumerate(cells))
    headers = [(i, c) for i, c in indexed if c.get('column_header')]
    if not headers:
        return [], [], []
    columns = defaultdict(list)
    for i, cell in headers:
        for col in range(cell['start_col_offset_idx'], cell['end_col_offset_idx']):
            columns[col].append((i, cell))
    unit_cols = {col for col, items in columns.items()
                 if any(re.fullmatch(r'don vi(?: tinh)?|dvt|unit', normalized(c.get('text', ''))) for _, c in items)}
    excluded = unit_cols | {col for col, items in columns.items()
                            if any(re.fullmatch(r'stt|nhom|group|ma so|code|gri|ghi chu|notes?', normalized(c.get('text', ''))) for _, c in items)}
    label_cols = [col for col, items in columns.items()
                  if any(re.search(r'chi tieu|chi so|noi dung|indicator|description|metric', normalized(c.get('text', ''))) for _, c in items)]
    usable = sorted(col for col in columns if col not in excluded)
    if not usable:
        return [], [], []
    label_col = min(label_cols) if label_cols else usable[0]
    data_cols = sorted(col for col in columns if col > label_col and col not in excluded)
    rows = defaultdict(list)
    for i, c in indexed:
        if not c.get('column_header'):
            rows[c['start_row_offset_idx']].append((i, c))
    context = _preceding_texts(block, bundle, work)
    # Only a standalone unit label before this table, never across pages/tables.
    context_units = [(explicit_unit(b['original_text'] or ''), b['source']) for b in context]
    context_units = [(u, s) for u, s in context_units if u]
    report = bundle['reports'][0]
    records, evidence, issues = [], [], []

    def make(kind, slot, raw, selected):
        record = new_record(report['report_version_id'], block['block_id'], kind, slot)
        record.update(company_id=report['company_id'], domain='esg', original_text=raw,
                      original_cells=[c for _, c in selected],
                      classification={'pillar': 'unknown', 'topic_candidates': [],
                                      'codebook_version': config['version'], 'status': 'candidate'},
                      field_sources={'/original_text': [_cell_source(block, selected[0][0], selected[0][1])]},
                      payload={'statement': raw, 'section_heading_raw': None,
                               'classification_method': 'explicit_table_cells', 'assertion_status': 'unverified'})
        record['review']['status'] = 'needs_review'
        record['field_status']['/company_id']['status'] = 'available' if report['company_id'] else 'unknown'
        return record

    def field(record, name, value, sources, reason='Explicit source cells only; no inferred defaults.'):
        record['payload'][name] = value
        pointer = '/payload/' + name
        record['field_sources'][pointer] = sources
        record['field_status'][pointer] = {'status': 'available' if value is not None else 'unknown', 'reason': reason}

    def classify(record, labels, row):
        groups = [(i, c) for i, c in indexed if c['start_col_offset_idx'] < label_col
                  and c['start_row_offset_idx'] <= row < c['end_row_offset_idx'] and not c.get('column_header')]
        raw = ' '.join(c.get('text', '') for _, c in labels + groups)
        topics = [{'topic_id': code, 'pillar': rule['pillar'], 'status': 'candidate',
                   'source_refs': record['source_refs']} for code, rule in config['topics'].items()
                  if re.search(rule['pattern'], normalized(raw))]
        pillars = {t['pillar'] for t in topics}
        record['classification'].update(pillar=next(iter(pillars)) if len(pillars) == 1 else 'unknown', topic_candidates=topics)
        record['field_sources']['/classification'] = [_cell_source(block, i, c) for i, c in labels + groups]

    for row, items in sorted(rows.items()):
        labels = [(i, c) for i, c in items if c['start_col_offset_idx'] == label_col]
        if len(labels) != 1 or not labels[0][1].get('text', '').strip():
            continue
        label = labels[0][1]['text']
        values = [(i, c) for i, c in items if c['start_col_offset_idx'] in data_cols
                  and (re.search(r'\d', c.get('text', '')) or c.get('text', '').strip() in ('', '-', '–', '—'))]
        if not values:
            continue
        metric = make('metric', f'row:{row}', label, labels)
        classify(metric, labels, row)
        metric['data_status'] = 'available'
        field(metric, 'name_raw', label, metric['field_sources']['/original_text'])
        metric['payload']['metric_code_candidates'] = metric_candidates(label, metrics)
        sync_missing_fields(metric)
        records.append(metric)
        row_units = [(explicit_unit(c.get('text', '')), _cell_source(block, i, c))
                     for i, c in items if c['start_col_offset_idx'] in unit_cols]
        for i, cell in values:
            col = cell['start_col_offset_idx']
            hs = sorted(columns[col], key=lambda item: item[1]['start_row_offset_idx'])
            header_raw = '\n'.join(c.get('text', '') for _, c in hs)
            header_sources = [_cell_source(block, j, c) for j, c in hs]
            raw = cell.get('text', '')
            rec = make('measurement', f'cell:{i}', raw, [(i, cell)])
            classify(rec, labels, row)
            rec['original_cells'] = [c for _, c in labels + hs + [(j, c) for j, c in items if c['start_col_offset_idx'] in unit_cols] + [(i, cell)]]
            rec['payload']['metric_id'] = metric['record_id']
            rec['payload']['metric_code_candidates'] = metric['payload']['metric_code_candidates']
            overlap = any(j != i and c['start_col_offset_idx'] < cell['end_col_offset_idx']
                          and c['end_col_offset_idx'] > col for j, c in items)
            merged = overlap or cell['end_col_offset_idx'] - col != 1 or cell['end_row_offset_idx'] - row != 1
            value, status = (None, 'ambiguous') if merged else parse_number(raw, number_format)
            field(rec, 'value', value, rec['field_sources']['/original_text'])
            rec['field_status']['/payload/value']['status'] = status
            rec['data_status'] = status
            field(rec, 'value_raw', raw, rec['field_sources']['/original_text'])
            field(rec, 'header_raw', header_raw, header_sources)
            header_key = normalized(header_raw)
            planned = bool(re.search(r'ke hoach|muc tieu|du kien|target|planned|budget', header_key))
            actual = bool(re.search(r'thuc hien|thuc te|actual|reported', header_key))
            field(rec, 'assertion_kind', 'unknown' if planned and actual else 'target' if planned else 'reported_result', header_sources)
            conflicting_years = len(set(re.findall(r'\b(?:19|20)\d{2}\b', header_raw))) > 1
            rec['content_period'] = None if merged or conflicting_years else parse_period(header_raw)
            rec['field_status']['/content_period'] = {'status': 'available' if rec['content_period'] else 'unknown',
                                                     'reason': 'Only explicit unambiguous column period; not report year.'}
            rec['field_sources']['/content_period'] = header_sources
            header_units = [(explicit_unit(c.get('text', '')), _cell_source(block, j, c)) for j, c in hs]
            # Row unit is authoritative only when all other explicit units agree.
            units = [(u, s) for u, s in row_units + header_units + context_units if u]
            if raw.strip().endswith('%'):
                units.append(('%', rec['field_sources']['/original_text'][0]))
            unit = units[0][0] if units and len({normalized(u) for u, _ in units}) == 1 else None
            field(rec, 'unit', unit, [s for _, s in units], 'Conflicting/absent units remain null; no standard-unit default.')
            rec['interpretation_notes'].append('Value and period candidates do not verify KPI legal-entity boundary. No cross-page header inheritance.')
            sync_missing_fields(rec)
            records.append(rec)
            evidence.append({'evidence_id': stable_id('evidence', rec['record_id']), 'record_id': rec['record_id'],
                             'metric_id': metric['record_id'], 'original_text': raw,
                             'source_refs': rec['source_refs'], 'source': rec['field_sources']['/original_text'][0],
                             'status': 'candidate', 'boundary_verified': False})
            for pointer in rec['missing_fields']:
                issues.append({'issue_id': stable_id('issue', rec['record_id'], pointer), 'record_id': rec['record_id'],
                               'field': pointer, 'code': 'ESG_FIELD_UNRESOLVED', 'status': 'open',
                               'source_refs': rec['source_refs'], 'pdf_page': block['source']['pdf_page'],
                               'details': rec['field_status'][pointer]['reason']})
    return records, evidence, issues


def candidate_links(records, evidence, metrics):
    by_id = {r['record_id']: r for r in records}
    links = []
    for claim in records:
        if claim['record_type'] not in ('claim', 'target'):
            continue
        codes = metric_candidates(claim['original_text'], metrics)
        # Multiple possible metrics are not a unique join key.
        if len(codes) != 1:
            continue
        for ev in evidence:
            measurement = by_id[ev['record_id']]
            if measurement['payload']['metric_code_candidates'] != codes:
                continue
            links.append({'link_id': stable_id('link', claim['record_id'], ev['evidence_id']),
                          'claim_id': claim['record_id'], 'evidence_id': ev['evidence_id'],
                          'relation': 'candidate_context', 'status': 'needs_review',
                          'match_basis': {'metric_code_candidate': codes[0]},
                          'comparability': {'period': 'unknown', 'unit': 'unknown', 'definition': 'unknown',
                                            'boundary': 'unknown', 'eligible': False},
                          'notes': 'Alias match only. No support/contradiction or target attainment inferred.'})
    return links
