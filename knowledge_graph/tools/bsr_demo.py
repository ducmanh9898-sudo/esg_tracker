"""Build and check the isolated BSR demo, then render a local evidence dashboard."""
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from kg.pipeline import ROOT, build
from tools.bsr_claim_review import build_claim_review
from tools.bsr_evidence_packet import render_review_packet
from tools.bsr_public_ui import render_public_ui

CONFIG = ROOT / "data/config/bsr_demo_config.json"
EXPECTED = ROOT / "data/config/bsr_demo_expected_cases.json"
PDF = ROOT / "data/source/pdf/BSR_2025_official.pdf"
PDF_SHA256 = "bb2e79c06b0781fe0da4cc3842ae7caeec73e4441d2da412ab3a466cb162c433"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    expected = read(EXPECTED)
    pdf_hash = hashlib.sha256(PDF.read_bytes()).hexdigest() if PDF.is_file() else None
    if pdf_hash != PDF_SHA256:
        raise RuntimeError("BSR source PDF missing or hash changed; source review must be repeated")
    summary = build(output_dir, CONFIG)
    names = ("normalized_claims", "rule_evaluations", "findings", "demo_findings",
             "claim_assessments", "company_assessments", "temporal_comparisons", "annotation_audit",
             "source_provenance_audit", "evidence_chain_sources", "graph", "financial_records",
             "financial_candidates", "financial_reconciliation")
    data = {name: read(output_dir / (name + ".json")) for name in names}
    data["summary"] = summary
    data["expected"] = expected
    data["annotations"] = read(ROOT / "data/review/bsr_demo_annotations.json")
    data["claim_review"] = build_claim_review(data)
    (output_dir / "claim_review.json").write_text(
        json.dumps(data["claim_review"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evals = {(row["report_year"], row["rule_id"]): row for row in data["rule_evaluations"]}
    case_results = []
    for case in expected["cases"]:
        result = evals.get((2025, case["rule_id"]))
        case_results.append({"case_id": case["case_id"], "expected": case["expected_outcome"],
                             "actual": result["outcome"] if result else None,
                             "input_claim_ids_match": bool(result and set(result["input_claim_ids"]) == set(case["claim_ids"]))})
    company_rows = (data["company_assessments"]["company_year_assessments"]
                    + data["company_assessments"]["company_multiyear_assessments"])
    main_ids = {row["finding_id"] for row in data["findings"]}
    source_audit = data["source_provenance_audit"]
    source_nodes = [row for row in data["graph"]["nodes"] if row["type"] == "SourceArtifact"]
    official_links = [row for row in data["evidence_chain_sources"]
                      if row.get("source_id") == "SRC-BSR-2025-OFFICIAL-PDF-134"]
    checks = {
        "bsr_only_claims": summary["companies"] == {"BSR": len(data["normalized_claims"])},
        "bsr_only_findings": all(row["company_id"] == "BSR" for row in data["findings"]),
        "bsr_only_company_assessments": all(row["company_id"] == "BSR" for row in company_rows),
        "expected_cases_match": all(row["expected"] == row["actual"] and row["input_claim_ids_match"] for row in case_results),
        "finding_evidence_chains_complete": not summary["missing_evidence_chains"],
        "claim_and_company_assessments_present": bool(data["claim_assessments"] and data["company_assessments"]["company_year_assessments"]),
        "company_findings_unique": all(len(row["finding_ids"]) == len(set(row["finding_ids"])) == row["finding_count"] for row in company_rows),
        "annotation_file_clean": not (data["annotation_audit"]["rejected"] or data["annotation_audit"]["file_errors"]),
        "no_primary_synthetic": all(not row.get("synthetic") for row in data["findings"])
                                 and all(not row.get("synthetic") for row in data["graph"]["nodes"]),
        "demo_findings_separate": not (main_ids & {row["finding_id"] for row in data["demo_findings"]}),
        "no_risk_score": summary["risk_score"] is None,
        "pdf_hash_matches_review": pdf_hash == PDF_SHA256,
        "distinct_source_artifacts": len(source_nodes) == 4 and len({row["sourceId"] for row in source_nodes}) == 4,
        "extract_pdf_binary_honestly_missing": not source_audit["declared_pdf_binary_available"]
                                               and not source_audit["whole_document_equivalence_verified"],
        "selected_page_crosswalk_verified": len(source_audit["validated_page_crosswalk"]) == 6,
        "official_pdf_evidence_linked": len(source_audit["attached_evidence"]) == 11
                                        and len(official_links) == 4,
        "source_corroboration_did_not_approve_context": not source_audit["context_review_status_changed"],
        "all_selected_claims_have_review_ledger": len(data["claim_review"]["claims"]) == 30
            and len({row["claim_id"] for row in data["claim_review"]["claims"]}) == 30,
    }
    acceptance = {"schema_version": "1.0", "technical_demo_pass": all(checks.values()),
                  "evidence_acceptance": "pending_human_adjudication", "checks": checks,
                  "case_results": case_results, "pdf_sha256": pdf_hash,
                  "primary_findings": dict(Counter(row["status"] for row in data["findings"])),
                  "evaluation_outcomes": dict(Counter(row["outcome"] for row in data["rule_evaluations"])),
                  "note": "This checks reproducibility and guards, not factual verification of all claims."}
    acceptance["claim_review_coverage"] = {
        "selected_claims": len(data["claim_review"]["claims"]),
        "rule_outcomes_by_claim": data["claim_review"]["counts"],
        "reader_triage_by_claim": data["claim_review"]["reader_triage_counts"],
        "all_claims_conclusively_assessed": False,
        "standards_compliance_assessed": False,
        "financial_candidates": sum(len(row["financial"]["candidates"]) for row in data["claim_review"]["claims"]),
        "financial_comparisons_permitted": sum(
            link["comparable"] for row in data["claim_review"]["claims"]
            for link in row["financial"]["candidates"]),
    }
    packet = render_review_packet(output_dir, expected, data["rule_evaluations"],
                                  data["normalized_claims"], source_audit, data["annotations"], PDF)
    acceptance["review_packet"] = packet
    (output_dir / "demo_acceptance.json").write_text(json.dumps(acceptance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    render_public_ui(output_dir, data, acceptance)
    if not acceptance["technical_demo_pass"]:
        raise RuntimeError("BSR demo acceptance check failed; inspect demo_acceptance.json")
    return acceptance


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the isolated BSR ESG demo")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "output/bsr_demo")
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
