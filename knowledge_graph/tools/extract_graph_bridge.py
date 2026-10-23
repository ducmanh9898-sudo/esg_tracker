"""Run the external Extract batch, cross-report discovery, and corporate Graph.

The Extract repository is only executed. All new artifacts live under --run-dir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

if __package__:
    from .bsr_review_dashboard import render as render_review_dashboard
else:
    from bsr_review_dashboard import render as render_review_dashboard


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data/handoff/bsr_cross_report_profit_v1/manifest_with_annual_v1.json"
DEFAULT_PROFILE = ROOT / "data/config/bsr_esg_bctc_only_v1.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def full_bsr_config(source_manifest: Path, scope: str = "all") -> dict:
    """Use verified PDF bytes and select the requested source scope."""
    if scope not in {"all", "esg_bctc"}:
        raise ValueError("unsupported_bsr_scope")
    source_manifest = source_manifest.resolve()
    manifest = read_json(source_manifest)
    if manifest.get("schema_version") != "corporate-extract-manifest-1.0":
        raise ValueError("unsupported_source_manifest")
    selected = {}
    for row in manifest["files"]:
        if row["status"] == "unavailable":
            continue
        if (scope == "esg_bctc" and not
                ((row["report_type"] == "ESG" and
                  "annual" not in Path(row["pdf_path"]).name.lower()) or
                 (row["report_type"] == "Financial" and
                  row["financial_scope"] == "Consolidated"))):
            continue
        pdf = (source_manifest.parent / row["pdf_path"]).resolve()
        handoff = (source_manifest.parent / row["json_path"]).resolve()
        if not pdf.is_file() or not handoff.is_file() or sha256(pdf) != row["pdf_sha256"]:
            raise ValueError("source_missing_or_hash_mismatch:" + row["document_id"])
        doc = read_json(handoff)["document"]
        if doc["company_id"] != "BSR" or doc["report_year"] != row["report_year"]:
            raise ValueError("source_identity_mismatch:" + row["document_id"])
        source_type = doc["source_document_type"]
        if source_type not in {"sustainability_report", "annual_report", "financial_statement"}:
            raise ValueError("unsupported_document_type:" + source_type)
        slot = (row["report_year"], source_type, row["financial_scope"])
        entry = {"pdf": str(pdf), "sha256": row["pdf_sha256"],
                 "report_type": "financial_statements" if source_type == "financial_statement"
                                else "annual_report" if source_type == "annual_report" else "ESG",
                 "report_year": row["report_year"], "number_format": "vi"}
        if doc["source"].get("url"):
            entry["url"] = doc["source"]["url"]
        # The older 2025 ESG PDF and the official 2025 PDF occupy one slot.
        # Select the explicitly named official version; do not merge page numbers.
        priority = 1 if "official" in pdf.name.lower() else 0
        if slot in selected and priority == selected[slot][0]:
            raise ValueError("ambiguous_source_slot:" + str(slot))
        if slot not in selected or priority > selected[slot][0]:
            selected[slot] = (priority, entry)
    required_types = (("sustainability_report", None),
                      ("financial_statement", "Consolidated")) if scope == "esg_bctc" else (
                      ("sustainability_report", None), ("annual_report", None),
                      ("financial_statement", "Separate"),
                      ("financial_statement", "Consolidated"))
    expected = {(year, kind, financial_scope)
                for year in (2023, 2024, 2025)
                for kind, financial_scope in required_types}
    if set(selected) != expected:
        raise ValueError("missing_or_extra_bsr_slots:" + str(sorted(map(str, expected - set(selected)))))
    return {"company_id": "BSR", "documents": [selected[slot][1]
            for slot in sorted(selected, key=lambda s: (s[0], s[1], s[2] or ""))]}


def esg_bctc_config(source_manifest: Path) -> dict:
    """Select one ESG PDF and one consolidated BCTC PDF for each year."""
    return full_bsr_config(source_manifest, scope="esg_bctc")


def invoke(command: list[str], cwd: Path, accepted: set[int]) -> int:
    print("RUN " + " ".join(command), flush=True)
    code = subprocess.run(command, cwd=cwd, check=False).returncode
    if code not in accepted:
        raise RuntimeError(f"stage_exit_code:{code}:" + command[2])
    return code


def run(args: argparse.Namespace) -> dict:
    run_dir = args.run_dir.resolve()
    if run_dir.exists():
        raise ValueError("run_dir_exists_choose_new_directory")
    run_dir.mkdir(parents=True)
    report = {"status": "failed", "stages": {}, "run_dir": str(run_dir)}
    report_path = run_dir / "bridge_report.json"
    try:
        if args.extract_config:
            extract_repo = args.extract_repo.resolve()
            extract_python = args.extract_python or extract_repo / ".venv/Scripts/python.exe"
            command = [str(extract_python), str(extract_repo / "scripts/run_extract_batch.py"),
                       "--config", str(args.extract_config.resolve()), "--output", str(run_dir / "extract"),
                       "--engine", args.engine, "--page-timeout", str(args.page_timeout),
                       "--checkpoint-interval", str(args.checkpoint_interval)]
            if args.allow_native_fallback:
                command.append("--allow-native-fallback")
            if args.reuse_extract_from:
                command.extend(("--reuse-checkpoints-from", str(args.reuse_extract_from.resolve())))
            # 1 may mean some documents failed while a valid partial delivery exists.
            # The report and delivery validation below decide whether Graph can run.
            invoke(command, extract_repo, {0, 1, 2})
            extraction = read_json(run_dir / "extract/run_report.json")
            report["stages"]["extract"] = extraction
            if extraction.get("status") == "failed" or extraction.get("delivery_error"):
                raise ValueError("extract_failed_or_delivery_missing")
            manifest = run_dir / "extract/delivery/manifest.json"
            validation = read_json(run_dir / "extract/delivery/validation/report.json")
            if not validation.get("mechanical_valid"):
                raise ValueError("extract_delivery_failed_mechanical_validation")
        else:
            manifest = args.manifest.resolve()
            if not manifest.is_file():
                raise ValueError("manifest_missing")
        report["manifest"] = str(manifest)
        graph_python = args.graph_python or Path(sys.executable)
        discovery = run_dir / "discovery"
        scan_command = [str(graph_python), "-B", "-m", "kg.cross_report_scan", "--manifest", str(manifest),
                        "--profile", str(args.profile.resolve()), "--output-dir", str(discovery)]
        for path in args.comparisons:
            scan_command.extend(("--comparisons", str(path.resolve())))
        invoke(scan_command, ROOT, {0, 2})
        scan = read_json(discovery / "summary.json")
        report["stages"]["discovery"] = scan
        graph = run_dir / "graph"
        graph_command = [str(graph_python), "-B", "-m", "kg.corporate_pipeline", "--manifest", str(manifest),
                         "--config", str(args.profile.resolve()), "--comparisons", str(discovery / "comparisons.json"),
                         "--output-dir", str(graph)]
        if args.narrative_candidates:
            graph_command.extend(("--narrative-candidates", str(args.narrative_candidates.resolve())))
        if args.reviews:
            graph_command.extend(("--reviews", str(args.reviews.resolve())))
        invoke(graph_command, ROOT, {0, 2})
        graph_report = read_json(graph / "run_manifest.json")
        report["stages"]["graph"] = graph_report
        if graph_report.get("errors") or not graph_report.get("shacl_conforms"):
            raise ValueError("graph_validation_failed")
        temporal = run_dir / "temporal"
        temporal_command = [str(graph_python), "-B", "-m", "kg.longitudinal_scan",
                            "--records", str(graph / "normalized_records.json"),
                            "--profile", str(args.profile.resolve()), "--output-dir", str(temporal)]
        invoke(temporal_command, ROOT, {0})
        report["stages"]["temporal"] = read_json(temporal / "summary.json")
        report["status"] = "partial" if (scan["status"] == "partial" or
                            graph_report["status"] == "partial" or args.extract_config) else "completed"
        report["candidate_pairs"] = scan["candidate_pairs"]
        report["graph_records"] = graph_report["records"]
        report["review_template"] = str(graph / "review_template.json")
        report["review_page"] = str(discovery / "review.html")
        report["temporal_report"] = str(temporal / "report.html")
        dashboard = render_review_dashboard(run_dir, manifest)
        report["dashboard"] = dashboard
        report["entry_page"] = dashboard["entry_page"]
    except (OSError, KeyError, ValueError, RuntimeError) as exc:
        report["error"] = str(exc)
    write_json(report_path, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-full-config", type=Path, help="Write all-page BSR Extract config and exit")
    parser.add_argument("--prepare-esg-bctc-config", type=Path,
                        help="Write six-PDF ESG and consolidated BCTC config and exit")
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--extract-config", type=Path)
    source.add_argument("--manifest", type=Path)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--extract-repo", type=Path, default=ROOT.parent / "esgtracker")
    parser.add_argument("--extract-python", type=Path)
    parser.add_argument("--graph-python", type=Path)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--comparisons", type=Path, action="append", default=[],
                        help="Optional explicit comparisons for this exact Extract batch")
    parser.add_argument("--narrative-candidates", type=Path,
                        help="Optional reviewed-source narrative proposals for this batch")
    parser.add_argument("--reviews", type=Path, help="Human review events for matching record digests")
    parser.add_argument("--engine", choices=("docling", "native"), default="docling")
    parser.add_argument("--allow-native-fallback", action="store_true")
    parser.add_argument("--reuse-extract-from", type=Path,
                        help="Previous Extract run to copy processed page checkpoints from")
    parser.add_argument("--page-timeout", type=float, default=120)
    parser.add_argument("--checkpoint-interval", type=int, default=10)
    args = parser.parse_args()
    if args.prepare_full_config and args.prepare_esg_bctc_config:
        parser.error("select one config output")
    if args.prepare_esg_bctc_config:
        if args.extract_config or args.manifest or args.run_dir:
            parser.error("--prepare-esg-bctc-config cannot be combined with run arguments")
        write_json(args.prepare_esg_bctc_config, esg_bctc_config(args.source_manifest))
        print(str(args.prepare_esg_bctc_config.resolve()))
        return 0
    if args.prepare_full_config:
        if args.extract_config or args.manifest or args.run_dir:
            parser.error("--prepare-full-config cannot be combined with run arguments")
        write_json(args.prepare_full_config, full_bsr_config(args.source_manifest))
        print(str(args.prepare_full_config.resolve()))
        return 0
    if not args.run_dir or not (args.extract_config or args.manifest):
        parser.error("--run-dir and either --extract-config or --manifest are required")
    if args.reuse_extract_from and not args.extract_config:
        parser.error("--reuse-extract-from requires --extract-config")
    result = run(args)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result["status"] == "failed" else 2 if result["status"] == "partial" else 0


if __name__ == "__main__":
    raise SystemExit(main())
