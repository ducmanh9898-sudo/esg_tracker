"""Human-readable status for a PDF upload and its optional Graph run."""
from dash import html


STAGES = {
    "queued": ("Đang chờ lượt xử lý", "File đã nhận; hệ thống sẽ bắt đầu khi lượt trước hoàn tất."),
    "preparing": ("Đang chuẩn bị tài liệu", "Kiểm tra PDF và thông tin báo cáo."),
    "document": ("Đang mở tài liệu", "Chuẩn bị đọc các trang của PDF này."),
    "reading": ("Đang đọc trang PDF", "Đọc nội dung trên trang hiện tại."),
    "ocr": ("Đang nhận dạng chữ trên trang PDF", "Trang dạng ảnh cần nhận dạng chữ nên có thể mất thêm thời gian."),
    "docling": ("Đang đọc bố cục và bảng", "Xác định chữ, bảng và vị trí trên trang."),
    "source_v2": ("Đang đọc và lưu từng trang PDF", "Trang đã xử lý được lưu để có thể tiếp tục nếu gián đoạn."),
    "semantic_v2": ("Đang tạo dữ liệu từ tài liệu", "Rút số liệu và thông tin cần đối chiếu từ các trang đã đọc."),
    "claims": ("Đang tạo các phát biểu", "Gắn nội dung trích xuất với vị trí nguồn."),
    "export": ("Đang lưu kết quả trích xuất", "Sắp chuyển sang bước đối chiếu nếu đủ sáu báo cáo BSR."),
    "graph_delivery": ("Đang chuẩn bị dữ liệu cho Graph", "Kiểm tra sáu nguồn và bàn giao dữ liệu trích xuất."),
    "knowledge_graph": ("Đang đối chiếu ESG với BCTC", "Tìm cặp số liệu và tạo danh sách cần người duyệt."),
}


def _step(label, state):
    return html.Div([html.Span("✓" if state == "done" else "●" if state == "active" else "○",
                               className="analysis-step-marker", **{"aria-hidden": "true"}),
                     html.Span(label)], className=f"analysis-step analysis-step--{state}")


def progress_card(event, files=None):
    """Render only observed progress; never imply a whole-batch percentage."""
    event = event or {}
    stage = event.get("stage", "preparing")
    title, explanation = STAGES.get(stage, ("Đang xử lý", "Hệ thống đang làm việc với tài liệu."))
    graph_stage = stage in ("graph_delivery", "knowledge_graph")
    steps = [
        _step("1. Trích xuất PDF", "done" if graph_stage else "active"),
        _step("2. Chuẩn bị dữ liệu đối chiếu", "done" if stage == "knowledge_graph" else "active" if stage == "graph_delivery" else "waiting"),
        _step("3. Đối chiếu ESG–BCTC", "active" if stage == "knowledge_graph" else "waiting"),
    ]
    details = []
    file_count = event.get("document_total") or len(files or [])
    file_index = event.get("document_index")
    if not graph_stage and file_count:
        if file_index:
            fallback = files[file_index - 1] if files and 0 < file_index <= len(files) else ""
            details.append(html.Div(f"Tài liệu {file_index}/{file_count}: {event.get('filename') or fallback}",
                                    className="analysis-progress-detail"))
        else:
            details.append(html.Div(f"Đã nhận {file_count} tài liệu.", className="analysis-progress-detail"))
    total = event.get("page_total") or 0
    if not graph_stage and total:
        finished = min(total, event.get("finished_pages", event.get("completed_pages", 0)) or 0)
        success = min(total, event.get("completed_pages", 0) or 0)
        current = event.get("page")
        page_text = f"Trang đang đọc: {current}/{total} · " if current else ""
        details.append(html.Div(f"{page_text}Đã xử lý {finished}/{total} trang; đọc thành công {success} trang.",
                                className="analysis-progress-detail"))
        details.append(html.Progress(value=finished, max=total, className="extract-progress-bar",
                                     **{"aria-label": "Tiến độ trang của tài liệu hiện tại"}))
    if graph_stage:
        details.append(html.Div("Bước này chưa có số trang hoặc phần trăm để hiển thị. Kết quả sẽ xuất hiện ở mục Đối chiếu BSR.",
                                className="analysis-progress-detail"))
    return html.Div([
        html.Div("ĐANG XỬ LÝ · tự cập nhật", className="analysis-progress-kicker"),
        html.Div(steps, className="analysis-progress-steps"),
        html.Strong(title, className="extract-progress-title"),
        html.P(explanation, className="analysis-progress-explanation"),
        *details,
        html.Small("Giữ ứng dụng đang chạy. Bạn có thể theo dõi trạng thái tại đây; số trang chỉ thuộc tài liệu hiện tại.",
                   className="analysis-progress-note"),
    ], className="analysis-progress-card")


def graph_result_message(status):
    """Describe Graph outcome separately from successful PDF extraction."""
    if not status:
        return "Chưa có trạng thái đối chiếu Graph cho lượt này."
    state = status.get("status")
    if state == "completed":
        count = status.get("review_cases")
        count_text = f"{count} trường hợp cần duyệt" if isinstance(count, int) else "danh sách cần duyệt"
        return f"Đã đối chiếu ESG–BCTC và tạo {count_text}. Mở mục Đối chiếu BSR → Phiên upload hiện tại để xem."
    if state == "skipped":
        return f"Đã trích xuất PDF. Chưa chạy đối chiếu Graph: {status.get('reason', 'không đủ điều kiện đầu vào.')}"
    if state == "failed":
        return f"Đã trích xuất PDF. Đối chiếu Graph gặp lỗi: {status.get('reason', 'chưa rõ nguyên nhân.')}"
    return "Đang tiếp tục xử lý Graph."
