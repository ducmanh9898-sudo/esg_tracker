"""Literal KPI card candidates from source lines with PDF geometry.

Only one uniquely placed value and observed unit may form a card. A page
headline never supplies the observation year or corporate boundary here.
"""
import re

from src.extraction.corporate_review import identify
from src.extraction.esg_tables_v2 import explicit_unit
from src.extraction.financial_v2 import parse_number
from src.extraction.source_v2 import new_record, stable_id, sync_missing_fields


ALLOWED = {'profit_after_tax', 'profit_before_tax', 'total_assets', 'owners_equity'}


def box(block):
    try:
        b = block['source']['native_provenance'][0]['bbox']
        return (b['l'], b['t'], b['r'], b['b'])
    except (KeyError, IndexError, TypeError):
        return None


def ref(block):
    source = dict(block['source'])
    b = box(block)
    if b:
        source['bbox'] = list(b)
    source['raw_text'] = block['original_text']
    return source


def extract_cards(bundle, config, number_format='auto'):
    report = bundle['reports'][0]
    pages = {}
    for block in bundle['source_blocks']:
        if block['kind'] == 'texts' and box(block):
            pages.setdefault(block['source']['pdf_page'], []).append(block)
    records, evidence, issues = [], [], []
    for page, blocks in pages.items():
        for label in blocks:
            raw_label = label['original_text'].strip()
            key = identify(raw_label)
            if key not in ALLOWED or len(raw_label) > 100:
                continue
            lb = box(label)
            center = (lb[0] + lb[2]) / 2
            values = []
            for candidate in blocks:
                cb = box(candidate)
                raw = candidate['original_text'].strip()
                if (candidate is not label and re.fullmatch(r'[0-9][0-9.,]*', raw)
                        and abs((cb[0] + cb[2]) / 2 - center) <= 65
                        and lb[1] - 10 <= cb[1] <= lb[1] + 60
                        and cb[3] - cb[1] >= 14):
                    values.append(candidate)
            if len(values) != 1:
                if values:
                    issues.append({'issue_id': stable_id('issue', label['block_id'], 'ambiguous_card'),
                                   'record_id': None, 'pdf_page': page, 'field': '/source_blocks',
                                   'code': 'CARD_VALUE_ASSOCIATION_AMBIGUOUS', 'status': 'open',
                                   'details': 'Several numeric source lines fit one KPI label; no candidate emitted.'})
                continue
            value = values[0]
            vb = box(value)
            units = [b for b in blocks if b is not value and explicit_unit(b['original_text'])
                     and (ub := box(b)) and vb[2] - 15 <= ub[0] <= vb[2] + 55
                     and ub[1] <= vb[3] and ub[3] >= vb[1]]
            if len(units) != 1:
                continue
            unit = units[0]
            amount, status = parse_number(value['original_text'], number_format)
            if status != 'available':
                continue
            metric = new_record(report['report_version_id'], label['block_id'], 'metric', 'card')
            metric.update(company_id=report['company_id'], domain='esg', original_text=label['original_text'],
                          original_cells=[], payload={'statement': label['original_text'],
                          'section_heading_raw': None, 'classification_method': 'source_geometry_card/1',
                          'assertion_status': 'unverified', 'name_raw': label['original_text'],
                          'metric_code_candidates': [key]},
                          classification={'pillar': 'G', 'topic_candidates': [],
                                          'codebook_version': config['version'], 'status': 'candidate'},
                          data_status='available', field_sources={'/original_text': [ref(label)],
                          '/payload/name_raw': [ref(label)]})
            metric['field_status']['/payload/name_raw'] = {'status': 'available', 'reason': 'Literal PDF source line.'}
            metric['review']['status'] = 'needs_review'
            sync_missing_fields(metric)
            rec = new_record(report['report_version_id'], value['block_id'], 'measurement', 'card')
            rec.update(company_id=report['company_id'], domain='esg', original_text=value['original_text'],
                       original_cells=[], source_refs=[value['block_id'], label['block_id'], unit['block_id']],
                       payload={'statement': value['original_text'], 'section_heading_raw': None,
                                'classification_method': 'source_geometry_card/1',
                                'assertion_status': 'unverified', 'metric_id': metric['record_id'],
                                'metric_code_candidates': [key], 'row_label_raw': label['original_text'],
                                'value': amount, 'value_raw': value['original_text'],
                                'header_raw': '', 'unit': explicit_unit(unit['original_text']),
                                'assertion_kind': 'reported_result' if 'dat' in raw_label.lower() or 'đạt' in raw_label.lower() else 'unknown'},
                       classification={'pillar': 'G', 'topic_candidates': [],
                                       'codebook_version': config['version'], 'status': 'candidate'},
                       data_status='available', field_sources={'/original_text': [ref(value)],
                           '/payload/value': [ref(value)], '/payload/value_raw': [ref(value)],
                           '/payload/unit': [ref(unit)], '/payload/row_label_raw': [ref(label)]})
            for field in ('value', 'value_raw', 'unit', 'row_label_raw'):
                rec['field_status']['/payload/' + field] = {'status': 'available',
                    'reason': 'Unique nearby PDF source line; geometric association needs human review.'}
            rec['interpretation_notes'].append('KPI card association is geometric; observation year, legal scope and semantics require review.')
            rec['review']['status'] = 'needs_review'
            sync_missing_fields(rec)
            records.extend([metric, rec])
            evidence.append({'evidence_id': stable_id('evidence', rec['record_id']),
                             'record_id': rec['record_id'], 'metric_id': metric['record_id'],
                             'original_text': rec['original_text'], 'source_refs': rec['source_refs'],
                             'source': ref(value), 'status': 'candidate', 'boundary_verified': False})
    return records, evidence, issues
