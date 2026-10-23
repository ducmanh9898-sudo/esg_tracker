import argparse
import csv
import json
import webbrowser
from pathlib import Path

from tools.assessment_builder import apply_assessment_graph, build_assessments
from tools.deduplicate_pvd import compare_overlapping_pvd_extracts
from tools.financial_adapter import adapt_reports, add_bsr_workforce_context
from tools.graph_builder import build_graph, render_html
from tools.normalizer import normalize
from tools.rule_engine import evaluate
from tools.standards_crosswalk import apply_crosswalk, load_crosswalk
from tools.temporal_assessment import apply_temporal_assessment, load_temporal_config
from tools.validator import validate_claims
from tools.validation_protocol import validate_system


ROOT = Path(__file__).resolve().parent


def _write_findings(findings, output):
    (output / "findings.json").write_text(
        json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    columns = [
        "finding_id", "rule_id", "status", "severity", "topic", "report_years",
        "observation_years", "summary", "calculation", "source_files", "source_pages",
    ]
    with (output / "findings.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for finding in findings:
            row = {key: finding[key] for key in columns}
            for key in ("report_years", "observation_years", "source_files", "source_pages"):
                row[key] = ", ".join(map(str, row[key]))
            writer.writerow(row)


def build(output_dir=None, claims_override=None):
    output = Path(output_dir) if output_dir else ROOT / "output"
    output.mkdir(parents=True, exist_ok=True)

    if claims_override is None:
        claims = normalize(output)
    else:
        # An isolated input snapshot for handoff impact runs. Never normalize over it.
        claims = claims_override
        (output / "normalized_claims.json").write_text(
            json.dumps(claims, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    input_validation = validate_claims(claims)
    (output / "validation_report.json").write_text(
        json.dumps(input_validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not input_validation["valid"]:
        raise ValueError(f"Common Input Schema không hợp lệ; xem {output / 'validation_report.json'}")

    rules = json.loads((ROOT / "data" / "config" / "rules.json").read_text(encoding="utf-8"))
    findings = evaluate(claims, rules)
    _write_findings(findings, output)

    graph = build_graph(claims, findings)
    financial = adapt_reports()
    workforce_candidate = json.loads((ROOT / "data" / "config" / "financial_link_bsr_workforce_sample.json").read_text(encoding="utf-8"))
    graph = add_bsr_workforce_context(graph, claims, financial["records"], workforce_candidate)
    graph = apply_crosswalk(graph, claims, load_crosswalk())
    graph = apply_temporal_assessment(graph, claims, load_temporal_config())
    assessments = build_assessments(claims, findings, graph)
    graph = apply_assessment_graph(
        graph,
        assessments["claim_assessments"],
        assessments["company_assessments"],
    )

    system_validation = validate_system(claims, findings, graph, assessments)
    (output / "system_validation_report.json").write_text(
        json.dumps(system_validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not system_validation["valid"]:
        raise ValueError(f"System validation failed; see {output / 'system_validation_report.json'}")

    (output / "claim_assessments.json").write_text(
        json.dumps(assessments["claim_assessments"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "company_assessments.json").write_text(
        json.dumps(assessments["company_assessments"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "assessment_metadata.json").write_text(
        json.dumps({"deduplication": assessments["deduplication"]}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "graph.json").write_text(
        json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    html_path = output / "graph_demo.html"
    html_path.write_text(render_html(graph, findings, assessments), encoding="utf-8")

    dedup_rows = compare_overlapping_pvd_extracts()
    status_counts = {
        status: sum(finding["status"] == status for finding in findings)
        for status in ("Contradicted", "NeedsReview", "Supported", "InsufficientEvidence")
    }
    return {
        "claims": claims,
        "findings": findings,
        "graph": graph,
        "assessments": assessments,
        "validation": input_validation,
        "system_validation": system_validation,
        "finding_status_counts": status_counts,
        "pvd_duplicate_mappings_checked": len(dedup_rows),
        "html_path": html_path,
    }


def main(open_browser=True, output_dir=None):
    result = build(output_dir)
    print(f"Claims: {len(result['claims'])}")
    print(
        "Validation: "
        f"{result['validation']['error_count']} structural errors; "
        f"{result['validation']['manual_review_count']} claims awaiting manual review"
    )
    print(f"Findings: {len(result['findings'])} — {result['finding_status_counts']}")
    print(f"Graph: {len(result['graph']['nodes'])} nodes, {len(result['graph']['edges'])} edges")
    print(f"PVD duplicate mappings checked: {result['pvd_duplicate_mappings_checked']}")
    print(f"Demo: {result['html_path']}")
    if open_browser:
        webbrowser.open(result["html_path"].resolve().as_uri())
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the ESG graph demo")
    parser.add_argument("--no-browser", action="store_true", help="Không tự mở trình duyệt")
    parser.add_argument("--output-dir", help="Ghi output vào thư mục chỉ định")
    args = parser.parse_args()
    main(open_browser=not args.no_browser, output_dir=args.output_dir)
