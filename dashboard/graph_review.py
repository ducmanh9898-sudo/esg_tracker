"""Show the latest BSR Graph review queue inside the ESG Tracker Dash workspace."""
from __future__ import annotations

from decimal import Decimal
import json
import os
from pathlib import Path
import re

from dash import Input, Output, State, dash_table, dcc, html
from flask import abort, send_file
from dashboard.graph_upload import read_graph_status


ROOT = Path(__file__).resolve().parents[1]
GRAPH_REPO = ROOT / "knowledge_graph" if (ROOT / "knowledge_graph" / "kg").is_dir() else ROOT.parent / "esg-greenwashing-risk-framework"
REASON_LABELS = {
    "measurement_date_mismatch": "Ngày đo chưa khớp",
    "metric_definition_not_equivalent": "Định nghĩa chỉ tiêu chưa tương đương",
    "metric_id_not_equivalent": "Mã chỉ tiêu chưa tương đương",
    "reporting_boundary_unknown": "Phạm vi báo cáo chưa rõ",
    "scope_unknown": "Phạm vi chưa rõ",
    "population_unknown": "Nhóm nhân sự chưa rõ",
    "restatement_not_reviewed": "Chưa kiểm tra điều chỉnh số liệu",
    "observation_interval_unknown": "Kỳ đo chưa rõ",
    "source_version_audit_basis_unreviewed": "Chưa duyệt phiên bản nguồn và cơ sở kiểm toán",
    "earlier_report_observation_year_unknown": "Chưa xác nhận năm đo trong báo cáo trước",
    "comparative_source_text_difference": "Cùng năm đo nhưng câu nguồn có hai giá trị",
    "rounding_tolerance_unreviewed": "Chưa kiểm tra cách làm tròn",
    "counting_method_unknown": "Cách đếm chưa rõ",
    "consolidation_unknown": "Phạm vi hợp nhất chưa rõ",
}


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _graph_root():
    return Path(os.environ.get("ESGTRACKER_GRAPH_REPO", GRAPH_REPO)).resolve()


def _latest_run(graph_root):
    configured = os.environ.get("ESGTRACKER_GRAPH_RUN_DIR")
    if configured:
        chosen = Path(configured).resolve()
        return chosen if chosen.is_relative_to(graph_root) else None
    output = graph_root / "output"
    if not output.is_dir():
        return None
    files = sorted((path for pattern in ("bsr_*/review_cases.json", "bsr_*/analysis/review_cases.json")
                    for path in output.glob(pattern) if (path.parent / "bridge_report.json").is_file()),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0].parent if files else None


def load_review_bundle(run_dir=None):
    """Read only local, pipeline produced files; never interpret a request as a path."""
    graph_root = _graph_root()
    run_dir = Path(run_dir).resolve() if run_dir is not None else _latest_run(graph_root)
    if run_dir is None or not run_dir.is_relative_to(graph_root / "output") or not run_dir.name.startswith("bsr_"):
        return None
    review_file = run_dir / "review_cases.json"
    report_file = run_dir / "bridge_report.json"
    if not review_file.is_file() or not report_file.is_file():
        return None
    payload = _read(review_file)
    if payload.get("schema_version") != "bsr-review-dashboard-1.0":
        return None
    manifest = Path(_read(report_file)["manifest"]).resolve()
    if not manifest.is_relative_to(graph_root) or not manifest.is_file():
        return None
    pdfs = {}
    by_name = {}
    for item in _read(manifest).get("files", []):
        pdf = (manifest.parent / item["pdf_path"]).resolve()
        sha = item.get("pdf_sha256", "")
        if pdf.is_relative_to(manifest.parent.resolve()) and pdf.is_file() and re.fullmatch(r"[0-9a-f]{64}", sha):
            pdfs[sha] = pdf
            by_name[pdf.name] = sha
    return {"run_dir": run_dir, "cases": payload.get("cases", []),
            "pdfs": pdfs, "pdf_by_name": by_name}


def _number(value):
    if value is None:
        return "Chưa rõ"
    number = Decimal(str(value))
    if number == number.to_integral():
        return f"{number:,.0f}".replace(",", ".")
    return f"{number:,.3f}".rstrip("0").rstrip(".").replace(",", "~").replace(".", ",").replace("~", ".")


def _unit(unit):
    return {"people": "người", "VND": "đồng"}.get(unit, unit or "")


def _rows(cases):
    rows = []
    for case in cases:
        sources = case.get("sources", [])
        rows.append({
            "id": case["id"], "priority": case.get("priority", ""),
            "title": case.get("title", ""), "kind": case.get("kind", ""),
            "year": case.get("year") or "Chưa rõ",
            "sources": " ↔ ".join(f"{s.get('report_type')} {s.get('report_year')} · tr. {s.get('page')}" for s in sources),
            "gap": f"{_number(case.get('delta'))} {_unit(case.get('unit'))}",
            "status": case.get("status", ""),
        })
    return rows


def graph_review_panel():
    return html.Section([
        html.Div([html.Span("04 / ĐỐI CHIẾU BSR", className="section-kicker"),
                  html.H2("Thông số cần duyệt từ Đồ thị tri thức"),
                  html.P("NeedsReview nghĩa là cần người duyệt. Chênh lệch số chưa chứng minh mâu thuẫn; hãy mở PDF và xác nhận định nghĩa, năm đo, phạm vi, đơn vị và số liệu điều chỉnh.")],
                 className="workspace-section-heading"),
        html.Div([
            html.Label("Nguồn kết quả", htmlFor="graph-review-source"),
            dcc.RadioItems(id="graph-review-source", options=[
                {"label": "Phiên upload hiện tại", "value": "current"},
                {"label": "Lượt BSR đã chạy trước", "value": "saved"}],
                value="current", inline=True, className="graph-review-source-choice"),
        ], className="graph-review-source-select"),
        dcc.Interval(id="graph-review-poll", interval=3000, n_intervals=0),
        dcc.Store(id="graph-review-active-run"),
        html.Div(id="graph-review-summary", className="graph-review-summary", role="status"),
        html.Div([
            html.Div([html.Label("Loại đối chiếu", htmlFor="graph-review-kind"),
                      dcc.Dropdown(id="graph-review-kind", options=[
                          {"label": "Tất cả", "value": "all"},
                          {"label": "ESG ↔ BCTC", "value": "ESG ↔ BCTC"},
                          {"label": "BCTC ↔ BCTC", "value": "BCTC ↔ BCTC"},
                          {"label": "ESG ↔ ESG", "value": "ESG ↔ ESG"}], value="all", clearable=False)], className="extract-field"),
            html.Div([html.Label("Năm đo", htmlFor="graph-review-year"),
                      dcc.Dropdown(id="graph-review-year", options=[{"label": "Tất cả", "value": "all"}] +
                                   [{"label": str(year), "value": str(year)} for year in (2023, 2024, 2025)],
                                   value="all", clearable=False)], className="extract-field"),
        ], className="graph-review-filters"),
        dash_table.DataTable(
            id="graph-review-table", data=[], row_selectable="single", selected_row_ids=[],
            columns=[{"name": label, "id": key} for key, label in [
                ("priority", "Ưu tiên"), ("title", "Thông số"), ("kind", "Loại"),
                ("year", "Năm đo"), ("sources", "Hai nguồn"), ("gap", "Chênh lệch"),
                ("status", "Trạng thái")]],
            page_size=10, sort_action="native", filter_action="native",
            style_table={"overflowX": "auto"},
            style_cell={"fontFamily": "Inter, Segoe UI, sans-serif", "fontSize": 13, "padding": "11px",
                        "whiteSpace": "normal", "height": "auto", "minWidth": "90px", "maxWidth": "310px",
                        "textAlign": "left", "color": "#172B22"},
            style_header={"backgroundColor": "#F0FDF4", "fontWeight": "bold"},
            style_data_conditional=[{"if": {"state": "selected"}, "backgroundColor": "#E0F2E9"},
                                    {"if": {"filter_query": '{priority} = "Cao"', "column_id": "priority"},
                                     "color": "#9A3412", "fontWeight": "bold"}]),
        html.Div(id="graph-review-detail", className="graph-review-detail"),
        html.P("Phiên upload mới chỉ có kết quả Graph sau khi trích xuất đủ 6 PDF BSR. Lượt cũ được xem riêng bằng lựa chọn phía trên. Các trường hợp BCTC ↔ BCTC và ESG ↔ ESG là đối chiếu bổ sung; chưa có mã kết luận trong Graph.",
               className="detail-note"),
    ], id="graph-review", className="workspace-section graph-review-section")


def _source_card(source, bundle):
    sha = bundle["pdf_by_name"].get(source.get("file"))
    page = source.get("page")
    alternate = source.get("alternate_page")
    link = html.A(f"Mở PDF trang {page} ↗", href=f"/bsr-graph-pdf/{bundle['run_dir'].name}/{sha}#page={page}",
                  target="_blank", rel="noopener noreferrer", className="ui-button ui-button--secondary") if sha and page else None
    return html.Div([
        html.Div([html.Strong(f"{source.get('report_type')} · báo cáo {source.get('report_year')}"),
                  html.Span(f"Năm đo: {source.get('observation_year') or 'chưa rõ'}")], className="graph-source-head"),
        html.Div(f"{_number(source.get('value'))} {_unit(source.get('unit'))}", className="graph-source-value"),
        html.P(f"{source.get('file')} · trang PDF {page}" +
               (f" · bản 68 trang: trang {alternate}" if alternate else ""), className="graph-source-meta"),
        html.Blockquote(source.get("quote") or "Chưa có câu trích nguyên văn.", className="graph-source-quote"),
        link,
    ], className="graph-source-card")


def _detail(case, bundle):
    reasons = list(dict.fromkeys(REASON_LABELS[key] for key in case.get("reasons", []) if key in REASON_LABELS))
    return html.Div([
        html.Div([html.H3(case["title"]), html.Span("NeedsReview · cần người duyệt", className="graph-review-badge")],
                 className="graph-detail-head"),
        html.Div([_source_card(source, bundle) for source in case.get("sources", [])], className="graph-source-grid"),
        html.Div([html.Strong(f"Chênh lệch quan sát: {_number(case.get('delta'))} {_unit(case.get('unit'))}"),
                  html.P(case.get("question", "Cần xác nhận hai nguồn có thể so trực tiếp không?"))],
                 className="graph-review-question"),
        html.H4("Lý do cần kiểm tra"),
        html.Ul([html.Li(reason) for reason in reasons] or [html.Li("Chưa xác nhận đủ ngữ cảnh nguồn")]),
        html.P(case.get("note") or "Giá trị và trạng thái lấy từ kết quả Graph; câu trích OCR cần kiểm tra trên PDF gốc.",
               className="detail-note"),
        html.Small(f"Mã đối chiếu: {case['id']}" +
                   (f" · Mã Graph: {case['graph_finding_id']}" if case.get("graph_finding_id") else "")),
    ], className="workspace-card graph-detail-card")


def register_graph_review_callbacks(app, root=ROOT):
    @app.server.get("/bsr-graph-pdf/<run_name>/<source_hash>")
    def view_graph_pdf(run_name, source_hash):
        if not re.fullmatch(r"bsr_[a-z0-9_]+", run_name) or not re.fullmatch(r"[0-9a-f]{64}", source_hash):
            abort(404)
        try:
            bundle = load_review_bundle(_graph_root() / "output" / run_name)
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            abort(404)
        pdf = bundle["pdfs"].get(source_hash) if bundle else None
        if pdf is None:
            abort(404)
        response = send_file(pdf, mimetype="application/pdf", as_attachment=False, download_name=pdf.name)
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @app.callback(Output("graph-review-table", "data"), Output("graph-review-table", "selected_row_ids"),
                  Output("graph-review-summary", "children"), Output("graph-review-active-run", "data"),
                  Input("graph-review-poll", "n_intervals"), Input("graph-review-source", "value"),
                  Input("graph-review-kind", "value"), Input("graph-review-year", "value"),
                  Input("analysis-job", "data"), State("graph-review-table", "selected_row_ids"))
    def refresh_graph_review(_tick, source, kind, year, job, selected):
        run_dir = None
        origin = "lượt BSR đã chạy trước"
        if source != "saved":
            origin = "phiên upload hiện tại"
            if not isinstance(job, dict) or not job.get("id"):
                return [], [], "Phiên này chưa upload PDF. Chọn 'Lượt BSR đã chạy trước' nếu muốn xem dữ liệu cũ.", None
            status = read_graph_status(root, job["id"])
            if not status:
                return [], [], "Phiên upload này đang Extract hoặc chưa có kết quả Graph.", None
            if status["status"] == "running":
                stage = "chuẩn bị nguồn" if status.get("stage") == "delivery" else "đối chiếu ESG–BCTC"
                return [], [], f"Graph của phiên này đang {stage}. Bảng sẽ cập nhật khi hoàn tất.", None
            if status["status"] != "completed":
                return [], [], status.get("reason") or "Graph chưa có kết quả cho phiên upload này.", None
            run_dir = status.get("run_dir")
            if not run_dir:
                return [], [], "Graph chưa ghi thư mục kết quả của phiên upload này.", None
        try:
            bundle = load_review_bundle(run_dir) if run_dir else load_review_bundle()
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            bundle = None
        if bundle is None:
            return [], [], f"Chưa đọc được kết quả Graph của {origin}.", None
        all_cases = [case for case in bundle["cases"] if case.get("status") == "NeedsReview"]
        cases = [case for case in all_cases if (kind == "all" or case.get("kind") == kind)
                 and (year == "all" or str(case.get("year")) == year)]
        rows = _rows(cases)
        ids = {row["id"] for row in rows}
        chosen = [selected[0]] if selected and selected[0] in ids else [rows[0]["id"]] if rows else []
        graph_count = sum(bool(case.get("graph_finding_id")) for case in all_cases)
        summary = (f"Nguồn: {origin} ({bundle['run_dir'].name}). "
                   f"{len(all_cases)} trường hợp cần duyệt · {graph_count} cặp ESG ↔ BCTC trong Graph · "
                   f"{len(all_cases)-graph_count} đối chiếu bổ sung. Đang hiển thị {len(rows)} trường hợp.")
        return rows, chosen, summary, str(bundle["run_dir"])

    @app.callback(Output("graph-review-detail", "children"),
                  Input("graph-review-table", "selected_row_ids"), Input("graph-review-table", "data"),
                  Input("graph-review-active-run", "data"))
    def show_graph_review(selected, rows, active_run):
        if not selected or not rows or not active_run:
            return html.P("Chọn một dòng để xem hai nguồn và câu trích PDF.", className="detail-note")
        try:
            bundle = load_review_bundle(active_run)
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            return html.P("Không đọc được nguồn Graph hiện tại.", className="detail-note")
        if not bundle:
            return html.P("Không còn kết quả Graph để hiển thị.", className="detail-note")
        case = next((item for item in bundle["cases"] if item["id"] == selected[0]), None)
        return _detail(case, bundle) if case else html.P("Không tìm thấy cặp đã chọn.", className="detail-note")
