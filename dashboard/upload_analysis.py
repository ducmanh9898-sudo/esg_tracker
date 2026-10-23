"""Session-isolated PDF uploads and background extraction for Dash."""
import json
import threading
import uuid
from pathlib import Path

from dash import Input, Output, State, dcc, html, dash_table, no_update
from flask import abort, send_file
from dashboard.upload_v2 import process_upload_v2, export_result, record_rows, selected_source, download_filename
from src.extraction.source_v2 import file_hash
from dashboard.extraction_worker import run_isolated_upload, load_job
from dashboard.extraction_history import history_options, load_saved_result
from src.extraction.corporate_handoff import build_delivery, zip_delivery
from dashboard.components.workspace import badge, icon, section_heading, stat_card, empty_state
from dashboard.components.presentation import display_rows, session_summary, review_label, table_filter
from dashboard.graph_review import graph_review_panel, register_graph_review_callbacks
from dashboard.graph_upload import run_graph_for_upload
from dashboard.graph_upload import read_graph_status
from dashboard.progress_view import progress_card, graph_result_message
from dashboard.extraction_worker import job_folder
from src.extraction.source_v2 import atomic_json

JOBS = {}
LOCK = threading.Lock()


def upload_panel():
    return html.Div([
        html.Section([
            html.Div([
                html.Div([html.Span('ESG ANALYSIS WORKSPACE', className='section-kicker'),
                          html.H1(['Hiểu báo cáo. ', html.Span('Rõ bằng chứng.')]),
                          html.P('Từ tài liệu gốc đến từng claim có thể truy vết. Một không gian để trích xuất, rà soát và hỗ trợ phân tích ESG.'),
                          html.A(['Tải báo cáo đầu tiên ', icon('upload')], href='#upload', className='ui-button ui-button--primary')],
                         className='workspace-hero-copy'),
                html.Div([badge('Phiên tải lên hiện tại'), html.Strong('Nguồn rõ ràng.\nĐánh giá thận trọng.'),
                          html.P('Kết quả trích xuất là ứng viên phân tích, không tự động trở thành dữ liệu đã xác minh.')],
                         className='workspace-hero-note'),
            ], className='workspace-hero'),
            html.Div([
                stat_card('Báo cáo trong phiên', 'ui-report-count', 'Chỉ tài liệu của phiên tải lên này', 'archive'),
                stat_card('Tổng claim', 'ui-claim-count', 'Không bao gồm metric, policy hoặc target', 'claims'),
                stat_card('Claim đã rà soát', 'ui-reviewed-count', 'Chỉ tính trạng thái rà soát được lưu rõ ràng', 'evidence'),
                stat_card('Claim chưa rà soát', 'ui-unreviewed-count', 'NOT_REVIEWED · Chưa rà soát', 'overview'),
            ], className='workspace-stats'),
            html.Div([
                html.Div([html.Span('01', className='workflow-number'), html.Strong('Tải báo cáo'), html.Small('ESG · BCTC · Thường niên')]),
                html.Div([html.Span('02', className='workflow-number'), html.Strong('Trích xuất claim'), html.Small('Giữ nguyên văn & vị trí nguồn')]),
                html.Div([html.Span('03', className='workflow-number'), html.Strong('Rà soát bằng chứng'), html.Small('Phân biệt từng loại kiểm tra')]),
                html.Div([html.Span('04', className='workflow-number'), html.Strong('Xem kết quả'), html.Small('Xuất JSON kèm nguồn truy vết')]),
            ], className='workspace-workflow'),
        ], id='overview'),
        html.Section([
            section_heading('01 / TẢI & TRÍCH XUẤT', 'Bắt đầu từ báo cáo gốc',
                            'Chọn tài liệu, kiểm tra thông tin và bắt đầu trích xuất. Mỗi số liệu đều cần có nguồn.'),
            html.Div([
                html.Div([
                    dcc.Upload(id='analysis-upload', multiple=True, accept='.pdf', className='extract-dropzone',
                        className_active='extract-dropzone extract-dropzone-active', children=html.Div([
                            html.Div(icon('upload'), className='extract-upload-icon'),
                            html.Strong('Kéo thả báo cáo vào đây'),
                            html.Div(['hoặc ', html.Button('Chọn file từ máy tính', type='button', className='upload-file-button')]),
                            html.Small('PDF · Tối đa 20 file/lần · 100 MB/file · 250 MB/lần tải'),
                        ])),
                    html.Div(id='analysis-file-list', className='extract-files', **{'aria-live': 'polite'}),
                    html.Div([badge('Tài liệu của bạn', 'neutral'), html.P('PDF nguồn được giữ nguyên. Kết quả mới không tự nhập vào dashboard dữ liệu đã lưu.')],
                             className='upload-source-note'),
                ], className='upload-drop-column'),
                html.Div([
                    html.H3('Thông tin trích xuất'),
                    html.Div([
                        html.Div([html.Label('Mã doanh nghiệp', htmlFor='analysis-company'),
                                  dcc.Input(id='analysis-company', placeholder='Ví dụ: BSR, PLX'),
                                  html.Small('Để trống để nhận diện từ tên file.')], className='extract-field'),
                        html.Div([html.Label('Năm báo cáo', htmlFor='analysis-year'),
                                  dcc.Input(id='analysis-year', type='number', placeholder='Ví dụ: 2025'),
                                  html.Small('Không tự dùng làm kỳ của từng chỉ tiêu.')], className='extract-field'),
                    ], className='extract-form'),
                    html.Div([html.Label('Loại báo cáo', htmlFor='analysis-type'),
                              dcc.Dropdown(id='analysis-type', options=[{'label': 'Tự nhận diện', 'value': 'auto'},
                                {'label': 'Báo cáo ESG', 'value': 'ESG'}, {'label': 'Báo cáo thường niên', 'value': 'annual_report'},
                                {'label': 'Báo cáo tài chính', 'value': 'financial_statements'}], value='auto', clearable=False)],
                             className='extract-field'),
                    html.Div([html.Label('Quy ước số', htmlFor='analysis-number-format'),
                              dcc.Dropdown(id='analysis-number-format', options=[
                                {'label': 'Tự động — giữ số chưa rõ để rà soát', 'value': 'auto'},
                                {'label': 'Việt Nam: 1.594 = 1594; 1,5 = 1.5', 'value': 'vi'},
                                {'label': 'English: 1,594 = 1594; 1.5 = 1.5', 'value': 'en'}], value='auto', clearable=False),
                              html.Small('Chỉ chọn sau khi kiểm tra định dạng trong báo cáo.')], className='extract-field'),
                    html.Button('Trích xuất và phân tích →', id='analysis-start', n_clicks=0, className='extract-primary'),
                    html.Small('Xử lý toàn bộ trang · Thời gian phụ thuộc chất lượng PDF', className='extract-action-note'),
                ], className='upload-settings'),
            ], className='workspace-card upload-grid'),
            html.Div([
                html.H3('Lịch sử trích xuất'),
                html.P('Kết quả được lưu trên máy này. Mở lại để xem dữ liệu và tải JSON/PDF, không cần trích xuất lại. Không tự nhập vào dashboard lưu trữ.'),
                html.Div([html.Label('Kết quả đã lưu', htmlFor='analysis-history'),
                          dcc.Dropdown(id='analysis-history', options=[], placeholder='Chọn lần trích xuất trước...',
                                       optionHeight=72, persistence=True, persistence_type='local')], className='extract-field'),
                html.Div([html.Button('Mở kết quả đã lưu', id='analysis-history-open', n_clicks=0, className='ui-button ui-button--primary'),
                          html.Button('Làm mới danh sách', id='analysis-history-refresh', n_clicks=0, className='ui-button')],
                         style={'display': 'flex', 'gap': '12px', 'flexWrap': 'wrap', 'marginTop': '12px'}),
                html.Div(id='analysis-history-note', role='status', **{'aria-live': 'polite'}),
                html.Div(id='analysis-history-feedback', role='status', **{'aria-live': 'polite'}),
            ], className='workspace-card', style={'padding': '24px', 'marginTop': '20px'}),
            dcc.Store(id='analysis-job', storage_type='session'), dcc.Interval(id='analysis-poll', interval=2000),
            html.Div(id='analysis-status', role='status', className='extract-status', **{'aria-live': 'polite'}),
            html.Div([html.Button('↻ Thử lại trích xuất', id='ui-retry', n_clicks=0, className='ui-button ui-button--secondary'),
                      html.Small('Giữ file đã chọn và thông tin của lần chạy trước.'),
                      html.Span(id='ui-retry-feedback', role='status')], id='ui-retry-help', hidden=True),
            html.Div(id='analysis-results', className='extract-results'),
        ], id='upload', className='workspace-section'),
        html.Section([
            section_heading('02 / DỮ LIỆU TRÍCH XUẤT', 'Danh sách claim & dữ liệu',
                            'Tìm nội dung cần xem, lọc theo nguồn và chọn một dòng để đối chiếu. Trích xuất không đồng nghĩa đã rà soát.'),
            html.Div([
                html.Div([
                    html.Div([html.Label('Tìm kiếm', htmlFor='ui-search'), dcc.Input(id='ui-search', type='search', debounce=True, placeholder='Nội dung, chỉ tiêu hoặc tên file…')], className='extract-field search-field'),
                    html.Div([html.Label('Doanh nghiệp', htmlFor='ui-company'), dcc.Dropdown(id='ui-company', placeholder='Tất cả')], className='extract-field'),
                    html.Div([html.Label('Năm báo cáo', htmlFor='ui-year'), dcc.Dropdown(id='ui-year', placeholder='Tất cả')], className='extract-field'),
                    html.Div([html.Label('Trụ cột', htmlFor='ui-pillar'), dcc.Dropdown(id='ui-pillar', options=[{'label': p, 'value': p} for p in ('E', 'S', 'G')], placeholder='Tất cả')], className='extract-field'),
                    html.Div([html.Label('Trạng thái', htmlFor='ui-review'), dcc.Dropdown(id='ui-review', options=[
                        {'label': 'Chưa rà soát · NOT_REVIEWED', 'value': 'NOT_REVIEWED'},
                        {'label': 'Đã rà soát (có trạng thái lưu)', 'value': 'REVIEWED'}], placeholder='Tất cả')], className='extract-field'),
                    html.Div([html.Label('Loại dữ liệu', htmlFor='ui-type'), dcc.Dropdown(id='ui-type', options=[
                        {'label': label, 'value': value} for value, label in [('claim','Claim'),('policy','Chính sách'),('action','Hành động'),
                        ('target','Mục tiêu'),('governance','Quản trị'),('metric','Chỉ tiêu'),('measurement','Số đo'),('financial_context','Thuyết minh tài chính')]], placeholder='Tất cả')], className='extract-field'),
                ], className='claim-filters'),
                html.Div(id='ui-table-summary', className='table-summary', role='status'),
                html.Div(id='ui-table-empty'),
                dash_table.DataTable(id='analysis-records', data=[], columns=[{'name': label, 'id': key} for key, label in [
                    ('company', 'Doanh nghiệp'), ('report_year', 'Năm báo cáo'), ('pillar', 'E/S/G'), ('type', 'Loại'),
                    ('indicator', 'Chỉ tiêu / nội dung'), ('original_text', 'Nguyên văn'), ('value', 'Giá trị'),
                    ('unit', 'Đơn vị'), ('page', 'Trang PDF'), ('review_label', 'Trạng thái rà soát'),
                    ('file', 'Tên tài liệu')]],
                    row_selectable='single', selected_row_ids=[], page_size=10,
                    filter_action='native', sort_action='native', style_table={'overflowX': 'auto'},
                    style_cell={'fontFamily': 'Inter, Segoe UI, sans-serif', 'fontSize': 13, 'padding': '14px 16px',
                                'whiteSpace': 'normal', 'height': 'auto', 'minWidth': '95px', 'maxWidth': '300px',
                                'color': '#172B22', 'border': '1px solid #DFE8E2'},
                    style_header={'backgroundColor': '#F0FDF4', 'color': '#14532D', 'fontWeight': 650},
                    style_data_conditional=[{'if': {'state': 'selected'}, 'backgroundColor': '#F0FDF4', 'border': '1px solid #15803D'}]),
            ], className='workspace-card claim-table-card'),
        ], id='claims', className='workspace-section'),
        html.Section([
            section_heading('03 / RÀ SOÁT BẰNG CHỨNG', 'Từ claim đến vị trí nguồn',
                            'Xem nguyên văn, tài liệu, trang PDF và các trường chưa xác định. Chưa có thao tác duyệt hoặc xác minh tự động.'),
            html.Div([
                html.Div([html.H3('Đối chiếu với báo cáo tài chính'), badge('Chưa có kết quả đối chiếu tài chính'),
                          html.P('Trích xuất BCTC và liên kết ứng viên không được tính là claim đã đối chiếu tài chính.')], className='check-lane'),
                html.Div([html.H3('Nhất quán nội bộ báo cáo ESG'), badge('Kiểm tra nội bộ — tách riêng'),
                          html.P('Không cộng các liên kết nội bộ ESG vào số claim đã đối chiếu tài chính.')], className='check-lane'),
            ], className='comparison-lanes'),
            html.Div(id='analysis-source-detail', className='workspace-card evidence-detail'),
            html.Div([
                html.Div([html.Label('Tài liệu PDF nguồn', htmlFor='analysis-source-document'),
                          dcc.Dropdown(id='analysis-source-document', options=[], placeholder='Chọn tài liệu sau khi trích xuất')], className='extract-field'),
                html.A('Mở PDF gốc ↗', id='analysis-source-link', target='_blank', rel='noopener noreferrer', hidden=True, className='ui-button ui-button--secondary'),
                html.Button('↓ Tải PDF gốc', id='analysis-source-download-button', n_clicks=0, className='extract-secondary', disabled=True),
                dcc.Download(id='analysis-source-download'),
            ], className='source-actions workspace-card'),
        ], id='evidence', className='workspace-section'),
        graph_review_panel(),
        html.Section([
            section_heading('04 / KẾT QUẢ', 'Mang theo dữ liệu và bằng chứng',
                            'JSON giữ dữ liệu ứng viên, vị trí nguồn và danh sách cần rà soát. Không tự tạo điểm ESG hoặc kết luận greenwashing.'),
            html.Div([html.Div([html.H3('Gói kết quả trích xuất'), html.P('Có nguyên văn, nguồn native, coverage và các trường còn thiếu. PDF gốc được tải riêng.'),
                               badge('Cần rà soát trước khi đưa vào báo cáo', 'warning')]),
                      html.Div([html.Button('↓ Tải kết quả JSON v2', id='analysis-download-button', n_clicks=0, className='extract-primary', disabled=True),
                                dcc.Download(id='analysis-download'),
                                html.Div(id='analysis-download-status', role='status', **{'aria-live': 'polite'}),
                                html.Button('↓ Tải gói bàn giao chuẩn (ZIP)', id='analysis-handoff-button', n_clicks=0,
                                            className='ui-button ui-button--secondary', disabled=True, style={'marginTop': '12px'}),
                                dcc.Download(id='analysis-handoff-download'),
                                dcc.Loading(html.Div(id='analysis-handoff-status', role='status', **{'aria-live': 'polite'})),
                                html.Small('PDF + JSON corporate-extract-1.0 + manifest + validator. Dữ liệu vẫn cần người rà soát.')])],
                     className='workspace-card export-card'),
        ], id='results', className='workspace-section'),
    ], className='extract-panel')


def process_upload(root, contents, filenames, company=None, year=None, report_type=None, progress_callback=None, number_format='auto'):
    return process_upload_v2(root, contents, filenames, company, year, report_type, progress_callback, number_format)


def job_result(job, root=None):
    if not isinstance(job, dict) or not isinstance(job.get('id'), str):
        return None
    with LOCK:
        result = JOBS.get(job['id'])
    return result if result is not None else load_saved_result(root, job['id']) if root is not None else None


def source_pdf(result, document_index):
    if not result or result['status'] != 'completed':
        return None
    for doc in result['documents']:
        if str(doc['document_index']) == str(document_index):
            work = Path(doc['workspace']).resolve()
            artifact = next(a for a in doc['output']['source_artifacts'] if a['kind'] == 'pdf')
            path = (work / artifact['path']).resolve()
            if not path.is_relative_to(work) or not path.is_file() or file_hash(path) != artifact['sha256']:
                raise ValueError('PDF nguồn đã thay đổi hoặc không còn truy cập được.')
            return path, doc['filename']
    return None


def render_source(selection):
    if not selection:
        return empty_state('Chưa chọn dữ liệu để rà soát', 'Chọn nút tròn ở một dòng trong danh sách để xem nội dung và vị trí nguồn.')
    record = selection['record']
    sources = []
    for field, refs in record.get('field_sources', {}).items():
        for ref in refs:
            sources.append({'field': field, **ref})
    locations = {}
    for source in sources:
        key = (source.get('pdf_page'), source.get('native_json_pointer'))
        locations.setdefault(key, source)
    visible_locations = list(locations.values())[:6]
    state, label = review_label(record)
    return [html.Div([
        html.Div([html.Div([html.H3('Nội dung trích xuất'), badge(label, code=state)], className='evidence-card-head'),
                  html.Blockquote(record.get('original_text') or 'Không có nguyên văn trong record này.', className='claim-quote'),
                  html.Dl([html.Dt('Tài liệu'), html.Dd(selection['filename']),
                           html.Dt('Loại dữ liệu'), html.Dd(record['record_type']),
                           html.Dt('Mã record'), html.Dd(record['record_id']),
                           html.Dt('Trạng thái nguồn'), html.Dd(record.get('review', {}).get('status') or 'Chưa xác định')]),
                  html.P('Màu nhận diện không biểu thị claim đã được xác minh.', className='detail-note')], className='evidence-pane'),
        html.Div([html.H3('Bằng chứng & vị trí nguồn'),
                  html.P('Các vị trí bên dưới là nguồn của nội dung trích xuất, chưa phải kết quả đối chiếu tài chính.'),
                  html.Ul([html.Li([html.Strong(f"Trang PDF {source.get('pdf_page') or 'chưa rõ'}"),
                                   html.Code(source['field']), html.Small(source.get('native_json_pointer'))], className='source-location') for source in visible_locations])
                  if sources else empty_state('Chưa có vị trí nguồn theo field', 'Không suy đoán trang hoặc JSON pointer khi chưa có dữ liệu.'),
                  html.P(f"{len(locations)} vị trí nguồn riêng biệt. Toàn bộ field và vị trí nằm trong mục dữ liệu kỹ thuật bên dưới.", className='detail-note') if sources else None,
                  html.H4('Ghi chú / lý do cần rà soát'),
                  html.Ul([html.Li(note) for note in record.get('interpretation_notes', [])])
                  if record.get('interpretation_notes') else html.P('Chưa có ghi chú diễn giải được lưu. Không tự tạo lý do đánh giá.'),
                  html.P(f"{len(record.get('missing_fields', []))} trường còn thiếu hoặc chưa xác định.", className='detail-note')], className='evidence-pane'),
        ], className='evidence-grid'),
            html.Details([html.Summary('Dữ liệu kỹ thuật & nguồn truy vết'),
            html.Details([html.Summary('Vị trí nguồn theo field — hash, bbox và raw text'), html.Pre(json.dumps(sources, ensure_ascii=False, indent=2), style={'whiteSpace': 'pre-wrap'})]),
            html.Details([html.Summary('Các ô nguồn của record'), html.Pre(json.dumps(record.get('original_cells'), ensure_ascii=False, indent=2), style={'whiteSpace': 'pre-wrap'})]),
            html.Details([html.Summary('Boundary và field còn thiếu'), html.Pre(json.dumps({'boundary': record['boundary'], 'missing_fields': record['missing_fields']}, ensure_ascii=False, indent=2), style={'whiteSpace': 'pre-wrap'})]),
            html.Details([html.Summary('Source blocks nguyên bản'), html.Pre(json.dumps(selection['source_blocks'], ensure_ascii=False, indent=2), style={'whiteSpace': 'pre-wrap'})])], className='source-technical')]


def register_upload_callbacks(app, root):
    register_graph_review_callbacks(app, root)
    @app.callback(Output('analysis-history', 'options'), Output('analysis-history-note', 'children'),
                  Input('analysis-history-refresh', 'n_clicks'), Input('analysis-job', 'data'),
                  Input('analysis-poll', 'n_intervals'))
    def refresh_history(clicks, job, tick):
        options = history_options(root)
        return options, (f'{len(options)} lần trích xuất đã lưu. Chưa được xác minh tự động.' if options
                         else 'Chưa có kết quả đã lưu. Kết quả sẽ xuất hiện sau khi trích xuất kết thúc.')

    # UUID is the per-job capability, not a user-provided filesystem path.
    @app.server.get('/extract-source/<job_id>/<int:document_index>')
    def view_pdf(job_id, document_index):
        try:
            found = source_pdf(job_result({'id': job_id}, root), document_index)
        except (ValueError, OSError):
            abort(409)
        if not found:
            abort(404)
        response = send_file(found[0], mimetype='application/pdf', as_attachment=False, download_name=found[1])
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @app.callback(Output('analysis-file-list', 'children'), Input('analysis-upload', 'filename'))
    def filenames(names):
        return [html.Div([icon('archive'), html.Strong(name), badge('PDF')], className='upload-file-chip')
                for name in (names if isinstance(names, list) else [names] if names else [])]

    @app.callback(Output('analysis-job', 'data'), Input('analysis-start', 'n_clicks'),
                  State('analysis-upload', 'contents'), State('analysis-upload', 'filename'),
                  State('analysis-company', 'value'), State('analysis-year', 'value'), State('analysis-type', 'value'), State('analysis-number-format', 'value'),
                  prevent_initial_call=True)
    def start(clicks, contents, names, company, year, kind, number_format):
        if not contents:
            return {'error': 'Hãy chọn ít nhất một file PDF.'}
        job_id = uuid.uuid4().hex
        with LOCK:
            JOBS[job_id] = {'status': 'running'}
        def work():
            def progress(event):
                with LOCK:
                    JOBS[job_id]['progress'] = event
            try:
                result = run_isolated_upload(root, job_id, contents, names, company, year,
                    None if kind == 'auto' else kind, progress, number_format)
            except Exception as exc:
                result = {'status': 'failed', 'error': str(exc)}
            if result.get('status') == 'completed':
                try:
                    result['graph_review'] = run_graph_for_upload(root, job_id, result, progress)
                except Exception as exc:
                    result['graph_review'] = {'status': 'failed', 'reason': f'{type(exc).__name__}: {exc}'}
                atomic_json(job_folder(root, job_id) / 'result.json', result)
            with LOCK:
                JOBS[job_id] = result
        threading.Thread(target=work, daemon=True).start()
        return {'id': job_id, 'files': names}

    @app.callback(Output('analysis-job', 'data', allow_duplicate=True),
                  Output('analysis-history-feedback', 'children'),
                  Input('analysis-history-open', 'n_clicks'), State('analysis-history', 'value'),
                  State('analysis-job', 'data'), prevent_initial_call=True)
    def open_history(clicks, saved_id, current):
        active = job_result(current, root)
        if active and active.get('status') == 'running':
            return no_update, 'Đang trích xuất. Hãy chờ kết thúc trước khi mở kết quả khác.'
        saved = load_saved_result(root, saved_id)
        if not saved or saved.get('status') != 'completed':
            return no_update, 'Hãy chọn kết quả còn được lưu trên máy; bấm làm mới nếu danh sách đã thay đổi.'
        with LOCK:
            JOBS[saved_id] = saved
        return {'id': saved_id, 'files': [d['filename'] for d in saved['documents']]}, 'Đã mở kết quả đã lưu; không chạy lại OCR. Xem danh sách dữ liệu và tải JSON bên dưới.'

    @app.callback(Output('analysis-status', 'children'), Output('analysis-results', 'children'),
                  Output('analysis-records', 'data'), Output('analysis-source-document', 'options'),
                  Output('analysis-download-button', 'disabled'), Output('analysis-start', 'disabled'),
                  Output('analysis-poll', 'disabled'), Output('analysis-records', 'selected_row_ids'),
                  Input('analysis-poll', 'n_intervals'), Input('analysis-job', 'data'))
    def poll(tick, job):
        if not job:
            return '○ Sẵn sàng nhận tài liệu. Tải báo cáo đầu tiên để bắt đầu trích xuất có nguồn.', [], [], [], True, False, True, []
        if job.get('error'):
            return job['error'], [], [], [], True, False, True, []
        result = job_result(job, root) or {'status': 'failed', 'error': 'Không tìm thấy phiên xử lý. Hãy tải lại cùng file để tiếp tục checkpoint đã lưu.'}
        graph_status = read_graph_status(root, job['id']) if len(job['id']) == 32 else None
        if result['status'] == 'running':
            event = result.get('progress', {})
            if graph_status and graph_status.get('status') == 'running' and event.get('stage') not in ('graph_delivery', 'knowledge_graph'):
                event = {'stage': 'graph_delivery' if graph_status.get('stage') == 'delivery' else 'knowledge_graph'}
            return progress_card(event, job.get('files')), [], [], [], True, True, False, []
        if result['status'] == 'failed':
            return result['error'], [], [], [], True, False, True, []
        if graph_status and graph_status.get('status') == 'running':
            stage = 'graph_delivery' if graph_status.get('stage') == 'delivery' else 'knowledge_graph'
            return progress_card({'stage': stage}, job.get('files')), [], [], [], True, True, False, []
        manifest = result['manifest']
        documents = result['documents']
        rows = display_rows(result)
        issues = [(d, i) for d in documents for i in d['output']['issues']]
        failures = [html.Li(f"{f['filename']}: {f['error']}") for f in manifest['failures']]
        coverage = [html.Li(f"{d['filename']} — {d['output']['reports'][0]['company_id']} / {d['output']['reports'][0]['reporting_year']} / {d['output']['reports'][0]['report_type']} — {d['coverage']['counts'].get('processed', 0)}/{d['coverage']['total_pages']} trang thành công; capture: {d['capture_status']}; semantic: partial") for d in documents]
        incomplete = sum(d['capture_status'] != 'completed' for d in documents)
        options = [{'label': d['filename'], 'value': d['document_index']} for d in documents]
        return html.Div([
            html.Strong(f"Đã trích xuất {len(documents)}/{manifest['document_count']} tài liệu."),
            html.Div(f"{len(rows)} dữ liệu trích xuất · {len(issues)} mục cần rà soát · {len(failures)} tài liệu lỗi · {incomplete} tài liệu chưa đọc đủ trang."),
            html.Div(graph_result_message(graph_status), className='analysis-graph-result'),
        ]), [
            html.P('Pipeline v2 · dữ liệu ứng viên phân tích, không phải kiểm toán hoặc kết luận greenwashing. Chọn record trong bảng bên dưới để đối chiếu nguồn. Metadata nhận diện từ tên file cần được kiểm tra.'),
            html.Ul(coverage), html.Ul(failures),
            html.Details([html.Summary(f'Cần rà soát ({len(issues)} mục; hiển thị tối đa 100, JSON chứa toàn bộ)'),
                          html.Ul([html.Li(f"{d['filename']} / trang {i.get('pdf_page')}: {i.get('code')} — {i.get('details')}") for d, i in issues[:100]])]),
        ], rows, options, False, False, True, []

    @app.callback(Output('analysis-source-detail', 'children'), Output('analysis-source-document', 'value'),
                  Input('analysis-records', 'selected_row_ids'), Input('analysis-job', 'data'))
    def source_detail(selected, job):
        result = job_result(job, root)
        if not result or result['status'] != 'completed' or not selected:
            return render_source(None), None
        selection = selected_source(result, selected[0])
        return render_source(selection), int(selected[0].split(':', 1)[0]) if selection else None

    @app.callback(Output('analysis-source-link', 'href'), Output('analysis-source-link', 'hidden'),
                  Output('analysis-source-download-button', 'disabled'),
                  Input('analysis-source-document', 'value'), Input('analysis-job', 'data'), Input('analysis-records', 'selected_row_ids'))
    def source_link(index, job, selected):
        result = job_result(job, root)
        if not result or result['status'] != 'completed' or not any(str(d['document_index']) == str(index) for d in result['documents']):
            return '', True, True
        anchor = ''
        if selected and str(selected[0]).split(':', 1)[0] == str(index):
            selection = selected_source(result, selected[0])
            if selection:
                refs = [s for sources in selection['record'].get('field_sources', {}).values() for s in sources]
                if refs:
                    anchor = f"#page={refs[0]['pdf_page']}"
        return f"/extract-source/{job['id']}/{index}{anchor}", False, False

    @app.callback(Output('analysis-source-download', 'data'), Input('analysis-source-download-button', 'n_clicks'),
                  State('analysis-source-document', 'value'), State('analysis-job', 'data'), prevent_initial_call=True)
    def download_pdf(clicks, index, job):
        try:
            found = source_pdf(job_result(job, root), index)
        except (ValueError, OSError):
            return no_update
        return dcc.send_file(str(found[0]), filename=found[1]) if found else no_update

    @app.callback(Output('analysis-download', 'data'), Output('analysis-download-status', 'children'), Input('analysis-download-button', 'n_clicks'),
                  State('analysis-job', 'data'), prevent_initial_call=True)
    def download(clicks, job):
        if not job or not job.get('id'):
            return no_update, 'Chưa có kết quả để tải.'
        result = job_result(job, root)
        if not result or result['status'] != 'completed':
            return no_update, 'Chưa có kết quả để tải.'
        try:
            exported = export_result(result)
        except (ValueError, OSError) as exc:
            return no_update, str(exc)
        filename = download_filename(result)
        return dcc.send_string(json.dumps(exported, ensure_ascii=False, indent=2), filename), f'Đã tạo {filename}, gồm nguồn native và các mục cần rà soát.'

    @app.callback(Output('analysis-handoff-button', 'disabled'),
                  Input('analysis-job', 'data'), Input('analysis-poll', 'n_intervals'))
    def handoff_enabled(job, tick):
        result = job_result(job, root)
        return not bool(result and result.get('status') == 'completed' and result.get('documents'))

    @app.callback(Output('analysis-handoff-download', 'data'), Output('analysis-handoff-status', 'children'),
                  Input('analysis-handoff-button', 'n_clicks'), State('analysis-job', 'data'), prevent_initial_call=True)
    def download_handoff(clicks, job):
        result = job_result(job, root)
        if not result or result.get('status') != 'completed':
            return no_update, 'Chưa có kết quả để bàn giao.'
        destination = Path(root) / 'data/processed/corporate_deliveries' / uuid.uuid4().hex
        try:
            provenance_path = Path(root) / 'config/bsr_verified_sources_20261016.json'
            provenance = json.loads(provenance_path.read_text(encoding='utf-8')) if provenance_path.is_file() else {}
            summary = build_delivery(result, destination, source_info=provenance)
            archive = zip_delivery(destination)
        except (ValueError, OSError, KeyError) as exc:
            return no_update, f'Chưa tạo được gói đạt hợp đồng: {exc}'
        return dcc.send_file(str(archive), filename='ESG_corporate_extract_' + destination.name[:12] + '.zip'), (
            f"Gói partial: {summary['partial_documents']} tài liệu; {summary['blocked_documents']} tài liệu bị chặn. "
            'Kiểm tra nguồn chính thức, issue_log và validation/report.json trước khi bàn giao. Không phải dữ liệu đã xác minh.')

    @app.callback(Output('ui-report-count', 'children'), Output('ui-claim-count', 'children'),
                  Output('ui-reviewed-count', 'children'), Output('ui-unreviewed-count', 'children'),
                  Output('ui-company', 'options'), Output('ui-year', 'options'),
                  Output('analysis-status', 'className'), Output('ui-retry-help', 'hidden'),
                  Input('analysis-job', 'data'), Input('analysis-records', 'data'), Input('analysis-poll', 'n_intervals'))
    def presentation(job, rows, tick):
        result = job_result(job, root)
        summary = session_summary(result)
        counts = [str(summary[key]) for key in ('reports', 'claims', 'reviewed', 'unreviewed')] if summary else ['—'] * 4
        rows = rows or []
        companies = sorted({r['company'] for r in rows if r.get('company')})
        years = sorted({r['report_year'] for r in rows if r.get('report_year') is not None})
        failed = bool(job and (job.get('error') or result and result.get('status') == 'failed'))
        status = 'error' if failed else 'running' if result and result.get('status') == 'running' else 'completed' if summary else 'empty'
        return (*counts, [{'label': c, 'value': c} for c in companies], [{'label': str(y), 'value': y} for y in years],
                f'extract-status extract-status--{status}', not failed)

    @app.callback(Output('analysis-records', 'filter_query'),
                  Input('ui-search', 'value'), Input('ui-company', 'value'), Input('ui-year', 'value'),
                  Input('ui-pillar', 'value'), Input('ui-review', 'value'), Input('ui-type', 'value'))
    def filter_records(search, company, year, pillar, review, kind):
        return table_filter(search, company, year, pillar, review, kind)

    @app.callback(Output('ui-table-summary', 'children'), Output('ui-table-empty', 'children'),
                  Input('analysis-records', 'data'), Input('analysis-records', 'derived_virtual_data'))
    def table_state(rows, visible):
        rows = rows or []
        shown = rows if visible is None else visible
        claims = sum(r.get('type') == 'claim' for r in shown)
        if not rows:
            return 'Chưa có dữ liệu trong phiên', empty_state('Báo cáo đầu tiên bắt đầu ở đây',
                'Tải báo cáo để trích xuất claim và dữ liệu có nguồn. Không sử dụng số liệu minh họa cho phiên này.',
                html.A('Tải báo cáo', href='#upload', className='ui-button ui-button--secondary'))
        if not shown:
            return f'0 / {len(rows)} record', empty_state('Không có kết quả phù hợp', 'Xóa nội dung tìm kiếm hoặc điều chỉnh các bộ lọc phía trên.')
        return f'{len(shown)} / {len(rows)} record · {claims} claim · Các loại dữ liệu khác được tính riêng', []

    app.clientside_callback("""function(n) {
        if (!n) return window.dash_clientside.no_update;
        const button = document.getElementById('analysis-start');
        if (button && !button.disabled) button.click();
        return 'Đã yêu cầu thử lại với file đã chọn.';
    }""", Output('ui-retry-feedback', 'children'), Input('ui-retry', 'n_clicks'), prevent_initial_call=True)
