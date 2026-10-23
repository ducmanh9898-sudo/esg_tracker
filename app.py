from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import dash
from dash import Dash, Input, Output, State, callback_context, dash_table, dcc, html
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.database import connect, fetch_df, initialize_database
from src.paths import DATABASE_PATH
from dashboard.upload_analysis import upload_panel, register_upload_callbacks
from dashboard.components.workspace import workspace_shell

# ==============================================================================
# BẢNG ÁNH XẠ THUẬT NGỮ TIẾNG VIỆT CHUẨN ESG
# ==============================================================================

PILLARS_VI = {
    "E": "E - Môi trường (Environmental)",
    "S": "S - Xã hội (Social)",
    "G": "G - Quản trị (Governance)",
    "X": "X - Kết nối tài chính (Financial)",
}

PILLARS_SHORT_VI = {
    "E": "Môi trường (E)",
    "S": "Xã hội (S)",
    "G": "Quản trị (G)",
    "X": "Tài chính (X)",
}

DOC_TYPES_VI = {
    "financial_statements": "Báo cáo tài chính (BCTC)",
    "DEMO_ESG_REPORT": "Báo cáo PTBV mô phỏng (Demo)",
    "ESG": "Báo cáo Phát triển bền vững (ESG)",
}

RELATIONSHIPS_VI = {
    "NOT_REVIEWED": "Chưa rà soát (NOT_REVIEWED)",
    "SUPPORTS": "Được chứng thực (SUPPORTS)",
    "PARTIAL_SUPPORT": "Chứng thực một phần (PARTIAL_SUPPORT)",
    "CONTRADICTS": "Mâu thuẫn trực tiếp (CONTRADICTS)",
    "MISSING": "Thiếu bằng chứng (MISSING)",
    "AMBIGUOUS": "Mơ hồ / Chưa rõ ràng (AMBIGUOUS)",
    "NOT_COMPARABLE": "Không thể so sánh (NOT_COMPARABLE)",
}

RELATIONSHIPS_SHORT_VI = {
    "NOT_REVIEWED": "Chưa rà soát · NOT_REVIEWED",
    "SUPPORTS": "Được chứng thực",
    "PARTIAL_SUPPORT": "Chứng thực một phần",
    "CONTRADICTS": "Mâu thuẫn",
    "MISSING": "Thiếu bằng chứng",
    "AMBIGUOUS": "Mơ hồ",
    "NOT_COMPARABLE": "Không thể so sánh",
}

SEVERITIES_VI = {
    5: "Mức 5 - Rất nghiêm trọng (Mâu thuẫn số liệu)",
    4: "Mức 4 - Nghiêm trọng (Sai lệch phương pháp/ranh giới)",
    3: "Mức 3 - Trung bình (Thiếu sót số liệu trọng yếu)",
    2: "Mức 2 - Thấp (Mơ hồ / chưa quy đổi đơn vị)",
}

SEVERITIES_SHORT_VI = {
    5: "Mức 5 (Rất cao)",
    4: "Mức 4 (Cao)",
    3: "Mức 3 (Trung bình)",
    2: "Mức 2 (Thấp)",
}

RISK_TYPES_VI = {
    "CROSS_DOC_CONTRADICTION": "Mâu thuẫn chéo giữa các tài liệu",
    "TEMPORAL_CONTRADICTION": "Mâu thuẫn chuỗi dữ liệu theo thời gian",
    "SCOPE_SHIFT": "Thay đổi phạm vi tính toán (Scope/Boundary)",
    "UNIT_MISMATCH": "Không khớp đơn vị đo lường",
    "ABS_INTENSITY_MIX": "Pha trộn số tuyệt đối và cường độ",
    "RESTATEMENT_GAP": "Chênh lệch số liệu hồi tố không giải trình",
    "EVIDENCE_GAP": "Thiếu hụt dữ liệu/bằng chứng kiểm chứng",
    "WEAK_TARGET": "Mục tiêu mơ hồ, thiếu mốc hoặc cơ sở",
    "VAGUE_CLAIM": "Phát biểu chung chung, mang tính tiếp thị",
    "BASELINE_SHIFT": "Thay đổi năm cơ sở không giải trình",
    "GRI_OMISSION": "Thiếu công bố chủ đề trọng yếu theo GRI 11",
    "UNBALANCED_CLAIM": "Công bố thiên lệch (chỉ nêu mặt tích cực)",
    "FUTURE_ONLY": "Chỉ cam kết tương lai, thiếu số liệu tiến độ",
    "SELECTIVE_DISCLOSURE": "Công bố chọn lọc / bỏ sót năm hiện tại",
    "MISSING_METHODOLOGY": "Thiếu phương pháp luận đo lường",
}

METRICS_VI = {
    "GHG_SCOPE_1": "Phát thải trực tiếp Scope 1 (tCO2e)",
    "GHG_SCOPE_2": "Phát thải gián tiếp Scope 2 (tCO2e)",
    "GHG_INTENSITY": "Cường độ phát thải GHG (tCO2e/tấn SP)",
    "ENERGY_TOTAL": "Tổng năng lượng tiêu thụ (GJ)",
    "WATER_WITHDRAWAL": "Khai thác nước đầu vào (m3)",
    "WATER_DISCHARGE": "Lượng nước xả ra (m3)",
    "HAZARDOUS_WASTE": "Chất thải nguy hại (tấn)",
    "NON_HAZ_WASTE": "Chất thải thông thường (tấn)",
    "SPILL_COUNT": "Số vụ sự cố tràn dầu (vụ)",
    "LTIFR": "Tần suất tai nạn mất ngày công (LTIFR)",
    "TRIR": "Tỷ lệ chấn thương ghi nhận (TRIR)",
    "TRAINING_HOURS": "Số giờ đào tạo bình quân (giờ/người)",
    "ENV_CAPEX": "Đầu tư môi trường CAPEX (VND)",
    "ENV_EXPENSE": "Chi phí môi trường OPEX (VND)",
    "ENV_FINE": "Tiền phạt vi phạm môi trường (VND)",
    "TAX_PAID": "Thuế & Nộp ngân sách nhà nước (VND)",
}

TOPICS_VI = {
    "E_CLIMATE": "Khí hậu & Phát thải GHG",
    "E_ENERGY": "Năng lượng & Hiệu quả tiêu thụ",
    "E_INTENSITY": "Cường độ phát thải khí nhà kính",
    "E_SPILLS": "Sự cố tràn dầu & Ứng phó môi trường",
    "E_WASTE": "Quản lý chất thải & Tái chế",
    "E_WATER": "Tài nguyên nước & Nước thải",
    "G_ANTICORRUPTION": "Phòng chống tham nhũng & Liêm chính",
    "G_GOVERNANCE": "Quản trị công ty & Tuân thủ",
    "G_TAX": "Minh bạch thuế & Nộp ngân sách",
    "S_COMMUNITY": "Cộng đồng & Trách nhiệm xã hội",
    "S_SAFETY": "An toàn & Sức khỏe nghề nghiệp",
    "S_TRAINING": "Đào tạo & Phát triển nhân lực",
    "BOARD_STRUCTURE": "Cơ cấu Hội đồng quản trị",
    "ENERGY_EFFICIENCY": "Hiệu quả sử dụng năng lượng",
    "GHG_INTENSITY": "Cường độ phát thải GHG",
    "OCCUPATIONAL_SAFETY": "An toàn lao động",
    "OCCUPATIONAL_HEALTH": "Sức khỏe nghề nghiệp",
    "OPERATING_CASH_FLOW": "Dòng tiền hoạt động kinh doanh",
    "PROFIT_AFTER_TAX": "Lợi nhuận sau thuế",
    "REVENUE": "Doanh thu thuần",
    "TOTAL_ASSETS": "Tổng tài sản",
    "TRAINING": "Đào tạo nhân viên",
    "WATER_REUSE": "Tái sử dụng nước",
    "WATER_WITHDRAWAL": "Khai thác tài nguyên nước",
    "COMMUNITY_INVESTMENT": "Đầu tư phát triển cộng đồng",
    "FINANCIAL_CONNECTIVITY": "Liên kết dữ liệu tài chính",
    "GHG_TOTAL": "Tổng phát thải khí nhà kính",
    "ENERGY_CONSUMPTION": "Tiêu thụ năng lượng",
    "GHG_SCOPE_1_AND_2": "Phát thải Scope 1 & Scope 2",
    "GOVERNANCE_ASSURANCE": "Đảm bảo và kiểm toán quản trị",
    "SPILLS": "Sự cố tràn đổ",
    "WATER_AND_WASTE": "Nước và chất thải",
}

VALUE_KINDS_VI = {
    "ABSOLUTE": "Giá trị tuyệt đối (Absolute)",
    "INTENSITY": "Cường độ / Chỉ số tương đối (Intensity)",
}

COLORS = {
    "SUPPORTS": "#059669",
    "PARTIAL_SUPPORT": "#0284c7",
    "CONTRADICTS": "#dc2626",
    "MISSING": "#d97706",
    "AMBIGUOUS": "#eab308",
    "NOT_COMPARABLE": "#64748b",
}


def ensure_ready():
    initialize_database()
    with connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    if not count:
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "import_data.py")], cwd=ROOT)
        subprocess.check_call([sys.executable, str(ROOT / "scripts" / "run_pipeline.py")], cwd=ROOT)


ensure_ready()


def options(series, mapping=None):
    vals = sorted(v for v in series.dropna().unique())
    if mapping:
        return [{"label": mapping.get(x, str(x)), "value": x} for x in vals]
    return [{"label": str(x), "value": x} for x in vals]


claims_all = fetch_df("""
SELECT c.*, s.risk_score, s.risk_level, s.evidence_coverage, s.confidence score_confidence,
       e.relationship, e.metric_id, e.explanation matching_explanation,
       d.title document_title
FROM claims c JOIN claim_scores s ON s.claim_id=c.claim_id
LEFT JOIN evidence_links e ON e.claim_id=c.claim_id
JOIN documents d ON d.document_id=c.document_id
""")
metrics_all = fetch_df("SELECT * FROM metrics")
rules_all = fetch_df("SELECT * FROM rule_results")
topics_all = fetch_df("SELECT * FROM topic_scores")


def dropdown(label, component_id, opts, value=None, multi=True):
    return dbc.Col([
        html.Label(label, htmlFor=component_id),
        dcc.Dropdown(id=component_id, options=opts, value=value, multi=multi, clearable=True, placeholder="Tất cả...", optionHeight=56)
    ], md=6, lg=4, xl=3)


def card(label, component_id, icon, accent="navy", subtext=None):
    return dbc.Col(html.Div([
        html.Div([
            html.Span(icon, className="kpi-icon"),
            html.Span(label, className="kpi-label")
        ], className="kpi-heading"),
        html.Div(id=component_id, className="kpi-value"),
        html.Div(subtext or "", className="kpi-subtext")
    ], className=f"kpi-card accent-{accent}"), xs=6, md=4, lg=2)


def table(component_id, columns, page_size=10):
    return dash_table.DataTable(
        id=component_id,
        columns=[{"name": name, "id": col} for col, name in columns],
        data=[],
        page_size=page_size,
        sort_action="native",
        filter_action="native",
        row_selectable="single",
        style_table={"overflowX": "auto", "overflowY": "auto", "maxHeight": "620px", "borderRadius": "10px"},
        style_cell={
            "fontFamily": "Inter, Segoe UI, sans-serif",
            "fontSize": 13,
            "padding": "12px 14px",
            "whiteSpace": "normal",
            "height": "auto",
            "maxWidth": 350,
            "minWidth": 110,
            "border": "1px solid #DFE8E2",
            "color": "#172B22",
        },
        style_cell_conditional=[
            {"if": {"column_id": "claim_id"}, "minWidth": 210, "width": 210},
        ] + [
            {"if": {"column_id": col}, "minWidth": 320, "width": 380, "maxWidth": 420}
            for col in ("source_text", "evidence_summary", "explanation")
        ],
        style_header={
            "backgroundColor": "#F0FDF4",
            "color": "#14532D",
            "fontWeight": "700",
            "border": "none",
            "padding": "13px 14px",
            "fontSize": "13px",
            "letterSpacing": "0.01em",
        },
        style_data_conditional=[
            {
                "if": {"filter_query": '{relationship} = "CONTRADICTS" || {relationship_label} contains "Mâu thuẫn"'},
                "backgroundColor": "#fef2f2",
                "color": "#991b1b",
                "fontWeight": "600",
            },
            {
                "if": {"filter_query": '{relationship} = "SUPPORTS" || {relationship_label} contains "chứng thực"'},
                "backgroundColor": "#f0fdf4",
            },
            {
                "if": {"state": "selected"},
                "backgroundColor": "#DCF3E3 !important",
                "border": "1px solid #15803D !important",
            },
        ],
    )


app = Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    assets_folder=str(ROOT / "dashboard" / "assets"),
    suppress_callback_exceptions=True,
    title="ESG Tracker · Phân tích báo cáo có bằng chứng",
)
server = app.server
server.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

app.layout = html.Div([
    upload_panel(),
    dcc.Store(id="tab-scroll-signal"),
    # Top Header Banner
    html.Div(dbc.Row([
        dbc.Col([
            html.Div([
                html.Span("BSR", className="eyebrow-badge"),
                html.Span("DẦU KHÍ QUỐC GIA"),
                html.Span("•"),
                html.Span("GIAI ĐOẠN 2022–2025"),
            ], className="eyebrow"),
            html.H1([
                html.Span("ESG", className="hero-accent"),
                " Tracker BSR"
            ]),
            html.P(
                "Hệ thống sàng lọc rủi ro greenwashing chuyên sâu có giải thích, đối chiếu bằng chứng khoa học và truy xuất nguồn gốc báo cáo phát triển bền vững.",
                className="hero-copy"
            ),
        ], lg=8),
        dbc.Col(html.Div([
            html.Div([
                html.Span("🤖 HỆ LUẬT CHUYÊN GIA", className="hero-badge hero-badge-blue"),
                html.Span("🌿 CHUẨN GRI 11 DẦU KHÍ", className="hero-badge hero-badge-green"),
            ], className="hero-badges-wrap"),
            html.Div("Phiên bản phân tích nghiên cứu (Research Edition)", className="hero-version"),
        ], className="hero-meta"), lg=4),
    ], align="center"), className="header"),

    # Scope Notice / Disclaimer
    html.Div([
        html.Span("ℹ", className="notice-icon"),
        html.Div([
            html.Strong("Phạm vi & Giới hạn sử dụng: "),
            html.Span(
                "Công cụ phục vụ nghiên cứu và hỗ trợ sàng lọc rủi ro công bố ESG, không thay thế ý kiến kiểm toán độc lập hay kết luận pháp lý. Dữ liệu thử nghiệm (Demo) và dữ liệu thực tế trích xuất từ các tài liệu BSR luôn được gắn nhãn minh bạch riêng biệt."
            )
        ])
    ], className="notice"),

    # Multi-dimensional Filters Bar
    html.Div([
        html.Div([
            html.Div([
                html.Span([
                    html.Span("⚡", className="filter-title-icon"),
                    "Bộ lọc phân tích đa chiều"
                ], className="filter-title"),
                html.Span("Áp dụng đồng bộ tức thì trên toàn bộ 5 màn hình phân tích", className="filter-subtitle")
            ]),
            dbc.Button("🔄 Đặt lại bộ lọc", id="reset", color="link", className="reset-button")
        ], className="filter-head"),
        dbc.Row([
            dropdown("Chế độ dữ liệu", "f-mode", [
                {"label": "Dữ liệu minh họa (Demo)", "value": "demo"},
                {"label": "Nguồn BSR thực tế", "value": "real"},
                {"label": "Tất cả dữ liệu", "value": "all"}
            ], "real", False),
            dropdown("Năm báo cáo", "f-year", options(claims_all["report_year"])),
            dropdown("Loại tài liệu", "f-doc", options(claims_all["document_type"], DOC_TYPES_VI)),
            dropdown("Trụ cột ESG", "f-pillar", options(claims_all["pillar"], PILLARS_VI)),
            dropdown("Chủ đề ESG", "f-topic", options(claims_all["topic_id"], TOPICS_VI)),
            dropdown("Chỉ số (Metric)", "f-metric", options(claims_all["metric_code"], METRICS_VI)),
        ], className="g-2"),
        dbc.Row([
            dropdown("Loại cảnh báo", "f-rule", options(rules_all["risk_type"], RISK_TYPES_VI)),
            dropdown("Mức độ nghiêm trọng", "f-severity", options(rules_all["severity"], SEVERITIES_VI)),
            dropdown("Trạng thái bằng chứng", "f-relationship", options(claims_all["relationship"], RELATIONSHIPS_VI)),
        ], className="g-2 mt-2"),
    ], className="filters"),

    # Tab Navigation Shell
    dcc.Tabs(id="tabs", value="overview", className="custom-tabs", parent_className="tabs-shell", children=[
        # TAB 1: Tổng quan rủi ro
        dcc.Tab(label="📊 01 · Tổng quan", value="overview", className="custom-tab", selected_className="custom-tab--selected", children=html.Div([
            html.Div([
                html.Div("Chỉ số tổng hợp rủi ro ESG", className="section-title"),
                html.Div("Đánh giá định lượng kết hợp độ bao phủ bằng chứng và độ tin cậy trích xuất", className="section-subtitle")
            ], className="section-head"),
            dbc.Row([
                card("Điểm rủi ro", "k-risk", "🛡️", "navy", "Thang điểm 0 - 100"),
                card("Phân loại rủi ro", "k-level", "⚠️", "amber", "Mức độ đánh giá"),
                card("Tổng số công bố", "k-claims", "📋", "blue", "Claims trong dữ liệu đã lưu"),
                card("Số cảnh báo", "k-warnings", "🚨", "red", "Tín hiệu phát hiện"),
                card("Độ phủ bằng chứng", "k-coverage", "🔗", "green", "Tỷ lệ có số liệu đối chiếu"),
                card("Độ tin cậy", "k-confidence", "🎯", "purple", "Mô hình trích xuất"),
            ], className="g-3 mt-1"),
            dbc.Row([
                dbc.Col(html.Div(dcc.Graph(id="pillar-chart"), className="panel"), lg=5),
                dbc.Col(html.Div(dcc.Graph(id="risk-chart"), className="panel"), lg=7)
            ]),
            html.Div([
                html.Div([
                    html.H4("Danh sách công bố cần ưu tiên rà soát (Risk Score cao nhất)"),
                    html.Span("Nhấp chọn một dòng bất kỳ để chuyển đến màn hình đối chiếu bằng chứng chi tiết", className="panel-hint")
                ], className="panel-head"),
                table("top-claims", [
                    ("claim_id", "Mã công bố"),
                    ("report_year", "Năm"),
                    ("topic_label", "Chủ đề ESG"),
                    ("source_text", "Nội dung công bố nguyên văn"),
                    ("risk_score", "Điểm rủi ro"),
                    ("relationship_label", "Trạng thái bằng chứng"),
                ])
            ], className="panel"),
        ], className="tab-content")),

        # TAB 2: Rủi ro theo chủ đề
        dcc.Tab(label="🗺️ 02 · Chủ đề", value="topics", className="custom-tab", selected_className="custom-tab--selected", children=html.Div([
            html.Div([
                html.Div("Bản đồ nhiệt rủi ro theo chủ đề (Heatmap GRI 11)", className="section-title"),
                html.Div("Nhấp chuột vào từng ô trên ma trận để lọc các công bố thuộc chủ đề và năm tương ứng", className="section-subtitle")
            ], className="section-head"),
            html.Div([dcc.Loading(dcc.Graph(id="heatmap"))], className="panel"),
            html.Div([
                html.Div([
                    html.H4("Bảng phân tích chi tiết từng chủ đề"),
                    html.Span("Thống kê điểm rủi ro, số lượng công bố, số cảnh báo và đối chiếu tiêu chuẩn GRI", className="panel-hint")
                ], className="panel-head"),
                table("topic-table", [
                    ("report_year", "Năm"),
                    ("pillar_label", "Trụ cột"),
                    ("topic_label", "Chủ đề ESG"),
                    ("risk_score", "Điểm rủi ro"),
                    ("claim_count", "Số công bố"),
                    ("warning_count", "Số cảnh báo"),
                    ("gri_reference", "Chuẩn GRI tham chiếu"),
                ])
            ], className="panel"),
        ], className="tab-content")),

        # TAB 3: Xu hướng chỉ số
        dcc.Tab(label="📈 03 · Chỉ số", value="metrics", className="custom-tab", selected_className="custom-tab--selected", children=html.Div([
            html.Div([
                html.Div("Chuỗi xu hướng dữ liệu ESG (2022–2025)", className="section-title"),
                html.Div("Giám sát biến động số liệu, đơn vị đo lường, ranh giới (Boundary) và Scope qua từng năm", className="section-subtitle")
            ], className="section-head"),
            html.Div([
                dbc.Row([
                    dropdown("Chỉ số hiển thị", "trend-metric", options(metrics_all["metric_code"], METRICS_VI), ["GHG_SCOPE_1"], True),
                    dropdown("Loại giá trị", "trend-kind", options(metrics_all["value_kind"], VALUE_KINDS_VI), None, True),
                ], className="mb-3"),
                dcc.Loading(dcc.Graph(id="trend-chart"))
            ], className="panel"),
            html.Div(id="trend-empty", className="notice"),
        ], className="tab-content")),

        # TAB 4: Đối chiếu mâu thuẫn
        dcc.Tab(label="⚖️ 04 · Mâu thuẫn", value="contradictions", className="custom-tab", selected_className="custom-tab--selected", children=html.Div([
            html.Div([
                html.Div("Công cụ phân tích mâu thuẫn (Contradiction Explorer)", className="section-title"),
                html.Div("Chỉ kết luận mâu thuẫn sau khi số liệu đã vượt qua cổng kiểm tra tính so sánh được (Comparability Gate)", className="section-subtitle")
            ], className="section-head"),
            html.Div([
                html.Div([
                    html.H4("Đối chiếu công bố với bằng chứng thực tế"),
                    html.Span("Tổng hợp cảnh báo về sai lệch Scope, không đồng nhất đơn vị và nhầm lẫn số tuyệt đối/cường độ", className="panel-hint")
                ], className="panel-head"),
                table("contradiction-table", [
                    ("claim_id", "Mã Claim"),
                    ("report_year", "Năm"),
                    ("source_text", "Công bố gốc"),
                    ("evidence_summary", "Bằng chứng đối chiếu"),
                    ("risk_type_label", "Quy tắc vi phạm"),
                    ("severity_label", "Mức độ"),
                    ("explanation", "Phân tích & Giải thích"),
                ], 12)
            ], className="panel")
        ], className="tab-content")),

        # TAB 5: Truy xuất bằng chứng
        dcc.Tab(label="🔍 05 · Bằng chứng", value="viewer", className="custom-tab", selected_className="custom-tab--selected", children=html.Div([
            html.Div([
                html.Div("Truy xuất nguồn gốc bằng chứng (Evidence Viewer)", className="section-title"),
                html.Div("Truy vết chi tiết từng công bố: văn bản gốc, tài liệu nguồn, số trang và các cảnh báo vi phạm", className="section-subtitle")
            ], className="section-head"),
            html.Div([
                html.Label("Chọn công bố (Claim) để kiểm tra chi tiết:"),
                dcc.Dropdown(
                    id="viewer-claim",
                    options=[
                        {"label": f"[{r.report_year}] {r.claim_id} • {str(r.source_text)[:90]}...", "value": r.claim_id}
                        for r in claims_all.itertuples()
                    ],
                    value=claims_all.iloc[0]["claim_id"] if len(claims_all) else None,
                    clearable=False,
                )
            ], className="panel"),
            html.Div(id="viewer-detail", className="panel")
        ], className="tab-content")),
    ])
], className="app-shell")


app.layout = workspace_shell(
    app.layout.children[0],
    html.Details([
        html.Summary('Mở dashboard dữ liệu đã lưu trước đây — độc lập với phiên tải lên'),
        *app.layout.children[1:],
    ], className='legacy-dashboard'),
)

app.clientside_callback(
    """
    function(tabValue) {
        if (!tabValue) {
            return window.dash_clientside.no_update;
        }
        window.setTimeout(function() {
            const tabs = document.getElementById('tabs');
            if (tabs) {
                tabs.scrollIntoView({behavior: 'smooth', block: 'start'});
                const activeTab = tabs.querySelector('.custom-tab--selected');
                if (activeTab) {
                    activeTab.scrollIntoView({behavior: 'smooth', block: 'nearest', inline: 'center'});
                }
            }
        }, 80);
        return tabValue;
    }
    """,
    Output("tab-scroll-signal", "data"),
    Input("tabs", "value"),
    prevent_initial_call=True,
)


def filtered(mode, years, docs, pillars, topics, metric_codes, relationships):
    df = claims_all.copy()
    if mode != "all":
        df = df[df.is_demo_data == (1 if mode == "demo" else 0)]
    for col, values in (
        ("report_year", years),
        ("document_type", docs),
        ("pillar", pillars),
        ("topic_id", topics),
        ("metric_code", metric_codes),
        ("relationship", relationships),
    ):
        if values:
            df = df[df[col].isin(values)]
    return df


@app.callback(
    [
        Output("f-year", "value"),
        Output("f-doc", "value"),
        Output("f-pillar", "value"),
        Output("f-metric", "value"),
        Output("f-rule", "value"),
        Output("f-severity", "value"),
        Output("f-relationship", "value"),
    ],
    Input("reset", "n_clicks"),
    prevent_initial_call=True,
)
def reset_filters(_):
    return [None] * 7


@app.callback(
    Output("f-topic", "value"),
    [Input("heatmap", "clickData"), Input("reset", "n_clicks")],
    prevent_initial_call=True,
)
def heatmap_drilldown(click_data, _reset_clicks):
    try:
        trigger = callback_context.triggered_id
    except Exception:
        trigger = None
    if trigger == "reset":
        return None
    if click_data and click_data.get("points"):
        # Y-axis can be mapped back to topic_id
        y_val = click_data["points"][0]["y"]
        # If y_val is formatted Vietnamese text, resolve back to code
        inv_map = {v: k for k, v in TOPICS_VI.items()}
        topic_code = inv_map.get(y_val, y_val)
        return [topic_code]
    return dash.no_update


@app.callback(
    [Output("tabs", "value"), Output("viewer-claim", "value")],
    Input("top-claims", "active_cell"),
    State("top-claims", "data"),
    prevent_initial_call=True,
)
def top_claim_drilldown(active_cell, rows):
    if not active_cell or not rows:
        return dash.no_update, dash.no_update
    return "viewer", rows[active_cell["row"]]["claim_id"]


@app.callback(
    [
        Output("k-risk", "children"),
        Output("k-level", "children"),
        Output("k-claims", "children"),
        Output("k-warnings", "children"),
        Output("k-coverage", "children"),
        Output("k-confidence", "children"),
        Output("pillar-chart", "figure"),
        Output("risk-chart", "figure"),
        Output("top-claims", "data"),
        Output("heatmap", "figure"),
        Output("topic-table", "data"),
        Output("trend-chart", "figure"),
        Output("trend-empty", "children"),
        Output("contradiction-table", "data"),
    ],
    [
        Input("f-mode", "value"),
        Input("f-year", "value"),
        Input("f-doc", "value"),
        Input("f-pillar", "value"),
        Input("f-topic", "value"),
        Input("f-metric", "value"),
        Input("f-rule", "value"),
        Input("f-severity", "value"),
        Input("f-relationship", "value"),
        Input("trend-metric", "value"),
        Input("trend-kind", "value"),
    ],
)
def update(mode, years, docs, pillars, topics, metric_codes, risk_types, severities, relationships, trend_metrics, trend_kinds):
    df = filtered(mode, years, docs, pillars, topics, metric_codes, relationships)
    rr = rules_all[rules_all.is_demo_data == (1 if mode == "demo" else 0)] if mode != "all" else rules_all.copy()
    rr = rr[rr.claim_id.isin(df.claim_id)]
    if risk_types:
        rr = rr[rr.risk_type.isin(risk_types)]
    if severities:
        rr = rr[rr.severity.isin(severities)]
    if risk_types or severities:
        df = df[df.claim_id.isin(rr.claim_id)]

    if df.empty:
        empty = go.Figure().add_annotation(
            text="Không có dữ liệu phù hợp với bộ lọc hiện tại",
            showarrow=False,
            font={"size": 15, "color": "#64746B", "family": "Inter, Segoe UI, sans-serif"}
        )
        empty.update_layout(
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)"
        )
        return (
            "0.0", "Không có dữ liệu", "0", "0", "0%", "0%",
            empty, empty, [], empty, [], empty,
            "Không có dữ liệu metric phù hợp với lựa chọn hiện tại.", []
        )

    risk = round(df.risk_score.mean(), 1)
    if risk < 30:
        level = "Thấp"
    elif risk < 60:
        level = "Trung bình"
    elif risk < 80:
        level = "Cao"
    else:
        level = "Rất cao"

    # 1. PILLAR CHART
    pillar = df.groupby("pillar", as_index=False).risk_score.mean()
    pillar["pillar_name"] = pillar["pillar"].map(lambda p: PILLARS_SHORT_VI.get(p, p))
    pillar_colors = {"Môi trường (E)": "#15803D", "Xã hội (S)": "#0F766E", "Quản trị (G)": "#52735D", "Tài chính (X)": "#475569"}
    pillar_fig = px.bar(
        pillar,
        x="pillar_name",
        y="risk_score",
        color="pillar_name",
        color_discrete_map=pillar_colors,
        title="<b>Điểm rủi ro trung bình theo Trụ cột ESG</b>",
        labels={"pillar_name": "Trụ cột", "risk_score": "Điểm rủi ro trung bình"},
        text_auto=".1f",
    )

    # 2. RISK SIGNAL DISTRIBUTION CHART
    dist = rr.groupby("risk_type", as_index=False).size().sort_values("size", ascending=False)
    if len(dist):
        dist["risk_name"] = dist["risk_type"].map(lambda r: RISK_TYPES_VI.get(r, r))
        risk_fig = px.bar(
            dist.sort_values("size"),
            x="size",
            y="risk_name",
            orientation="h",
            color_discrete_sequence=["#14532D"],
            title="<b>Phân bố các loại tín hiệu cảnh báo rủi ro</b>",
            labels={"risk_name": "Loại cảnh báo", "size": "Số lượng cảnh báo"},
            text_auto=True,
        )
    else:
        risk_fig = go.Figure().add_annotation(
            text="Không có cảnh báo rủi ro nào",
            showarrow=False,
            font={"size": 14, "color": "#64748b"}
        )

    # 3. TOP CLAIMS TABLE DATA
    top_df = df.nlargest(15, "risk_score").copy()
    top_df["topic_label"] = top_df["topic_id"].map(lambda t: TOPICS_VI.get(t, t))
    top_df["relationship_label"] = top_df["relationship"].map(lambda r: RELATIONSHIPS_SHORT_VI.get(r, str(r)))
    top = top_df[["claim_id", "report_year", "topic_label", "source_text", "risk_score", "relationship_label", "relationship"]].to_dict("records")

    # 4. TOPIC HEATMAP & TABLE
    ts = topics_all[topics_all.is_demo_data == (1 if mode == "demo" else 0)] if mode != "all" else topics_all.copy()
    if years:
        ts = ts[ts.report_year.isin(years)]
    if pillars:
        ts = ts[ts.pillar.isin(pillars)]
    if topics:
        ts = ts[ts.topic_id.isin(topics)]

    ts = ts.copy()
    ts["topic_label"] = ts["topic_id"].map(lambda t: TOPICS_VI.get(t, t))
    ts["pillar_label"] = ts["pillar"].map(lambda p: PILLARS_SHORT_VI.get(p, p))

    pivot = ts.pivot_table(index="topic_label", columns="report_year", values="risk_score", aggfunc="mean")
    if not pivot.empty:
        heat = px.imshow(
            pivot,
            aspect="auto",
            color_continuous_scale=[[0, "#ecfdf5"], [0.4, "#fef3c7"], [0.75, "#fed7aa"], [1.0, "#e11d48"]],
            zmin=0,
            zmax=100,
            title="<b>Ma trận rủi ro chủ đề theo từng năm (Heatmap GRI 11)</b>",
            labels={"x": "Năm báo cáo", "y": "Chủ đề ESG", "color": "Điểm rủi ro"},
            text_auto=".0f",
        )
    else:
        heat = go.Figure().add_annotation(text="Không có dữ liệu cho ma trận chủ đề", showarrow=False)

    # 5. METRICS TREND CHART
    metric_df = metrics_all.copy()
    if mode != "all":
        metric_df = metric_df[metric_df.is_demo_data == (1 if mode == "demo" else 0)]
    if years:
        metric_df = metric_df[metric_df.metric_year.isin(years)]
    selected_trends = trend_metrics or metric_codes
    if selected_trends:
        metric_df = metric_df[metric_df.metric_code.isin(selected_trends)]
    if trend_kinds:
        metric_df = metric_df[metric_df.value_kind.isin(trend_kinds)]

    if len(metric_df):
        metric_df["metric_name"] = metric_df["metric_code"].map(lambda m: METRICS_VI.get(m, m))
        trend = px.line(
            metric_df.sort_values("metric_year"),
            x="metric_year",
            y="normalized_value",
            color="metric_name",
            markers=True,
            hover_data=["normalized_unit", "scope", "boundary", "document_id", "page_number"],
            title="<b>Diễn biến chỉ số định lượng qua các năm (2022–2025)</b>",
            labels={"metric_year": "Năm báo cáo", "normalized_value": "Giá trị chuẩn hóa", "metric_name": "Chỉ số ESG"},
        )
    else:
        trend = go.Figure().add_annotation(
            text="Không có dữ liệu chỉ số định lượng phù hợp",
            showarrow=False,
            font={"size": 14, "color": "#64748b"}
        )

    # Polish Layout for all Plotly Figures
    for figure in (pillar_fig, risk_fig, heat, trend):
        figure.update_layout(
            template="plotly_white",
            font={"family": "Inter, Segoe UI, sans-serif", "color": "#172B22"},
            title={"font": {"size": 16, "color": "#14532D"}, "x": 0.02, "xanchor": "left"},
            margin={"l": 40, "r": 28, "t": 60, "b": 42},
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="#F8FAF9",
            hoverlabel={"bgcolor": "#14532D", "font_color": "#ffffff", "font_family": "Inter, Segoe UI"},
            legend_title_text="",
        )
        figure.update_xaxes(showgrid=False, zeroline=False)
        figure.update_yaxes(gridcolor="#DFE8E2", zeroline=False)

    pillar_fig.update_layout(showlegend=False, height=360)
    risk_fig.update_layout(showlegend=False, coloraxis_showscale=False, height=360)
    heat.update_layout(height=480)
    trend.update_layout(height=480, hovermode="x unified")

    # 6. CONTRADICTION EXPLORER TABLE DATA
    contradiction_rows = rr.merge(df[["claim_id", "source_text"]], on="claim_id", how="left")
    contradiction_rows = contradiction_rows[contradiction_rows.risk_type.isin([
        "CROSS_DOC_CONTRADICTION", "TEMPORAL_CONTRADICTION", "SCOPE_SHIFT",
        "UNIT_MISMATCH", "ABS_INTENSITY_MIX", "RESTATEMENT_GAP"
    ])].copy()
    contradiction_rows["risk_type_label"] = contradiction_rows["risk_type"].map(lambda r: RISK_TYPES_VI.get(r, r))
    contradiction_rows["severity_label"] = contradiction_rows["severity"].map(lambda s: SEVERITIES_SHORT_VI.get(s, f"Mức {s}"))

    return (
        f"{risk:.1f}",
        level,
        str(len(df)),
        str(len(rr)),
        f"{df.evidence_coverage.mean()*100:.0f}%",
        f"{df.score_confidence.mean()*100:.0f}%",
        pillar_fig,
        risk_fig,
        top,
        heat,
        ts.to_dict("records"),
        trend,
        "" if len(metric_df) else "Không có dữ liệu chỉ số cho lựa chọn hiện tại.",
        contradiction_rows[["claim_id", "report_year", "source_text", "evidence_summary", "risk_type_label", "severity_label", "explanation"]].to_dict("records"),
    )


@app.callback(Output("viewer-detail", "children"), Input("viewer-claim", "value"))
def viewer(claim_id):
    if not claim_id:
        return html.Div("Vui lòng chọn một công bố (Claim) để xem chi tiết.", className="text-muted p-3")

    row = claims_all[claims_all.claim_id == claim_id]
    if row.empty:
        return html.Div("Không tìm thấy thông tin công bố này trong hệ thống.", className="text-danger p-3")

    c = row.iloc[0]
    metric = metrics_all[metrics_all.metric_id == c.metric_id] if pd.notna(c.metric_id) else pd.DataFrame()
    evidence = "Chưa tìm thấy bằng chứng đối chiếu ứng viên trong tài liệu đã nạp." if metric.empty else metric.iloc[0].source_text
    warning = rules_all[rules_all.claim_id == claim_id]

    relationship_label = RELATIONSHIPS_VI.get(c.relationship, str(c.relationship))
    status_class = "badge-gray"
    if c.relationship == "SUPPORTS":
        status_class = "badge-green"
    elif c.relationship == "PARTIAL_SUPPORT":
        status_class = "badge-blue"
    elif c.relationship == "CONTRADICTS":
        status_class = "badge-red"
    elif c.relationship in ("MISSING", "AMBIGUOUS"):
        status_class = "badge-amber"

    pillar_text = PILLARS_VI.get(c.pillar, str(c.pillar))
    topic_text = TOPICS_VI.get(c.topic_id, str(c.topic_id))

    return dbc.Row([
        # Left Column: Claim Info
        dbc.Col(html.Div([
            html.Div([
                html.Span("📋", className="me-2"),
                html.Span("Nội dung công bố nguyên văn (Claim gốc)")
            ], className="detail-card-title"),
            html.Div(f'"{c.source_text}"', className="quote-box"),
            html.Dl([
                html.Dt("Mã công bố (ID)", className="meta-dt"),
                html.Dd(c.claim_id, className="meta-dd"),
                html.Dt("Trụ cột & Chủ đề", className="meta-dt"),
                html.Dd(f"{pillar_text} • {topic_text}", className="meta-dd"),
                html.Dt("Nguồn tài liệu", className="meta-dt"),
                html.Dd(f"{c.document_title} ({DOC_TYPES_VI.get(c.document_type, c.document_type)}) - Năm {c.report_year} - Trang {c.page_number}", className="meta-dd"),
                html.Dt("Độ tin cậy trích xuất", className="meta-dt"),
                html.Dd(f"{c.score_confidence:.1%}", className="meta-dd"),
                html.Dt("Chế độ dữ liệu", className="meta-dt"),
                html.Dd(
                    html.Span("Dữ liệu mô phỏng (Demo)", className="badge-pill badge-amber") if c.is_demo_data
                    else html.Span("Dữ liệu thực tế (BSR trích xuất)", className="badge-pill badge-green"),
                    className="meta-dd"
                ),
            ], className="meta-dl"),
        ], className="detail-card"), md=6),

        # Right Column: Evidence & Rules
        dbc.Col(html.Div([
            html.Div([
                html.Span("🔗", className="me-2"),
                html.Span("Bằng chứng đối chiếu & Kiểm chứng")
            ], className="detail-card-title"),
            html.Div(evidence, className="evidence-box"),
            html.Dl([
                html.Dt("Trạng thái đối chiếu", className="meta-dt"),
                html.Dd(html.Span(relationship_label, className=f"badge-pill {status_class}"), className="meta-dd"),
                html.Dt("Giải thích thuật toán so sánh", className="meta-dt"),
                html.Dd(c.matching_explanation or "Không có ghi chú thêm.", className="meta-dd"),
            ], className="meta-dl"),
            html.H5([
                html.Span("🚨", className="me-2"),
                "Tín hiệu cảnh báo rủi ro phát hiện (Rule Alerts)"
            ], className="panel-head mt-3"),
            html.Div([
                html.Div([
                    html.Div(f"Quy tắc {r.rule_id} • {RISK_TYPES_VI.get(r.risk_type, r.risk_type)} ({SEVERITIES_SHORT_VI.get(r.severity, f'Mức {r.severity}')})", className="rule-item-title"),
                    html.Div(r.explanation, className="rule-item-body")
                ], className="rule-item")
                for r in warning.itertuples()
            ] if len(warning) else html.Div("✓ Không phát hiện cảnh báo rủi ro nào từ hệ luật chuyên gia.", className="text-success p-2 small font-monospace"))
        ], className="detail-card"), md=6)
    ], className="g-3")


register_upload_callbacks(app, ROOT)

if __name__ == "__main__":
    app.run(debug=False, host="127.0.0.1", port=8050)
