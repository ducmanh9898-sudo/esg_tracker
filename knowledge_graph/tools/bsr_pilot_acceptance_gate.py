"""Repeatable acceptance gate for the single-company BSR pilot milestone."""

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.bsr_pilot_dry_run import ROOT, _read, run as run_dry_run
from tools.bsr_review_packet import build_packet, response_template, validate_responses
from tools.pilot_readiness import build_inventory
from tools.standards_crosswalk import load_crosswalk
from tools.standards_coverage_report import build_report as build_coverage
from tools.validation_protocol import LAYERS


CLAIMS_PATH = ROOT / "output" / "normalized_claims.json"
ASSESSMENTS_PATH = ROOT / "output" / "claim_assessments.json"
COMMON_SCHEMA_PATH = ROOT / "schemas" / "common-input-schema-v1.0.json"
HANDOFF_PATH = ROOT / "data" / "handoff" / "provenance_boundary_handoff.json"
RULE_CATALOGUE_PATH = ROOT / "data" / "config" / "rule_catalogue.json"
GAP_STATUS_PATH = ROOT / "data" / "integration_gap_status.json"
EXCEPTION_FIELDS = {"source_text", "period_type", "reporting_boundary", "source_review", "handoff_manual_review"}


def _criterion(criterion_id, status, evidence, actions):
    return {
        "criterion_id": criterion_id,
        "status": status,
        "evidence": evidence,
        "actions": actions,
    }


def _accepted_exceptions(exceptions, claim_ids):
    accepted = set()
    invalid = []
    for index, item in enumerate(exceptions):
        if not isinstance(item, dict):
            invalid.append(f"row:{index + 1} is not an object")
            continue
        ref = f"{item.get('claim_id', 'unknown')}/{item.get('field', 'unknown')}"
        if item.get("claim_id") not in claim_ids or item.get("field") not in EXCEPTION_FIELDS:
            invalid.append(f"{ref}: unknown claim or exception field")
        elif item.get("status") != "accepted" or any(
            not isinstance(item.get(field), str) or not item[field].strip()
            for field in ("reviewer", "reason", "source_basis")
        ):
            invalid.append(f"{ref}: exception needs accepted status, reviewer, reason and source basis")
        else:
            accepted.add((item["claim_id"], item["field"]))
    return accepted, invalid


def _input_provenance(context):
    claims = [claim for claim in context["claims"] if claim.get("company_id") == "BSR"]
    claim_ids = [claim.get("claim_id") for claim in claims]
    common_schema = _read(COMMON_SCHEMA_PATH)
    validator = Draft202012Validator(common_schema)
    schema_errors = [
        {"claim_id": claim.get("claim_id"), "message": error.message}
        for claim in claims for error in validator.iter_errors(claim)
    ]
    evidence_count = sum(len(claim.get("evidence", [])) for claim in claims)
    preflight = context["dry_run"].get("handoff_preflight")
    preflight_summary = preflight.get("summary") if preflight else None
    accepted_exceptions, invalid_exceptions = _accepted_exceptions(context["exceptions"], set(claim_ids))
    issues = []
    null_claim_ids = []
    for claim in claims:
        claim_id = claim["claim_id"]
        if claim.get("value") is None:
            null_claim_ids.append(claim_id)
        if any(not evidence.get("source_text") for evidence in claim.get("evidence", [])):
            issues.append((claim_id, "source_text"))
        if not claim.get("period_type"):
            issues.append((claim_id, "period_type"))
        if not claim.get("reporting_boundary") or claim.get("reporting_boundary_verified") is not True:
            issues.append((claim_id, "reporting_boundary"))
        if claim.get("review_status") != "reviewed":
            issues.append((claim_id, "source_review"))
    for record in preflight.get("manual_review_records", []) if preflight else []:
        issues.append((record["claim_id"], "handoff_manual_review"))
    unresolved = [
        {"claim_id": claim_id, "field": field}
        for claim_id, field in sorted(set(issues)) if (claim_id, field) not in accepted_exceptions
    ]
    hard_errors = []
    if len(claims) != 30 or len(set(claim_ids)) != 30:
        hard_errors.append(f"Expected 30 unique BSR claims; found {len(claims)} rows and {len(set(claim_ids))} IDs")
    if schema_errors:
        hard_errors.append(f"{len(schema_errors)} common input schema errors")
    if preflight_summary is None:
        hard_errors.append("Handoff preflight result unavailable")
    elif preflight_summary["blocking"] or preflight_summary["records"] != evidence_count or preflight_summary["valid"] != evidence_count:
        hard_errors.append("Handoff preflight has blocking errors or does not cover every evidence record")
    if invalid_exceptions:
        hard_errors.append(f"{len(invalid_exceptions)} invalid exception records")
    status = "blocked" if hard_errors else "needs_review" if unresolved else "pass"
    actions = []
    if hard_errors:
        actions.append("Correct identity/schema or handoff coverage errors and rerun preflight.")
    if unresolved:
        actions.append("Provide verified provenance/period/boundary/source review or submit explicit accepted exceptions with reviewer and source basis.")
    return _criterion("input_provenance", status, {
        "claim_count": len(claims),
        "unique_claim_count": len(set(claim_ids)),
        "evidence_count": evidence_count,
        "schema_error_count": len(schema_errors),
        "schema_errors": schema_errors,
        "preflight": preflight_summary,
        "unresolved_issue_count": len(unresolved),
        "unresolved_issues": unresolved,
        "accepted_exception_count": len(accepted_exceptions),
        "invalid_exceptions": invalid_exceptions,
        "exception_fields": sorted(EXCEPTION_FIELDS),
        "explicit_null_value_claim_ids": null_claim_ids,
        "null_policy": "A schema-valid null is an explicit evidence gap, not a structural input error.",
        "hard_errors": hard_errors,
    }, actions)


def _finding_trace(context):
    trace = context["dry_run"]["traceability"]
    layer = context["dry_run"]["validation"]["layers"]["evidence_linkage"]
    complete = (
        trace["finding_count"] > 0
        and trace["fully_traceable_findings"] == trace["finding_count"]
        and trace["complete_paths"] == trace["path_count"]
        and trace["path_count"] > 0 and layer["valid"]
    )
    return _criterion("finding_traceability", "pass" if complete else "blocked", {
        "findings": trace["finding_count"],
        "fully_traceable_findings": trace["fully_traceable_findings"],
        "paths": trace["path_count"],
        "complete_paths": trace["complete_paths"],
        "evidence_linkage_validation": layer,
        "scope": "Finding → Claim → Measurement → Evidence and Report, with source pages and JSON pointer; structural trace only.",
    }, [] if complete else ["Repair missing graph links or source locators and rerun six-layer validation."])


def _esg_assessments(context):
    claims = [claim for claim in context["claims"] if claim.get("company_id") == "BSR"]
    assessments = [item for item in context["assessments"] if item.get("company_id") == "BSR"]
    claim_dimensions = Counter(claim["dimension"] for claim in claims)
    assessment_dimensions = Counter(item["dimension"] for item in assessments)
    counts = context["dry_run"]["counts"]
    inventory = [item for item in context["inventory"]["records"] if item["company_id"] == "BSR"]
    company_layer = context["dry_run"]["validation"]["layers"]["company_aggregation"]
    complete = (
        all(claim_dimensions[dimension] > 0 and assessment_dimensions[dimension] > 0 for dimension in "ESG")
        and counts["claim_assessments"] == len(assessments) and counts["company_assessments"] > 0
        and counts["company_year_assessments"] > 0 and counts["company_multiyear_assessments"] > 0
        and company_layer["valid"]
    )
    return _criterion("esg_two_level_assessments", "pass" if complete else "blocked", {
        "claim_dimensions": dict(claim_dimensions),
        "assessment_dimensions": dict(assessment_dimensions),
        "claim_assessments": len(assessments),
        "company_year_assessments": counts["company_year_assessments"],
        "company_multiyear_assessments": counts["company_multiyear_assessments"],
        "readiness_inventory_entries": len(inventory),
        "readiness_inventory_statuses": dict(Counter(item["status"] for item in inventory)),
        "company_aggregation_validation": company_layer,
    }, [] if complete else ["Complete E/S/G claim and claim/company assessment coverage; fix company aggregation validation."])


def _pdf_review(context):
    packet = context["packet"]
    result = context["review_validation"]
    cases = result["cases"]
    expected_ids = {case["case_id"] for case in packet["cases"]}
    accepted_ids = {case["case_id"] for case in cases if case["effective_status"] == "accepted"}
    complete = (
        len(expected_ids) == 4 and result["valid"] and accepted_ids == expected_ids
        and result["gold_labels_created"] == 0
    )
    status = "pass" if complete else "blocked"
    actions = [] if complete else [
        "Have a named reviewer inspect every cited PDF source and enter page basis, concrete decision and all six checks for each of the four cases; validate responses again."
    ]
    return _criterion("pdf_case_adjudication", status, {
        "packet_id": packet["packet_id"],
        "case_count": len(expected_ids),
        "response_validation_valid": result["valid"],
        "accepted_count": result["accepted_count"],
        "pending_count": result["pending_count"],
        "rejected_count": result["rejected_count"],
        "unclear_count": result["unclear_count"],
        "case_statuses": {case["case_id"]: case["effective_status"] for case in cases},
        "gold_labels_created": result["gold_labels_created"],
        "policy": "Current findings never supply a gold label or an automatic reviewer decision.",
    }, actions)


def _temporal(context):
    board = context["dry_run"]["cases"]["board_temporal"]
    pairs = board.get("comparisons", [])
    layer = context["dry_run"]["validation"]["layers"]["temporal_comparison"]
    invalid = not layer["valid"] or any(
        item.get("comparison_performed") and item.get("flags", {}).get("incompatibilities")
        for item in pairs
    )
    complete = len(pairs) == 2 and all(
        item.get("comparison_performed") is True
        and item.get("assessment_status") == "Comparable"
        and not item.get("flags", {}).get("incompatibilities")
        and not item.get("flags", {}).get("missing_context")
        for item in pairs
    )
    return _criterion("temporal_comparability", "blocked" if invalid else "pass" if complete else "needs_review", {
        "pair_count": len(pairs),
        "pairs": [{
            "comparison_id": item["comparison_id"],
            "from_year": item["from_year"],
            "to_year": item["to_year"],
            "assessment_status": item["assessment_status"],
            "comparison_performed": item["comparison_performed"],
            "flags": item["flags"],
        } for item in pairs],
        "temporal_validation": layer,
        "policy": "A numeric change alone is not a temporal inconsistency or new finding.",
    }, [] if complete else ["Confirm period type, boundary, baseline/restatement and original text for both board pairs; rerun comparability guards."])


def _financial(context):
    candidate = context["dry_run"]["cases"]["workforce_financial"]
    finding_ids = [
        item["finding_id"] for item in context["dry_run"]["traceability"]["findings"]
        if item["rule_id"] == "FC01"
    ]
    safe_candidate = (
        candidate.get("category") == "financial_candidate"
        and candidate.get("status") == "NeedsReview"
        and candidate.get("fc01_status") == "inactive"
        and candidate.get("comparison_performed") is False
        and candidate.get("finding_created") is False
        and not finding_ids
    )
    return _criterion("financial_candidate_safety", "pass" if safe_candidate else "blocked", {
        "candidate_id": candidate.get("case_id"),
        "status": candidate.get("status"),
        "fc01_status": candidate.get("fc01_status"),
        "comparison_performed": candidate.get("comparison_performed"),
        "finding_created": candidate.get("finding_created"),
        "fc01_finding_ids": finding_ids,
        "join_checks": candidate.get("join_checks"),
        "missing_conditions": candidate.get("missing_conditions"),
        "policy": "The candidate is not a rule finding and cannot be promoted to Contradicted by this gate.",
    }, [] if safe_candidate else ["Restore candidate-only FC01 handling; investigate any comparison or FC01 finding before acceptance."])


def _standards(context):
    coverage = context["coverage"]
    rows = coverage["claims"]
    claim_ids = {claim["claim_id"] for claim in context["claims"] if claim.get("company_id") == "BSR"}
    report_ids = {row["claim_id"] for row in rows}
    families = coverage["families"]
    wrong_status = [row["claim_id"] for row in rows if (
        row["has_verified_mapping"] != any(mapping["verification_status"] == "verified" for mapping in row["mappings"])
        or row["has_unverified_candidate"] != any(mapping["verification_status"] == "unverified" for mapping in row["mappings"])
    )]
    industry = [mapping for row in rows for mapping in row["mappings"]
                if mapping["source_type"] in {"sasb_standard", "industry_based_guidance"}]
    industry_misrepresented = [mapping["mapping_id"] for mapping in industry if (
        mapping["source_type"] == "sasb_standard"
        and mapping["verification_status"] == "verified"
        and mapping["industry_applicability_status"] != "verified"
    ) or mapping["industry_applicability_status"] is None]
    distinct = (
        "SASB Standard" in families and "IFRS S2 Industry-based Guidance" in families
        and all(mapping["family"] == ("SASB Standard" if mapping["source_type"] == "sasb_standard"
                                      else "IFRS S2 Industry-based Guidance") for mapping in industry)
    )
    complete = (
        report_ids == claim_ids and len(rows) == len(claim_ids) == 30
        and not wrong_status and not industry_misrepresented and distinct
        and coverage["counts"]["project_rules"] == 9
        and "not compliance tests" in coverage["project_rule_policy"]
        and "no compliance or violation conclusion" in coverage["conclusion_policy"]
    )
    return _criterion("standards_verification_level", "pass" if complete else "blocked", {
        "coverage_counts": coverage["counts"],
        "families": {name: {
            "verified_claim_count": item["verified_claim_count"],
            "candidate_claim_count": item["candidate_claim_count"],
            "industry_applicability_unverified_claim_count": item["industry_applicability_unverified_claim_count"],
        } for name, item in families.items()},
        "wrong_status_claim_ids": wrong_status,
        "industry_misrepresented_mapping_ids": industry_misrepresented,
        "sasb_and_ifrs_s2_guidance_separate": distinct,
        "unmapped_claims_allowed": True,
        "policy": coverage["project_rule_policy"],
    }, [] if complete else ["Correct mapping status/source_type or industry applicability presentation; do not require mappings for every claim."])


def evaluate_gate(context):
    """Evaluate supplied evidence; this function never mutates source artifacts."""
    criteria = [
        _input_provenance(context),
        _finding_trace(context),
        _esg_assessments(context),
        _pdf_review(context),
        _temporal(context),
        _financial(context),
        _standards(context),
    ]
    statuses = Counter(item["status"] for item in criteria)
    overall = "blocked" if statuses["blocked"] else "needs_review" if statuses["needs_review"] else "pass"
    return {
        "gate_id": "BSR-SINGLE-COMPANY-PILOT-ACCEPTANCE",
        "scope": "BSR only, current 30 claims; read-only repeatable acceptance check",
        "status": overall,
        "bsr_pilot_accepted": overall == "pass",
        "milestones": [
            {
                "milestone": "BSR single-company pilot acceptance",
                "status": "accepted" if overall == "pass" else "not_accepted",
                "gate_status": overall,
            },
            {
                "milestone": "Roadmap expansion to 3–5 companies",
                "status": "future_expansion",
                "satisfied_by_bsr_gate": False,
            },
        ],
        "criteria": criteria,
        "status_counts": {status: statuses[status] for status in ("pass", "needs_review", "blocked")},
        "conclusion_policy": "No gold label, standards compliance/violation conclusion, new finding or automatic NeedsReview→Contradicted promotion is created.",
        "validation_protocol_layers": list(LAYERS),
        "source_handoff": (context["dry_run"].get("handoff_preflight") or {}).get("handoff_file"),
    }


def _load_exceptions(path):
    if path is None:
        return []
    payload = _read(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("exceptions"), list):
        raise ValueError("Exceptions file must be an object with an exceptions array")
    return payload["exceptions"]


def collect_context(handoff_path=HANDOFF_PATH, responses_path=None, exceptions_path=None):
    with tempfile.TemporaryDirectory(prefix="bsr_acceptance_dry_run_") as temp:
        dry_run = run_dry_run(Path(temp), handoff_path)
    claims = _read(CLAIMS_PATH)
    assessments = _read(ASSESSMENTS_PATH)
    coverage = build_coverage(
        claims, assessments, load_crosswalk(), _read(RULE_CATALOGUE_PATH), _read(GAP_STATUS_PATH)
    )
    packet = build_packet(dry_run)
    responses = _read(responses_path) if responses_path else response_template(packet)
    return {
        "dry_run": dry_run,
        "claims": claims,
        "assessments": assessments,
        "inventory": build_inventory(),
        "coverage": coverage,
        "packet": packet,
        "review_validation": validate_responses(packet, responses),
        "exceptions": _load_exceptions(exceptions_path),
    }


def render_markdown(result):
    lines = [
        "# BSR single-company pilot acceptance gate", "",
        f"Gate: **{result['status']}**; BSR accepted: **{str(result['bsr_pilot_accepted']).lower()}**.",
        "Roadmap milestones: (1) BSR single-company pilot acceptance; "
        "(2) future expansion to 3–5 companies. The BSR gate does not complete milestone 2.",
        result["conclusion_policy"], "",
        "| Criterion | Status | Evidence | Next action |",
        "|---|---|---|---|",
    ]
    for item in result["criteria"]:
        evidence = item["evidence"]
        if item["criterion_id"] == "input_provenance":
            summary = f"{evidence['unique_claim_count']} unique claims; {evidence['unresolved_issue_count']} unresolved provenance items; preflight {evidence['preflight']}"
        elif item["criterion_id"] == "finding_traceability":
            summary = f"{evidence['fully_traceable_findings']}/{evidence['findings']} findings, {evidence['complete_paths']}/{evidence['paths']} paths"
        elif item["criterion_id"] == "esg_two_level_assessments":
            summary = f"claims {evidence['claim_dimensions']}; claim assessments {evidence['claim_assessments']}; company-year {evidence['company_year_assessments']}, multiyear {evidence['company_multiyear_assessments']}"
        elif item["criterion_id"] == "pdf_case_adjudication":
            summary = f"{evidence['accepted_count']}/{evidence['case_count']} accepted; {evidence['pending_count']} pending; gold labels 0"
        elif item["criterion_id"] == "temporal_comparability":
            summary = f"{evidence['pair_count']} board pairs; " + ", ".join(
                f"{pair['from_year']}→{pair['to_year']} {pair['assessment_status']}/performed={pair['comparison_performed']}"
                for pair in evidence["pairs"]
            )
        elif item["criterion_id"] == "financial_candidate_safety":
            summary = f"{evidence['status']}, FC01 {evidence['fc01_status']}, comparison={evidence['comparison_performed']}, finding={evidence['finding_created']}"
        else:
            summary = f"{evidence['coverage_counts']['unique_claims']} claims; {evidence['coverage_counts']['unmapped_claims']} unmapped allowed; separate SASB/guidance={evidence['sasb_and_ifrs_s2_guidance_separate']}"
        lines.append(f"| {item['criterion_id']} | {item['status']} | {summary.replace('|', '/')} | {'; '.join(item['actions']).replace('|', '/')} |")
    lines.extend([
        "", "Detailed evidence and all unresolved claim IDs are in `bsr_pilot_acceptance_gate.json`.",
        "An optional exceptions JSON has an `exceptions` array. Each accepted entry needs "
        "`claim_id`, `field`, `status: accepted`, `reviewer`, `reason`, and `source_basis`; "
        "the `handoff_manual_review` field covers a preflight manual-review record. "
        "Exceptions are documented waivers, not PDF verification or gold labels.", "",
    ])
    return "\n".join(lines)


def run(out_dir, handoff_path=HANDOFF_PATH, responses_path=None, exceptions_path=None):
    out_dir = Path(out_dir).resolve()
    main_output = (ROOT / "output").resolve()
    if out_dir == main_output or main_output in out_dir.parents:
        raise ValueError("Gate report directory must be outside the main output/ snapshot")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError("Gate report directory must be empty to avoid overwriting files")
    context = collect_context(handoff_path, responses_path, exceptions_path)
    result = evaluate_gate(context)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bsr_pilot_acceptance_gate.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "bsr_pilot_acceptance_gate.md").write_text(render_markdown(result), encoding="utf-8")
    (out_dir / "exceptions_template.json").write_text(json.dumps({"schema_version": "0.1", "exceptions": []}, indent=2) + "\n", encoding="utf-8")
    return result


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True, help="New or empty temporary directory")
    parser.add_argument("--handoff", type=Path, default=HANDOFF_PATH, help="Preflight-only handoff (defaults to current baseline)")
    parser.add_argument("--responses", type=Path, help="Optional completed reviewer responses JSON")
    parser.add_argument("--exceptions", type=Path, help="Optional documented claim provenance exceptions JSON")
    args = parser.parse_args(argv)
    try:
        result = run(args.out_dir, args.handoff, args.responses, args.exceptions)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"BSR acceptance gate failed: {exc}\n")
    print(f"Wrote BSR acceptance gate to {args.out_dir.resolve()}")
    print(f"Status: {result['status']}; criteria: {result['status_counts']}")
    return {"pass": 0, "needs_review": 1, "blocked": 2}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
