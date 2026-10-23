"""Read-only standards coverage report for the current 30 BSR claims."""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from tools.standards_crosswalk import claim_matches, load_crosswalk


ROOT = Path(__file__).resolve().parents[1]
CLAIMS_PATH = ROOT / "output" / "normalized_claims.json"
ASSESSMENTS_PATH = ROOT / "output" / "claim_assessments.json"
RULE_CATALOGUE_PATH = ROOT / "data" / "config" / "rule_catalogue.json"
GAP_STATUS_PATH = ROOT / "data" / "integration_gap_status.json"
CROSSWALK_SCHEMA_PATH = ROOT / "schemas" / "standards-crosswalk-schema-v0.1.json"
FAMILIES = (
    "GRI", "IFRS S1", "IFRS S2", "SASB Standard",
    "IFRS S2 Industry-based Guidance",
)


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _unique(values):
    return list(dict.fromkeys(values))


def _family(mapping):
    source_type = mapping["source_type"]
    if source_type == "sasb_standard":
        return "SASB Standard"
    if source_type == "industry_based_guidance":
        return "IFRS S2 Industry-based Guidance"
    name = mapping["standard_name"]
    for prefix, family in (("GRI", "GRI"), ("IFRS S1", "IFRS S1"), ("IFRS S2", "IFRS S2")):
        if name.startswith(prefix):
            return family
    raise ValueError(f"Unrecognized standard family for {mapping['mapping_id']}: {name}")


def _mapping_detail(mapping, concept):
    covered = mapping.get("covered_aspects") or [concept["description"]]
    unchecked = mapping.get("unverified_aspects") or [mapping["mapping_reason"]]
    applicability = list(mapping.get("verification_blockers", []))
    if mapping.get("industry_applicability_status") == "unverified":
        applicability.append("Industry classification and applicability to BSR require reviewer evidence.")
    if mapping.get("applicability_status") == "unverified":
        applicability.append("Application of this requirement to BSR is unverified.")
    if mapping["source_type"] == "sasb_standard":
        applicability.append("Reviewed SICS code or equivalent industry classification, source, effective period and applicability decision are missing.")
    return {
        "mapping_id": mapping["mapping_id"],
        "reference_id": mapping["reference_id"],
        "family": _family(mapping),
        "standard_name": mapping["standard_name"],
        "standard_version": mapping["standard_version"],
        "source_type": mapping["source_type"],
        "source_document": mapping["source_document"],
        "source_url": mapping["source_url"],
        "source_locator": mapping.get("source_locator") or mapping["reference_code"],
        "reference_code": mapping["reference_code"],
        "reference_title": mapping["reference_title"],
        "relevant_requirement_excerpt": mapping.get("relevant_requirement_excerpt"),
        "verification_status": mapping["verification_status"],
        "relationship_type": mapping["relationship_type"],
        "mapping_reason": mapping["mapping_reason"],
        "covered_aspects": covered,
        "unverified_aspects": unchecked,
        "industry_applicability_status": mapping.get("industry_applicability_status"),
        "applicability_status": mapping.get("applicability_status"),
        "applicability_missing": _unique(applicability),
    }


def _evidence_sources(claim):
    sources = []
    for evidence in claim.get("evidence", []):
        path = ROOT / "data" / "extract" / "esg" / evidence["source_file"]
        sources.append({
            "evidence_id": evidence["evidence_id"],
            "source_file": evidence["source_file"],
            "source_pages": evidence["source_pages"],
            "json_pointer": evidence["json_pointer"],
            "extract_json_path": str(path.resolve()) if path.is_file() else None,
            "original_source_text_available": bool(evidence.get("source_text")),
        })
    return sources


def _extract_needs(claim, mappings, gap_status):
    needs = []
    if any(not evidence.get("source_text") for evidence in claim.get("evidence", [])):
        needs.append("Original PDF text or adjudicated table/chart transcription for each evidence source.")
    if claim.get("review_status") != "reviewed":
        needs.append("Manual PDF source adjudication and reviewer identity/status.")
    if not claim.get("period_type"):
        needs.append("Verified period_type and observation period distinct from report_year where applicable.")
    if claim.get("reporting_boundary_verified") is not True:
        needs.append("Reporting boundary, included/excluded entities, consolidation approach and supporting PDF pages.")
    if not mappings:
        needs.append("Reviewed metric definition and standard-specific source text before proposing a new canonical concept or mapping.")
    if any(mapping["source_type"] in {"sasb_standard", "industry_based_guidance"} for mapping in mappings):
        industry_fields = gap_status["extract_handoff_required"]["industry_applicability"]
        needs.append("Industry applicability record: " + ", ".join(industry_fields) + ".")
    return needs


def _claim_row(claim, concepts, mappings_by_concept, assessments_by_claim, gap_status):
    matched = [concept for concept in concepts if claim_matches(claim, concept["claim_match"])]
    mappings = [
        _mapping_detail(mapping, concept)
        for concept in matched
        for mapping in mappings_by_concept[concept["concept_id"]]
    ]
    verified = [mapping for mapping in mappings if mapping["verification_status"] == "verified"]
    candidates = [mapping for mapping in mappings if mapping["verification_status"] == "unverified"]
    status = "verified_with_candidates" if verified and candidates else (
        "verified" if verified else "candidate_only" if candidates else "unmapped"
    )
    assessment_refs = _unique(
        (item["finding_id"], item["rule_id"], item["status"])
        for item in assessments_by_claim.get(claim["claim_id"], [])
    )
    covered = _unique(aspect for mapping in mappings for aspect in mapping["covered_aspects"])
    unchecked = _unique(aspect for mapping in mappings for aspect in mapping["unverified_aspects"])
    if not mappings:
        covered = [f"Claim reports {claim['label']} ({claim['metric_id']}) with value {claim['value']} {claim['unit']}."]
        unchecked = ["No standard-specific disclosure element was evaluated for this metric in the sample crosswalk."]
    return {
        "claim_id": claim["claim_id"],
        "company_id": claim["company_id"],
        "report_year": claim["report_year"],
        "observation_year": claim["observation_year"],
        "dimension": claim["dimension"],
        "topic": claim["topic"],
        "metric_id": claim["metric_id"],
        "label": claim["label"],
        "value": claim["value"],
        "unit": claim["unit"],
        "scope": claim["scope"],
        "review_status": claim.get("review_status"),
        "period_type": claim.get("period_type"),
        "reporting_boundary_verified": claim.get("reporting_boundary_verified") is True,
        "coverage_status": status,
        "has_verified_mapping": bool(verified),
        "has_unverified_candidate": bool(candidates),
        "matched_concepts": [{"concept_id": concept["concept_id"], "name": concept["name"]} for concept in matched],
        "mappings": mappings,
        "claim_addresses": covered,
        "not_checked": unchecked,
        "applicability_missing": _unique(
            condition for mapping in mappings for condition in mapping["applicability_missing"]
        ),
        "source_evidence": _evidence_sources(claim),
        "extract_data_needed": _extract_needs(claim, mappings, gap_status),
        "project_assessments": [
            {"finding_id": finding_id, "rule_id": rule_id, "status": status}
            for finding_id, rule_id, status in assessment_refs
        ],
    }


def _family_summary(rows, gap_status):
    summaries = {}
    gap_key = {"GRI": "GRI", "IFRS S1": "IFRS_S1", "SASB Standard": "SASB"}
    for family in FAMILIES:
        linked = [(row, mapping) for row in rows for mapping in row["mappings"] if mapping["family"] == family]
        verified_ids = {row["claim_id"] for row, mapping in linked if mapping["verification_status"] == "verified"}
        candidate_ids = {row["claim_id"] for row, mapping in linked if mapping["verification_status"] == "unverified"}
        unique_refs = {(mapping["reference_id"], mapping["source_type"]): mapping for _, mapping in linked}
        gap_component = gap_status["components"].get(gap_key.get(family, ""), {})
        summaries[family] = {
            "verified_claim_count": len(verified_ids),
            "candidate_claim_count": len(candidate_ids),
            "candidate_only_claim_count": len(candidate_ids - verified_ids),
            "unmapped_claim_count": len(rows) - len(verified_ids | candidate_ids),
            "verified_relation_count": sum(mapping["verification_status"] == "verified" for _, mapping in linked),
            "candidate_relation_count": sum(mapping["verification_status"] == "unverified" for _, mapping in linked),
            "reference_count": len(unique_refs),
            "references": [{
                "reference_id": mapping["reference_id"],
                "standard_name": mapping["standard_name"],
                "standard_version": mapping["standard_version"],
                "source_type": mapping["source_type"],
                "reference_code": mapping["reference_code"],
                "verification_status": mapping["verification_status"],
                "industry_applicability_status": mapping["industry_applicability_status"],
            } for mapping in unique_refs.values()],
            "industry_applicability_unverified_claim_count": len({
                row["claim_id"] for row, mapping in linked
                if mapping["industry_applicability_status"] == "unverified"
            }),
            "integration_gap_context": {
                "status": gap_component.get("status"),
                "missing": gap_component.get("missing", []),
            },
        }
    return summaries


def build_report(claims, assessments, crosswalk, rule_catalogue, gap_status):
    schema_errors = list(Draft202012Validator(_read(CROSSWALK_SCHEMA_PATH), format_checker=FormatChecker()).iter_errors(crosswalk))
    if schema_errors:
        raise ValueError(f"Existing crosswalk fails schema: {schema_errors[0].message}")
    bsr = [claim for claim in claims if claim["company_id"] == "BSR"]
    if len(bsr) != 30 or len({claim["claim_id"] for claim in bsr}) != 30:
        raise ValueError(f"This report is scoped to the current 30 unique BSR claims; found {len(bsr)} rows")
    rules = rule_catalogue["rules"]
    if len(rules) != 9 or any(
        rule["basis"]["basis_type"] != "project_defined_reconciliation"
        or rule["basis"]["standard_reference_ids"]
        for rule in rules
    ):
        raise ValueError("Rule catalogue no longer matches the nine project-defined reconciliations")
    concepts = crosswalk["concepts"]
    mappings_by_concept = defaultdict(list)
    for mapping in crosswalk["mappings"]:
        mappings_by_concept[mapping["concept_id"]].append(mapping)
    assessments_by_claim = defaultdict(list)
    bsr_ids = {claim["claim_id"] for claim in bsr}
    for assessment in assessments:
        if assessment.get("company_id") == "BSR" and assessment.get("claim_id") in bsr_ids:
            assessments_by_claim[assessment["claim_id"]].append(assessment)
    rows = [
        _claim_row(claim, concepts, mappings_by_concept, assessments_by_claim, gap_status)
        for claim in sorted(bsr, key=lambda item: (item["report_year"], item["claim_id"]))
    ]
    families = _family_summary(rows, gap_status)
    verified_ids = {row["claim_id"] for row in rows if row["has_verified_mapping"]}
    candidate_ids = {row["claim_id"] for row in rows if row["has_unverified_candidate"]}
    unmapped_ids = [row["claim_id"] for row in rows if row["coverage_status"] == "unmapped"]
    evidence_pending_ids = {
        row["claim_id"] for row in rows
        if row["review_status"] != "reviewed"
        or any(not source["original_source_text_available"] for source in row["source_evidence"])
        or not row["period_type"]
        or not row["reporting_boundary_verified"]
    }
    return {
        "report_type": "BSR standards coverage, sample crosswalk only",
        "scope": "Current 30 normalized BSR claims; read-only crosswalk analysis",
        "review_packet_status": "Four PDF review cases remain pending_adjudication; no gold label is inferred.",
        "conclusion_policy": "Mapping relationships provide partial context only; no compliance or violation conclusion is made.",
        "project_rule_policy": f"The {len(rules)} project reconciliation rules are not compliance tests for GRI, IFRS S1, IFRS S2, SASB Standard or IFRS S2 Industry-based Guidance.",
        "counts": {
            "unique_claims": len(rows),
            "verified_mapping_claims": len(verified_ids),
            "unverified_candidate_claims": len(candidate_ids),
            "candidate_only_claims": len(candidate_ids - verified_ids),
            "unmapped_claims": len(unmapped_ids),
            "verified_mapping_relations": sum(mapping["verification_status"] == "verified" for row in rows for mapping in row["mappings"]),
            "unverified_candidate_relations": sum(mapping["verification_status"] == "unverified" for row in rows for mapping in row["mappings"]),
            "project_rules": len(rules),
            "unreviewed_claims": sum(row["review_status"] != "reviewed" for row in rows),
        },
        "families": families,
        "priority_gaps": [
            {
                "priority": 1,
                "issue": "Original PDF text, source adjudication, verified period and reporting boundary are missing for current claims.",
                "affected_claim_count": len(evidence_pending_ids),
                "owner": "Extract/reviewer",
            },
            {
                "priority": 2,
                "issue": "Reviewed SICS or equivalent industry classification and applicability decision are absent for SASB; IFRS S2 industry guidance applicability is separately unverified.",
                "affected_claim_count": len({
                    row["claim_id"] for row in rows for mapping in row["mappings"]
                    if mapping["source_type"] in {"sasb_standard", "industry_based_guidance"}
                }),
                "owner": "Extract/standards reviewer",
            },
            {
                "priority": 3,
                "issue": "Most BSR metrics have no concept/mapping in this sample crosswalk; propose and review coverage without inferring compliance.",
                "affected_claim_count": len(unmapped_ids),
                "owner": "Graph/standards reviewer",
            },
        ],
        "claims": rows,
    }


def render_markdown(report):
    counts = report["counts"]
    lines = [
        "# BSR standards coverage report", "",
        report["scope"] + ". " + report["conclusion_policy"], "",
        f"Unique claims: {counts['unique_claims']}; claims with verified mapping: {counts['verified_mapping_claims']}; "
        f"claims with unverified candidate: {counts['unverified_candidate_claims']} "
        f"(candidate only: {counts['candidate_only_claims']}); unmapped claims: {counts['unmapped_claims']}.",
        f"Mapping relations: {counts['verified_mapping_relations']} verified, "
        f"{counts['unverified_candidate_relations']} unverified candidates. Overlapping claim groups are counted once in the 30-claim total.",
        report["project_rule_policy"], report["review_packet_status"], "",
        "## Coverage by source family", "",
        "| Family | Verified claims | Candidate claims | Unmapped claims | Verified relations | Candidate relations | Industry applicability unverified |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for family, summary in report["families"].items():
        lines.append(
            f"| {family} | {summary['verified_claim_count']} | {summary['candidate_claim_count']} | "
            f"{summary['unmapped_claim_count']} | {summary['verified_relation_count']} | "
            f"{summary['candidate_relation_count']} | {summary['industry_applicability_unverified_claim_count']} |"
        )
    lines.extend(["", "Mapped references by family:", ""])
    for family, summary in report["families"].items():
        references = "; ".join(
            f"{item['standard_name']} ({item['standard_version']}), {item['reference_code']}, "
            f"source_type={item['source_type']}, {item['verification_status']}"
            for item in summary["references"]
        ) or "none in the sample crosswalk"
        lines.append(f"- {family}: {references}.")
    lines.extend(["", "SASB Standard and IFRS S2 Industry-based Guidance are separate sources even where both use EM-RM-110a.1. "
                  "A verified mapping relation in the guidance does not verify BSR's industry applicability.", "",
                  "## Priority gaps", ""])
    for item in report["priority_gaps"]:
        lines.append(f"- {item['priority']}. {item['issue']} ({item['affected_claim_count']} claims; {item['owner']})")
    lines.extend(["", "## Per-claim coverage", "",
                  "| Claim | Report/observation | Metric | Coverage | Mappings |",
                  "|---|---|---|---|---|"])
    for row in report["claims"]:
        mapping_labels = ", ".join(
            f"{mapping['family']} {mapping['reference_code']} [{mapping['verification_status']}]"
            for mapping in row["mappings"]
        ) or "none"
        lines.append(f"| {row['claim_id']} | {row['report_year']}/{row['observation_year']} | "
                     f"{row['metric_id']} | {row['coverage_status']} | {mapping_labels} |")
    for row in report["claims"]:
        lines.extend(["", f"### {row['claim_id']} · {row['metric_id']} ({row['report_year']}/{row['observation_year']})", "",
                      f"Value: {row['value']} {row['unit']}; scope: {row['scope']}; status: {row['coverage_status']}.",
                      "Claim addresses: " + "; ".join(row["claim_addresses"]),
                      "Not checked: " + "; ".join(row["not_checked"]),
                      "Extract needed: " + "; ".join(row["extract_data_needed"])])
        if row["applicability_missing"]:
            lines.append("Applicability missing: " + "; ".join(row["applicability_missing"]))
        for source in row["source_evidence"]:
            lines.append(f"Evidence {source['evidence_id']}: {source['source_file']} "
                         f"p.{','.join(map(str, source['source_pages']))} `{source['json_pointer']}`; "
                         f"extract `{source['extract_json_path'] or 'unavailable'}`.")
        for mapping in row["mappings"]:
            lines.append(
                f"- {mapping['family']} · {mapping['standard_name']} ({mapping['standard_version']}); "
                f"source_type={mapping['source_type']}; {mapping['reference_code']} "
                f"({mapping['verification_status']}, {mapping['relationship_type']}). "
                f"Source: {mapping['source_document']} · {mapping['source_locator']} · {mapping['source_url']}. "
                f"Requirement excerpt: {mapping['relevant_requirement_excerpt'] or 'not stored in crosswalk'}. "
                f"Covered: {'; '.join(mapping['covered_aspects'])}. "
                f"Unchecked: {'; '.join(mapping['unverified_aspects'])}. "
                f"Applicability: {'; '.join(mapping['applicability_missing']) or 'no specific applicability record stored'}. "
                f"Reason: {mapping['mapping_reason']}"
            )
        if row["project_assessments"]:
            lines.append("Project assessments (not standards tests): " + ", ".join(
                f"{item['rule_id']} {item['status']} ({item['finding_id']})" for item in row["project_assessments"]
            ))
    return "\n".join(lines) + "\n"


def run(out_dir):
    out_dir = Path(out_dir).resolve()
    main_output = (ROOT / "output").resolve()
    if out_dir == main_output or main_output in out_dir.parents:
        raise ValueError("Coverage report directory must be outside the main output/ snapshot")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError("Coverage report directory must be empty to avoid overwriting files")
    report = build_report(
        _read(CLAIMS_PATH), _read(ASSESSMENTS_PATH), load_crosswalk(),
        _read(RULE_CATALOGUE_PATH), _read(GAP_STATUS_PATH),
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "bsr_standards_coverage.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "bsr_standards_coverage.md").write_text(render_markdown(report), encoding="utf-8")
    return report


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True, help="New or empty temporary directory")
    args = parser.parse_args(argv)
    try:
        report = run(args.out_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Standards coverage failed: {exc}\n")
    print(f"Wrote BSR standards coverage to {args.out_dir.resolve()}")
    print(report["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
