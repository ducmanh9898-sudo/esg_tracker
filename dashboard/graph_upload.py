"""Run the Graph bridge for one completed six-PDF BSR upload batch."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

from dashboard.extraction_worker import job_folder
from src.extraction.corporate_handoff import build_delivery
from src.extraction.source_v2 import atomic_json, now


ROOT = Path(__file__).resolve().parents[1]
GRAPH_REPO = ROOT / "knowledge_graph" if (ROOT / "knowledge_graph" / "kg").is_dir() else ROOT.parent / "esg-greenwashing-risk-framework"
YEARS = (2023, 2024, 2025)
EXPECTED = {(year, kind, scope) for year in YEARS
            for kind, scope in (("ESG", None), ("Financial", "Consolidated"))}


def graph_root():
    return Path(os.environ.get("ESGTRACKER_GRAPH_REPO", GRAPH_REPO)).resolve()


def read_graph_status(root, job_id):
    try:
        path = job_folder(root, job_id) / "graph_status.json"
    except ValueError:
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write_status(root, job_id, status):
    atomic_json(job_folder(root, job_id) / "graph_status.json", {**status, "updated_at": now()})
    return status


def eligible_bsr_batch(result):
    if result.get("status") != "completed":
        return False, "Extract chưa hoàn tất."
    documents = result.get("documents", [])
    if len(documents) != 6 or result.get("manifest", {}).get("failures"):
        return False, "Graph BSR cần đủ 6 PDF đã trích xuất thành công: ESG và BCTC hợp nhất của từng năm 2023–2025."
    seen = set()
    for doc in documents:
        reports = doc.get("output", {}).get("reports", [])
        if not reports:
            return False, "Một báo cáo chưa có metadata nguồn để đưa vào Graph."
        report = reports[0]
        if str(report.get("company_id", "")).upper() != "BSR":
            return False, "Batch này không phải toàn bộ báo cáo BSR."
        year = report.get("reporting_year")
        kind = report.get("report_type")
        if year not in YEARS or kind not in ("ESG", "financial_statements"):
            return False, "Batch cần đúng ESG và BCTC BSR của ba năm 2023–2025."
        slot = (year, kind)
        if slot in seen:
            return False, "Có hai PDF cùng năm và loại báo cáo; cần chọn đúng sáu nguồn."
        seen.add(slot)
    required = {(year, kind) for year in YEARS for kind in ("ESG", "financial_statements")}
    return (True, "") if seen == required else (False, "Thiếu ESG hoặc BCTC của một trong ba năm.")


def run_graph_for_upload(root, job_id, result, progress=None):
    """Preserve Extract success even when delivery or Graph cannot complete."""
    allowed, reason = eligible_bsr_batch(result)
    if not allowed:
        return _write_status(root, job_id, {"status": "skipped", "reason": reason})
    repo = graph_root()
    script = repo / "tools" / "extract_graph_bridge.py"
    if not script.is_file():
        return _write_status(root, job_id, {"status": "failed", "reason": "Không tìm thấy dự án Graph bên cạnh ESG Tracker."})
    run_dir = repo / "output" / f"bsr_upload_{job_id}"
    analysis_dir = repo / "output" / f"bsr_upload_{job_id}_analysis"
    delivery = run_dir / "extract" / "delivery"
    run_dir.mkdir(parents=True, exist_ok=True)
    _write_status(root, job_id, {"status": "running", "stage": "delivery", "run_dir": str(analysis_dir)})
    if progress:
        progress({"stage": "graph_delivery"})
    try:
        if not (delivery / "manifest.json").is_file():
            build_delivery(result, delivery)
        manifest = json.loads((delivery / "manifest.json").read_text(encoding="utf-8"))
        slots = {(item["report_year"], item["report_type"], item.get("financial_scope"))
                 for item in manifest.get("files", []) if item.get("status") == "partial"}
        if slots != EXPECTED:
            return _write_status(root, job_id, {"status": "skipped", "run_dir": str(analysis_dir),
                "reason": "Gói bàn giao chưa có đủ 3 ESG và 3 BCTC hợp nhất hợp lệ; xem delivery/notes/blocked_documents.json."})
        validation = json.loads((delivery / "validation" / "report.json").read_text(encoding="utf-8"))
        if not validation.get("mechanical_valid"):
            return _write_status(root, job_id, {"status": "failed", "run_dir": str(analysis_dir),
                "reason": "Gói Extract chưa qua kiểm tra kỹ thuật cho Graph."})
        _write_status(root, job_id, {"status": "running", "stage": "graph", "run_dir": str(analysis_dir)})
        if progress:
            progress({"stage": "knowledge_graph"})
        python = repo / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not python.is_file():
            python = Path(sys.executable)
        command = [str(python), "-B", str(script), "--manifest", str(delivery / "manifest.json"),
                   "--run-dir", str(analysis_dir)]
        with (run_dir / "graph_bridge.log").open("w", encoding="utf-8") as log:
            finished = subprocess.run(command, cwd=repo, stdout=log, stderr=subprocess.STDOUT,
                                      timeout=1800, check=False,
                                      creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        report_file = analysis_dir / "bridge_report.json"
        report = json.loads(report_file.read_text(encoding="utf-8")) if report_file.is_file() else {}
        if finished.returncode not in (0, 2) or report.get("status") == "failed" or not (analysis_dir / "review_cases.json").is_file():
            return _write_status(root, job_id, {"status": "failed", "run_dir": str(analysis_dir),
                "reason": report.get("error") or "Graph dừng; xem graph_bridge.log trong thư mục lượt chạy."})
        count = len(json.loads((analysis_dir / "review_cases.json").read_text(encoding="utf-8")).get("cases", []))
        return _write_status(root, job_id, {"status": "completed", "run_dir": str(analysis_dir),
            "review_cases": count, "graph_status": report.get("status")})
    except (OSError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        return _write_status(root, job_id, {"status": "failed", "run_dir": str(analysis_dir),
            "reason": f"{type(exc).__name__}: {exc}"})
