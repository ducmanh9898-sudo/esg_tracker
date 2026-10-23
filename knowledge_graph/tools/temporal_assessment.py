import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_temporal_config(path=None):
    source = Path(path) if path else ROOT / "data" / "config" / "temporal_assessment_sample.json"
    with source.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def _has_text(value):
    return isinstance(value, str) and bool(value.strip())


def _source_texts(claim):
    return [evidence.get("source_text") for evidence in claim.get("evidence", [])]


def assess_temporal_pair(earlier, later):
    """Assess comparability without turning a numeric change into a finding."""
    incompatibilities = []
    missing_context = []
    review_reasons = []

    for field in ("company_id", "metric_id", "unit"):
        if earlier.get(field) != later.get(field):
            incompatibilities.append(f"{field}_mismatch")

    if earlier.get("variant") != later.get("variant"):
        incompatibilities.append("variant_mismatch")

    earlier_period_type = earlier.get("period_type")
    later_period_type = later.get("period_type")
    if not earlier_period_type or not later_period_type:
        missing_context.append("period_type")
        incompatibilities.append("period_type_unverified")
    elif earlier_period_type != later_period_type:
        incompatibilities.append("period_type_mismatch")

    earlier_observation = earlier.get("observation_year")
    later_observation = later.get("observation_year")
    earlier_report = earlier.get("report_year")
    later_report = later.get("report_year")
    if not all(isinstance(value, int) for value in (
        earlier_observation, later_observation, earlier_report, later_report
    )):
        incompatibilities.append("period_missing")
    else:
        if later_observation <= earlier_observation or later_report <= earlier_report:
            incompatibilities.append("period_not_forward")
        if earlier_report - earlier_observation != later_report - later_observation:
            incompatibilities.append("report_observation_lag_mismatch")

    scope_change = "unchanged"
    if earlier.get("scope") != later.get("scope"):
        if (
            later.get("scope_change_status") == "changed"
            and _has_text(later.get("scope_change_explanation"))
        ):
            scope_change = "changed_explained"
            review_reasons.append("scope_change")
        else:
            scope_change = "changed_unexplained"
            incompatibilities.append("scope_mismatch")

    earlier_boundary = earlier.get("reporting_boundary")
    later_boundary = later.get("reporting_boundary")
    boundaries_verified = (
        earlier.get("reporting_boundary_verified") is True
        and later.get("reporting_boundary_verified") is True
        and _has_text(earlier_boundary)
        and _has_text(later_boundary)
    )
    if not boundaries_verified:
        boundary_change = "unknown"
        missing_context.append("reporting_boundary")
        incompatibilities.append("reporting_boundary_unverified")
    elif earlier_boundary == later_boundary:
        boundary_change = "unchanged"
    elif (
        later.get("boundary_change_status") == "changed"
        and _has_text(later.get("boundary_change_explanation"))
    ):
        boundary_change = "changed_explained"
        review_reasons.append("boundary_change")
    else:
        boundary_change = "changed_unexplained"
        incompatibilities.append("reporting_boundary_mismatch")

    earlier_baseline = earlier.get("baseline_id")
    later_baseline = later.get("baseline_id")
    if earlier_baseline is not None and earlier_baseline == later_baseline:
        baseline_change = "unchanged"
    elif (
        later.get("baseline_change_status") == "changed"
        and _has_text(later.get("baseline_change_explanation"))
    ):
        baseline_change = "changed_explained"
        review_reasons.append("baseline_change")
    elif earlier_baseline is None and later_baseline is None:
        baseline_change = "unknown"
        missing_context.append("baseline_change")
        review_reasons.append("baseline_change_unknown")
    else:
        baseline_change = "changed_unexplained"
        incompatibilities.append("baseline_change_unexplained")

    restatement_status = later.get("restatement_status")
    if restatement_status == "not_restatement":
        restatement = "not_restatement"
    elif restatement_status == "restated" and _has_text(later.get("restatement_explanation")):
        restatement = "restated_explained"
        review_reasons.append("restatement")
    elif restatement_status == "restated":
        restatement = "restated_unexplained"
        incompatibilities.append("restatement_unexplained")
    else:
        restatement = "unknown"
        missing_context.append("restatement")
        review_reasons.append("restatement_unknown")

    source_texts = _source_texts(earlier) + _source_texts(later)
    if not source_texts or any(not _has_text(text) for text in source_texts):
        missing_context.append("original_text")
        review_reasons.append("original_text_missing")

    earlier_value = earlier.get("value")
    later_value = later.get("value")
    numeric_values = (
        isinstance(earlier_value, (int, float))
        and not isinstance(earlier_value, bool)
        and isinstance(later_value, (int, float))
        and not isinstance(later_value, bool)
    )
    if not numeric_values:
        incompatibilities.append("value_missing_or_non_numeric")

    comparison_performed = not incompatibilities
    numeric_change = None
    if comparison_performed:
        numeric_change = {
            "absolute": later_value - earlier_value,
            "percent": None if earlier_value == 0 else (later_value - earlier_value) / earlier_value * 100,
        }

    assessment_status = "NeedsReview" if incompatibilities or review_reasons else "Comparable"
    change_type = "not_assessed"
    if comparison_performed:
        change_type = "unchanged" if earlier_value == later_value else (
            "target_change" if later.get("variant") == "target" else "numeric_change"
        )

    return {
        "assessment_status": assessment_status,
        "comparison_performed": comparison_performed,
        "change_type": change_type,
        "numeric_change": numeric_change,
        "flags": {
            "scope_change": scope_change,
            "boundary_change": boundary_change,
            "baseline_change": baseline_change,
            "restatement": restatement,
            "missing_context": sorted(set(missing_context)),
            "incompatibilities": sorted(set(incompatibilities)),
        },
        "disclaimer": "A numeric change is not, by itself, a Temporal Inconsistency.",
    }


def apply_temporal_assessment(graph, claims, config=None):
    """Add a small directed temporal layer without creating or modifying findings."""
    config = config or load_temporal_config()
    result = copy.deepcopy(graph)
    nodes = {node["id"]: node for node in result["nodes"]}
    edges = list(result["edges"])
    claims_by_id = {claim["claim_id"]: claim for claim in claims}

    for series in config["series"]:
        missing_claim_ids = [
            claim_id for claim_id in series["claim_ids"] if claim_id not in claims_by_id
        ]
        if missing_claim_ids:
            raise ValueError(
                f"Temporal series '{series['series_id']}' references missing claims: "
                + ", ".join(missing_claim_ids)
            )
        selected = [claims_by_id[claim_id] for claim_id in series["claim_ids"]]
        if any(claim["company_id"] != series["company_id"] for claim in selected):
            raise ValueError(f"Temporal series '{series['series_id']}' mixes companies")
        if any(claim["metric_id"] != series["metric_id"] for claim in selected):
            raise ValueError(f"Temporal series '{series['series_id']}' mixes metrics")
        selected.sort(key=lambda claim: (claim["observation_year"], claim["report_year"], claim["claim_id"]))

        series_node_id = "temporal-series:" + series["series_id"]
        nodes[series_node_id] = {
            "id": series_node_id,
            "type": "TemporalSeries",
            "label": f"{series['metric_id']} · {series['company_id']}",
            "series_id": series["series_id"],
            "concept_id": series["concept_id"],
            "company_id": series["company_id"],
            "metric_id": series["metric_id"],
            "known_limitations": list(series["known_limitations"]),
        }

        for sequence, claim in enumerate(selected, start=1):
            claim_id = "claim:" + claim["claim_id"]
            measurement_id = "measurement:" + claim["claim_id"]
            edges.append({
                "source": series_node_id,
                "target": claim_id,
                "label": "HAS_TEMPORAL_CLAIM",
                "sequence": sequence,
            })
            edges.append({
                "source": series_node_id,
                "target": measurement_id,
                "label": "HAS_TEMPORAL_TARGET" if claim.get("variant") == "target" else "HAS_TEMPORAL_MEASUREMENT",
                "sequence": sequence,
            })

        for earlier, later in zip(selected, selected[1:]):
            assessment = assess_temporal_pair(earlier, later)
            comparison_id = (
                f"{series['series_id']}:{earlier['claim_id']}:{later['claim_id']}"
            )
            comparison_node_id = "temporal-comparison:" + comparison_id
            nodes[comparison_node_id] = {
                "id": comparison_node_id,
                "type": "TemporalComparison",
                "label": f"{earlier['observation_year']} → {later['observation_year']}",
                "comparison_id": comparison_id,
                "series_id": series["series_id"],
                "company_id": earlier["company_id"],
                "metric_id": earlier["metric_id"],
                "from_report_year": earlier["report_year"],
                "to_report_year": later["report_year"],
                "from_observation_year": earlier["observation_year"],
                "to_observation_year": later["observation_year"],
                "from_value": earlier.get("value"),
                "to_value": later.get("value"),
                "unit": earlier.get("unit"),
                "from_scope": earlier.get("scope"),
                "to_scope": later.get("scope"),
                "from_original_texts": _source_texts(earlier),
                "to_original_texts": _source_texts(later),
                **assessment,
            }

            earlier_claim_id = "claim:" + earlier["claim_id"]
            later_claim_id = "claim:" + later["claim_id"]
            earlier_measurement_id = "measurement:" + earlier["claim_id"]
            later_measurement_id = "measurement:" + later["claim_id"]
            measurement_edge_label = (
                "NEXT_YEAR_TARGET"
                if earlier.get("variant") == later.get("variant") == "target"
                else "NEXT_YEAR_MEASUREMENT"
            )
            edge_attributes = {
                "comparison_id": comparison_id,
                "assessment_status": assessment["assessment_status"],
                "comparison_performed": assessment["comparison_performed"],
            }
            edges.extend([
                {"source": earlier_claim_id, "target": later_claim_id, "label": "NEXT_YEAR_CLAIM", **edge_attributes},
                {"source": earlier_measurement_id, "target": later_measurement_id, "label": measurement_edge_label, **edge_attributes},
                {"source": comparison_node_id, "target": series_node_id, "label": "PART_OF_SERIES"},
                {"source": comparison_node_id, "target": earlier_claim_id, "label": "FROM_CLAIM"},
                {"source": comparison_node_id, "target": later_claim_id, "label": "TO_CLAIM"},
                {"source": comparison_node_id, "target": earlier_measurement_id, "label": "FROM_MEASUREMENT"},
                {"source": comparison_node_id, "target": later_measurement_id, "label": "TO_MEASUREMENT"},
            ])

            provenance_edges = set()
            for claim in (earlier, later):
                report_id = f"report:{claim['company_id']}:{claim['report_year']}"
                provenance_edges.add((comparison_node_id, report_id, "DERIVED_FROM_REPORT"))
                for evidence in claim.get("evidence", []):
                    provenance_edges.add((
                        comparison_node_id,
                        "evidence:" + evidence["evidence_id"],
                        "BASED_ON_EVIDENCE",
                    ))
            edges.extend(
                {"source": source, "target": target, "label": label}
                for source, target, label in sorted(provenance_edges)
            )

    result["nodes"] = list(nodes.values())
    result["edges"] = edges
    return result
