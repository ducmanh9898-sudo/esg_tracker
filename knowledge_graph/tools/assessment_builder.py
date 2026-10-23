import copy
import json
from collections import Counter, defaultdict


def _finding_signature(finding):
    calculation = finding.get("calculation")
    if isinstance(calculation, (dict, list)):
        calculation = json.dumps(calculation, sort_keys=True, ensure_ascii=False, default=str)
    return (
        finding["rule_id"],
        finding["status"],
        tuple(sorted(finding["input_claim_ids"])),
        finding.get("summary"),
        calculation,
    )


def deduplicate_findings(findings):
    """Remove exact duplicates only; paraphrase equivalence is not inferred."""
    by_id = {}
    by_signature = {}
    unique = []
    removed = []
    for finding in findings:
        finding_id = finding["finding_id"]
        signature = _finding_signature(finding)
        previous_by_id = by_id.get(finding_id)
        if previous_by_id is not None:
            if _finding_signature(previous_by_id) != signature:
                raise ValueError(f"Conflicting records for finding_id '{finding_id}'")
            removed.append({"finding_id": finding_id, "duplicate_of": finding_id})
            continue
        previous_id = by_signature.get(signature)
        if previous_id is not None:
            removed.append({"finding_id": finding_id, "duplicate_of": previous_id})
            by_id[finding_id] = finding
            continue
        by_id[finding_id] = finding
        by_signature[signature] = finding_id
        unique.append(finding)
    return unique, {
        "exact_duplicates_removed": removed,
        "paraphrase_deduplication_status": "unverified",
        "paraphrase_note": "No semantic/paraphrase merge is performed without adjudication.",
    }


def _standard_context_by_claim(graph):
    nodes = {node["id"]: node for node in graph["nodes"]}
    concept_by_claim = defaultdict(list)
    mappings_by_concept = defaultdict(list)
    direct_by_claim = defaultdict(list)
    for edge in graph["edges"]:
        if edge["label"] == "HAS_CONCEPT":
            concept_by_claim[edge["source"]].append(edge["target"])
        elif edge["label"] == "MAPPED_TO" and edge.get("verification_status") == "verified":
            mappings_by_concept[edge["source"]].append(edge)
        elif edge["label"] == "HAS_STANDARD_CONTEXT":
            direct_by_claim[edge["source"]].append(edge["target"])

    result = defaultdict(list)
    for claim_node_id, reference_ids in direct_by_claim.items():
        for reference_id in reference_ids:
            standard = nodes.get(reference_id, {})
            if standard.get("verificationStatus") != "verified":
                continue
            result[claim_node_id].append({
                "concept_id": None,
                "concept_name": None,
                "standard_node_id": reference_id,
                "reference_code": standard.get("referenceCode"),
                "reference_title": standard.get("label"),
                "standard_name": standard.get("standardName"),
                "source_url": standard.get("sourceUrl"),
                "relationship_type": standard.get("relationshipType"),
                "mapping_reason": standard.get("mappingReason"),
                "industry_applicability_status": standard.get("industryApplicabilityStatus"),
                "verification_status": "verified",
                "disclaimer": "Context only; not a compliance or industry applicability conclusion.",
            })
    for claim_node_id, concept_ids in concept_by_claim.items():
        for concept_id in concept_ids:
            concept = nodes.get(concept_id, {})
            for mapping in mappings_by_concept.get(concept_id, []):
                standard = nodes.get(mapping["target"], {})
                result[claim_node_id].append({
                    "concept_id": concept.get("concept_id"),
                    "concept_name": concept.get("label"),
                    "standard_node_id": mapping["target"],
                    "reference_code": standard.get("reference_code"),
                    "reference_title": standard.get("reference_title"),
                    "standard_name": standard.get("standard_name"),
                    "standard_version": standard.get("standard_version"),
                    "source_type": standard.get("source_type"),
                    "source_url": standard.get("source_url"),
                    "relationship_type": mapping.get("relationship_type"),
                    "mapping_reason": mapping.get("mapping_reason"),
                    "verification_status": "verified",
                    "disclaimer": "Standard context only; not a compliance or violation conclusion.",
                })
    return result


def _claim_fact(claim):
    evidence = []
    for item in claim.get("evidence", []):
        evidence.append({
            "evidence_id": item["evidence_id"],
            "source_file": item["source_file"],
            "source_pages": list(item["source_pages"]),
            "json_pointer": item["json_pointer"],
            "source_text": item.get("source_text"),
            "source_id": item.get("source_id"),
            "source_sha256": item.get("source_sha256"),
            "page_system": item.get("page_system"),
            "corroborates_evidence_id": item.get("corroborates_evidence_id"),
            "reviewer_kind": item.get("reviewer_kind"),
            "review_scope": item.get("review_scope"),
        })
    return {
        "claim_id": claim["claim_id"],
        "company_id": claim["company_id"],
        "report_year": claim["report_year"],
        "observation_year": claim["observation_year"],
        "dimension": claim["dimension"],
        "topic": claim["topic"],
        "metric_id": claim["metric_id"],
        "label": claim["label"],
        "value": claim.get("value"),
        "unit": claim.get("unit"),
        "scope": claim.get("scope"),
        "variant": claim.get("variant"),
        "reporting_boundary": claim.get("reporting_boundary"),
        "reporting_boundary_verified": claim.get("reporting_boundary_verified") is True,
        "review_status": claim.get("review_status"),
        "evidence": evidence,
    }


def _uncertainty_for_claims(claims, finding):
    unverified = []
    if any(claim.get("reporting_boundary_verified") is not True for claim in claims):
        unverified.append("reporting_boundary")
    if any(claim.get("review_status") != "reviewed" for claim in claims):
        unverified.append("manual_source_review")
    if any(
        not evidence.get("source_text")
        for claim in claims
        for evidence in claim.get("evidence", [])
    ):
        unverified.append("original_source_text")
    return {
        "conditions_unverified": sorted(set(unverified)),
        "rule_guard": finding.get("guard"),
        "status_interpretation": (
            "Supported means only that this rule passed for the checked inputs."
            if finding["status"] == "Supported"
            else "The status is limited to the rule and supplied evidence; it is not a misconduct conclusion."
        ),
    }


def build_claim_assessments(claims, findings, graph):
    claims_by_id = {claim["claim_id"]: claim for claim in claims}
    standard_context = _standard_context_by_claim(graph)
    unique_findings, deduplication = deduplicate_findings(findings)
    assessments = []

    for finding in unique_findings:
        related_claims = []
        for claim_id in finding["input_claim_ids"]:
            if claim_id not in claims_by_id:
                raise ValueError(
                    f"Finding '{finding['finding_id']}' references missing claim '{claim_id}'"
                )
            related_claims.append(claims_by_id[claim_id])
        facts = [_claim_fact(claim) for claim in related_claims]
        all_standard_context = []
        seen_standard_context = set()
        for claim in related_claims:
            for context in standard_context.get("claim:" + claim["claim_id"], []):
                key = (context["concept_id"], context["standard_node_id"])
                if key not in seen_standard_context:
                    all_standard_context.append(context)
                    seen_standard_context.add(key)
        all_standard_context.sort(key=lambda context: (
            str(context.get("concept_id")), str(context.get("standard_node_id"))))

        for claim in related_claims:
            assessments.append({
                "assessment_id": f"CA-{finding['finding_id']}-{claim['claim_id']}",
                "assessment_level": "claim",
                "finding_id": finding["finding_id"],
                "claim_id": claim["claim_id"],
                "company_id": claim["company_id"],
                "report_year": claim["report_year"],
                "observation_year": claim["observation_year"],
                "dimension": claim["dimension"],
                "status": finding["status"],
                "rule_id": finding["rule_id"],
                "rule_name": finding["rule_name"],
                "reason": finding["summary"],
                "calculation": finding.get("calculation"),
                "uncertainty": _uncertainty_for_claims(related_claims, finding),
                "input_claim_ids": list(finding["input_claim_ids"]),
                "facts": copy.deepcopy(facts),
                "standard_context": copy.deepcopy(all_standard_context),
                "disclaimer": "Assessment of a project rule, not a standards compliance or violation conclusion.",
            })
    return assessments, deduplication


def _finding_ids_for_claims(findings, claim_ids):
    claim_ids = set(claim_ids)
    return sorted({
        finding["finding_id"]
        for finding in findings
        if claim_ids.intersection(finding["input_claim_ids"])
    })


def _dimension_distribution(claims, findings):
    result = {}
    for dimension in ("E", "S", "G"):
        dimension_claims = [claim for claim in claims if claim["dimension"] == dimension]
        claim_ids = [claim["claim_id"] for claim in dimension_claims]
        result[dimension] = {
            "claim_count": len(claim_ids),
            "claim_ids": sorted(claim_ids),
            "finding_ids": _finding_ids_for_claims(findings, claim_ids),
        }
    return result


def _temporal_patterns(graph, company_id, findings):
    edges_by_source = defaultdict(list)
    for edge in graph["edges"]:
        edges_by_source[edge["source"]].append(edge)
    patterns = []
    for node in graph["nodes"]:
        if node["type"] != "TemporalComparison" or node.get("company_id") != company_id:
            continue
        claim_ids = [
            edge["target"].removeprefix("claim:")
            for edge in edges_by_source[node["id"]]
            if edge["label"] in {"FROM_CLAIM", "TO_CLAIM"}
        ]
        patterns.append({
            "comparison_id": node["comparison_id"],
            "assessment_status": node["assessment_status"],
            "comparison_performed": node["comparison_performed"],
            "from_report_year": node["from_report_year"],
            "to_report_year": node["to_report_year"],
            "from_observation_year": node["from_observation_year"],
            "to_observation_year": node["to_observation_year"],
            "change_type": node["change_type"],
            "flags": copy.deepcopy(node["flags"]),
            "claim_ids": sorted(claim_ids),
            "finding_ids": _finding_ids_for_claims(findings, claim_ids),
        })
    return sorted(patterns, key=lambda item: (item["from_observation_year"], item["to_observation_year"]))


def _coverage(claims, findings):
    evidence = [item for claim in claims for item in claim.get("evidence", [])]
    finding_ids = sorted(finding["finding_id"] for finding in findings)
    claim_ids = {claim["claim_id"] for claim in claims}
    participating_ids = claim_ids.intersection({
        claim_id for finding in findings for claim_id in finding["input_claim_ids"]
    })
    needs_review_ids = participating_ids.intersection({
        claim_id for finding in findings if finding["status"] == "NeedsReview"
        for claim_id in finding["input_claim_ids"]
    })
    strong_ids = participating_ids.intersection({
        claim_id for finding in findings if finding["status"] in {"Supported", "Contradicted"}
        for claim_id in finding["input_claim_ids"]
    })
    return {
        "claim_count": len(claim_ids),
        "claim_record_count": len(claims),
        "assessed_claim_count": len(participating_ids),
        "assessed_claim_count_meaning": "Unique claims participating in primary findings, including NeedsReview.",
        "needs_review_claim_count": len(needs_review_ids),
        "needs_review_claim_ids": sorted(needs_review_ids),
        "strong_conclusion_claim_count": len(strong_ids),
        "strong_conclusion_claim_ids": sorted(strong_ids),
        "unassessed_claim_ids": sorted(claim_ids - participating_ids),
        "evidence_count": len({item["evidence_id"] for item in evidence}),
        "evidence_with_source_text": sum(bool(item.get("source_text")) for item in evidence),
        "manual_review_pending_claim_count": sum(
            claim.get("review_status") != "reviewed" for claim in claims
        ),
        "finding_ids": finding_ids,
        "limitations": [
            {
                "type": "source_text_coverage",
                "message": "Original source text is absent for some or all evidence records.",
                "finding_ids": finding_ids,
            },
            {
                "type": "manual_review",
                "message": "Claims not marked reviewed remain pending source/PDF adjudication.",
                "finding_ids": finding_ids,
            },
        ],
    }


def _assessment_summary(company_id, years, claims, findings, graph, deduplication, level):
    finding_ids = sorted(finding["finding_id"] for finding in findings)
    temporal_patterns = _temporal_patterns(graph, company_id, findings)
    if level == "company_year":
        year = years[0]
        temporal_patterns = [
            pattern for pattern in temporal_patterns
            if year in {pattern["from_report_year"], pattern["to_report_year"]}
        ]
    notable = [
        {
            "finding_id": finding["finding_id"],
            "rule_id": finding["rule_id"],
            "status": finding["status"],
            "summary": finding["summary"],
        }
        for finding in findings
        if finding["status"] != "Supported"
    ]
    return {
        "assessment_id": (
            f"CYA-{company_id}-{years[0]}" if level == "company_year"
            else f"COA-{company_id}-MULTIYEAR"
        ),
        "assessment_level": level,
        "company_id": company_id,
        "report_years": years,
        "finding_ids": finding_ids,
        "finding_count": len(finding_ids),
        "finding_status_distribution": dict(sorted(Counter(
            finding["status"] for finding in findings
        ).items())),
        "dimension_distribution": _dimension_distribution(claims, findings),
        "notable_findings": notable,
        "temporal_patterns": temporal_patterns,
        "coverage": _coverage(claims, findings),
        "deduplication": copy.deepcopy(deduplication),
        "risk_score": None,
        "risk_score_note": "No arbitrary score or weighting is assigned.",
        "supported_note": "Supported means only that the corresponding rule passed for the checked data.",
    }


def build_company_assessments(claims, findings, graph, deduplication):
    unique_findings, _ = deduplicate_findings(findings)
    claims_by_id = {claim["claim_id"]: claim for claim in claims}
    companies = sorted({claim["company_id"] for claim in claims})
    company_year = []
    company_multiyear = []

    for company_id in companies:
        company_claims = [claim for claim in claims if claim["company_id"] == company_id]
        company_claim_ids = {claim["claim_id"] for claim in company_claims}
        company_findings = [
            finding for finding in unique_findings
            if company_claim_ids.intersection(finding["input_claim_ids"])
        ]
        years = sorted({claim["report_year"] for claim in company_claims})
        company_multiyear.append(_assessment_summary(
            company_id, years, company_claims, company_findings,
            graph, deduplication, "company_multiyear",
        ))
        for year in years:
            year_claims = [claim for claim in company_claims if claim["report_year"] == year]
            year_claim_ids = {claim["claim_id"] for claim in year_claims}
            year_finding_ids = {
                finding["finding_id"] for finding in company_findings
                if year_claim_ids.intersection(finding["input_claim_ids"])
            }
            year_findings = [
                finding for finding in company_findings
                if finding["finding_id"] in year_finding_ids
            ]
            company_year.append(_assessment_summary(
                company_id, [year], year_claims, year_findings,
                graph, deduplication, "company_year",
            ))
    return {
        "company_year_assessments": company_year,
        "company_multiyear_assessments": company_multiyear,
    }


def apply_assessment_graph(graph, claim_assessments, company_assessments):
    result = copy.deepcopy(graph)
    nodes = {node["id"]: node for node in result["nodes"]}
    edges = list(result["edges"])
    edge_keys = {(edge["source"], edge["target"], edge["label"]) for edge in edges}

    def add_edge(source, target, label):
        key = (source, target, label)
        if key not in edge_keys:
            edges.append({"source": source, "target": target, "label": label})
            edge_keys.add(key)

    for assessment in claim_assessments:
        node_id = "claim-assessment:" + assessment["assessment_id"]
        nodes[node_id] = {
            "id": node_id,
            "type": "ClaimAssessment",
            "label": f"{assessment['rule_id']} · {assessment['status']}",
            **copy.deepcopy(assessment),
        }
        add_edge(node_id, "finding:" + assessment["finding_id"], "DERIVED_FROM_FINDING")
        add_edge(node_id, "claim:" + assessment["claim_id"], "ASSESSES_CLAIM")
        for fact in assessment["facts"]:
            for evidence in fact["evidence"]:
                add_edge(node_id, "evidence:" + evidence["evidence_id"], "BASED_ON_EVIDENCE")
        for context in assessment["standard_context"]:
            add_edge(node_id, context["standard_node_id"], "HAS_STANDARD_CONTEXT")

    combined = (
        company_assessments["company_year_assessments"]
        + company_assessments["company_multiyear_assessments"]
    )
    for assessment in combined:
        node_id = "company-assessment:" + assessment["assessment_id"]
        nodes[node_id] = {
            "id": node_id,
            "type": "CompanyAssessment",
            "label": assessment["assessment_id"],
            **copy.deepcopy(assessment),
        }
        add_edge("company:" + assessment["company_id"], node_id, "HAS_ASSESSMENT")
        for finding_id in assessment["finding_ids"]:
            add_edge(node_id, "finding:" + finding_id, "SUMMARIZES_FINDING")

    result["nodes"] = list(nodes.values())
    result["edges"] = edges
    return result


def build_assessments(claims, findings, graph):
    claim_assessments, deduplication = build_claim_assessments(claims, findings, graph)
    company_assessments = build_company_assessments(
        claims, findings, graph, deduplication
    )
    return {
        "claim_assessments": claim_assessments,
        "company_assessments": company_assessments,
        "deduplication": deduplication,
    }
