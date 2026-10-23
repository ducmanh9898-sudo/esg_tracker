"""A per-claim review ledger. Reference matches never imply standards compliance."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from kg.pipeline import _legacy
from tools.standards_coverage_report import build_report
from tools.standards_crosswalk import load_crosswalk


ROOT = Path(__file__).resolve().parents[1]


def _read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def build_claim_review(data):
    """Join rule executions, standards references and guarded BCTC candidates by ID."""
    claims = data["normalized_claims"]
    coverage = build_report(
        [_legacy(claim) for claim in claims], data["claim_assessments"],
        load_crosswalk(), _read(ROOT / "data/config/rule_catalogue.json"),
        _read(ROOT / "data/integration_gap_status.json"),
    )
    coverage_by_id = {row["claim_id"]: row for row in coverage["claims"]}
    candidate_refs = _read(ROOT / "data/config/standard_metric_candidates.json")
    locator_issue = _read(ROOT / "data/review/bsr_2025_waste_locator.issue.json")
    reference_issue = _read(ROOT / "data/review/bsr_2025_workforce_gri_reference.issue.json")
    finance_by_id = {row["disclosure_id"]: row for row in data["financial_records"]}
    events_by_claim = {claim["record_id"]: [] for claim in claims}
    if {claim["metric_id"] for claim in claims} - candidate_refs.keys():
        raise ValueError("Every selected metric needs an explicit standards reference review candidate")
    for event in data["rule_evaluations"]:
        for claim_id in event["input_claim_ids"]:
            if claim_id in events_by_claim:
                events_by_claim[claim_id].append(event)
    signals_by_claim = {claim["record_id"]: [] for claim in claims}
    for finding in data["demo_findings"]:
        for claim_id in finding["input_claim_ids"]:
            if claim_id in signals_by_claim:
                signals_by_claim[claim_id].append({
                    "rule_id": finding["rule_id"], "status": "screening_only",
                    "arithmetic_observation": ("matched" if finding["status"] == "Supported" else "difference_or_context_to_review"),
                    "summary": finding["summary"], "input_claim_ids": finding["input_claim_ids"],
                })
    finance_by_claim = {claim["record_id"]: [] for claim in claims}
    for link in data["financial_candidates"]:
        if link["claim_id"] in finance_by_claim:
            record = finance_by_id[link["financial_disclosure_id"]]
            finance_by_claim[link["claim_id"]].append({
                **link,
                "financial_value": record.get("value"),
                "financial_unit": record.get("unit"),
                "financial_report": record.get("source_file"),
                "financial_pages": record.get("source_pages", []),
                "financial_pointer": record.get("source_pointer"),
                "financial_scope": record.get("scope", {}).get("scope_id"),
            })
    temporal_by_claim = {claim["record_id"]: [] for claim in claims}
    for pair in data["temporal_comparisons"]:
        for claim_id in (pair["from_claim_id"], pair["to_claim_id"]):
            if claim_id in temporal_by_claim:
                temporal_by_claim[claim_id].append(pair)
    rows = []
    for claim in claims:
        claim_id = claim["record_id"]
        events = events_by_claim[claim_id]
        if any(event["outcome"] == "Contradicted" for event in events):
            outcome = "Contradicted"
        elif any(event["outcome"] == "NeedsReview" for event in events):
            outcome = "NeedsReview"
        elif any(event["outcome"] == "Supported" for event in events):
            outcome = "Supported"
        elif events:
            outcome = "Skipped"
        else:
            outcome = "NotEvaluated"
        current_coverage = coverage_by_id[claim_id]
        reference_candidates = candidate_refs.get(claim["metric_id"], [])
        rows.append({
            "claim_id": claim_id,
            "report_year": claim["report_year"],
            "metric_id": claim["metric_id"],
            "rule_outcome": outcome,
            "reader_triage": "limited_supported" if outcome == "Supported" else (
                "potential_contradiction" if outcome == "Contradicted" else "requires_review"),
            "rule_checks": [{"evaluation_id": e["evaluation_id"], "rule_id": e["rule_id"],
                             "outcome": e["outcome"], "reasons": e["reasons"],
                             "input_claim_ids": e["input_claim_ids"]} for e in events],
            "standards": {
                "reviewed_relationships": current_coverage["mappings"],
                "reference_candidates": reference_candidates,
                "ifrs_s1_connected_information": {
                    "reference": "IFRS S1 paragraphs 20–22",
                    "source_url": "https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards-issb/english/2023/issued/part-a/issb-2023-a-ifrs-s1-general-requirements-for-disclosure-of-sustainability-related-financial-information.pdf?bypass=on",
                    "status": "not_established",
                    "reason": "ESG reporting entity/boundary is not verified against the related financial statements; no financial-effect claim is established by this metric alone.",
                },
                "compliance_status": "not_assessed",
            },
            "financial": {
                "status": "candidate_not_comparable" if finance_by_claim[claim_id] else "no_direct_candidate",
                "candidates": finance_by_claim[claim_id],
                "reason": ("Existing link is blocked by its comparability guards; numeric difference is not a contradiction."
                           if finance_by_claim[claim_id] else
                           "No semantically comparable financial disclosure was linked for this metric; this is not evidence that BSR omitted it."),
            },
            "cross_year_candidates": temporal_by_claim[claim_id],
            "screening_signals": signals_by_claim[claim_id],
            "source_status": "partial_ai_pdf_corroboration" if claim_id in {
                row["claim_id"] for row in data["source_provenance_audit"]["attached_evidence"]
            } else "extract_locator_only",
            "source_locator_issue": locator_issue if claim_id == locator_issue["claim_id"] else None,
            "standard_reference_issue": reference_issue if claim_id == reference_issue["claim_id"] else None,
        })
    if len(rows) != 30 or len({row["claim_id"] for row in rows}) != 30:
        raise ValueError("BSR claim review must cover 30 unique selected claims")
    return {
        "schema_version": "1.0",
        "scope": "30 selected BSR ESG claims; checks are limited to available evidence",
        "counts": dict(Counter(row["rule_outcome"] for row in rows)),
        "reader_triage_counts": dict(Counter(row["reader_triage"] for row in rows)),
        "standards_policy": "A standards reference is a topic/metric relationship, not proof that a disclosure satisfies GRI or IFRS S1.",
        "financial_policy": "Only guarded same-metric candidates may be numerically compared; absence of a candidate is not a disclosure gap.",
        "claims": rows,
    }
