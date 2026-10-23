"""Stage 17 BSR inspection using the existing demo pipeline; never ingests handoff data."""

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from build_demo import build
from tools.financial_adapter import adapt_reports
from tools.handoff_preflight import preflight
from tools.pilot_readiness import build_inventory


ROOT = Path(__file__).resolve().parents[1]
COMPANY_ID = "BSR"


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _claim_detail(claim):
    return {
        "claim_id": claim["claim_id"],
        "report_year": claim["report_year"],
        "metric_period_year": claim["observation_year"],
        "metric_id": claim["metric_id"],
        "value": claim.get("value"),
        "unit": claim.get("unit"),
        "scope": claim.get("scope"),
        "variant": claim.get("variant"),
        "report_id": f"report:{claim['company_id']}:{claim['report_year']}",
        "evidence": [
            {
                "evidence_id": item["evidence_id"],
                "source_file": item["source_file"],
                "source_pages": item["source_pages"],
                "json_pointer": item["json_pointer"],
                "source_text_available": bool(item.get("source_text")),
            }
            for item in claim.get("evidence", [])
        ],
    }


def trace_findings(claims, findings, graph):
    """Check every BSR finding path and expose the exact source locators."""
    by_id = {claim["claim_id"]: claim for claim in claims}
    nodes = {node["id"]: node for node in graph["nodes"]}
    edges = {(edge["source"], edge["target"], edge["label"]) for edge in graph["edges"]}
    traces = []
    for finding in findings:
        finding_node = "finding:" + finding["finding_id"]
        paths = []
        finding_issues = []
        if finding_node not in nodes:
            finding_issues.append("finding_node_missing")
        for claim_id in finding["input_claim_ids"]:
            claim = by_id.get(claim_id)
            if claim is None:
                finding_issues.append(f"claim_missing:{claim_id}")
                continue
            claim_node = "claim:" + claim_id
            measurement_node = "measurement:" + claim_id
            report_node = f"report:{claim['company_id']}:{claim['report_year']}"
            for node_id, label in ((claim_node, "claim"), (measurement_node, "measurement"), (report_node, "report")):
                if node_id not in nodes:
                    finding_issues.append(f"{label}_node_missing:{claim_id}")
            required = (
                (finding_node, claim_node, "BASED_ON_CLAIM"),
                (finding_node, report_node, "DERIVED_FROM_REPORT"),
                (report_node, claim_node, "CONTAINS"),
                (claim_node, measurement_node, "HAS_MEASUREMENT"),
            )
            for source, target, label in required:
                if (source, target, label) not in edges:
                    finding_issues.append(f"edge_missing:{label}:{claim_id}")
            if not claim.get("evidence"):
                finding_issues.append(f"evidence_missing:{claim_id}")
            for evidence in claim.get("evidence", []):
                evidence_node = "evidence:" + evidence["evidence_id"]
                details = nodes.get(evidence_node)
                issues = []
                if details is None:
                    issues.append("evidence_node_missing")
                else:
                    for field in ("source_file", "source_pages", "json_pointer"):
                        if details.get(field) != evidence.get(field):
                            issues.append(f"evidence_{field}_mismatch")
                for source, target, label in (
                    (finding_node, evidence_node, "BASED_ON_EVIDENCE"),
                    (measurement_node, evidence_node, "SOURCED_FROM"),
                ):
                    if (source, target, label) not in edges:
                        issues.append(f"edge_missing:{label}")
                if not evidence.get("source_file") or not evidence.get("source_pages") or not evidence.get("json_pointer"):
                    issues.append("source_locator_incomplete")
                path = {
                    "finding_id": finding["finding_id"],
                    "claim_id": claim_id,
                    "evidence_id": evidence["evidence_id"],
                    "report_id": report_node,
                    "source_file": evidence.get("source_file"),
                    "source_pages": evidence.get("source_pages"),
                    "json_pointer": evidence.get("json_pointer"),
                    "complete": not issues,
                    "issues": issues,
                }
                paths.append(path)
                finding_issues.extend(f"{issue}:{claim_id}/{evidence['evidence_id']}" for issue in issues)
        traces.append({
            "finding_id": finding["finding_id"],
            "rule_id": finding["rule_id"],
            "status": finding["status"],
            "complete": not finding_issues,
            "issues": finding_issues,
            "paths": paths,
        })
    return {
        "finding_count": len(traces),
        "fully_traceable_findings": sum(item["complete"] for item in traces),
        "path_count": sum(len(item["paths"]) for item in traces),
        "complete_paths": sum(path["complete"] for item in traces for path in item["paths"]),
        "note": "Structural graph/source-locator trace only; PDF text and boundary still require review.",
        "findings": traces,
    }


def _r01_case(claims, findings, validation_cases):
    matches = [f for f in findings if f["rule_id"] == "R01"]
    if len(matches) != 1:
        return {"case_id": "R01", "status": "not_available", "reason": "Expected one BSR R01 finding"}
    finding = matches[0]
    by_id = {claim["claim_id"]: claim for claim in claims}
    inputs = [by_id[claim_id] for claim_id in finding["input_claim_ids"]]
    validation = next((case for case in validation_cases if case["case_id"] == "VC-REAL-R01"), {})
    return {
        "case_id": "R01",
        "category": "current_rule_result",
        "finding_id": finding["finding_id"],
        "rule_status": finding["status"],
        "rule_calculation": finding.get("calculation"),
        "rule_guard": finding.get("guard"),
        "rule_reason": finding.get("summary"),
        "claims": [_claim_detail(claim) for claim in inputs],
        "raw_difference": abs(inputs[0]["value"] - inputs[1]["value"]),
        "adjudication_status": validation.get("adjudication_status", "pending_adjudication"),
        "missing_conditions": sorted({
            condition
            for claim in inputs
            for condition in (
                ([] if claim.get("reporting_boundary_verified") is True else ["verified_reporting_boundary"])
                + ([] if claim.get("review_status") == "reviewed" else ["manual_pdf_adjudication"])
                + ([] if all(e.get("source_text") for e in claim["evidence"]) else ["original_source_text"])
            )
        }),
        "interpretation": "The numeric difference remains a rule NeedsReview result, not a misconduct conclusion.",
    }


def _workforce_case(claims, financial_records, candidate):
    check = candidate["checks"][0]
    by_claim = {claim["claim_id"]: claim for claim in claims}
    by_disclosure = {record["disclosure_id"]: record for record in financial_records}
    esg = by_claim.get(check["esg_claim_id"])
    financial = by_disclosure.get(check["financial_disclosure_id"])
    missing = [name for name, value in (("esg_claim", esg), ("financial_disclosure", financial)) if value is None]
    if missing:
        return {
            "case_id": check["check_id"], "category": "financial_candidate",
            "status": "not_run_missing_data", "comparison_performed": False,
            "finding_created": False, "fc01_status": "inactive", "missing_conditions": missing,
        }
    esg_context = esg.get("workforce_context") or check["esg_measurement_context"]
    esg_boundary = esg_context["reporting_boundary"]
    financial_boundary = financial["scope"]
    esg_date = esg_context["measurement_date"]
    financial_date = financial.get("measurement_date") or {}
    esg_definition = esg_context["employee_definition"]
    financial_definition = financial.get("employee_definition") or {}
    boundary_verified = (
        esg_boundary.get("verification_status") == "verified"
        and financial_boundary.get("verification_status") == "verified"
    )
    date_verified = (
        esg_date.get("verification_status") == "verified"
        and financial_date.get("verification_status") == "verified"
    )
    definition_verified = (
        esg_definition.get("verification_status") == "verified"
        and financial_definition.get("verification_status") == "verified"
    )
    checks = {
        "company_match": esg["company_id"] == financial["company_id"],
        "year_match": esg["report_year"] == financial["reporting_period"]["fiscal_year"],
        "unit_match": esg["unit"] == financial["unit"],
        "verified_scope_match": boundary_verified and esg_boundary.get("entity_set") == financial_boundary.get("entity_set")
        and esg_boundary.get("entity_set") not in (None, "unknown"),
        "verified_measurement_date_match": date_verified and esg_date.get("value") == financial_date.get("value")
        and esg_date.get("value") is not None,
        "verified_employee_definition_match": definition_verified
        and esg_definition.get("definition_id") == financial_definition.get("definition_id")
        and esg_definition.get("definition_id") is not None,
    }
    missing_conditions = []
    if not boundary_verified:
        missing_conditions.append("reporting_boundary_unverified")
    elif not checks["verified_scope_match"]:
        missing_conditions.append("reporting_boundary_mismatch")
    if not date_verified:
        missing_conditions.append("measurement_date_unverified")
    elif not checks["verified_measurement_date_match"]:
        missing_conditions.append("measurement_date_mismatch")
    if not definition_verified:
        missing_conditions.append("employee_definition_unverified")
    elif not checks["verified_employee_definition_match"]:
        missing_conditions.append("employee_definition_mismatch")
    if not all(checks[key] for key in ("company_match", "year_match", "unit_match")):
        missing_conditions.append("financial_join_conditions")
    comparison_eligible = all(checks.values())
    esg_detail = _claim_detail(esg)
    esg_detail["workforce_context"] = esg_context
    return {
        "case_id": check["check_id"],
        "category": "financial_candidate",
        "status": "NeedsReview",
        "candidate_check_status": check["status"],
        "fc01_status": check["result_policy"]["fc01_status"],
        "comparison_eligible": comparison_eligible,
        "comparison_performed": False,
        "finding_created": False,
        "esg": esg_detail,
        "financial": {
            "disclosure_id": financial["disclosure_id"],
            "value": financial["value"], "unit": financial["unit"],
            "scope": financial_boundary, "report_id": financial["source_report_id"],
            "report_year": financial["report_year"],
            "reporting_period": financial["reporting_period"],
            "observation_year": financial.get("observation_year"),
            "measurement_date": financial_date,
            "employee_definition": financial_definition,
            "source_uri": financial["report"]["source_uri"],
            "source_pages": financial["source_pages"],
            "json_pointer": financial["source_pointer"],
            "original_text_available": bool(financial.get("original_text")),
        },
        "related_financial_observations": check.get("related_financial_observations", []),
        "join_checks": checks,
        "raw_difference": financial["value"] - esg["value"],
        "difference_interpretation": "reviewable_on_equivalent_basis" if comparison_eligible else "arithmetic_only_not_comparable",
        "missing_conditions": missing_conditions,
        "interpretation": "The arithmetic gap is not a confirmed discrepancy. FC01 remains inactive and no finding is created; organizational boundary, measurement date and employee definition must all be verified and equal before comparison.",
    }


def _board_case(claims, findings, graph, validation_cases):
    series = next((node for node in graph["nodes"] if node["type"] == "TemporalSeries"
                   and node.get("company_id") == COMPANY_ID and node.get("metric_id") == "board_total"), None)
    if series is None:
        return {"case_id": "BSR-BOARD-2023-2025", "status": "not_available", "reason": "TemporalSeries node missing"}
    edges = graph["edges"]
    by_id = {claim["claim_id"]: claim for claim in claims}
    claim_ids = [edge["target"].removeprefix("claim:") for edge in edges
                 if edge["source"] == series["id"] and edge["label"] == "HAS_TEMPORAL_CLAIM"]
    selected = sorted((by_id[claim_id] for claim_id in claim_ids), key=lambda claim: claim["observation_year"])
    comparisons = sorted((node for node in graph["nodes"] if node["type"] == "TemporalComparison"
                          and node.get("series_id") == series["series_id"]),
                         key=lambda node: node["from_observation_year"])
    validation = next((case for case in validation_cases if case["case_id"] == "VC-REAL-TEMPORAL-BOARD"), {})
    related = [f for f in findings if set(f["input_claim_ids"]).intersection(claim_ids)]
    return {
        "case_id": series["series_id"],
        "category": "temporal_assessment",
        "claims": [_claim_detail(claim) for claim in selected],
        "raw_values_by_year": {str(claim["observation_year"]): claim["value"] for claim in selected},
        "comparisons": [{
            "comparison_id": node["comparison_id"],
            "from_year": node["from_observation_year"],
            "to_year": node["to_observation_year"],
            "from_value": node["from_value"], "to_value": node["to_value"],
            "assessment_status": node["assessment_status"],
            "comparison_performed": node["comparison_performed"],
            "numeric_change": node["numeric_change"],
            "flags": node["flags"],
        } for node in comparisons],
        "related_rule_findings": [{"finding_id": f["finding_id"], "rule_id": f["rule_id"], "status": f["status"]} for f in related],
        "adjudication_status": validation.get("adjudication_status", "pending_adjudication"),
        "missing_conditions": sorted({condition for node in comparisons for condition in node["flags"]["missing_context"]}),
        "interpretation": "R06 findings concern board composition; this year-to-year series is a separate pending temporal assessment.",
    }


def _blocker(owner, blocker_id, detail, references):
    return {"owner": owner, "blocker_id": blocker_id, "detail": detail, "references": references}


def _blockers(claims, trace, cases, inventory, validation, handoff_report):
    blockers = []
    missing_text = [claim["claim_id"] for claim in claims if any(not e.get("source_text") for e in claim["evidence"])]
    unverified_boundary = [claim["claim_id"] for claim in claims if claim.get("reporting_boundary_verified") is not True]
    missing_period = [claim["claim_id"] for claim in claims if not claim.get("period_type")]
    unreviewed = [claim["claim_id"] for claim in claims if claim.get("review_status") != "reviewed"]
    for blocker_id, detail, refs in (
        ("source_text", f"{len(missing_text)} BSR claims lack normalized original source text/PDF adjudication.", missing_text),
        ("reporting_boundary", f"{len(unverified_boundary)} BSR claims lack verified reporting boundary.", unverified_boundary),
        ("period_type", f"{len(missing_period)} BSR claims lack verified period_type.", missing_period),
        ("manual_source_review", f"{len(unreviewed)} BSR claims remain unreviewed against source.", unreviewed),
    ):
        if refs:
            blockers.append(_blocker("Extract", blocker_id, detail, refs))
    if handoff_report is None:
        blockers.append(_blocker("Extract", "updated_handoff", "Updated provenance/boundary handoff was not supplied for this dry-run.", []))
    elif handoff_report["summary"]["blocking"]:
        blockers.append(_blocker("Extract", "handoff_preflight_errors", "Optional handoff has blocking preflight errors.",
                                 [item["claim_id"] for item in handoff_report["blocking_records"]]))
    elif handoff_report["summary"]["manual_review"]:
        blockers.append(_blocker("Extract", "handoff_manual_review", "Optional handoff has records requiring PDF/boundary review.",
                                 [item["claim_id"] for item in handoff_report["manual_review_records"]]))
    workforce = cases["workforce_financial"]
    if workforce["status"] == "not_run_missing_data":
        blockers.append(_blocker("Extract", "workforce_financial_missing", "ESG or BCTC workforce disclosure is missing.", workforce["missing_conditions"]))
    elif workforce["missing_conditions"]:
        blockers.append(_blocker("Extract", "workforce_scope_definition", "BCTC/ESG workforce scope, definition and original text are not verified as comparable.",
                                 [workforce["esg"]["claim_id"], workforce["financial"]["disclosure_id"]]))
    if trace["fully_traceable_findings"] != trace["finding_count"]:
        blockers.append(_blocker("Graph/validation", "finding_trace", "Some finding provenance paths are incomplete.",
                                 [item["finding_id"] for item in trace["findings"] if not item["complete"]]))
    if not validation["valid"]:
        blockers.append(_blocker("Graph/validation", "system_validation", "Existing six-layer validation reports errors.",
                                 [name for name, layer in validation["layers"].items() if not layer["valid"]]))
    for key in ("r01", "board_temporal"):
        if cases[key].get("status") == "not_available":
            blockers.append(_blocker("Graph/validation", f"{key}_case_missing", cases[key]["reason"], []))
    if cases["r01"].get("adjudication_status") == "pending_adjudication" or cases["board_temporal"].get("adjudication_status") == "pending_adjudication":
        blockers.append(_blocker("Graph/validation", "real_case_adjudication", "Real R01 and board cases still need reviewed expected outcomes before a gold set can be declared.",
                                 ["VC-REAL-R01", "VC-REAL-TEMPORAL-BOARD"]))
    if workforce.get("fc01_status") == "inactive":
        blockers.append(_blocker("Graph/validation", "financial_candidate_inactive", "FC01 remains inactive; verified join conditions and a reviewed validation case are required before activation.",
                                 [workforce["case_id"]]))
    if any(not item["comparison_performed"] for item in cases["board_temporal"].get("comparisons", [])):
        blockers.append(_blocker("Graph/validation", "temporal_revalidation", "Re-run temporal comparability after Extract supplies period, boundary and source evidence.",
                                 [item["comparison_id"] for item in cases["board_temporal"]["comparisons"]]))
    inventory_partial = [item for item in inventory["records"] if item["company_id"] == COMPANY_ID and item["status"] != "ready"]
    inventory_claim_ids = {
        claim_id for item in inventory["records"] if item["company_id"] == COMPANY_ID
        for claim_id in item["claims"]["claim_ids"]
    }
    current_claim_ids = {claim["claim_id"] for claim in claims}
    if inventory_claim_ids != current_claim_ids:
        blockers.append(_blocker("Graph/validation", "inventory_snapshot_mismatch",
                                 "Read-only readiness inventory and the rebuilt BSR claim set differ; reconcile before relying on inventory status.",
                                 sorted(inventory_claim_ids ^ current_claim_ids)))
    if inventory_partial:
        blockers.append(_blocker("Graph/validation", "inventory_not_ready", "BSR readiness inventory still has partial/blocked company-year-dimension entries.",
                                 [f"{item['report_year']}:{item['dimension']}" for item in inventory_partial]))
    return blockers


def assemble_report(pipeline, financial, inventory, candidate, validation_cases, handoff_report=None):
    claims = [claim for claim in pipeline["claims"] if claim["company_id"] == COMPANY_ID]
    claim_ids = {claim["claim_id"] for claim in claims}
    findings = [finding for finding in pipeline["findings"] if set(finding["input_claim_ids"]).intersection(claim_ids)]
    claim_assessments = [item for item in pipeline["assessments"]["claim_assessments"] if item["company_id"] == COMPANY_ID]
    company_assessments = [item for group in pipeline["assessments"]["company_assessments"].values()
                           for item in group if item["company_id"] == COMPANY_ID]
    trace = trace_findings(claims, findings, pipeline["graph"])
    cases = {
        "r01": _r01_case(claims, findings, validation_cases),
        "workforce_financial": _workforce_case(claims, financial["records"], candidate),
        "board_temporal": _board_case(claims, findings, pipeline["graph"], validation_cases),
    }
    bsr_inventory = [item for item in inventory["records"] if item["company_id"] == COMPANY_ID]
    report = {
        "report_type": "BSR stage 17 dry-run inspection",
        "pilot_status": "not_official_pilot",
        "cohort_note": "This run covers BSR only; it is not a validated three-to-five-company pilot cohort.",
        "data_scope": "Current normalized ESG extracts and supplied BSR financial extracts; optional handoff is preflighted only.",
        "counts": {
            "claims": len(claims),
            "findings": len(findings),
            "finding_statuses": dict(Counter(item["status"] for item in findings)),
            "claim_assessments": len(claim_assessments),
            "company_assessments": len(company_assessments),
            "company_year_assessments": sum(item["assessment_level"] == "company_year" for item in company_assessments),
            "company_multiyear_assessments": sum(item["assessment_level"] == "company_multiyear" for item in company_assessments),
            "financial_records": sum(item["company_id"] == COMPANY_ID for item in financial["records"]),
        },
        "traceability": trace,
        "cases": cases,
        "validation": pipeline["system_validation"],
        "readiness_inventory": [{
            "report_year": item["report_year"], "dimension": item["dimension"],
            "status": item["status"], "claim_count": item["claims"]["claim_count"],
            "blockers": item["blockers"],
        } for item in bsr_inventory],
        "handoff_preflight": handoff_report,
        "handoff_status": "not_supplied" if handoff_report is None else "preflight_only_not_ingested",
        "gold_set_status": "pending_manual_adjudication",
        "financial_candidate_status": cases["workforce_financial"].get("fc01_status", "inactive"),
    }
    report["blockers"] = _blockers(claims, trace, cases, inventory, pipeline["system_validation"], handoff_report)
    return report


def _locator_lines(claims):
    lines = []
    for claim in claims:
        for evidence in claim["evidence"]:
            lines.append(
                f"  - {claim['claim_id']} → {evidence['evidence_id']} → {claim['report_id']} "
                f"→ {evidence['source_file']} p.{','.join(map(str, evidence['source_pages']))} "
                f"`{evidence['json_pointer']}`"
            )
    return lines


def render_markdown(report):
    counts = report["counts"]
    trace = report["traceability"]
    cases = report["cases"]
    r01, workforce, board = cases["r01"], cases["workforce_financial"], cases["board_temporal"]
    lines = [
        "# BSR stage 17 dry-run inspection",
        "",
        "Status: dry-run on current data; not an official pilot, gold set or greenwashing conclusion.",
        "",
        f"Claims: {counts['claims']}; findings: {counts['findings']} ({counts['finding_statuses']}); "
        f"claim assessments: {counts['claim_assessments']}; company assessments: {counts['company_assessments']}; "
        f"financial records: {counts['financial_records']}.",
        f"Traceability: {trace['fully_traceable_findings']}/{trace['finding_count']} findings and "
        f"{trace['complete_paths']}/{trace['path_count']} finding–claim–evidence–report paths contain graph links, pages and JSON pointers.",
        "Structural traceability does not verify the source PDF sentence or reporting boundary.",
        "",
        "## Finding provenance audit",
        "",
    ]
    for item in trace["findings"]:
        lines.append(f"- {item['finding_id']} ({item['rule_id']}, {item['status']}): "
                     f"{'complete' if item['complete'] else 'incomplete'}; {len(item['paths'])} paths")
        for path in item["paths"]:
            lines.append(
                f"  - {path['claim_id']} → {path['evidence_id']} → {path['report_id']} "
                f"→ {path['source_file']} p.{','.join(map(str, path['source_pages'] or []))} "
                f"`{path['json_pointer']}`"
            )
        for issue in item["issues"]:
            lines.append(f"  - Issue: {issue}")
    lines.extend([
        "",
        "## Three inspection cases",
        "",
        "### R01 · Scope 1 BSR 2025",
    ])
    if r01.get("category"):
        lines.extend([
            f"Rule result: **{r01['rule_status']}** ({r01['finding_id']}); values "
            + " vs ".join(f"{claim['value']} {claim['unit']}" for claim in r01["claims"])
            + f"; raw difference {r01['raw_difference']} {r01['claims'][0]['unit']}.",
            f"Rule calculation: {r01['rule_calculation']}",
            f"Guard: {r01['rule_guard']}",
            f"Pending: {', '.join(r01['missing_conditions'])}; validation case {r01['adjudication_status']}.",
            "Provenance:", *_locator_lines(r01["claims"]),
        ])
    else:
        lines.append(r01["reason"])
    lines.extend(["", "### Workforce ESG ↔ BCTC BSR 2025"])
    if workforce["status"] == "not_run_missing_data":
        lines.append(f"Candidate not run: missing {', '.join(workforce['missing_conditions'])}; no finding.")
    else:
        lines.extend([
            f"Candidate: **{workforce['status']}**, FC01 {workforce['fc01_status']}; "
            f"ESG {workforce['esg']['value']} vs BCTC {workforce['financial']['value']} "
            f"{workforce['esg']['unit']} (arithmetic gap {workforce['raw_difference']}; not a confirmed discrepancy).",
            f"Join checks: {workforce['join_checks']}; comparison_eligible={str(workforce['comparison_eligible']).lower()}; "
            "comparison_performed=false; finding_created=false.",
            f"Pending: {', '.join(workforce['missing_conditions'])}.",
            "ESG provenance:", *_locator_lines([workforce["esg"]]),
            f"BCTC provenance: {workforce['financial']['disclosure_id']} → {workforce['financial']['report_id']} "
            f"→ {workforce['financial']['source_uri']} p.{','.join(map(str, workforce['financial']['source_pages']))} "
            f"`{workforce['financial']['json_pointer']}`",
        ])
    lines.extend(["", "### HĐQT BSR 2023 → 2024 → 2025"])
    if board.get("category"):
        lines.append(f"Raw values: {board['raw_values_by_year']}; temporal validation case {board['adjudication_status']}.")
        for item in board["comparisons"]:
            lines.append(
                f"- {item['from_year']} → {item['to_year']}: {item['from_value']} → {item['to_value']}; "
                f"{item['assessment_status']}, comparison_performed={str(item['comparison_performed']).lower()}; "
                f"missing {item['flags']['missing_context']}; incompatible {item['flags']['incompatibilities']}."
            )
        lines.extend([f"Related rule findings (board composition, separate from temporal assessment): {board['related_rule_findings']}.",
                      "Provenance:", *_locator_lines(board["claims"])])
    else:
        lines.append(board["reason"])
    lines.extend(["", "## Readiness blockers", ""])
    for item in report["blockers"]:
        lines.append(f"- **{item['owner']} · {item['blocker_id']}**: {item['detail']} References: {', '.join(item['references'][:8])}"
                     + (f" (+{len(item['references']) - 8} more)" if len(item["references"]) > 8 else ""))
    lines.extend(["", "## Validation and handoff", "",
                  f"Six-layer system validation: {'pass' if report['validation']['valid'] else 'fail'} "
                  f"({report['validation']['error_count']} errors).",
                  f"Handoff: {report['handoff_status']}; preflight "
                  f"{report['handoff_preflight']['summary'] if report['handoff_preflight'] else 'not run'}.",
                  "No handoff data was merged into claims, findings, assessments or the graph.", ""])
    return "\n".join(lines)


def run(report_dir, handoff_path=None):
    report_dir = Path(report_dir).resolve()
    main_output = (ROOT / "output").resolve()
    if report_dir == main_output or main_output in report_dir.parents:
        raise ValueError("Report directory must be outside the main output/ snapshot")
    if report_dir.exists() and any(report_dir.iterdir()):
        raise ValueError("Report directory must be empty to avoid overwriting existing files")
    handoff_report = None
    if handoff_path is not None:
        try:
            handoff_report = preflight(handoff_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            handoff_report = {
                "handoff_file": str(handoff_path), "dry_run": True,
                "valid_records": [], "manual_review_records": [],
                "blocking_records": [{"claim_id": "<handoff>", "evidence_id": None, "reasons": [str(exc)]}],
                "summary": {"records": 0, "valid": 0, "manual_review": 0, "blocking": 1},
            }
    with tempfile.TemporaryDirectory(prefix="bsr_stage17_pipeline_") as temp:
        pipeline = build(Path(temp))
        financial = adapt_reports()
        inventory = build_inventory()
        candidate = _read(ROOT / "data" / "config" / "financial_link_bsr_workforce_sample.json")
        validation_cases = _read(ROOT / "data" / "config" / "validation_cases.json")["cases"]
        report = assemble_report(pipeline, financial, inventory, candidate, validation_cases, handoff_report)
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "bsr_dry_run_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (report_dir / "bsr_dry_run_report.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True, help="An empty temporary report directory")
    parser.add_argument("--handoff", type=Path, help="Optional Extract handoff JSON, preflight only")
    args = parser.parse_args(argv)
    try:
        report = run(args.report_dir, args.handoff)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"BSR dry-run failed: {exc}\n")
    print(f"Wrote BSR dry-run report to {args.report_dir.resolve()}")
    print(f"Counts: {report['counts']}; traceable findings: {report['traceability']['fully_traceable_findings']}/{report['traceability']['finding_count']}")
    return 2 if report["handoff_preflight"] and report["handoff_preflight"]["summary"]["blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
