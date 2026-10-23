"""Validate annual-report narrative proposals and add review-only graph links."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import fitz
from rdflib import Literal, RDF

from kg.text_normalize import normalized_label
from kg.rdf_store import ESG, uri


def attach(graph, proposals, claims, sources):
    if proposals.get("schema_version") != "annual-narrative-review-1.0":
        raise ValueError("unknown_narrative_candidate_version")
    index = {claim["record_id"]: claim for claim in claims}
    source_index = {source["source_id"]: source for source in sources}
    seen = set()
    documents = {}
    try:
        for case in proposals.get("cases", []):
            candidate_id = case["candidate_id"]
            if candidate_id in seen:
                raise ValueError("duplicate_narrative_candidate_id:" + candidate_id)
            seen.add(candidate_id)
            if (case.get("relation") != "exact_normalized_text_overlap" or
                    case.get("assessment_status") != "review_only_not_graph_verdict" or
                    case.get("decision") != "pending"):
                raise ValueError("narrative_candidate_not_pending:" + candidate_id)
            claim = index.get(case["esg_record_id"])
            source = source_index.get(case["annual_source_id"])
            if (claim is None or claim["input_digest"] != case["esg_input_digest"] or
                    (claim.get("source_document_type") or
                     (claim.get("raw_document") or {}).get("source_document_type")) != "sustainability_report" or
                    claim.get("claim_type") not in {"policy", "governance_statement"}):
                raise ValueError("narrative_esg_claim_mismatch:" + candidate_id)
            if (source is None or source["sha256"] != case["annual_source_sha256"] or
                    claim["report_year"] != case["annual_report_year"] or
                    claim["company_id"] != case["company_id"]):
                raise ValueError("narrative_annual_source_mismatch:" + candidate_id)
            path = Path(source["path"])
            if str(path.resolve()) != str(Path(case["annual_pdf_path"]).resolve()):
                # A copied delivery PDF is acceptable only when its bytes match the registry source.
                with Path(case["annual_pdf_path"]).open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != source["sha256"]:
                        raise ValueError("narrative_pdf_hash_mismatch:" + candidate_id)
            if source["source_id"] not in documents:
                documents[source["source_id"]] = fitz.open(path)
            pdf = documents[source["source_id"]]
            page = case["annual_physical_page"]
            if not isinstance(page, int) or isinstance(page, bool) or not 1 <= page <= len(pdf):
                raise ValueError("narrative_page_out_of_range:" + candidate_id)
            text = pdf[page - 1].get_text()
            start, end = case["annual_char_start"], case["annual_char_end"]
            if (not isinstance(start, int) or isinstance(start, bool) or
                    not isinstance(end, int) or isinstance(end, bool) or
                    not 0 <= start < end <= len(text) or
                    text[start:end] != case["annual_exact_quote"]):
                raise ValueError("narrative_quote_span_mismatch:" + candidate_id)
            esg_quote = claim["raw_record"]["statement"]["original_quote"]
            if normalized_label(esg_quote) not in normalized_label(case["annual_exact_quote"]):
                raise ValueError("narrative_text_overlap_mismatch:" + candidate_id)
            node = uri("narrative-candidate", candidate_id)
            graph.add((node, RDF.type, ESG.NarrativeCandidate))
            graph.add((node, ESG.inputClaim, uri("claim", case["esg_record_id"])))
            graph.add((node, ESG.fromSourceArtifact, uri("source", source["source_id"])))
            for predicate, value in ((ESG.candidateId, candidate_id),
                                     (ESG.status, "NeedsReview"),
                                     (ESG.sourceSha256, source["sha256"]),
                                     (ESG.sourcePage, page), (ESG.charStart, start),
                                     (ESG.charEnd, end), (ESG.originalText, case["annual_exact_quote"]),
                                     (ESG.relation, case["relation"])):
                graph.add((node, predicate, Literal(value)))
    finally:
        for document in documents.values():
            document.close()
    return len(seen)
