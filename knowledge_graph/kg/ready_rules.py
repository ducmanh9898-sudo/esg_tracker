"""Reviewed arithmetic checks from the KG-E/S/G-01 catalogue.

The catalogue's aliases are candidates until an explicit mapping review is
recorded. Evaluation events are distinct from findings: missing roles never
become invented evidence or ESG contradictions.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from decimal import Decimal, InvalidOperation


VERSION = "1.1"
RULES = {
    "KG-E-01": {"name": "Explicit Scope 1 + Scope 2 total", "dimension": "E",
                "roles": ("scope1_emissions", "scope2_emissions", "scope1_plus_scope2_total"),
                "topic": "climate_and_ghg"},
    "KG-S-01": {"name": "Female employees within total employees", "dimension": "S",
                "roles": ("employees_female_count", "employees_total_count"), "topic": "workforce"},
    "KG-G-01": {"name": "Independent directors within board total", "dimension": "G",
                "roles": ("board_independent_count", "board_total_count"), "topic": "board"},
}
STRONG = {"Supported", "Contradicted"}


def _number(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _identified(value):
    return value is not None and str(value).strip().lower() not in {"", "unknown", "unspecified"}


def _evidence_ok(claim):
    return bool(claim.get("evidence")) and all(
        _identified(e.get("evidence_id")) and _identified(e.get("source_file"))
        and _identified(e.get("original_text") or e.get("reviewed_source_text"))
        and (e.get("source_pages") or e.get("json_pointer"))
        for e in claim["evidence"]
    )


def _precision_interval(claim, value):
    """Only source-reviewed exact or half-up displayed rounding has an interval."""
    precision = claim.get("precision") or {}
    if precision.get("verification_status") != "verified" or not precision.get("source_basis"):
        return None
    if precision.get("mode") == "exact":
        return value, value
    if precision.get("mode") == "rounded_half_up":
        step = _number(precision.get("step"))
        if step is not None and step > 0:
            return value - step / 2, value + step / 2
    return None


def _mapping_index(config):
    index = defaultdict(list)
    for entry in config.get("aliases", []):
        if entry.get("rule_id") in RULES and entry.get("role") in RULES[entry["rule_id"]]["roles"]:
            index[(entry["rule_id"], entry["metric_id"])].append(entry)
    return index


def _context_reasons(rule_id, claims):
    reasons = []
    if any(c.get("graph_context_review_required") and rule_id not in c.get("graph_context_reviewed_rules", []) for c in claims):
        reasons.append("graph_context_review_missing")
    def equal_known(field, *, verified_field=None):
        values = [c.get(field) for c in claims]
        if not all(_identified(v) for v in values):
            reasons.append(field + "_unknown")
        elif len({str(v).strip().lower() for v in values}) != 1:
            reasons.append(field + "_mismatch")
        if verified_field and not all(c.get(verified_field) is True for c in claims):
            reasons.append(field + "_unverified")

    def comparable_frame():
        """A shared reviewed source frame can identify a pair without a date."""
        dates = [c.get("measurement_date") for c in claims]
        frames = [c.get("comparison_frame_id") for c in claims]
        if all(_identified(v) for v in dates):
            if len(set(dates)) != 1:
                reasons.append("measurement_date_mismatch")
            return
        if all(_identified(v) for v in frames):
            if len(set(frames)) != 1:
                reasons.append("comparison_frame_id_mismatch")
            return
        reasons.append("comparison_frame_unknown")

    equal_known("observation_year")
    equal_known("period_type", verified_field="period_type_verified")
    equal_known("reporting_boundary", verified_field="reporting_boundary_verified")
    equal_known("unit")
    equal_known("variant")
    if any(not _identified(c.get("metric_definition")) or c.get("metric_definition_verified") is not True for c in claims):
        reasons.append("metric_definition_unverified")
    if rule_id == "KG-E-01":
        if any(c.get("unit") != "tCO2e" for c in claims):
            reasons.append("unit_requires_verified_conversion")
        # Scope 1 and Scope 2 necessarily have distinct scope labels; a shared
        # organizational scope must be supplied independently for comparison.
        equal_known("organizational_scope")
        for field in ("emission_basis", "scope2_method", "calculation_method"):
            equal_known(field)
        total = claims[2]
        for claim, expected_scope in zip(claims, ("scope1", "scope2", "scope1_plus_scope2")):
            if claim.get("scope") != expected_scope:
                reasons.append("ghg_scope_role_unverified")
        if total.get("total_definition") != "scope1_plus_scope2":
            reasons.append("total_definition_unverified")
        if any(c.get("baseline_id") for c in claims):
            equal_known("baseline_id")
    elif rule_id == "KG-S-01":
        if any(c.get("unit") != "person" for c in claims):
            reasons.append("unit_not_person_count")
        for field in ("population_id", "counting_method"):
            equal_known(field)
        comparable_frame()
        equal_known("scope")
    else:
        if any(c.get("unit") != "person" for c in claims):
            reasons.append("unit_not_person_count")
        equal_known("board_id")
        comparable_frame()
        equal_known("scope")
    return reasons


def _arithmetic(rule_id, claims):
    values = [_number(c.get("value")) for c in claims]
    if any(v is None for v in values):
        return "NeedsReview", "non_numeric_value", None
    if rule_id == "KG-E-01":
        intervals = [_precision_interval(c, v) for c, v in zip(claims, values)]
        calc = {"scope1": str(values[0]), "scope2": str(values[1]),
                "reported_total": str(values[2]),
                "displayed_delta": str(values[2] - values[0] - values[1]),
                "precision": [c.get("precision") for c in claims]}
        if any(i is None for i in intervals):
            return "NeedsReview", "precision_unverified", calc
        lower, upper = intervals[0][0] + intervals[1][0], intervals[0][1] + intervals[1][1]
        total_low, total_high = intervals[2]
        calc["component_sum_interval"] = [str(lower), str(upper)]
        calc["total_interval"] = [str(total_low), str(total_high)]
        if all(low == high for low, high in intervals):
            ok = lower == total_low
            return ("Supported" if ok else "Contradicted"), "exact_equal" if ok else "exact_unequal", calc
        # Endpoint contact alone depends on interval endpoint inclusion; keep
        # it for review rather than declaring a supported or conflicting fact.
        if lower == total_high or total_low == upper:
            return "NeedsReview", "precision_interval_endpoint_contact", calc
        ok = lower < total_high and total_low < upper
        return ("Supported" if ok else "Contradicted"), "intervals_overlap" if ok else "intervals_disjoint", calc
    if any(v < 0 or v != v.to_integral_value() for v in values):
        return "NeedsReview", "count_negative_or_noninteger", {"values": [str(v) for v in values]}
    left, total = values
    calc = {"subset_count": str(left), "total_count": str(total), "comparison": "subset <= total"}
    return ("Supported" if left <= total else "Contradicted"), ("subset_within_total" if left <= total else "subset_exceeds_total"), calc


def evaluate_ready_rules(claims, config):
    """Return (findings, evaluation log); all candidates stay visible in logs."""
    mapping = _mapping_index(config)
    verified_claim_mappings = {(row.get("alias_id"), row.get("record_id"), row.get("report_id")): row
                               for row in config.get("verified_claim_mappings", [])}
    by_report = defaultdict(list)
    for claim in claims:
        if claim.get("report_type") == "ESG":
            by_report[(claim["company_id"], claim["report_id"])].append(claim)
    findings, evaluations = [], []
    for (company, report_id), report_claims in sorted(by_report.items()):
        for rule_id, rule in RULES.items():
            relevant = []
            for claim in report_claims:
                if (claim.get("dimension") != rule["dimension"]
                        or claim.get("claim_type") not in {"measurement", "reported_measurement"}
                        or claim.get("variant") == "target"):
                    continue
                for alias in mapping.get((rule_id, claim.get("metric_id")), []):
                    if config.get("require_claim_mapping_review"):
                        key = ("|".join((alias["rule_id"], alias["metric_id"], alias["role"])),
                               claim["record_id"], claim["report_id"])
                        review = verified_claim_mappings.get(key)
                        scoped_alias = {**alias, "verification_status": "verified" if review else "candidate",
                                        "review_basis": review.get("review_basis") if review else None}
                        relevant.append((claim, scoped_alias))
                    else:
                        relevant.append((claim, alias))
            # Multiple years in one report are independent measurements. Unknown
            # year is retained as a separate unresolved group.
            groups = defaultdict(list)
            for claim, alias in relevant:
                groups[claim.get("observation_year")].append((claim, alias))
            known_periods = {p for p in groups if p is not None}
            # Unknown observation years are their own group. Reporting year
            # and a neighbouring candidate cannot resolve their period.
            if not groups:
                groups[None] = []
            for period, entries in sorted(groups.items(), key=lambda p: str(p[0])):
                roles = defaultdict(list)
                for claim, alias in entries:
                    roles[alias["role"]].append((claim, alias))
                ids = sorted({c["record_id"] for c, _ in entries})
                missing = [r for r in rule["roles"] if not roles[r]]
                reasons = []
                calculation = None
                if not entries:
                    topic_records = [c for c in report_claims if
                        c.get("dimension") == rule["dimension"] and c.get("topic") == rule["topic"]
                    ]
                    explicit_non_numeric = bool(topic_records) and all(
                        c.get("claim_type") in {"policy", "governance_statement"}
                        for c in topic_records)
                    outcome = "NotApplicable" if explicit_non_numeric else "Skipped"
                    reasons.append("explicit_non_numeric_record_only" if explicit_non_numeric else "no_candidate_or_coverage_unverified")
                elif missing:
                    outcome = "Skipped"
                    reasons.append("missing_role_record")
                    if any(a.get("verification_status") != "verified" or not a.get("review_basis") for _, a in entries):
                        reasons.append("mapping_unverified")
                    if any(not _identified(c.get("reporting_boundary")) or c.get("reporting_boundary_verified") is not True for c, _ in entries):
                        reasons.append("reporting_boundary_unknown_or_unverified")
                    if any(not _identified(c.get("observation_year")) or not _identified(c.get("period_type")) or c.get("period_type_verified") is not True for c, _ in entries):
                        reasons.append("period_unknown_or_unverified")
                    if any(c.get("review_status") != "reviewed" or not _evidence_ok(c) for c, _ in entries):
                        reasons.append("source_review_or_provenance_incomplete")
                    if any(c.get("value") is None or c.get("value_status") in {"missing", "unknown", "ambiguous"} for c, _ in entries):
                        reasons.append("value_missing_or_uncertain")
                else:
                    if any(len(roles[r]) != 1 for r in rule["roles"]):
                        reasons.append("multiple_candidates_for_role")
                        selected = None
                    else:
                        selected = [roles[r][0][0] for r in rule["roles"]]
                    if any(a.get("verification_status") != "verified" or not a.get("review_basis") for _, a in entries):
                        reasons.append("mapping_unverified")
                    # A known different board is an inapplicable pair, not a
                    # tentative contradiction and not an evidence gap.
                    if selected and rule_id == "KG-G-01" and all(_identified(c.get("board_id")) for c in selected) and len({c["board_id"] for c in selected}) > 1:
                        outcome = "Skipped"
                        reasons.append("different_boards")
                    else:
                        if selected:
                            reasons.extend(_context_reasons(rule_id, selected))
                        if any(c.get("review_status") != "reviewed" or not _evidence_ok(c) for c, _ in entries):
                            reasons.append("source_review_or_provenance_incomplete")
                        if any(c.get("value") is None or c.get("value_status") in {"missing", "unknown", "ambiguous"} for c, _ in entries):
                            reasons.append("value_missing_or_uncertain")
                        if any(c.get("value_status") == "not_applicable" for c, _ in entries):
                            reasons.append("value_not_applicable")
                        if reasons:
                            outcome = "NeedsReview" if any(r != "value_missing_or_uncertain" for r in reasons) else "InsufficientEvidence"
                        else:
                            outcome, arithmetic_reason, calculation = _arithmetic(rule_id, selected)
                            reasons.append(arithmetic_reason)
                if missing and entries:
                    reasons.extend("missing_" + role for role in missing)
                event_id = hashlib.sha256((rule_id + "|" + report_id + "|" + str(period) + "|" + "|".join(ids)).encode()).hexdigest()[:16].upper()
                event = {"evaluation_id": "EVAL-" + event_id, "rule_id": rule_id, "rule_version": VERSION,
                         "company_id": company, "report_id": report_id,
                         "report_year": report_claims[0]["report_year"], "observation_year": period,
                         "input_claim_ids": ids, "candidate_count": len(entries),
                         "role_candidate_counts": {r: len(roles[r]) for r in rule["roles"]},
                         "outcome": outcome, "reasons": sorted(set(reasons)),
                         "missing_inputs": missing if entries else [], "finding_id": None}
                if entries and not missing and outcome not in {"Skipped", "NotApplicable"}:
                    # All candidate inputs, including ambiguous variants, are linked.
                    f_id = "FND-" + event_id
                    chosen = [c for c, _ in entries]
                    if calculation and rule_id == "KG-E-01":
                        explanation = (f"{calculation['scope1']} + {calculation['scope2']} versus reported "
                                       f"{calculation['reported_total']} tCO2e; verified precision intervals "
                                       f"{calculation.get('component_sum_interval')} and {calculation.get('total_interval')}; "
                                       f"result: {outcome}.")
                    elif calculation:
                        explanation = (f"{calculation.get('subset_count')} <= {calculation.get('total_count')} "
                                       f"persons; exact reviewed counts; result: {outcome}.")
                    else:
                        explanation = "; ".join(sorted(set(reasons))) + "; no numerical conclusion."
                    finding = {"finding_id": f_id, "rule_id": rule_id, "rule_version": VERSION,
                               "rule_name": rule["name"], "status": outcome,
                               "company_id": company, "report_years": sorted({c["report_year"] for c in chosen}),
                               "observation_years": [period] if period is not None else [],
                               "topic": rule["topic"], "summary": "; ".join(sorted(set(reasons))),
                               "calculation": calculation,
                               "explanation": explanation,
                               "basis": "Project arithmetic/subset check; no standards compliance claim.",
                               "guard": "Verified mapping, source review and comparable context required; G accepts a reviewed common source frame without an exact date.",
                               "input_claim_ids": ids,
                               "source_files": sorted({e.get("source_file") for c in chosen for e in c.get("evidence", []) if e.get("source_file")}),
                               "source_pages": sorted({p for c in chosen for e in c.get("evidence", []) for p in e.get("source_pages", [])})}
                    findings.append(finding)
                    event["finding_id"] = f_id
                    event["calculation"] = finding["calculation"]
                evaluations.append(event)
    return findings, evaluations
