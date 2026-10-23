"""Guarded statuses whose prerequisites are absent from the current pilot data."""
from __future__ import annotations

import hashlib
from collections import defaultdict


def _finding(rule, claims, status, reason):
    ids = sorted(c["record_id"] for c in claims)
    digest = hashlib.sha256((rule["rule_id"] + "|" + "|".join(ids)).encode("utf-8")).hexdigest()[:12].upper()
    return {
        "finding_id": "FND-" + digest, "rule_id": rule["rule_id"],
        "rule_name": rule.get("name", rule["rule_id"]), "status": status,
        "severity": "medium" if status in {"DisclosureGap", "TemporalInconsistency"} else "info",
        "company_id": claims[0]["company_id"],
        "report_years": sorted({c["report_year"] for c in claims}),
        "observation_years": sorted({c.get("observation_year") for c in claims if c.get("observation_year") is not None}),
        "topic": claims[0]["topic"], "summary": reason, "calculation": None,
        "basis": rule["source_basis"], "guard": rule.get("guard", "Reviewed applicability and comparable source context required."),
        "input_claim_ids": ids,
        "source_files": sorted({e["source_file"] for c in claims for e in c.get("evidence", [])}),
        "source_pages": sorted({p for c in claims for e in c.get("evidence", []) for p in e.get("source_pages", [])}),
    }


def disclosure_gap_findings(claims, profile, coverage):
    """A missing value is a gap only after applicability and search coverage are verified."""
    complete = {(row["company_id"], row["report_year"]) for row in coverage
                if row.get("coverage") == "verified_complete"}
    findings = []
    for rule in profile.get("required_disclosures", []):
        if rule.get("applicability_status") != "verified" or not rule.get("source_basis"):
            continue
        for claim in claims:
            if claim["metric_id"] != rule["metric_id"] or (claim["company_id"], claim["report_year"]) not in complete:
                continue
            if claim.get("value_status") != "missing":
                continue
            findings.append(_finding(rule, [claim], "DisclosureGap",
                                     "Required disclosure value is missing after verified applicability and complete source search."))
    return findings


def temporal_revision_findings(claims, profile):
    """Only same-period cross-report revisions with reviewed context can be strong findings."""
    by_metric = defaultdict(list)
    for claim in claims:
        by_metric[(claim["company_id"], claim["metric_id"], claim.get("observation_year"))].append(claim)
    findings = []
    for rule in profile.get("temporal_revision_rules", []):
        if not isinstance(rule.get("tolerance"), (int, float)) or not rule.get("source_basis"):
            continue
        for (company, metric, observation_year), group in by_metric.items():
            if metric != rule["metric_id"] or observation_year is None:
                continue
            group = sorted(group, key=lambda c: (c["report_year"], c["record_id"]))
            for earlier, later in zip(group, group[1:]):
                if earlier["report_year"] == later["report_year"]:
                    continue
                if {earlier.get("variant"), later.get("variant")} - {"reported", "comparative"}:
                    continue
                same = all(earlier.get(key) == later.get(key) for key in
                           ("company_id", "metric_id", "metric_definition", "unit", "scope", "period_type", "baseline_id", "reporting_boundary"))
                reviewed = all(c.get("reporting_boundary_verified") is True and c.get("period_type_verified") is True
                               and c.get("review_status") == "reviewed"
                               and all(e.get("original_text") for e in c.get("evidence", [])) for c in (earlier, later))
                if not same or not reviewed or later.get("restatement_status") != "not_restatement":
                    continue
                if not all(isinstance(c.get("value"), (int, float)) and c.get("value_status") == "available" for c in (earlier, later)):
                    continue
                delta = abs(later["value"] - earlier["value"])
                if delta > rule["tolerance"]:
                    findings.append(_finding(rule, [earlier, later], "TemporalInconsistency",
                                             f"The same observation period differs by {delta:g} {earlier.get('unit') or ''} across reviewed reports without a reported restatement."))
    return findings
