import json

from rapidfuzz.fuzz import token_set_ratio

from src.normalization.units import normalize_value, units_convertible


def candidate_score(claim: dict, metric: dict) -> float:
    score = token_set_ratio(claim.get("source_text", ""), metric.get("source_text", "")) / 100
    if claim.get("metric_code") and claim.get("metric_code") == metric.get("metric_code"):
        score += 0.35
    if claim.get("report_year") == metric.get("metric_year"):
        score += 0.15
    return min(score, 1.0)


def check_comparability(claim: dict, metric: dict) -> dict:
    same_metric = bool(claim.get("metric_code") and claim.get("metric_code") == metric.get("metric_code"))
    same_period = claim.get("report_year") == metric.get("metric_year")
    claim_unit, metric_unit = claim.get("raw_unit"), metric.get("normalized_unit") or metric.get("raw_unit")
    same_unit = bool(claim_unit and metric_unit and claim_unit.lower() == metric_unit.lower())
    convertible = units_convertible(claim_unit, metric_unit)
    same_scope = not claim.get("scope") or not metric.get("scope") or claim.get("scope") == metric.get("scope")
    same_boundary = not claim.get("boundary") or not metric.get("boundary") or claim.get("boundary") == metric.get("boundary")
    same_kind = not claim.get("value_kind") or claim.get("value_kind") == metric.get("value_kind")
    same_definition = claim.get("metric_code") not in {"ENV_CAPEX", "ENV_EXPENSE"} or claim.get("metric_code") == metric.get("metric_code")
    comparable = all((same_metric, same_period, same_scope, same_boundary, same_kind, same_definition, same_unit or convertible))
    return {
        "same_metric": same_metric, "same_period": same_period, "same_unit": same_unit,
        "unit_convertible": convertible, "same_scope": same_scope, "same_boundary": same_boundary,
        "same_definition": same_definition, "same_value_kind": same_kind, "comparable": comparable,
    }


def relationship_for(claim: dict, metric: dict | None, tolerance: float = 0.02) -> tuple[str, dict]:
    if metric is None:
        return "MISSING", {"reason": "no_candidate"}
    checks = check_comparability(claim, metric)
    if not checks["same_scope"] or not checks["same_boundary"] or not checks["same_value_kind"] or not checks["same_definition"]:
        return "NOT_COMPARABLE", checks
    if not (checks["same_unit"] or checks["unit_convertible"]):
        return "AMBIGUOUS", checks
    if not checks["same_metric"] or not checks["same_period"]:
        return "PARTIAL_SUPPORT", checks
    cval = claim.get("raw_value")
    mval = metric.get("normalized_value")
    target_unit = metric.get("normalized_unit") or metric.get("raw_unit")
    if mval is None:
        mval = metric.get("raw_value")
    if cval is None or mval is None:
        return "PARTIAL_SUPPORT", checks
    if claim.get("raw_unit") and target_unit:
        normalized_claim, _unit, status = normalize_value(cval, claim.get("raw_unit"), target_unit)
        if status == "OK" and normalized_claim is not None:
            cval = normalized_claim
    relative = abs(cval - mval) / max(abs(mval), 1e-12)
    checks["relative_difference"] = relative
    checks["tolerance"] = tolerance
    return ("CONTRADICTS" if relative > tolerance else "SUPPORTS"), checks


def checks_json(checks: dict) -> str:
    return json.dumps(checks, ensure_ascii=False, sort_keys=True)
