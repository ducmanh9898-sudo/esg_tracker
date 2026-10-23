"""Reusable, presentation-only Dash components for the analysis workspace."""
from dash import html


def icon(name):
    # One monochrome geometric icon vocabulary; no decorative leaf graphics.
    return html.Span({'overview': '▦', 'upload': '↑', 'claims': '≡', 'evidence': '⌕',
                      'results': '↓', 'archive': '▤'}.get(name, '○'),
                     className='ui-icon', **{'aria-hidden': 'true'})


def badge(label, tone='neutral', code=None):
    return html.Span([html.Span({'neutral': '○', 'success': '✓', 'warning': '!', 'error': '×', 'info': '↻'}[tone],
                               **{'aria-hidden': 'true'}), label,
                      html.Code(code) if code else None], className=f'ui-badge ui-badge--{tone}')


def section_heading(step, title, description, action=None):
    return html.Div([html.Div([html.Span(step, className='section-kicker'), html.H2(title),
                              html.P(description)]), action], className='workspace-section-heading')


def stat_card(label, component_id, help_text, symbol):
    return html.Div([html.Div([html.Span(label), icon(symbol)], className='stat-heading'),
                     html.Div('—', id=component_id, className='stat-value'),
                     html.P(help_text)], className='stat-card')


def empty_state(title, description, action=None):
    return html.Div([html.Span('○', className='empty-mark', **{'aria-hidden': 'true'}),
                     html.Strong(title), html.P(description), action], className='ui-empty')


def workspace_shell(content, archive):
    navigation = [('overview', 'Tổng quan'), ('upload', 'Tải báo cáo'), ('claims', 'Danh sách claim'),
                  ('evidence', 'Rà soát bằng chứng'), ('graph-review', 'Đối chiếu BSR'),
                  ('results', 'Xem kết quả')]
    return html.Div([
        html.A('Bỏ qua điều hướng, đến nội dung', href='#workspace-main', className='skip-link'),
        html.Aside([
            html.A([html.Span('ESG', className='brand-wordmark'), html.Span('Tracker', className='brand-name')],
                   href='#overview', className='workspace-brand', **{'aria-label': 'ESG Tracker — Tổng quan'}),
            html.Div('KHÔNG GIAN PHÂN TÍCH', className='nav-caption'),
            html.Nav([html.A([icon(key), html.Span(label)], href=f'#{key}',
                            className='workspace-nav-link' + (' is-active' if key == 'overview' else ''),
                            **{'aria-current': 'location' if key == 'overview' else 'false'})
                      for key, label in navigation], **{'aria-label': 'Điều hướng chính'}),
            html.Div([html.Span('NGUỒN DỮ LIỆU', className='nav-caption'),
                      html.A([icon('archive'), 'Dữ liệu đã lưu'], href='#archive', className='workspace-nav-link')],
                     className='sidebar-archive'),
            html.Div([badge('Hỗ trợ phân tích', 'neutral'),
                      html.P('Không thay thế kiểm toán độc lập hoặc kết luận greenwashing.')], className='sidebar-note'),
        ], className='workspace-sidebar'),
        html.Main([
            html.Header([html.Div([html.Span('WORKSPACE', className='topbar-kicker'),
                                   html.Span('Phân tích báo cáo ESG', className='topbar-title')]),
                         html.A([icon('upload'), 'Tải báo cáo mới'], href='#upload', className='ui-button ui-button--primary')],
                        className='workspace-topbar'),
            html.Div([content, html.Section([
                section_heading('DỮ LIỆU ĐÃ LƯU', 'Dashboard lưu trữ',
                                'Không thuộc phiên tải lên hiện tại. Bộ lọc và kết quả nghiên cứu trước đây được giữ riêng.'),
                archive], id='archive', className='archive-section'),
                html.Footer(['ESG Tracker', html.Span('Dữ liệu có nguồn · Đánh giá có giới hạn · Luôn cần rà soát')],
                            className='workspace-footer')], className='workspace-content'),
        ], id='workspace-main', className='workspace-main', tabIndex=-1),
    ], className='workspace-shell')
