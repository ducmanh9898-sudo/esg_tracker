"""Explicit comparison proposals and separately recorded human adjudication."""
from decimal import Decimal
from datetime import datetime
from itertools import combinations
import math

from kg.corporate_adapter import digest
from kg.corporate_table_context import table_rows_compatible

LAYERS = ("source_quote", "value", "association", "semantic_context")


def proposal(ids, relation="equal"):
    # Sum operands are [components..., total]; their order must be preserved.
    ids = sorted(ids) if relation == "equal" else list(ids)
    return {"comparison_id": "CMP-" + digest([relation, ids])[:20],
            "record_ids": ids, "relation": relation}


def candidates(claims, explicit, auto=True):
    found = {}
    by_metric = {}
    if auto:
        for claim in claims:
            if claim["metric_id"] and claim["observation_year"] is not None:
                by_metric.setdefault((claim["company_id"], claim["metric_id"],
                                      claim["observation_year"]), []).append(claim)
        for group in by_metric.values():
            for a, b in combinations(group, 2):
                if a["report_id"] != b["report_id"]:
                    row = proposal([a["record_id"], b["record_id"]])
                    found[row["comparison_id"]] = row
    for item in explicit:
        relation = item["relation"]
        ids = item["record_ids"]
        if relation not in {"equal", "sum_equals", "subset"} or len(ids) != len(set(ids)):
            raise ValueError("invalid comparison relation or duplicate operands")
        if (relation in {"equal", "subset"} and len(ids) != 2) or (relation == "sum_equals" and len(ids) < 3):
            raise ValueError("invalid comparison arity")
        row = proposal(ids, relation)
        found[row["comparison_id"]] = row
    return list(found.values())


def arithmetic_candidates(claims, templates):
    proposals, audit = [], []
    groups = {}
    for claim in claims:
        groups.setdefault((claim["report_id"], claim["observation_year"]), []).append(claim)
    for (report_id, year), group in groups.items():
        for rule in templates:
            roles = [[c for c in group if c["metric_id"] in aliases] for aliases in rule["operand_metrics"]]
            if not any(roles):
                continue
            if all(len(role) == 1 for role in roles):
                row = proposal([role[0]["record_id"] for role in roles], rule["relation"])
                if len(set(row["record_ids"])) != len(row["record_ids"]):
                    raise ValueError("arithmetic_template_reuses_operand")
                proposals.append(row)
                status = "candidate_pending_review"
            else:
                status = "missing_or_ambiguous_operands"
            audit.append({"rule_id": rule["rule_id"], "report_id": report_id, "observation_year": year,
                          "status": status, "operand_record_ids": [[c["record_id"] for c in role] for role in roles]})
    return proposals, audit


def human_event(event):
    if not (event and event.get("reviewer_kind") == "human" and
            all(isinstance(event.get(k), str) and event[k].strip() for k in ("reviewer", "reviewed_at_utc", "basis"))):
        return False
    try:
        return datetime.fromisoformat(event["reviewed_at_utc"].replace("Z", "+00:00")).utcoffset() is not None
    except ValueError:
        return False


def record_review(claim, events):
    event = events.get(claim["record_id"], {})
    if event and event.get("input_digest") != claim["input_digest"]:
        return ["stale_record_review"]
    if human_event(event) and event.get("decision") == "reject":
        return ["record_rejected"]
    if not human_event(event) or event.get("decision") != "accept":
        return ["record_pending_human_review"]
    return ["unreviewed_" + layer for layer in LAYERS if event.get("checks", {}).get(layer) is not True]


def comparison_digest(row, index):
    return digest({**row, "inputs": [index[i]["input_digest"] for i in row["record_ids"]]})


def assess(row, index, record_events, comparison_events, require_source_basis=False):
    selected = [index[i] for i in row["record_ids"]]
    signature = comparison_digest(row, index)
    event = comparison_events.get(row["comparison_id"], {})
    reasons = []
    for claim in selected:
        reasons.extend(record_review(claim, record_events))
        raw = claim["raw_record"]
        if raw["record_type"] not in {"measurement", "financial_measurement"} or raw["statement"]["assertion_kind"] != "reported_result":
            reasons.append("not_reported_numeric_result")
        if claim["value_status"] != "available" or claim["value"] is None:
            reasons.append("value_unavailable")
        if raw["period"]["year_basis"] == "unknown":
            reasons.append("observation_year_ungrounded")
        if not claim["metric_definition"]:
            reasons.append("metric_definition_unknown")
    valid_event = human_event(event) and event.get("input_digest") == signature
    if not valid_event or event.get("decision") not in {"comparable", "not_comparable"}:
        reasons.append("comparison_pending_human_review")
    if event and event.get("input_digest") != signature:
        reasons.append("stale_comparison_review")
    if valid_event and event.get("decision") == "not_comparable":
        reasons.append("human_confirmed_not_comparable")
    for field in ("company_id", "observation_year", "period_type", "unit", "reporting_boundary"):
        values = [c.get(field) for c in selected]
        if any(v in (None, "", "unknown") for v in values):
            reasons.append(field + "_unknown")
        elif any(v != values[0] for v in values):
            reasons.append(field + "_mismatch")
    if row["relation"] == "equal":
        if not table_rows_compatible(selected[0]["raw_record"], selected[1]["raw_record"]):
            reasons.append("table_row_context_mismatch")
        for field in ("metric_id", "metric_definition"):
            values = [c.get(field) for c in selected]
            if not all(values) or len(set(values)) != 1:
                reasons.append(field + "_not_equivalent")
    elif len({c["report_id"] for c in selected}) != 1:
        reasons.append("arithmetic_requires_same_report")
    for field in ("consolidation", "population", "counting_method", "calculation_method", "scope"):
        values = [c["raw_record"]["boundary"][field] for c in selected]
        if any(v in (None, "", "unknown") for v in values):
            if not (valid_event and all(v is None for v in values) and
                    field in event.get("not_applicable_fields", []) and field in {"population", "counting_method"}):
                reasons.append(field + "_unknown")
        elif len(set(values)) != 1:
            if not (field == "scope" and row["relation"] != "equal" and valid_event and event.get("scope_relation_confirmed") is True):
                reasons.append(field + "_mismatch")
    for field in ("observation_start", "observation_end", "measurement_date"):
        values = [c["raw_record"]["period"][field] for c in selected]
        if any(v != values[0] for v in values):
            reasons.append(field + "_mismatch")
    for claim in selected:
        p = claim["raw_record"]["period"]
        if p["period_type"] == "at_date" and not p["measurement_date"]:
            reasons.append("measurement_date_unknown")
        if p["period_type"] != "at_date" and not (p["observation_start"] and p["observation_end"]):
            reasons.append("observation_interval_unknown")
    if len({c["report_id"] for c in selected}) > 1:
        if require_source_basis and not (
                valid_event and event.get("source_basis_checked") is True
                and isinstance(event.get("source_basis_note"), str)
                and event["source_basis_note"].strip()):
            reasons.append("source_version_audit_basis_unreviewed")
        if any(c["raw_record"]["restatement"]["status"] != "not_restatement_reported" for c in selected):
            reasons.append("restatement_unresolved_or_present")
        if not (valid_event and event.get("restatement_checked") is True):
            reasons.append("restatement_not_reviewed")
    tolerance = event.get("absolute_tolerance")
    if isinstance(tolerance, bool) or not isinstance(tolerance, (int, float)) or not math.isfinite(tolerance) or tolerance < 0:
        reasons.append("rounding_tolerance_unreviewed")
    calculation = None
    status = "NeedsReview"
    if not reasons:
        values = [Decimal(str(c["value"])) for c in selected]
        delta = (sum(values[:-1]) - values[-1] if row["relation"] == "sum_equals" else values[0] - values[1])
        ok = delta <= Decimal(str(tolerance)) if row["relation"] == "subset" else abs(delta) <= Decimal(str(tolerance))
        if row["relation"] == "subset" and any(v < 0 or v != v.to_integral_value() for v in values):
            reasons.append("invalid_subset_count")
        else:
            status = "Supported" if ok else "Contradicted"
        calculation = {"values": [str(v) for v in values], "delta": str(delta), "absolute_tolerance": tolerance}
    return {**row, "input_digest": signature, "finding_id": "FND-" + row["comparison_id"],
            "rule_id": "CORPORATE-" + row["relation"].upper(), "status": status,
            "input_claim_ids": row["record_ids"], "reasons": sorted(set(reasons)), "calculation": calculation,
            "summary": "; ".join(sorted(set(reasons))) if reasons else "Reviewed numeric comparison: " + status,
            "basis": event.get("basis") if valid_event else None}
