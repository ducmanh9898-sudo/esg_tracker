from collections import defaultdict

from tools.validator import validate_claims


LAYERS = (
    "input", "evidence_linkage", "standard_mapping", "rule",
    "temporal_comparison", "company_aggregation",
)


def _layer():
    return {"valid": True, "error_count": 0, "errors": []}


def _error(layer, code, message, **context):
    layer["errors"].append({"code": code, "message": message, **context})
    layer["error_count"] = len(layer["errors"])
    layer["valid"] = False


def validate_system(claims, findings, graph, assessments):
    layers = {name: _layer() for name in LAYERS}
    claims_by_id = {claim["claim_id"]: claim for claim in claims}
    nodes = {node["id"]: node for node in graph["nodes"]}
    edge_keys = {
        (edge["source"], edge["target"], edge["label"])
        for edge in graph["edges"]
    }

    input_report = validate_claims(claims)
    if not input_report["valid"]:
        for item in input_report["errors"]:
            _error(layers["input"], "invalid_claim", item["message"], claim=item["claim"])

    seen_finding_ids = set()
    for finding in findings:
        finding_id = finding["finding_id"]
        finding_node_id = "finding:" + finding_id
        if finding_id in seen_finding_ids:
            _error(layers["rule"], "duplicate_finding_id", "Finding ID is duplicated", finding_id=finding_id)
        seen_finding_ids.add(finding_id)
        if finding_node_id not in nodes:
            _error(layers["rule"], "missing_finding_node", "Finding node is absent", finding_id=finding_id)
        for claim_id in finding["input_claim_ids"]:
            claim = claims_by_id.get(claim_id)
            if claim is None:
                _error(layers["rule"], "missing_input_claim", "Finding references an absent claim", finding_id=finding_id, claim_id=claim_id)
                continue
            required_claim_edge = (finding_node_id, "claim:" + claim_id, "BASED_ON_CLAIM")
            if required_claim_edge not in edge_keys:
                _error(layers["evidence_linkage"], "missing_claim_edge", "Finding-to-claim provenance edge is absent", finding_id=finding_id, claim_id=claim_id)
            report_id = f"report:{claim['company_id']}:{claim['report_year']}"
            if (finding_node_id, report_id, "DERIVED_FROM_REPORT") not in edge_keys:
                _error(layers["evidence_linkage"], "missing_report_edge", "Finding-to-report provenance edge is absent", finding_id=finding_id, report_id=report_id)
            for evidence in claim.get("evidence", []):
                evidence_node_id = "evidence:" + evidence["evidence_id"]
                if (finding_node_id, evidence_node_id, "BASED_ON_EVIDENCE") not in edge_keys:
                    _error(layers["evidence_linkage"], "missing_evidence_edge", "Finding-to-evidence provenance edge is absent", finding_id=finding_id, evidence_id=evidence["evidence_id"])
                evidence_node = nodes.get(evidence_node_id)
                if evidence_node is None:
                    _error(layers["evidence_linkage"], "missing_evidence_node", "Evidence node is absent", evidence_id=evidence["evidence_id"])
                elif any(field not in evidence_node for field in ("source_file", "source_pages", "json_pointer")):
                    _error(layers["evidence_linkage"], "incomplete_evidence_node", "Evidence provenance metadata is incomplete", evidence_id=evidence["evidence_id"])
            if finding["status"] == "Contradicted":
                if claim.get("value") is None or not claim.get("evidence"):
                    _error(layers["rule"], "contradiction_without_evidence", "Contradicted requires present values and evidence", finding_id=finding_id)
                if claim.get("reporting_boundary_verified") is not True:
                    _error(layers["rule"], "contradiction_without_boundary", "Contradicted requires a verified reporting boundary", finding_id=finding_id)

    for edge in graph["edges"]:
        if edge["label"] != "MAPPED_TO":
            continue
        if edge.get("verification_status") != "verified":
            _error(layers["standard_mapping"], "unverified_mapping_in_graph", "Unverified mapping was materialized", mapping_id=edge.get("mapping_id"))
        target = nodes.get(edge["target"], {})
        if target.get("verification_status") != "verified" or not target.get("source_url"):
            _error(layers["standard_mapping"], "incomplete_standard_reference", "Verified mapping lacks a verified sourced target", target=edge["target"])
    if any(node["type"] in {"ComplianceConclusion", "ViolationConclusion"} for node in graph["nodes"]):
        _error(layers["standard_mapping"], "standard_conclusion_present", "Crosswalk must not create compliance or violation conclusions")

    for node in graph["nodes"]:
        if node["type"] != "TemporalComparison":
            continue
        incompatibilities = node.get("flags", {}).get("incompatibilities", [])
        if node.get("comparison_performed") and incompatibilities:
            _error(layers["temporal_comparison"], "comparison_with_incompatibility", "Temporal comparison ran despite incompatible inputs", comparison_id=node.get("comparison_id"))
        if node.get("change_type") == "TemporalInconsistency":
            _error(layers["temporal_comparison"], "automatic_temporal_inconsistency", "Numeric change must not automatically become Temporal Inconsistency", comparison_id=node.get("comparison_id"))

    unique_finding_ids_by_company = defaultdict(set)
    for finding in findings:
        for claim_id in finding["input_claim_ids"]:
            claim = claims_by_id.get(claim_id)
            if claim:
                unique_finding_ids_by_company[claim["company_id"]].add(finding["finding_id"])
    summaries = assessments["company_assessments"]["company_multiyear_assessments"]
    for summary in summaries:
        actual = summary["finding_ids"]
        expected = sorted(unique_finding_ids_by_company[summary["company_id"]])
        if actual != expected or summary["finding_count"] != len(expected):
            _error(layers["company_aggregation"], "finding_count_mismatch", "Company summary does not match unique company findings", company_id=summary["company_id"])
        if len(actual) != len(set(actual)):
            _error(layers["company_aggregation"], "double_counted_finding", "Company summary double-counts a finding", company_id=summary["company_id"])
        if summary.get("risk_score") is not None:
            _error(layers["company_aggregation"], "arbitrary_risk_score", "Company summary must not assign an arbitrary risk score", company_id=summary["company_id"])
        if summary["company_id"].startswith("SYNTHETIC"):
            _error(layers["company_aggregation"], "synthetic_company_mixed", "Synthetic data is mixed into real-company aggregation", company_id=summary["company_id"])

    claim_assessment_edges = defaultdict(set)
    for edge in graph["edges"]:
        if edge["source"].startswith("claim-assessment:"):
            claim_assessment_edges[edge["source"]].add(edge["label"])
    for assessment in assessments["claim_assessments"]:
        node_id = "claim-assessment:" + assessment["assessment_id"]
        required = {"DERIVED_FROM_FINDING", "ASSESSES_CLAIM", "BASED_ON_EVIDENCE"}
        if not required.issubset(claim_assessment_edges[node_id]):
            _error(layers["company_aggregation"], "incomplete_assessment_trace", "Claim assessment is not fully traceable", assessment_id=assessment["assessment_id"])

    return {
        "valid": all(layer["valid"] for layer in layers.values()),
        "layers": layers,
        "error_count": sum(layer["error_count"] for layer in layers.values()),
    }
