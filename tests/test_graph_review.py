"""The BSR Graph queue is visible in Dash and PDFs are served by a fixed manifest ID."""
import hashlib
import json

from dash import Dash

from dashboard.graph_review import graph_review_panel, load_review_bundle, register_graph_review_callbacks
from dashboard.upload_analysis import upload_panel, register_upload_callbacks
from dashboard.components.workspace import workspace_shell


def test_graph_review_load_and_pdf_route(tmp_path, monkeypatch):
    graph = tmp_path / "esg-greenwashing-risk-framework"
    run = graph / "output" / "bsr_test"
    delivery = graph / "output" / "extract" / "delivery"
    pdf = delivery / "pdf" / "BSR_2025.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"%PDF-1.4\nreview fixture\n")
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    (delivery / "manifest.json").write_text(json.dumps({"files": [
        {"pdf_path": "pdf/BSR_2025.pdf", "pdf_sha256": digest}]}), encoding="utf-8")
    run.mkdir(parents=True)
    (run / "bridge_report.json").write_text(json.dumps({"manifest": str(delivery / "manifest.json")}), encoding="utf-8")
    (run / "review_cases.json").write_text(json.dumps({
        "schema_version": "bsr-review-dashboard-1.0", "cases": [{
            "id": "CMP-TEST", "title": "Số lao động", "kind": "ESG ↔ BCTC", "year": 2025,
            "priority": "Cao", "status": "NeedsReview", "delta": "352", "unit": "people",
            "sources": [{"file": pdf.name, "report_type": "ESG", "report_year": 2025,
                         "observation_year": 2025, "page": 76, "value": 1594,
                         "unit": "people", "quote": "Tổng số lao động 1.594"}],
            "reasons": [], "graph_finding_id": "FND-TEST"}]}), encoding="utf-8")
    monkeypatch.setenv("ESGTRACKER_GRAPH_REPO", str(graph))
    monkeypatch.setenv("ESGTRACKER_GRAPH_RUN_DIR", str(run))

    bundle = load_review_bundle()
    assert len(bundle["cases"]) == 1
    assert bundle["pdf_by_name"][pdf.name] == digest

    app = Dash(__name__)
    app.layout = graph_review_panel()
    register_graph_review_callbacks(app)
    client = app.server.test_client()
    assert client.get("/_dash-layout").status_code == 200
    response = client.get(f"/bsr-graph-pdf/bsr_test/{digest}")
    assert response.status_code == 200
    assert response.data == pdf.read_bytes()
    assert client.get("/bsr-graph-pdf/bsr_test/not-a-hash").status_code == 404

    integrated = Dash("integrated_graph_review")
    integrated.layout = workspace_shell(upload_panel(), "")
    register_upload_callbacks(integrated, tmp_path)
    layout = integrated.server.test_client().get("/_dash-layout").get_json()
    assert '"graph-review"' in json.dumps(layout)
    callback = next(item["callback"].__wrapped__ for key, item in integrated.callback_map.items()
                    if "graph-review-table.data" in key)
    rows, selected, summary, active = callback(0, "current", "all", "all", None, [])
    assert rows == [] and selected == [] and active is None
    assert "chưa upload PDF" in summary
    rows, selected, summary, active = callback(0, "saved", "all", "all", None, [])
    assert len(rows) == 1
    assert rows[0]["status"] == "NeedsReview"
    assert selected == ["CMP-TEST"]
    assert "1 trường hợp cần duyệt" in summary
    assert active == str(run)

    job_id = "a" * 32
    folder = tmp_path / "data" / "processed" / "extraction_jobs" / job_id
    folder.mkdir(parents=True)
    (folder / "graph_status.json").write_text(json.dumps({"status": "completed", "run_dir": str(run)}), encoding="utf-8")
    rows, selected, summary, active = callback(0, "current", "all", "all", {"id": job_id}, [])
    assert len(rows) == 1 and "phiên upload hiện tại" in summary
