"""Source-bound enrichment and review hypotheses, never adjudicated comparisons.

Metric IDs below are a versioned local vocabulary, not GRI/IFRS identifiers.
No generic report boundary is inherited by an ESG KPI.
"""
from copy import deepcopy
from decimal import Decimal, localcontext
import re

from src.extraction.financial_context_v2 import normalized
from src.extraction.financial_v2 import parse_number
from src.extraction.source_v2 import stable_id

VERSION = 'corporate-review/2.1'
CATALOG = {
    'total_assets': ('financial_position', 'Tổng tài sản tại thời điểm báo cáo; không phải tổng tài sản ngắn hạn hoặc dài hạn.'),
    'owners_equity': ('financial_position', 'Vốn chủ sở hữu tại thời điểm báo cáo; không phải vốn góp của chủ sở hữu.'),
    'net_sales_revenue': ('financial_performance', 'Doanh thu thuần bán hàng và cung cấp dịch vụ; không bao gồm doanh thu tài chính hoặc thu nhập khác.'),
    'profit_after_tax': ('financial_performance', 'Lợi nhuận sau thuế thu nhập doanh nghiệp của kỳ; không phải lợi nhuận chưa phân phối hoặc riêng phần thuộc cổ đông công ty mẹ.'),
    'profit_before_tax': ('financial_performance', 'Tổng lợi nhuận kế toán trước thuế thu nhập doanh nghiệp của kỳ.'),
    'current_income_tax_expense': ('income_tax_expense', 'Chi phí thuế thu nhập doanh nghiệp hiện hành ghi nhận trong kỳ, không phải tiền thuế đã nộp.'),
    'deferred_income_tax_expense': ('income_tax_expense', 'Chi phí thuế thu nhập doanh nghiệp hoãn lại trong kỳ.'),
    'employee_payables': ('employee_payables_money', 'Số dư khoản phải trả người lao động tại ngày đo, bằng tiền; không phải số người hoặc chi phí lương cả năm.'),
    'employee_advances': ('employee_advances_money', 'Số dư tạm ứng cho nhân viên tại ngày đo, bằng tiền; không phải số lượng nhân viên.'),
    'sales_staff_expense': ('personnel_expense_money', 'Chi phí nhân viên bán hàng trong kỳ, bằng tiền; không phải số người.'),
    'management_staff_expense': ('personnel_expense_money', 'Chi phí nhân viên quản lý trong kỳ, bằng tiền; không phải số người.'),
    'employee_headcount_at_date': ('workforce_headcount', 'Tổng số nhân viên/người lao động tại ngày đo; phạm vi người được tính và cách đếm phải kiểm tra riêng.'),
}


def identify(label):
    t = normalized(label)
    clean = re.sub(r'^\s*(?:[a-z]|[ivx]+|\d+)[.)]\s*', '', t).strip()
    clean = re.sub(r'\s*\([^()]*\d+\s*=[^()]+\)\s*$', '', clean).strip()
    if clean == 'tong tai san':
        return 'total_assets'
    if clean == 'von chu so huu':
        return 'owners_equity'
    if 'phai tra nguoi lao dong' in t:
        return 'employee_payables'
    if 'tam ung cho nhan vien' in t:
        return 'employee_advances'
    if 'chi phi nhan vien ban hang' in t:
        return 'sales_staff_expense'
    if 'chi phi nhan vien quan ly' in t:
        return 'management_staff_expense'
    if 'doanh thu thuan ve ban hang' in t:
        return 'net_sales_revenue'
    if 'loi nhuan sau thue' in t and not any(s in t for s in ('chua phan phoi', 'co dong', 'trich', 'quy', 'dieu chinh')):
        return 'profit_after_tax'
    if 'tong loi nhuan ke toan truoc thue' in t:
        return 'profit_before_tax'
    if re.fullmatch(r'loi nhuan truoc thue(?: dat)?', t):
        return 'profit_before_tax'
    if 'chi phi thue thu nhap doanh nghiep' in t and not any(s in t for s in ('dieu chinh', 'tinh tren', 'phat sinh', 'hoan nhap')):
        if 'hien hanh' in t:
            return 'current_income_tax_expense'
        if 'hoan lai' in t:
            return 'deferred_income_tax_expense'
    if re.fullmatch(r'(tong so lao dong|tong so nhan vien)', t.strip()):
        return 'employee_headcount_at_date'
    return None


def review_topics(record):
    """Currency employment accounts cannot become workforce count candidates."""
    key = identify(record['metric_label'])
    if key:
        return [CATALOG[key][0]]
    t = normalized(record['metric_label'])
    if any(s in t for s in ('lao dong', 'nhan vien', 'nhan su')):
        return ['employment_context_not_headcount']
    if any(s in t for s in ('phat thai', 'khi nha kinh')):
        return ['emissions']
    if any(s in t for s in ('hoi dong quan tri', 'hdqt')):
        return ['board']
    return []


def _header(block, role='other'):
    s = block['source']
    return {'role': role, 'text': block['original_text'], 'physical_page': s['pdf_page'],
            'row': None, 'column': None, 'bbox': None}


def _attach(record, blocks):
    ev = record['evidence'][0]
    for b, role in blocks:
        h = _header(b, role)
        if h not in ev['headers']:
            ev['headers'].append(h)
        if h['text'] not in ev['context_text']:
            ev['context_text'] += '\n' + h['text']


def _issue(h, r, code, message):
    row = {'issue_id': stable_id('review_issue', r['record_id'], code), 'code': code,
           'message': message, 'record_id': r['record_id'], 'status': 'needs_review',
           'source_pages': sorted({e['physical_page'] for e in r['evidence']})}
    if not any(i['issue_id'] == row['issue_id'] for i in h['issue_log']):
        h['issue_log'].append(row)


def _set_metric(r, key):
    topic, definition = CATALOG[key]
    r.update(metric_id='local:' + key + ':v1', metric_definition=definition, topic=topic)
    r['quality']['uncertainty'] = sorted(set(r['quality']['uncertainty']) | {'local_metric_mapping_pending_human_review'})


def _amount(r, literal, factor, unit, scale=None, number_format='vi'):
    raw = r['value']['original_value']
    parsed, status = parse_number(raw, number_format)
    if parsed is None or status != 'available':
        return False
    with localcontext() as ctx:
        ctx.prec = 256
        v = Decimal(parsed) * Decimal(str(factor))
    number = int(v) if v == v.to_integral_value() else float(v)
    if Decimal(str(number)) != v:
        return False
    notation = 'Explicit Vietnamese source notation;' if number_format == 'vi' or re.fullmatch(r'\(?-?\d{1,3}(?:\.\d{3}){2,}(?:,\d+)?\)?', raw.strip()) else 'Source notation parsed with ' + number_format + ';'
    r['value'].update(status='available', original_unit=literal, original_scale=scale,
                      normalized_value=number, normalized_unit=unit, normalization_factor=factor,
                      normalization_note=notation + ' original amount × factor exactly once. Human review pending.')
    r['quality']['uncertainty'] = [x for x in r['quality']['uncertainty'] if x not in ('normalization_unit_or_factor_unknown', 'numeric_value_not_resolved_from_source')]
    return True


def enrich_records(handoff, native):
    """Mutates a fresh handoff only. Leaves raw native/checkpoint bytes untouched."""
    blocks = [b for b in native.get('source_blocks', []) if b.get('original_text')]
    native_records = {r['record_id']: r for r in native.get('records', [])}
    financial = handoff['document']['report_type'] == 'Financial'
    changes = []
    for r in handoff['records']:
        key = identify(r['metric_label'])
        if not key or r['record_type'] not in ('measurement', 'financial_measurement'):
            continue
        ev = r['evidence'][0]
        page = ev['physical_page']
        nr = native_records.get(r['record_id'], {})
        column = ev['column']
        # Never classify a statement code/reference column as a measurement.
        if financial and (r['period']['observation_year'] is None or not any(
                x['role'] == 'year' and x['column'] == column for x in ev['headers'])):
            continue
        before = deepcopy(r)
        _set_metric(r, key)
        same_page = [b for b in blocks if b['source']['pdf_page'] == page]
        units = [b for b in same_page if re.search(r'(don vi|unit)\s*[:：].*\bvnd\b', normalized(b['original_text']))]
        # An explicit page-level unit is valid for a financial statement table,
        # not for unrelated ESG KPIs elsewhere on the page.
        if financial and units and not re.search(r'\b(trieu|ty|nghin|million|billion|thousand)\b', normalized(units[0]['original_text'])):
            _attach(r, [(units[0], 'unit')])
            _amount(r, units[0]['original_text'], 1, 'VND', number_format=native.get('number_format', 'auto'))
        # ESG table units must be on the same source row, not general cover text.
        if not financial:
            cells = nr.get('original_cells') or []
            row_units = [c['text'] for c in cells if re.fullmatch(r'ty\s*(vnd|dong)', normalized(c['text']).strip())]
            if row_units:
                literal = row_units[0]
                unit_cell = next(c for c in cells if c['text']==literal)
                table = next((b for b in native.get('source_blocks', []) if b['block_id'] in nr.get('source_refs', []) and
                              unit_cell in (b.get('original_cells') or []) and b['source']['pdf_page']==page), None)
                if table and unit_cell['start_row_offset_idx'] == ev['row']:
                    header = {'role':'unit','text':literal,'physical_page':page,
                              'row':unit_cell['start_row_offset_idx'],'column':unit_cell['start_col_offset_idx'],'bbox':None}
                    if header not in ev['headers']:
                        ev['headers'].append(header)
                    if literal not in ev['context_text']:
                        ev['context_text'] += '\n' + literal
                    _amount(r, literal, 10**9, 'VND', 'Tỷ')
            if key == 'employee_headcount_at_date':
                _issue(handoff, r, 'HEADCOUNT_DATE_AND_BOUNDARY_UNCONFIRMED',
                       'Year-column alone does not establish a year-end date, included population, or separate/consolidated legal scope. Do not infer these from BCTC.')
        year = r['period']['observation_year']
        year_headers = [x for x in ev['headers'] if x['role'] == 'year' and x['column'] == column]
        # Year headers establish a year, not automatically a full calendar year.
        # Preserve periods already resolved by the source parser. Relative labels
        # and report-year metadata never become human-reviewed context here.
        if year and column is not None and any(
                set(re.findall(r'(?<!\d)(?:19|20)\d{2}(?!\d)', x['text'])) == {str(year)}
                for x in year_headers):
            r['period']['year_basis'] = 'table_header'
        # Record-specific financial title, not report-wide ESG boundary inheritance.
        entity = handoff['document'].get('reporting_entity')
        title = next((b for b in same_page if entity and normalized(entity) in normalized(b['original_text'])), None)
        scope = handoff['document']['financial_scope']
        scope_word = 'rieng' if scope == 'Separate' else 'hop nhat'
        scope_evidence = next((b for b in same_page if 'bao cao tai chinh ' + scope_word in normalized(b['original_text'])), None)
        if financial and title and scope_evidence:
            _attach(r, [(title, 'caption'), (scope_evidence, 'caption')])
            r['boundary']['reporting_entity'] = entity
            r['boundary']['consolidation'] = scope
            if scope == 'Separate':
                r['boundary']['scope'] = 'Báo cáo tài chính riêng của ' + entity + '.'
        if not financial and key == 'profit_after_tax' and 'hop nhat' in normalized(r['metric_label']):
            r['boundary']['consolidation'] = 'Consolidated'
        if financial:
            formula = re.search(r'\([^()]*\d+\s*=[^()]+\)', r['metric_label'])
            if formula:
                r['boundary']['calculation_method'] = 'Công thức dòng báo cáo: ' + formula.group(0)
        comparative = next((b for b in blocks if 'so lieu so sanh la so lieu cua bao cao tai chinh rieng' in normalized(b['original_text'])), None)
        if financial and comparative and year and year < handoff['document']['report_year']:
            _attach(r, [(comparative, 'other')])
            r['restatement']['note'] = comparative['original_text'] + ' Không đủ để khẳng định có/không trình bày lại; trạng thái giữ unknown nếu chưa có nhãn trực tiếp.'
        r['boundary']['verified'] = False
        if before != r:
            changes.append({'record_id': r['record_id'], 'kind': 'source_bound_enrichment', 'metric_id': r['metric_id'],
                            'source_pages': sorted({x['physical_page'] for x in r['evidence']}),
                            'unresolved_fields': [k for k,v in r['boundary'].items() if v is None],
                            'human_review_status': 'pending_human_review'})
            _issue(handoff, r, 'SEMANTIC_ENRICHMENT_PENDING_REVIEW',
                   'Local metric definition and explicit source context added by corporate-review/2.0. Original quote/ID preserved; unresolved method, population, footnotes, boundary/restatement remain unknown. No human verification asserted.')
    return changes


def recover_headcounts(handoff, native):
    """Extract dated headcounts from explicit note sentences, not account balances."""
    if handoff['document']['report_type'] != 'Financial':
        return []
    added = []
    for b in native.get('source_blocks', []):
        quote = b.get('original_text') or ''
        if not re.search(r'tong so (nhan vien|lao dong)', normalized(quote)):
            continue
        # Require explicit date, count and direct company/group wording.
        matches = re.findall(r'(?:tại ngày\s*)?31\s+tháng\s+12\s+năm\s+(20\d{2})\s*(?:là\s*|:\s*)([\d.]+)', quote, re.I)
        if not matches or not re.search(r'của (?:Công ty|Tập đoàn)', quote, re.I):
            continue
        for year_s, amount in matches:
            year = int(year_s)
            rid = stable_id('record', handoff['document']['source']['sha256'], b['source']['native_json_pointer'], b['source']['pdf_page'], 'headcount', year)
            if any(r['record_id'] == rid for r in handoff['records']):
                continue
            source = b['source']
            eid = stable_id('handoff_evidence', rid, quote)
            scope = handoff['document']['financial_scope']
            r = {'record_id': rid, 'dimension': 'X', 'record_type': 'financial_measurement',
                 'topic': 'workforce_headcount', 'metric_id': None, 'metric_label': 'Tổng số nhân viên', 'metric_definition': None,
                 'statement': {'original_quote': quote, 'interpretation': 'Số nhân viên tại ngày ghi trực tiếp trong thuyết minh; không suy ra cách đếm hay phạm vi ESG.', 'assertion_kind': 'reported_result'},
                 'value': {'status': 'unknown', 'original_value': amount, 'original_unit': None, 'original_scale': None, 'normalized_value': None, 'normalized_unit': None, 'normalization_factor': None, 'normalization_note': None},
                 'period': {'observation_year': year, 'observation_start': None, 'observation_end': None, 'measurement_date': f'{year}-12-31', 'period_type': 'at_date', 'year_basis': 'explicit_quote', 'baseline_year': None, 'target_deadline': None},
                 'boundary': {'reporting_entity': handoff['document'].get('reporting_entity'), 'consolidation': scope if scope == 'Separate' or 'tap doan' in normalized(quote) else 'unknown', 'scope': 'Tổng số nhân viên của Công ty theo đoạn thuyết minh trực tiếp.' if scope == 'Separate' else None, 'population': None, 'counting_method': None, 'calculation_method': None, 'verified': False},
                 'restatement': {'status': 'unknown', 'note': None},
                 'evidence': [{'evidence_id': eid, 'source_sha256': handoff['document']['source']['sha256'], 'physical_page': source['pdf_page'], 'printed_page': source.get('printed_page'), 'exact_quote': quote, 'context_text': quote, 'section': 'Thông tin khái quát', 'element_id': source['native_json_pointer'], 'char_start': None, 'char_end': None, 'bbox': None, 'table_id': None, 'row': None, 'column': None, 'headers': [], 'footnotes': []}],
                 'quality': {'extraction_method': 'rule', 'parser_name': VERSION + '/dated_headcount_note', 'model_id': None, 'prompt_version': None, 'uncertainty': ['headcount_population_and_counting_method_unknown', 'pending_human_source_review', 'reporting_boundary_not_verified', 'restatement_not_fully_searched'], 'review_status': 'pending_human_review', 'reviewer': None, 'reviewed_at_utc': None, 'review_basis': None}, 'comparison_group_id': None}
            _set_metric(r, 'employee_headcount_at_date')
            _amount(r, 'nhân viên', 1, 'people')
            handoff['records'].append(r)
            _issue(handoff, r, 'SUPPLEMENTAL_HEADCOUNT_SOURCE_REVIEW', 'Dated employee count extracted from exact native note sentence. No equivalence with ESG total workforce assumed.')
            added.append({'record_id': rid, 'kind': 'supplemental_dated_headcount', 'native_json_pointer': source['native_json_pointer'], 'physical_page': source['pdf_page'], 'number_format': 'vi', 'human_review_status': 'pending_human_review'})
    return added


def build_review_queue(handoffs):
    priorities, pairs, exclusions = [], [], []
    sides = {'ESG': [], 'Financial': []}
    for h in handoffs:
        d = h['document']
        for r in h['records']:
            topics = review_topics(r)
            if not topics:
                continue
            ref = {'document_id': d['document_id'], 'record_id': r['record_id'], 'metric_id': r['metric_id'],
                   'metric_label': r['metric_label'], 'topics': topics, 'report_type': d['report_type'],
                   'evidence_ids': [e['evidence_id'] for e in r['evidence']],
                   'physical_pages': sorted({e['physical_page'] for e in r['evidence']}),
                   'review_status': 'pending_human_review'}
            if r['metric_id'] or identify(r['metric_label']):
                priorities.append(ref)
            if r['metric_id'] and r['period']['observation_year'] and r['value']['status'] == 'available':
                sides[d['report_type']].append((d, r, ref))
            if identify(r['metric_label']) in ('employee_payables', 'employee_advances', 'sales_staff_expense', 'management_staff_expense'):
                exclusions.append(dict(ref, reason='Monetary balance/expense; never a headcount counterpart.'))
    for de, e, er in sides['ESG']:
        for df, f, fr in sides['Financial']:
            if de['company_id'] != df['company_id'] or e['metric_id'] != f['metric_id']:
                continue
            if e['period']['observation_year'] != f['period']['observation_year']:
                continue
            if e['value']['normalized_unit'] != f['value']['normalized_unit']:
                continue
            se, sf = e['boundary']['consolidation'], f['boundary']['consolidation']
            if se in ('Separate', 'Consolidated') and sf != se:
                continue
            blockers = []
            if e['period']['period_type'] == 'unknown' or e['period']['period_type'] != f['period']['period_type']:
                blockers.append('ESG measurement date/period is not established as equivalent to the financial period.')
            if se == 'unknown' or not e['boundary']['scope'] or not f['boundary']['scope']:
                blockers.append('Legal-entity/population boundary is not fully established on both sides.')
            if not e['boundary']['counting_method'] and 'headcount' in e['metric_id']:
                blockers.append('Employee/workforce counting method and population equivalence unconfirmed.')
            blockers.append('Source transcription, restatement and any rounding require human PDF review.')
            pair_id = stable_id('candidate_pair', e['record_id'], f['record_id'])
            pairs.append({'pair_id': pair_id, 'status': 'NeedsReview', 'review_status': 'pending_human_review',
                          'metric_id': e['metric_id'], 'observation_year': e['period']['observation_year'],
                          'esg': er, 'financial': fr, 'check_type': 'ESG_FINANCIAL',
                          'candidate_basis': ['Same local metric candidate definition.', 'Same explicit observation-year candidate and base unit.', 'No known separate/consolidated scope conflict.'],
                          'comparability': 'unconfirmed', 'eligible_for_numeric_comparison': False,
                          'blockers': blockers, 'verdict': None})
    paired_ids = {p[s]['record_id'] for p in pairs for s in ('esg', 'financial')}
    for item in priorities:
        item['priority'] = 1 if item['record_id'] in paired_ids else 2 if item['metric_id'] else 3
        item['reason'] = 'Evidence-linked pair endpoint; resolve listed blockers first.' if item['record_id'] in paired_ids else 'Local metric candidate or monetary-account exclusion; source and semantic review pending.'
    priorities.sort(key=lambda r: (r['priority'],r['document_id'],r['record_id']))
    return {'schema_version': 'corporate-review-queue/2.0', 'purpose': 'Evidence-backed hypotheses for human review, not verified comparisons.',
            'priority_records': priorities, 'candidate_pairs': pairs, 'excluded_from_headcount_pairing': exclusions,
            'counts': {'priority_records': len(priorities), 'candidate_pairs': len(pairs), 'financially_verified_claims': 0}}
