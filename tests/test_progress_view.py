"""Upload status remains accurate through extraction and Graph completion."""
import json

from dash import Dash

from dashboard import upload_analysis as ui
from dashboard.progress_view import progress_card, graph_result_message


def _text(node):
    if isinstance(node, (list, tuple)):
        return " ".join(_text(item) for item in node)
    if hasattr(node, "children"):
        return _text(node.children)
    return str(node or "")


def test_progress_card_explains_current_document_and_page():
    card = progress_card({"stage": "source_v2", "document_index": 1, "document_total": 6,
                          "filename": "BSR_2023.pdf", "page": 22, "page_total": 39,
                          "completed_pages": 21, "finished_pages": 22})
    rendered = _text(card)
    assert "Đang đọc và lưu từng trang PDF" in rendered
    assert "Tài liệu 1/6: BSR_2023.pdf" in rendered
    assert "Đã xử lý 22/39 trang; đọc thành công 21 trang" in rendered
    assert "Đối chiếu ESG–BCTC" in rendered


def test_poll_keeps_running_after_extract_until_graph_finishes(tmp_path):
    app = Dash(__name__)
    app.layout = ui.upload_panel()
    ui.register_upload_callbacks(app, tmp_path)
    poll = next(item["callback"].__wrapped__ for key, item in app.callback_map.items()
                if "analysis-poll.disabled" in key)
    job_id = "f" * 32
    folder = tmp_path / "data" / "processed" / "extraction_jobs" / job_id
    folder.mkdir(parents=True)
    job = {"id": job_id, "files": ["BSR_2023.pdf"]}
    result = {"status": "completed", "manifest": {"document_count": 0, "failures": []}, "documents": []}
    ui.JOBS[job_id] = result
    try:
        (folder / "graph_status.json").write_text(json.dumps({"status": "running", "stage": "graph"}), encoding="utf-8")
        status, _, _, _, _, start_disabled, poll_disabled, _ = poll(0, job)
        assert "Đang đối chiếu ESG với BCTC" in _text(status)
        assert start_disabled and not poll_disabled

        (folder / "graph_status.json").write_text(json.dumps({"status": "completed", "review_cases": 4}), encoding="utf-8")
        status, _, _, _, _, start_disabled, poll_disabled, _ = poll(1, job)
        assert "4 trường hợp cần duyệt" in _text(status)
        assert not start_disabled and poll_disabled
    finally:
        ui.JOBS.pop(job_id, None)


def test_extract_success_is_distinct_from_graph_skip_or_error():
    assert "Đã trích xuất PDF" in graph_result_message({"status": "skipped", "reason": "Thiếu BCTC 2024"})
    assert "Thiếu BCTC 2024" in graph_result_message({"status": "skipped", "reason": "Thiếu BCTC 2024"})
    assert "Đối chiếu Graph gặp lỗi" in graph_result_message({"status": "failed", "reason": "bridge failed"})
