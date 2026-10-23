"""RDFLib mapping. The RDF graph is the authoritative graph representation."""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef, XSD

ESG = Namespace("https://example.org/esg/core#")
DATA = Namespace("https://example.org/esg/data/")
ROOT = Path(__file__).resolve().parents[1]


def uri(kind, identifier):
    # Hashing only the URI suffix keeps source IDs as literal properties while
    # making URI encoding stable for arbitrary Extract identifiers.
    digest = hashlib.sha256(str(identifier).encode("utf-8")).hexdigest()[:24]
    return URIRef(f"{DATA}{kind}/{digest}")


def lit(value):
    if isinstance(value, bool):
        return Literal(value, datatype=XSD.boolean)
    if isinstance(value, int):
        return Literal(value, datatype=XSD.integer)
    if isinstance(value, float):
        return Literal(value, datatype=XSD.double)
    return Literal(value)


def add_if(g, subject, predicate, value):
    if value is not None and value != "":
        g.add((subject, predicate, lit(value)))


def new_graph():
    graph = Graph()
    graph.bind("esg", ESG)
    graph.bind("data", DATA)
    graph.parse(ROOT / "kg" / "core.ttl", format="turtle")
    return graph


def add_claim(g, claim):
    company = uri("company", claim["company_id"])
    report = uri("report", claim["report_id"])
    node = uri("claim", claim["record_id"])
    metric = uri("metric", claim["metric_id"]) if claim.get("metric_id") else None
    topic = uri("topic", claim["topic"])
    has_period = claim.get("observation_year") is not None or claim.get("period_type") is not None
    period = uri("period", f"{claim['report_id']}:{claim.get('observation_year')}:{claim.get('period_type')}") if has_period else None
    value_node = uri("target" if claim.get("variant") == "target" else "measurement", claim["record_id"])
    g.add((company, RDF.type, ESG.Company))
    g.add((report, RDF.type, ESG.Report))
    g.add((node, RDF.type, ESG.Claim))
    if metric is not None:
        g.add((metric, RDF.type, ESG.Metric))
    g.add((topic, RDF.type, ESG.Topic))
    if period is not None:
        g.add((period, RDF.type, ESG.Period))
    has_value_node = claim.get("claim_type") not in {"claim", "policy", "governance_statement"}
    if has_value_node:
        g.add((value_node, RDF.type, ESG.Target if claim.get("variant") == "target" else ESG.Measurement))
    g.add((company, ESG.hasReport, report))
    g.add((report, ESG.containsClaim, node))
    g.add((node, ESG.fromReport, report))
    g.add((node, ESG.hasTopic, topic))
    if metric is not None:
        g.add((node, ESG.hasMetric, metric))
    if period is not None:
        g.add((node, ESG.hasPeriod, period))
    if has_value_node:
        g.add((node, ESG.hasTarget if claim.get("variant") == "target" else ESG.hasMeasurement, value_node))
    add_if(g, company, ESG.companyId, claim["company_id"])
    add_if(g, report, ESG.reportId, claim["report_id"])
    add_if(g, report, ESG.reportYear, claim["report_year"])
    add_if(g, report, ESG.reportType, claim["report_type"])
    add_if(g, report, ESG.sourceDocumentType, claim.get("source_document_type"))
    add_if(g, report, ESG.reportingEntity, claim.get("reporting_entity"))
    add_if(g, report, ESG.reportingPeriodStart, claim.get("reporting_period_start"))
    add_if(g, report, ESG.reportingPeriodEnd, claim.get("reporting_period_end"))
    add_if(g, report, ESG.publicationDate, claim.get("publication_date"))
    add_if(g, report, ESG.extractionTimestamp, claim.get("extraction_timestamp"))
    add_if(g, node, ESG.recordId, claim["record_id"])
    add_if(g, node, ESG.dimension, claim["dimension"])
    add_if(g, node, ESG.claimType, claim["claim_type"])
    add_if(g, node, ESG.label, claim.get("label"))
    add_if(g, node, ESG.scope, claim.get("scope"))
    add_if(g, node, ESG.reportingBoundary, claim.get("reporting_boundary"))
    add_if(g, node, ESG.boundaryVerified, claim.get("reporting_boundary_verified", False))
    add_if(g, node, ESG.baselineId, claim.get("baseline_id"))
    add_if(g, node, ESG.baselineYear, claim.get("baseline_year"))
    add_if(g, node, ESG.targetDeadline, claim.get("target_deadline"))
    add_if(g, node, ESG.yearBasis, claim.get("year_basis"))
    add_if(g, node, ESG.populationId, claim.get("population_id"))
    add_if(g, node, ESG.countingMethod, claim.get("counting_method"))
    add_if(g, node, ESG.extractionMethod, claim.get("extraction_method"))
    add_if(g, node, ESG.modelId, claim.get("model_id"))
    add_if(g, node, ESG.promptVersion, claim.get("prompt_version"))
    add_if(g, node, ESG.reviewStatus, claim.get("review_status"))
    add_if(g, node, ESG.extractReviewStatus, claim.get("extract_review_status"))
    add_if(g, node, ESG.graphContextReviewStatus, claim.get("graph_context_review_status"))
    for reviewed_rule in claim.get("graph_context_reviewed_rules", []):
        add_if(g, node, ESG.graphContextReviewedRule, reviewed_rule)
    for annotation_id in claim.get("graph_review_annotation_ids", []):
        add_if(g, node, ESG.graphReviewAnnotationId, annotation_id)
    add_if(g, node, ESG.extractionStatus, claim.get("extraction_status"))
    add_if(g, node, ESG.valueStatus, claim["value_status"])
    add_if(g, node, ESG.sourceOriginalValue, claim.get("source_original_value"))
    add_if(g, node, ESG.originalUnit, claim.get("original_unit"))
    add_if(g, node, ESG.originalScale, claim.get("original_scale"))
    add_if(g, node, ESG.normalizationNote, claim.get("normalization_note"))
    add_if(g, node, ESG.relatedRecordId, claim.get("related_record_id"))
    if metric is not None:
        add_if(g, metric, ESG.metricId, claim["metric_id"])
        add_if(g, metric, ESG.metricDefinition, claim.get("metric_definition"))
    add_if(g, topic, ESG.topicId, claim["topic"])
    if period is not None:
        add_if(g, period, ESG.observationYear, claim.get("observation_year"))
        add_if(g, period, ESG.periodType, claim.get("period_type"))
        add_if(g, period, ESG.periodTypeVerified, claim.get("period_type_verified", False))
    if has_value_node:
        add_if(g, value_node, ESG.valueStatus, claim["value_status"])
        add_if(g, value_node, ESG.unit, claim.get("unit"))
        add_if(g, value_node, ESG.variant, claim.get("variant"))
    value = claim.get("value")
    if has_value_node and value is not None and claim["value_status"] == "available":
        add_if(g, value_node, ESG.numericValue if isinstance(value, (int, float)) and not isinstance(value, bool) else ESG.textValue, value)
    for reason in claim.get("uncertainty", []):
        add_if(g, node, ESG.uncertainty, reason)
    for evidence in claim.get("evidence", []):
        evidence_node = uri("evidence", evidence["evidence_id"])
        g.add((evidence_node, RDF.type, ESG.Evidence))
        g.add((node, ESG.hasEvidence, evidence_node))
        g.add((evidence_node, ESG.fromReport, report))
        if evidence.get("source_id"):
            g.add((evidence_node, ESG.fromSourceArtifact, uri("source", evidence["source_id"])))
        add_if(g, evidence_node, ESG.evidenceId, evidence["evidence_id"])
        add_if(g, evidence_node, ESG.sourceId, evidence.get("source_id"))
        add_if(g, evidence_node, ESG.sourceSha256, evidence.get("source_sha256"))
        add_if(g, evidence_node, ESG.pageSystem, evidence.get("page_system"))
        add_if(g, evidence_node, ESG.corroboratesEvidenceId, evidence.get("corroborates_evidence_id"))
        add_if(g, evidence_node, ESG.reviewerKind, evidence.get("reviewer_kind"))
        add_if(g, evidence_node, ESG.reviewScope, evidence.get("review_scope"))
        add_if(g, evidence_node, ESG.sourceFile, evidence.get("source_file"))
        add_if(g, evidence_node, ESG.sourceLocator, evidence.get("source_locator"))
        add_if(g, evidence_node, ESG.chunkId, evidence.get("chunk_id"))
        add_if(g, evidence_node, ESG.charStart, evidence.get("char_start"))
        add_if(g, evidence_node, ESG.charEnd, evidence.get("char_end"))
        add_if(g, evidence_node, ESG.elementId, evidence.get("element_id"))
        add_if(g, evidence_node, ESG.tableId, evidence.get("table_id"))
        add_if(g, evidence_node, ESG.tableRow, evidence.get("row"))
        add_if(g, evidence_node, ESG.tableColumn, evidence.get("column"))
        add_if(g, evidence_node, ESG.printedPage, evidence.get("printed_page"))
        if evidence.get("bbox") is not None:
            add_if(g, evidence_node, ESG.boundingBoxJson, json.dumps(evidence["bbox"], sort_keys=True))
        add_if(g, evidence_node, ESG.sourceExtractPath, evidence.get("source_extract_path"))
        add_if(g, evidence_node, ESG.jsonPointer, evidence.get("json_pointer"))
        add_if(g, evidence_node, ESG.originalText, evidence.get("original_text"))
        add_if(g, evidence_node, ESG.reviewedSourceText, evidence.get("reviewed_source_text"))
        for page in evidence.get("source_pages", []):
            add_if(g, evidence_node, ESG.sourcePage, page)
        for header in evidence.get("header_evidence_ids", []):
            add_if(g, evidence_node, ESG.headerEvidenceId, header)
        for footnote in evidence.get("footnote_evidence_ids", []):
            add_if(g, evidence_node, ESG.footnoteEvidenceId, footnote)
        for note in evidence.get("ocr_limitations", []):
            add_if(g, evidence_node, ESG.ocrLimitation, note)
    return node


def add_source_artifact(g, source):
    node = uri("source", source["source_id"])
    g.add((node, RDF.type, ESG.SourceArtifact))
    add_if(g, node, ESG.sourceId, source["source_id"])
    add_if(g, node, ESG.sourceKind, source.get("kind"))
    add_if(g, node, ESG.sourcePath, source.get("path"))
    add_if(g, node, ESG.sourceSha256, source.get("sha256"))
    add_if(g, node, ESG.sourceAvailability, source.get("availability"))
    add_if(g, node, ESG.pageSystem, source.get("page_system"))
    add_if(g, node, ESG.declaredFilename, source.get("declared_filename"))
    add_if(g, node, ESG.officialUrl, source.get("official_url"))
    return node


def add_finding(g, finding):
    node = uri("finding", finding["finding_id"])
    g.add((node, RDF.type, ESG.Finding))
    add_if(g, node, ESG.findingId, finding["finding_id"])
    add_if(g, node, ESG.status, finding["status"])
    add_if(g, node, ESG.summary, finding.get("summary"))
    add_if(g, node, ESG.explanation, finding.get("explanation"))
    add_if(g, node, ESG.rationale, finding.get("basis"))
    rule = uri("rule", finding["rule_id"])
    g.add((rule, RDF.type, ESG.Rule))
    add_if(g, rule, ESG.ruleId, finding["rule_id"])
    g.add((node, ESG.generatedBy, rule))
    for claim_id in finding["input_claim_ids"]:
        g.add((node, ESG.inputClaim, uri("claim", claim_id)))
    return node


def add_assessment(g, assessment):
    node = uri("assessment", assessment["assessment_id"])
    g.add((node, RDF.type, ESG.Assessment))
    add_if(g, node, ESG.assessmentId, assessment["assessment_id"])
    add_if(g, node, ESG.assessmentLevel, assessment["assessment_level"])
    add_if(g, node, ESG.status, assessment.get("status"))
    add_if(g, node, ESG.reason, assessment.get("reason"))
    add_if(g, node, ESG.findingCount, assessment.get("finding_count"))
    coverage = assessment.get("coverage", {})
    for field, predicate in (("claim_count", ESG.claimCount),
                             ("assessed_claim_count", ESG.assessedClaimCount),
                             ("needs_review_claim_count", ESG.needsReviewClaimCount),
                             ("strong_conclusion_claim_count", ESG.strongConclusionClaimCount),
                             ("manual_review_pending_claim_count", ESG.manualReviewPendingClaimCount)):
        add_if(g, node, predicate, coverage.get(field))
    for condition in assessment.get("uncertainty", {}).get("conditions_unverified", []):
        add_if(g, node, ESG.uncertainty, condition)
    for limitation in coverage.get("limitations", []):
        add_if(g, node, ESG.limitation, limitation.get("type"))
    if assessment.get("claim_id"):
        g.add((node, ESG.assessesClaim, uri("claim", assessment["claim_id"])))
    if assessment.get("finding_id"):
        g.add((node, ESG.derivedFromFinding, uri("finding", assessment["finding_id"])))
    if assessment.get("company_id"):
        g.add((uri("company", assessment["company_id"]), ESG.hasAssessment, node))
    for finding_id in assessment.get("finding_ids", []):
        g.add((node, ESG.summarizesFinding, uri("finding", finding_id)))
    return node


def add_financial(g, record):
    disclosure = uri("financial", record["disclosure_id"])
    report = uri("report", record["source_report_id"])
    company = uri("company", record["company_id"])
    g.add((disclosure, RDF.type, ESG.FinancialDisclosure))
    g.add((report, RDF.type, ESG.Report))
    g.add((company, RDF.type, ESG.Company))
    g.add((company, ESG.hasReport, report))
    g.add((report, ESG.containsFinancialDisclosure, disclosure))
    g.add((disclosure, ESG.fromReport, report))
    add_if(g, report, ESG.reportId, record["source_report_id"])
    add_if(g, report, ESG.reportYear, record["report_year"])
    add_if(g, report, ESG.reportType, "Financial")
    add_if(g, report, ESG.reportingEntity, record.get("scope", {}).get("scope_id"))
    add_if(g, report, ESG.publicationDate, record.get("publication_date"))
    add_if(g, report, ESG.extractionTimestamp, record.get("extraction_timestamp"))
    add_if(g, report, ESG.sourceCreatedAt, record.get("source_created_at"))
    add_if(g, report, ESG.reportingDate, record.get("reporting_date"))
    add_if(g, disclosure, ESG.disclosureId, record["disclosure_id"])
    add_if(g, disclosure, ESG.numericValue, record.get("value"))
    add_if(g, disclosure, ESG.valueStatus, record.get("value_status"))
    add_if(g, disclosure, ESG.reviewStatus, record.get("review_status"))
    for reason in record.get("review_reasons", []):
        add_if(g, disclosure, ESG.uncertainty, reason)
    add_if(g, disclosure, ESG.confidence, record.get("confidence"))
    add_if(g, disclosure, ESG.extractionNotes, record.get("extraction_notes"))
    add_if(g, disclosure, ESG.sourceRecordId, record.get("source_record_id"))
    add_if(g, disclosure, ESG.sourceMeasurementId, record.get("source_measurement_id"))
    add_if(g, disclosure, ESG.metricId, record.get("item", {}).get("item_id"))
    add_if(g, disclosure, ESG.dimension, record.get("graph_dimension"))
    add_if(g, disclosure, ESG.reportingBoundary, record.get("scope", {}).get("scope_id"))
    add_if(g, disclosure, ESG.variant, record.get("variant"))
    add_if(g, disclosure, ESG.unit, record.get("unit"))
    add_if(g, disclosure, ESG.unitMultiplier, record.get("unit_multiplier"))
    add_if(g, disclosure, ESG.sourceFile, record.get("source_file"))
    add_if(g, disclosure, ESG.extractFile, record.get("extract_file"))
    add_if(g, disclosure, ESG.jsonPointer, record.get("source_pointer"))
    for page in record.get("source_pages", []):
        add_if(g, disclosure, ESG.sourcePage, page)
    add_if(g, disclosure, ESG.observationYear, record.get("observation_year"))
    add_if(g, disclosure, ESG.periodType, record.get("reporting_period", {}).get("period_type"))
    add_if(g, disclosure, ESG.measurementDate, record.get("measurement_date", {}).get("value"))
    if record.get("record_type") == "financial_candidate":
        measurement = uri("measurement", record["disclosure_id"])
        has_period = record.get("observation_year") is not None or record.get("reporting_period", {}).get("period_type") is not None
        period = uri("period", f"{record['source_report_id']}:{record.get('observation_year')}") if has_period else None
        evidence = uri("evidence", record["disclosure_id"])
        g.add((measurement, RDF.type, ESG.Measurement))
        if period is not None:
            g.add((period, RDF.type, ESG.Period))
        g.add((evidence, RDF.type, ESG.Evidence))
        g.add((disclosure, ESG.hasMeasurement, measurement))
        if period is not None:
            g.add((disclosure, ESG.hasPeriod, period))
        g.add((disclosure, ESG.hasEvidence, evidence))
        if period is not None:
            g.add((measurement, ESG.hasPeriod, period))
        g.add((evidence, ESG.fromReport, report))
        add_if(g, measurement, ESG.numericValue, record.get("value"))
        add_if(g, measurement, ESG.valueStatus, record.get("value_status"))
        add_if(g, measurement, ESG.unit, record.get("unit"))
        add_if(g, measurement, ESG.unitMultiplier, record.get("unit_multiplier"))
        add_if(g, measurement, ESG.variant, record.get("variant"))
        if period is not None:
            add_if(g, period, ESG.observationYear, record.get("observation_year"))
            add_if(g, period, ESG.periodType, record.get("reporting_period", {}).get("period_type"))
        add_if(g, evidence, ESG.sourceFile, record.get("source_file"))
        add_if(g, evidence, ESG.sourceExtractPath, record.get("extract_file"))
        add_if(g, evidence, ESG.jsonPointer, record.get("source_pointer"))
        add_if(g, evidence, ESG.originalText, record.get("original_text"))
        for page in record.get("source_pages", []):
            add_if(g, evidence, ESG.sourcePage, page)
        for pointer in record.get("ocr_page_pointers", []):
            add_if(g, evidence, ESG.ocrPagePointer, pointer)
        add_if(g, evidence, ESG.ocrLimitation, "OCR/table-order mapping requires human review")
    return disclosure


def add_standards(g, claims, crosswalk):
    """Materialize reviewed crosswalk links; unverified candidates remain in config."""
    concepts = {c["concept_id"]: c for c in crosswalk.get("concepts", [])}
    count = 0
    for mapping in crosswalk.get("mappings", []):
        if mapping.get("verification_status") != "verified":
            continue
        concept = concepts.get(mapping["concept_id"])
        if not concept:
            continue
        ref = uri("standard", mapping["reference_id"])
        g.add((ref, RDF.type, ESG.StandardReference))
        add_if(g, ref, ESG.referenceCode, mapping["reference_code"])
        add_if(g, ref, ESG.standardName, mapping["standard_name"])
        add_if(g, ref, ESG.sourceUrl, mapping.get("source_url"))
        add_if(g, ref, ESG.verificationStatus, "verified")
        add_if(g, ref, ESG.industryApplicabilityStatus, mapping.get("industry_applicability_status", "unknown"))
        add_if(g, ref, ESG.relationshipType, mapping.get("relationship_type"))
        add_if(g, ref, ESG.mappingReason, mapping.get("mapping_reason"))
        for claim in claims:
            selector = concept.get("claim_match", {})
            if all(claim.get(field) in accepted for field, accepted in selector.items()):
                g.add((uri("claim", claim["record_id"]), ESG.hasStandardContext, ref))
                count += 1
    return count


def add_standard_candidates(g, claims, references_by_metric):
    """Keep suggested references distinct from reviewed standard relationships."""
    count = 0
    for claim in claims:
        for reference in references_by_metric.get(claim["metric_id"], []) + references_by_metric.get("_all", []):
            candidate_id = f"{claim['record_id']}:{reference['reference']}"
            candidate = uri("standard-candidate", candidate_id)
            g.add((candidate, RDF.type, ESG.StandardCandidate))
            g.add((uri("claim", claim["record_id"]), ESG.hasStandardCandidate, candidate))
            add_if(g, candidate, ESG.candidateId, candidate_id)
            add_if(g, candidate, ESG.referenceCode, reference["reference"])
            add_if(g, candidate, ESG.relationshipType, reference["relationship"])
            add_if(g, candidate, ESG.mappingReason, reference["reason"])
            add_if(g, candidate, ESG.sourceUrl, reference["source_url"])
            add_if(g, candidate, ESG.verificationStatus, "unverified_candidate")
            count += 1
    return count


def add_financial_candidate_links(g, links):
    """Materialize guarded candidates without a direct equality edge."""
    for link in links:
        candidate_id = f"{link['claim_id']}:{link['financial_disclosure_id']}"
        candidate = uri("financial-candidate", candidate_id)
        g.add((candidate, RDF.type, ESG.FinancialComparisonCandidate))
        g.add((uri("claim", link["claim_id"]), ESG.hasFinancialCandidate, candidate))
        g.add((candidate, ESG.candidateFinancialDisclosure,
               uri("financial", link["financial_disclosure_id"])))
        add_if(g, candidate, ESG.candidateId, candidate_id)
        add_if(g, candidate, ESG.comparable, link["comparable"])
        add_if(g, candidate, ESG.verificationStatus, link["status"])
        for reason in link["reasons"]:
            add_if(g, candidate, ESG.comparisonBlocker, reason)
    return len(links)


CHAIN_QUERY = """
PREFIX esg: <https://example.org/esg/core#>
SELECT ?findingId ?claimId ?evidenceId ?sourceFile ?sourcePage ?reportId WHERE {
  ?finding a esg:Finding ; esg:findingId ?findingId ; esg:inputClaim ?claim .
  ?claim esg:recordId ?claimId ; esg:hasEvidence ?evidence ; esg:fromReport ?report .
  ?evidence esg:evidenceId ?evidenceId ; esg:sourceFile ?sourceFile .
  OPTIONAL { ?evidence esg:sourcePage ?sourcePage }
  ?report esg:reportId ?reportId .
}
"""


def evidence_chain(g):
    return [tuple(str(cell) if cell is not None else None for cell in row) for row in g.query(CHAIN_QUERY)]


def link_cross_year(g, claims):
    """SPARQL discovers same-company/metric candidates; Python guards comparability."""
    query = """
    PREFIX esg: <https://example.org/esg/core#>
    SELECT ?a ?b WHERE {
      ?a a esg:Claim ; esg:hasMetric ?m ; esg:fromReport ?ra ; esg:hasPeriod ?pa .
      ?b a esg:Claim ; esg:hasMetric ?m ; esg:fromReport ?rb ; esg:hasPeriod ?pb .
      ?ca esg:hasReport ?ra . ?ca esg:hasReport ?rb .
      ?pa esg:observationYear ?ya . ?pb esg:observationYear ?yb .
      FILTER (?ya < ?yb)
    }
    """
    by_uri = {uri("claim", c["record_id"]): c for c in claims}
    pairs = []
    seen = set()
    for a, b in g.query(query):
        first, second = by_uri.get(a), by_uri.get(b)
        if not first or not second or (a, b) in seen:
            continue
        seen.add((a, b))
        guard = []
        for field in ("unit", "scope", "period_type", "baseline_id", "variant"):
            if first.get(field) != second.get(field):
                guard.append(field + "_mismatch")
        if not first.get("reporting_boundary_verified") or not second.get("reporting_boundary_verified"):
            guard.append("boundary_unverified")
        elif first.get("reporting_boundary") != second.get("reporting_boundary"):
            guard.append("boundary_mismatch")
        if not first.get("period_type_verified") or not second.get("period_type_verified"):
            guard.append("period_type_unverified")
        status = "Comparable" if not guard else "NeedsReview"
        g.add((a, ESG.nextYearClaim, b))
        pairs.append({"from_claim_id": first["record_id"], "to_claim_id": second["record_id"],
                      "status": status, "guards": guard,
                      "from_year": first.get("observation_year"), "to_year": second.get("observation_year")})
    return pairs


def project_json(g):
    """Disposable UI projection generated entirely from the RDF graph."""
    types = {
        ESG.Company: "Company", ESG.Report: "Report", ESG.Claim: "Claim",
        ESG.Measurement: "Measurement", ESG.Target: "Measurement",
        ESG.Evidence: "Evidence", ESG.SourceArtifact: "SourceArtifact", ESG.Rule: "Rule", ESG.Finding: "Finding",
        ESG.StandardReference: "StandardReference", ESG.StandardCandidate: "StandardCandidate",
        ESG.NarrativeCandidate: "NarrativeCandidate",
        ESG.FinancialComparisonCandidate: "FinancialComparisonCandidate", ESG.Assessment: "ClaimAssessment",
        ESG.FinancialDisclosure: "FinancialDisclosure",
    }
    id_properties = {
        "Company": ESG.companyId, "Report": ESG.reportId, "Claim": ESG.recordId,
        "Evidence": ESG.evidenceId, "SourceArtifact": ESG.sourceId, "Rule": ESG.ruleId, "Finding": ESG.findingId,
        "StandardReference": ESG.referenceCode, "ClaimAssessment": ESG.assessmentId,
        "FinancialDisclosure": ESG.disclosureId,
        "StandardCandidate": ESG.candidateId, "FinancialComparisonCandidate": ESG.candidateId,
        "NarrativeCandidate": ESG.candidateId,
    }
    prefix = {"Company": "company", "Report": "report", "Claim": "claim",
              "Evidence": "evidence", "SourceArtifact": "source", "Rule": "rule", "Finding": "finding",
              "Measurement": "measurement", "StandardReference": "standard",
              "ClaimAssessment": "claim-assessment", "CompanyAssessment": "company-assessment", "FinancialDisclosure": "financial"}
    prefix.update({"StandardCandidate": "standard-candidate", "FinancialComparisonCandidate": "financial-candidate",
                   "NarrativeCandidate": "narrative-candidate"})
    nodes, ids = [], {}
    for subject, _, klass in g.triples((None, RDF.type, None)):
        kind = types.get(klass)
        if not kind:
            continue
        if kind == "ClaimAssessment" and str(g.value(subject, ESG.assessmentLevel)) != "claim":
            kind = "CompanyAssessment"
        identity = g.value(subject, ESG.assessmentId) if kind == "CompanyAssessment" else (g.value(subject, id_properties[kind]) if kind in id_properties else str(subject).rsplit("/", 1)[-1])
        identity = str(identity or str(subject).rsplit("/", 1)[-1])
        node_id = prefix[kind] + ":" + identity
        if node_id in {n["id"] for n in nodes}:
            continue
        ids[subject] = node_id
        props = {}
        for _, predicate, obj in g.triples((subject, None, None)):
            if predicate == RDF.type or isinstance(obj, URIRef):
                continue
            key = str(predicate).split("#")[-1]
            value = obj.toPython()
            if key in props:
                props[key] = props[key] + [value] if isinstance(props[key], list) else [props[key], value]
            else:
                props[key] = value
        node = {"id": node_id, "type": kind, "label": str(props.get("label") or identity), **props}
        if kind == "Company":
            node["company_id"] = identity
        if kind == "Claim":
            node["claim_id"] = identity
            node["dimension"] = props.get("dimension")
        if kind == "Finding":
            node["status"] = props.get("status")
        nodes.append(node)
    labels = {
        ESG.hasReport: "HAS_REPORT", ESG.containsClaim: "CONTAINS",
        ESG.fromSourceArtifact: "FROM_SOURCE_ARTIFACT",
        ESG.fromReport: "DERIVED_FROM_REPORT", ESG.hasEvidence: "SOURCED_FROM",
        ESG.hasMeasurement: "HAS_MEASUREMENT", ESG.hasTarget: "HAS_MEASUREMENT",
        ESG.inputClaim: "BASED_ON_CLAIM", ESG.generatedBy: "GENERATED_BY",
        ESG.nextYearClaim: "NEXT_YEAR_CLAIM", ESG.hasStandardContext: "HAS_STANDARD_CONTEXT",
        ESG.hasStandardCandidate: "HAS_STANDARD_CANDIDATE",
        ESG.hasFinancialCandidate: "HAS_FINANCIAL_CANDIDATE",
        ESG.candidateFinancialDisclosure: "CANDIDATE_FINANCIAL_DISCLOSURE",
        ESG.assessesClaim: "ASSESSES_CLAIM", ESG.derivedFromFinding: "DERIVED_FROM_FINDING",
        ESG.hasAssessment: "HAS_ASSESSMENT", ESG.summarizesFinding: "SUMMARIZES_FINDING",
    }
    edges = []
    for subject, predicate, obj in g:
        if predicate in labels and subject in ids and obj in ids:
            edges.append({"source": ids[subject], "target": ids[obj], "label": labels[predicate]})
    return {"nodes": nodes, "edges": edges}
