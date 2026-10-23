"""Only a complete six-source BSR upload can start this Graph route."""
import json
from pathlib import Path
from types import SimpleNamespace

from dashboard import graph_upload


def _result():
    return {"status": "completed", "manifest": {"failures": []}, "documents": [
        {"output": {"reports": [{"company_id": "BSR", "reporting_year": year, "report_type": kind}]}}
        for year in (2023, 2024, 2025) for kind in ("ESG", "financial_statements")
    ]}


def test_six_pdf_upload_runs_graph_bridge(tmp_path, monkeypatch):
    root = tmp_path / "esgtracker"
    repo = tmp_path / "esg-greenwashing-risk-framework"
    script = repo / "tools" / "extract_graph_bridge.py"
    script.parent.mkdir(parents=True)
    script.write_text("# mocked Graph bridge\n", encoding="utf-8")
    job_id = "b" * 32
    (root / "data" / "processed" / "extraction_jobs" / job_id).mkdir(parents=True)
    monkeypatch.setenv("ESGTRACKER_GRAPH_REPO", str(repo))
    seen = []

    def delivery(_result, path):
        path.mkdir(parents=True)
        (path / "validation").mkdir()
        (path / "manifest.json").write_text(json.dumps({"files": [
            {"report_year": year, "report_type": kind, "financial_scope": scope, "status": "partial"}
            for year, kind, scope in graph_upload.EXPECTED]}), encoding="utf-8")
        (path / "validation" / "report.json").write_text(json.dumps({"mechanical_valid": True}), encoding="utf-8")

    def bridge(command, **_kwargs):
        seen.append(command)
        run_dir = Path(command[command.index("--run-dir") + 1])
        run_dir.mkdir(parents=True)
        (run_dir / "bridge_report.json").write_text(json.dumps({"status": "partial"}), encoding="utf-8")
        (run_dir / "review_cases.json").write_text(json.dumps({"cases": [{"id": "CMP-ONE"}]}), encoding="utf-8")
        return SimpleNamespace(returncode=2)

    monkeypatch.setattr(graph_upload, "build_delivery", delivery)
    monkeypatch.setattr(graph_upload.subprocess, "run", bridge)
    result = graph_upload.run_graph_for_upload(root, job_id, _result())
    assert result["status"] == "completed"
    assert result["review_cases"] == 1
    assert Path(result["run_dir"]).name == f"bsr_upload_{job_id}_analysis"
    assert len(seen) == 1
    assert graph_upload.read_graph_status(root, job_id)["status"] == "completed"


def test_partial_upload_stays_out_of_graph(tmp_path):
    root = tmp_path / "esgtracker"
    job_id = "c" * 32
    (root / "data" / "processed" / "extraction_jobs" / job_id).mkdir(parents=True)
    result = _result()
    result["documents"].pop()
    status = graph_upload.run_graph_for_upload(root, job_id, result)
    assert status["status"] == "skipped"
    assert "6 PDF" in status["reason"]
