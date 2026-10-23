import copy
import json

import pymupdf
import pytest

from src.extraction.esg_v2 import extract_esg, validate_esg
from src.extraction.source_v2 import capture_pdf


def page(*items):
    texts = [{'text': value[0], 'label': value[1]} if isinstance(value, tuple) else {'text': value, 'label': 'text'} for value in items]
    return {'texts': texts, 'body': {'children': [{'$ref': f'#/texts/{i}'} for i in range(len(texts))]}}


def run_esg(tmp_path, pages, kind='ESG', failure=None):
    source = tmp_path / 'esg.pdf'
    with pymupdf.open() as pdf:
        for _ in pages:
            pdf.new_page()
        pdf.save(source)
    def reader(path, number):
        if number == failure:
            raise RuntimeError('OCR failure')
        return {'status': 'processed', 'document': pages[number - 1], 'markdown': 'source'}
    work = capture_pdf(source, tmp_path / 'out', company_id='BSR', report_type=kind, report_year=2025,
                       page_reader=reader, profile={'engine': 'test-esg'}, retries=0)
    result_path = extract_esg(work)
    return work, json.loads(result_path.read_text(encoding='utf-8'))


def records_of(output, kind):
    return [r for r in output['records'] if r['record_type'] == kind]


def table_page(values, claim=None):
    cells = []
    for row, items in enumerate(values):
        for col, raw in enumerate(items):
            cells.append({'text': raw, 'start_row_offset_idx': row, 'end_row_offset_idx': row + 1,
                          'start_col_offset_idx': col, 'end_col_offset_idx': col + 1,
                          'column_header': row == 0})
    result = page(claim) if claim else page()
    result['tables'] = [{'data': {'table_cells': cells}}]
    result['body']['children'].append({'$ref': '#/tables/0'})
    return result


def test_esg_table_periods_units_and_candidate_links(tmp_path):
    native = table_page([['Chỉ tiêu', 'Đơn vị', '2024', '2025'],
                         ['Phát thải trực tiếp', 'tCO2e', '12', '0']],
                        'Công ty cam kết giảm phát thải trực tiếp đến năm 2030.')
    work, output = run_esg(tmp_path, [native])
    ms = records_of(output, 'measurement')
    assert [r['payload']['value'] for r in ms] == ['12', '0']
    assert [r['content_period']['year'] for r in ms] == [2024, 2025]
    assert all(r['payload']['unit'] == 'tCO2e' for r in ms)
    assert all(r['boundary']['included_entities'] is None for r in ms)
    assert len(output['evidence']) == 2 and len(output['links']) == 4
    assert all(not link['comparability']['eligible'] for link in output['links'])
    assert ms[0]['original_text'] == '12'
    assert output['evidence'][0]['source']['native_json_pointer'].endswith('/table_cells/6')
    assert validate_esg(output, work) == []
    rerun = json.loads(extract_esg(work).read_text(encoding='utf-8'))
    assert [r['record_id'] for r in rerun['records']] == [r['record_id'] for r in output['records']]


def test_workforce_table_stt_group_dvt_and_indicator_headers(tmp_path):
    _, output = run_esg(tmp_path, [table_page([
        ['STT', 'NHÓM', 'CHỈ SỐ TRỌNG YẾU', 'ĐVT', '2025'],
        ['1', 'Quy mô lao động', 'Tổng số lao động', 'Người', '1594'],
        ['1', 'Quy mô lao động', 'Nữ', 'Người', '214']])])
    values = records_of(output, 'measurement')
    assert [r['payload']['value'] for r in values] == ['1594', '214']
    assert all(r['payload']['unit'] == 'Người' for r in values)
    assert all(r['classification']['pillar'] == 'S' for r in values)
    assert all(r['content_period']['year'] == 2025 for r in values)


def test_table_unknown_metric_and_no_period_guess(tmp_path):
    _, output = run_esg(tmp_path, [table_page([['Chỉ tiêu', 'Đơn vị', 'Năm nay', '2023 / 2024'],
                                              ['Chỉ số chưa có taxonomy', 'người', '-', '1.594']])])
    ms = records_of(output, 'measurement')
    assert len(ms) == 2
    assert all(r['content_period'] is None and r['payload']['value'] is None for r in ms)
    assert ms[0]['data_status'] == 'missing' and ms[1]['data_status'] == 'ambiguous'
    assert ms[0]['payload']['metric_code_candidates'] == []
    assert '/payload/value' in ms[0]['missing_fields']
    assert output['links'] == []


def test_table_explicit_locale_and_intensity_not_defaulted(tmp_path):
    work, _ = run_esg(tmp_path, [table_page([['Chỉ tiêu', 'Đơn vị', '2025'],
                                           ['Cường độ phát thải', 'tCO2e/tấn sản phẩm', '1.594']])])
    result = json.loads(extract_esg(work, number_format='vi').read_text(encoding='utf-8'))
    rec = records_of(result, 'measurement')[0]
    assert rec['payload']['value'] == '1594'
    assert rec['payload']['unit'] == 'tCO2e/tấn sản phẩm'
    assert rec['content_period']['year'] == 2025


def test_top_unit_and_merged_value_remain_reviewable(tmp_path):
    native = table_page([['Chỉ tiêu', '2024', '2025'], ['Năng lượng tiêu thụ', '25', '30']], 'Đơn vị: GJ')
    native['tables'][0]['data']['table_cells'][4]['end_col_offset_idx'] = 3
    _, result = run_esg(tmp_path, [native])
    ms = records_of(result, 'measurement')
    assert ms[0]['payload']['value'] is None and ms[0]['content_period'] is None
    assert ms[0]['data_status'] == 'ambiguous'
    assert ms[1]['payload']['unit'] == 'GJ'


def test_same_topic_different_metric_does_not_link(tmp_path):
    _, result = run_esg(tmp_path, [table_page([['Chỉ tiêu', 'Đơn vị', '2025'],
                                             ['Phát thải trực tiếp', 'tCO2e', '25']],
                                            'Cam kết giảm phát thải gián tiếp đến năm 2030.')])
    assert result['evidence'] and result['links'] == []


def test_table_tampered_source_evidence_and_links_detected(tmp_path):
    work, result = run_esg(tmp_path, [table_page([['Chỉ tiêu', '2025'], ['Phát thải trực tiếp', '25']],
                                               'Cam kết giảm phát thải trực tiếp.')])
    changed = copy.deepcopy(result)
    records_of(changed, 'measurement')[0]['original_text'] = '999'
    assert 'Original cell differs from source.' in validate_esg(changed, work)
    changed = copy.deepcopy(result)
    changed['evidence'][0]['original_text'] = '999'
    assert 'Evidence source mismatch.' in validate_esg(changed, work)
    changed = copy.deepcopy(result)
    changed['links'][0]['evidence_id'] = 'absent'
    assert 'Unresolved candidate link.' in validate_esg(changed, work)


def test_policy_without_number_keeps_original_and_unknown_date(tmp_path):
    raw = 'Chính sách an toàn lao động áp dụng cho mọi nhân viên.\nKhông tự suy luận phạm vi pháp nhân.'
    work, result = run_esg(tmp_path, [page(raw)])
    policy = records_of(result, 'policy')[0]
    assert policy['original_text'] == raw
    assert policy['payload']['policy_text'] == raw
    assert policy['payload']['effective_date'] is None
    assert policy['classification']['pillar'] == 'S'
    assert policy['review']['status'] == 'needs_review'
    assert policy['boundary']['included_entities'] is None
    assert 'included_entities' in policy['boundary']['missing_fields']
    assert '/boundary/included_entities' in policy['missing_fields']
    assert policy['content_period'] is None
    assert result['validation']['valid']
    assert validate_esg(result, work) == []


def test_multi_type_paragraph_with_explicit_target_year_baseline_not_guessed(tmp_path):
    raw = 'Công ty triển khai chương trình tiết kiệm năng lượng, cam kết giảm 20% đến năm 2030 so với năm 2020.'
    _, result = run_esg(tmp_path, [page(raw)])
    assert set(result['counts']) == {'claim', 'action', 'target'}
    target = records_of(result, 'target')[0]
    assert target['payload']['target_year'] == 2030
    assert '/payload/target_year' not in target['missing_fields']
    assert target['payload']['baseline_year'] is None
    assert target['payload']['target_value'] == '20'
    assert target['payload']['baseline_value'] is None
    assert all(r['original_text'] == raw for r in result['records'])
    assert result['evidence'] == [] and result['links'] == []


def test_explicit_baseline_and_ambiguous_deadline(tmp_path):
    _, result = run_esg(tmp_path, [page('Mục tiêu giảm phát thải đến năm 2030 và đến năm 2040; năm cơ sở: 2020.')])
    target = records_of(result, 'target')[0]
    assert target['payload']['target_year'] is None
    assert target['field_status']['/payload/target_year']['status'] == 'ambiguous'
    assert target['payload']['baseline_year'] == 2020
    assert target['payload']['deadline'] is None


def test_policy_effective_date_only_explicit_source_phrase(tmp_path):
    _, result = run_esg(tmp_path, [page('Chính sách môi trường có hiệu lực từ ngày 01/02/2024. Báo cáo năm 2025.')])
    policy = records_of(result, 'policy')[0]
    assert policy['payload']['effective_date'] == '2024-02-01'
    assert policy['content_period'] is None


def test_governance_body_named_but_other_roles_remain_unknown(tmp_path):
    _, result = run_esg(tmp_path, [page('HĐQT giám sát hoạt động tuân thủ của công ty.')])
    governance = records_of(result, 'governance')[0]
    assert governance['payload']['responsible_body'] == 'HĐQT'
    assert governance['payload']['role'] is None
    assert governance['payload']['reporting_frequency'] is None
    assert governance['classification']['pillar'] == 'G'


def test_mixed_pillars_not_forced_into_single_pillar(tmp_path):
    _, result = run_esg(tmp_path, [page('Công ty thực hiện chương trình giảm phát thải và đào tạo an toàn lao động.')])
    claim = records_of(result, 'claim')[0]
    assert claim['classification']['pillar'] == 'unknown'
    assert {t['pillar'] for t in claim['classification']['topic_candidates']} == {'E', 'S'}


def test_unknown_retained_and_tables_explicitly_pending(tmp_path):
    native = page('Một đoạn văn chưa có tín hiệu phân loại trong bảng mã.')
    native['tables'] = [{'data': {'table_cells': []}}]
    native['pictures'] = [{'label': 'picture'}]
    native['body']['children'] += [{'$ref': '#/tables/0'}, {'$ref': '#/pictures/0'}]
    _, result = run_esg(tmp_path, [native])
    assert len(records_of(result, 'unknown')) == 1
    assert len(result['coverage']['blocks']) == 3
    assert any(c['disposition'] == 'pending_table_extraction' for c in result['coverage']['blocks'])
    assert sum(i['code'] == 'ESG_BLOCK_PENDING' for i in result['issues']) == 2
    assert result['semantic_status'] == 'partial' and not result['graph_ready']


def test_heading_inherited_but_not_across_failed_page(tmp_path):
    pages = [page(('Chính sách an toàn lao động', 'section_header')), {}, page('Nội dung áp dụng cho nhân viên.')]
    _, result = run_esg(tmp_path, pages, failure=2)
    assert not records_of(result, 'policy')
    # Workforce is now a configured S topic; a topic candidate must still not
    # inherit the policy heading across an unreadable page.
    following = [r for r in result['records'] if r['original_text'] == 'Nội dung áp dụng cho nhân viên.']
    assert following and all(r['payload']['section_heading_raw'] is None for r in following)
    assert result['coverage']['source_pages']['counts']['failed'] == 1


def test_heading_inherited_on_adjacent_processed_pages_and_stable_ids(tmp_path):
    work, result = run_esg(tmp_path, [page(('Chính sách an toàn lao động', 'section_header')), page('Nội dung áp dụng cho nhân viên.')])
    policy = records_of(result, 'policy')[0]
    assert policy['field_sources']['/payload/section_heading_raw'][0]['pdf_page'] == 1
    assert policy['field_sources']['/payload/statement'][0]['pdf_page'] == 2
    rerun = json.loads(extract_esg(work).read_text(encoding='utf-8'))
    assert [r['record_id'] for r in result['records']] == [r['record_id'] for r in rerun['records']]


def test_unreachable_heading_not_inherited(tmp_path):
    native = page(('Chính sách đào tạo', 'section_header'), 'Một đoạn khác.')
    native['body']['children'] = []
    _, result = run_esg(tmp_path, [native])
    assert records_of(result, 'unknown')[0]['payload']['section_heading_raw'] is None
    assert any(i['code'] == 'ESG_READING_ORDER_UNKNOWN' for i in result['issues'])


def test_negated_target_is_only_candidate_not_positive_assertion(tmp_path):
    _, result = run_esg(tmp_path, [page('Công ty không công bố mục tiêu phát thải cho kỳ này.')])
    target = records_of(result, 'target')[0]
    assert target['payload']['target_year'] is None
    assert target['review']['status'] == 'needs_review'
    assert any(i['code'] == 'ESG_CANDIDATE_REVIEW' for i in result['issues'])
    assert target['payload']['negation_cue'] is True
    assert any(i['code'] == 'ESG_NEGATION_REVIEW' for i in result['issues'])


def test_direct_target_percentage_not_actual_number_elsewhere(tmp_path):
    _, result = run_esg(tmp_path, [page('Mục tiêu giảm 20% phát thải đến năm 2030.'),
                                   page('Mục tiêu đến năm 2030 chưa lượng hóa; kết quả năm 2025 giảm 10%.')])
    targets = records_of(result, 'target')
    assert targets[0]['payload']['target_value'] == '20'
    assert targets[0]['payload']['unit'] == '%'
    assert targets[1]['payload']['target_value'] is None
    assert targets[1]['payload']['unit'] is None


def test_governance_report_frequency_not_meeting_frequency(tmp_path):
    _, result = run_esg(tmp_path, [page('HĐQT nhận báo cáo hàng quý.'), page('HĐQT họp hàng tháng.')])
    governance = records_of(result, 'governance')
    assert governance[0]['payload']['reporting_frequency'] == 'hàng quý'
    assert governance[1]['payload']['reporting_frequency'] is None


def test_annual_report_allowed_without_forcing_financial_paragraph_as_esg(tmp_path):
    _, result = run_esg(tmp_path, [page('Doanh thu bán hàng năm 2025 được trình bày ở bảng sau.')], kind='annual_report')
    assert len(records_of(result, 'unknown')) == 1
    assert not records_of(result, 'claim')


def test_financial_report_requires_own_branch(tmp_path):
    with pytest.raises(ValueError, match='financial branch'):
        run_esg(tmp_path, [page('Chính sách kế toán.')], kind='financial_statements')


def test_tamper_missing_list_source_text_and_coverage_detected(tmp_path):
    work, result = run_esg(tmp_path, [page('Chính sách môi trường.')])
    altered = copy.deepcopy(result)
    altered['records'][0]['original_text'] = 'Invented text'
    altered['records'][0]['missing_fields'] = []
    altered['coverage']['blocks'] = []
    errors = validate_esg(altered, work)
    assert 'Original text differs from source.' in errors
    assert 'Missing fields out of sync.' in errors
    assert 'Block coverage mismatch.' in errors
