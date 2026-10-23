from copy import deepcopy
import importlib.util
from pathlib import Path

from src.extraction.corporate_review import identify, review_topics, build_review_queue, recover_headcounts
from src.extraction.corporate_review import _amount


def test_monetary_accounts_are_not_employee_counts():
    assert identify('Phải trả người lao động') == 'employee_payables'
    assert identify('Tạm ứng cho nhân viên') == 'employee_advances'
    assert review_topics({'metric_label':'Phải trả người lao động'}) == ['employee_payables_money']
    assert identify('Lợi nhuận sau thuế chưa phân phối') is None
    assert identify('Lợi nhuận sau thuế của cổ đông của Công ty mẹ') is None
    assert identify('Tổng doanh thu') is None
    assert identify('Nộp ngân sách Nhà nước') is None


def record(rid, unit='person', scope='unknown', year=2024):
    return {'record_id':rid,'metric_id':'local:employee_headcount_at_date:v1','metric_label':'Tổng số lao động',
            'evidence':[{'evidence_id':'e_'+rid,'physical_page':12}],
            'period':{'observation_year':year,'period_type':'unknown'},
            'value':{'status':'available','normalized_unit':unit},
            'boundary':{'consolidation':scope,'scope':None,'counting_method':None}}


def test_pairs_are_hypotheses_not_numeric_verdicts():
    a=record('esg')
    b=record('fs',scope='Separate')
    docs=[{'document':{'document_id':'de','company_id':'BSR','report_type':'ESG'},'records':[a]},
          {'document':{'document_id':'df','company_id':'BSR','report_type':'Financial'},'records':[b]}]
    q=build_review_queue(docs)
    assert len(q['candidate_pairs'])==1
    pair=q['candidate_pairs'][0]
    assert pair['status']=='NeedsReview' and pair['verdict'] is None
    assert not pair['eligible_for_numeric_comparison'] and len(pair['blockers'])>=3
    assert pair['esg']['record_id']=='esg' and pair['financial']['evidence_ids']==['e_fs']
    b['value']['normalized_unit']='VND'
    assert not build_review_queue(docs)['candidate_pairs']


def test_different_year_or_known_scope_cannot_pair():
    a,b=record('esg',scope='Consolidated'),record('fs',scope='Separate')
    docs=[{'document':{'document_id':'de','company_id':'BSR','report_type':'ESG'},'records':[a]},
          {'document':{'document_id':'df','company_id':'BSR','report_type':'Financial'},'records':[b]}]
    assert not build_review_queue(docs)['candidate_pairs']
    b['boundary']['consolidation']='Consolidated'
    b['period']['observation_year']=2023
    assert not build_review_queue(docs)['candidate_pairs']


def test_headcount_recovery_has_explicit_date_and_source_and_is_idempotent():
    h={'document':{'report_type':'Financial','source':{'sha256':'a'*64},'financial_scope':'Separate'},'records':[],'issue_log':[]}
    n={'source_blocks':[{'original_text':'Tổng số nhân viên của Công ty tại ngày 31 tháng 12 năm 2024 là 1.543 (tại ngày 31 tháng 12 năm 2023: 1.531).',
                        'source':{'pdf_page':12,'native_json_pointer':'/document/texts/19'}}]}
    assert len(recover_headcounts(h,n))==2
    assert [r['value']['normalized_value'] for r in h['records']]==[1543,1531]
    assert all(r['period']['year_basis']=='explicit_quote' for r in h['records'])
    assert all(r['quality']['review_status']=='pending_human_review' and not r['boundary']['verified'] for r in h['records'])
    assert not recover_headcounts(h,n)
    assert h['records'][0]['boundary']['counting_method'] is None


def test_graph_loader_rejects_dangling_nodes():
    spec=importlib.util.spec_from_file_location('graph_review',Path(__file__).resolve().parents[1]/'scripts/validate_corporate_review.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import pytest
    with pytest.raises(ValueError,match='Dangling'):
        module.graph_import({'nodes':[{'id':'a','type':'Record'}], 'edges':[{'source':'a','target':'absent','type':'SUPPORTED_BY'}]})


def test_normalization_is_once_and_keeps_exact_large_integer():
    r={'value':{'original_value':'8.592,6'},'quality':{'uncertainty':['normalization_unit_or_factor_unknown','pending_human_source_review']}}
    assert _amount(r,'Tỷ đồng',10**9,'VND','Tỷ')
    assert r['value']['normalized_value']==8592600000000
    assert r['value']['original_value']=='8.592,6'
    assert 'normalization_unit_or_factor_unknown' not in r['quality']['uncertainty']
    assert _amount(r,'Tỷ đồng',10**9,'VND','Tỷ')
    assert r['value']['normalized_value']==8592600000000


def test_new_priority_queue_does_not_promote_keyword_only_narrative():
    r=record('text')
    r.update(metric_label='Chăm lo đời sống người lao động',metric_id=None)
    docs=[{'document':{'document_id':'de','company_id':'BSR','report_type':'ESG'},'records':[r]}]
    q=build_review_queue(docs)
    assert q['priority_records']==[] and q['candidate_pairs']==[]
