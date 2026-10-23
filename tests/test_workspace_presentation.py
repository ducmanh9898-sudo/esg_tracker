from copy import deepcopy
import json

from dash import Dash

from dashboard.components.presentation import display_rows, session_summary, table_filter
from dashboard.components.workspace import workspace_shell
from dashboard import upload_analysis as ui


def result_fixture():
    def record(kind, rid, review='needs_review'):
        return {'record_id': rid, 'record_type': kind, 'company_id': 'PLX', 'original_text': 'Nội dung ESG',
                'review': {'status': review}, 'classification': {'pillar': 'E'}, 'payload': {}, 'field_sources': {}}
    records = [record('claim', 'claim1'), record('claim', 'claim2', 'verified'), record('policy', 'policy1'),
               record('measurement', 'measurement1')]
    return {'status': 'completed', 'manifest': {'document_count': 1}, 'documents': [
        {'document_index': 0, 'filename': 'PLX_2025.pdf', 'output': {'records': records,
         'reports': [{'reporting_year': 2025}], 'links': [{'relation_type': 'internal_candidate'}]}}]}


def test_counts_only_claims_and_explicit_review_not_candidate_links():
    result = result_fixture()
    before = deepcopy(result)
    assert session_summary(result) == {'reports': 1, 'claims': 2, 'reviewed': 1, 'unreviewed': 1}
    rows = display_rows(result)
    assert rows[0]['status'] == 'needs_review'
    assert rows[0]['review_status'] == 'NOT_REVIEWED'
    assert 'Chưa rà soát' in rows[0]['review_label']
    assert rows[0]['pillar'] == 'E' and rows[0]['report_year'] == 2025
    assert result == before


def test_no_data_not_invented_as_zero_or_score():
    assert session_summary(None) is None
    assert session_summary({'status': 'running'}) is None
    assert session_summary({'status': 'failed'}) is None


def test_filter_input_is_quoted_and_all_dimensions_are_supported():
    query = table_filter('" || {value} > 0', 'PLX', 2025, 'E', 'NOT_REVIEWED', 'claim')
    assert '{company} = "PLX"' in query
    assert '{report_year} = "2025"' in query
    assert '{pillar} = "E"' in query
    assert '{review_label} = "○ Chưa rà soát · NOT_REVIEWED"' in query
    assert '{type} = "claim"' in query
    assert '\\" || {value} > 0' in query
    assert table_filter() == ''


def test_layout_ids_are_unique_and_workflow_and_disclaimers_are_present(tmp_path):
    app = Dash(__name__)
    app.layout = workspace_shell(ui.upload_panel(), 'Dữ liệu lưu trữ độc lập')
    ui.register_upload_callbacks(app, tmp_path)
    ids, nodes = [], {}
    def walk(node):
        if getattr(node, 'id', None):
            ids.append(node.id)
            nodes[node.id] = node
        children = getattr(node, 'children', None)
        for child in children if isinstance(children, list) else [children]:
            if hasattr(child, 'to_plotly_json'):
                walk(child)
    walk(app.layout)
    assert len(ids) == len(set(ids))
    assert set(('overview', 'upload', 'claims', 'evidence', 'results', 'archive')) <= set(ids)
    table = nodes['analysis-records']
    assert {'review_label', 'file'} <= {c['id'] for c in table.columns}
    with app.server.test_client() as client:
        response = client.get('/_dash-layout')
        assert response.status_code == 200
        text = json.dumps(response.json, ensure_ascii=False)
        assert 'NOT_REVIEWED' in text and 'Không cộng' in text


def test_error_state_exposes_retry_without_changing_worker_result(tmp_path):
    app = Dash(__name__)
    app.layout = ui.upload_panel()
    ui.register_upload_callbacks(app, tmp_path)
    callback = next(v['callback'].__wrapped__ for k,v in app.callback_map.items() if 'ui-report-count.children' in k)
    key = 'ui-presentation-test'
    ui.JOBS[key] = {'status': 'failed', 'error': 'OCR dừng'}
    try:
        output = callback({'id': key}, [], 1)
        assert output[:4] == ('—',) * 4
        assert output[-2] == 'extract-status extract-status--error'
        assert output[-1] is False
    finally:
        ui.JOBS.pop(key, None)
