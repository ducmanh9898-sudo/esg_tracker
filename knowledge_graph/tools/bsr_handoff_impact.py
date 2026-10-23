"""Merge a reviewed BSR handoff into a temporary claim copy and compare pilot results."""

import argparse
import copy
import json
import re
import sys
from collections import Counter
from pathlib import Path

from build_demo import build
from tools.bsr_pilot_acceptance_gate import (
    GAP_STATUS_PATH, RULE_CATALOGUE_PATH, evaluate_gate,
)
from tools.bsr_pilot_dry_run import ROOT, _read, assemble_report
from tools.bsr_review_packet import build_packet, response_template, validate_responses
from tools.financial_adapter import adapt_reports
from tools.handoff_preflight import preflight
from tools.normalizer import find_source_dir, load_json, resolve_pointer
from tools.pilot_readiness import build_inventory
from tools.standards_coverage_report import build_report as build_coverage
from tools.standards_crosswalk import load_crosswalk


HANDOFF = ROOT / "data" / "handoff" / "provenance_boundary_handoff_bsr2023_2025_strict_review.json"
CLAIMS = ROOT / "output" / "normalized_claims.json"
CLAIM_PERIOD_TYPES = {"annual", "quarterly", "monthly", "instant", "other"}
IDENTITY_FIELDS = ("company_id", "report_year", "source_file", "source_pages", "json_pointer")
PROVENANCE_FIELDS = (
    "report_id", "period_type", "metric_period_year", "original_text", "extraction_status",
    "boundary", "missing_fields", "uncertainty_reason", "source_pdf", "source_pdf_path",
    "data_quality_flags", "provenance_update", "source_interpretation_note",
)


def _text_type(record):
    declared = record.get("original_text_type")
    if declared:
        return declared
    value = record.get("original_text")
    if value is None:
        return "missing"
    if re.match(r"\s*(Bảng|Table|GRI\s+\d{3}-\d)\b", value, re.IGNORECASE):
        return "structured_table_transcription"
    if re.match(r"\s*(Biểu đồ|Chart|Infographic)\b", value, re.IGNORECASE):
        return "structured_chart_transcription"
    return "unverified_transcription"


def merge_handoff(claims, handoff, source_dir=None):
    """Return a new list; report all conflicts before allowing any merge."""
    merged = copy.deepcopy(claims)
    index = {claim["claim_id"]: claim for claim in merged}
    conflicts = []
    seen = set()
    source_dir = Path(source_dir) if source_dir else find_source_dir()
    source_cache = {}
    text_types = Counter()
    for record in handoff["records"]:
        pair = (record["claim_id"], record["evidence_id"])
        issues = []
        if pair in seen:
            issues.append("duplicate claim_id/evidence_id")
        seen.add(pair)
        claim = index.get(pair[0])
        evidence = next((e for e in claim.get("evidence", []) if e["evidence_id"] == pair[1]), None) if claim else None
        if claim is None:
            issues.append("claim_id missing")
        elif evidence is None:
            issues.append("evidence_id does not belong to claim_id")
        else:
            for field in IDENTITY_FIELDS:
                current = (claim if field in ("company_id", "report_year") else evidence).get(field)
                if current != record[field]:
                    issues.append(f"{field}: handoff={record[field]!r}, current={current!r}")
            if record.get("metric_period_year") is not None and claim.get("observation_year") != record["metric_period_year"]:
                issues.append("metric_period_year differs from claim observation_year")
            if not re.fullmatch(rf"BSR_{record['report_year']}_esg\.json", record["source_file"]):
                issues.append("source_file does not match report_year")
            if record.get("source_pdf") != f"BSR_{record['report_year']}.pdf":
                issues.append("source_pdf does not match report_year")
            path = source_dir / record["source_file"]
            try:
                if path not in source_cache:
                    source_cache[path] = load_json(path)
                value = resolve_pointer(source_cache[path], record["json_pointer"])
                if type(value) is not type(claim["value"]) or value != claim["value"]:
                    issues.append(f"source value differs: JSON={value!r}, claim={claim['value']!r}")
            except (OSError, KeyError, IndexError, TypeError, ValueError) as exc:
                issues.append(f"source pointer cannot be resolved: {exc}")
            for field in PROVENANCE_FIELDS:
                if field in evidence and evidence[field] != record.get(field):
                    issues.append(f"existing evidence.{field} conflicts with handoff")
            derived_type = _text_type(record)
            derived_verbatim = record.get("original_text_verbatim") is True and derived_type == "verbatim_pdf_quote"
            for field, expected in (("original_text_type", derived_type), ("original_text_verbatim", derived_verbatim)):
                if field in evidence and evidence[field] != expected:
                    issues.append(f"existing evidence.{field} conflicts with handoff")
            if evidence.get("source_text") is not None and evidence["source_text"] != record.get("original_text"):
                issues.append("existing source_text conflicts with handoff original_text")
            if claim.get("reporting_boundary_verified") is True and record["boundary"]["status"] != "verified":
                issues.append("existing verified boundary conflicts with handoff status")
            period = record.get("period_type")
            if period in CLAIM_PERIOD_TYPES and claim.get("period_type") not in (None, period):
                issues.append("existing claim period_type conflicts with handoff")
        if issues:
            conflicts.append({"claim_id": pair[0], "evidence_id": pair[1], "reasons": issues})
            continue
        for field in PROVENANCE_FIELDS:
            if field in record:
                evidence[field] = copy.deepcopy(record[field])
        evidence["original_text_type"] = _text_type(record)
        evidence["original_text_verbatim"] = (
            record.get("original_text_verbatim") is True
            and evidence["original_text_type"] == "verbatim_pdf_quote"
        )
        text_types[evidence["original_text_type"]] += 1
        # A structured table/chart transcription is not an exact PDF quotation.
        # source_text remains reserved for text verified as verbatim.
        if evidence["original_text_verbatim"]:
            evidence["source_text"] = record["original_text"]
        if record.get("period_type") in CLAIM_PERIOD_TYPES:
            claim["period_type"] = record["period_type"]
        claim["reporting_boundary_verified"] = record["boundary"]["status"] == "verified" and record.get("reporting_boundary_verified") is True
        if claim["reporting_boundary_verified"]:
            claim["reporting_boundary"] = record["boundary"]["basis"]
    return (None if conflicts else merged), {"matched_records": len(seen), "conflicts": conflicts, "text_types": dict(text_types)}


def _gate(pipeline, report, inventory):
    claims = pipeline["claims"]
    packet = build_packet(report)
    responses = response_template(packet)
    context = {
        "dry_run": report,
        "claims": claims,
        "assessments": pipeline["assessments"]["claim_assessments"],
        "inventory": inventory,
        "coverage": build_coverage(claims, pipeline["assessments"]["claim_assessments"],
                                   load_crosswalk(), _read(RULE_CATALOGUE_PATH), _read(GAP_STATUS_PATH)),
        "packet": packet,
        "review_validation": validate_responses(packet, responses),
        "exceptions": [],
    }
    return evaluate_gate(context), context["coverage"]


def _summary(report, gate, coverage):
    trace = report["traceability"]
    return {
        "claims": report["counts"]["claims"],
        "findings": report["counts"]["findings"],
        "finding_statuses": report["counts"]["finding_statuses"],
        "r01": report["cases"]["r01"].get("rule_status"),
        "traceability": {key: trace[key] for key in ("fully_traceable_findings", "finding_count", "complete_paths", "path_count")},
        "temporal": [{key: pair[key] for key in ("from_year", "to_year", "assessment_status", "comparison_performed")}
                     for pair in report["cases"]["board_temporal"].get("comparisons", [])],
        "financial": {key: report["cases"]["workforce_financial"].get(key)
                      for key in ("status", "fc01_status", "comparison_performed", "finding_created", "join_checks")},
        "standards": coverage["counts"],
        "gate_status": gate["status"],
        "gate_criteria": {item["criterion_id"]: item["status"] for item in gate["criteria"]},
    }


def run(temp_dir, handoff_path=HANDOFF):
    temp_dir = Path(temp_dir).resolve()
    protected = (ROOT / "output").resolve()
    if temp_dir == protected or protected in temp_dir.parents:
        raise ValueError("temporary directory must be outside output/")
    if temp_dir.exists() and any(temp_dir.iterdir()):
        raise ValueError("temporary directory must be new or empty")
    check = preflight(handoff_path, CLAIMS)
    if check["summary"]["blocking"]:
        raise ValueError(f"handoff preflight has {check['summary']['blocking']} blocking records")
    baseline_claims = _read(CLAIMS)
    merged, merge_report = merge_handoff(baseline_claims, _read(handoff_path))
    if merge_report["conflicts"]:
        return {"status": "conflict", "preflight": check["summary"], "merge": merge_report}
    temp_dir.mkdir(parents=True)
    financial = adapt_reports()
    inventory = build_inventory()
    candidate = _read(ROOT / "data" / "config" / "financial_link_bsr_workforce_sample.json")
    validation_cases = _read(ROOT / "data" / "config" / "validation_cases.json")["cases"]
    results = {}
    for label, claims in (("before", baseline_claims), ("after", merged)):
        output = temp_dir / label
        pipeline = build(output, claims_override=claims)
        report = assemble_report(pipeline, financial, inventory, candidate, validation_cases, check)
        report["handoff_status"] = "preflight_only_not_ingested" if label == "before" else "merged_into_temporary_copy"
        gate, coverage = _gate(pipeline, report, inventory)
        (output / "bsr_dry_run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "bsr_pilot_acceptance_gate.json").write_text(json.dumps(gate, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output / "standards_coverage.json").write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results[label] = _summary(report, gate, coverage)
    comparison = {"status": "dry_run_complete", "handoff": str(handoff_path), "preflight": check["summary"],
                  "merge": merge_report, "before": results["before"], "after": results["after"],
                  "review_required": "All 30 handoff records and four PDF review cases remain pending human adjudication."}
    (temp_dir / "comparison.json").write_text(json.dumps(comparison, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return comparison


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--temp-dir", type=Path, required=True)
    parser.add_argument("--handoff", type=Path, default=HANDOFF)
    args = parser.parse_args(argv)
    result = run(args.temp_dir, args.handoff)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if result["status"] == "conflict" else 0


if __name__ == "__main__":
    raise SystemExit(main())
