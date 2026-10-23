"""Offline entry point for JSON + PDF deliveries; legacy corpus remains separate."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import html
import json
import math
import os
import re
from decimal import Decimal
from pathlib import Path
import tempfile

from pyshacl import validate as shacl_validate
from rdflib import Graph, Literal, RDF

from handoff.bsr_extract_2023_2025_v1.validate import (
    HERE as CONTRACT, load_json, schema_errors, sha256, validate_handoff, validate_manifest,
)
from kg.corporate_adapter import adapt, digest
from kg.corporate_assessment import (LAYERS, arithmetic_candidates, assess, candidates, comparison_digest,
                                     human_event, record_review)
from kg.annual_narrative_graph import attach as attach_annual_narratives
from kg.rdf_store import ESG, add_claim, add_finding, add_source_artifact, new_graph, project_json, uri

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def event_index(events, key):
    if not isinstance(events, list):
        raise ValueError("review_events_must_be_array")
    result = {}
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get(key), str):
            raise ValueError("review_event_missing_identity:" + key)
        identity = event[key]
        if identity in result:
            raise ValueError("duplicate_review_event:" + identity)
        result[identity] = event
    return result


def finite_numbers(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("non_finite_number")
    if isinstance(value, dict):
        for v in value.values():
            finite_numbers(v)
    elif isinstance(value, list):
        for v in value:
            finite_numbers(v)


def resolve_delivery(root, relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("path_outside_delivery:" + relative)
    return path


def prepare(manifest_path, config):
    manifest, errors = validate_manifest(manifest_path, load_json(CONTRACT / "manifest_schema.json"))
    if errors:
        raise ValueError("; ".join(errors))
    claims, documents, inventory, sources = [], [], [], {}
    evidence_bindings, record_ids, slots = {}, set(), set()
    for row in manifest["files"]:
        item = {**row, "errors": []}
        inventory.append(item)
        if row["status"] == "unavailable":
            continue
        path = resolve_delivery(manifest_path.parent, row["json_path"])
        pdf = resolve_delivery(manifest_path.parent, row["pdf_path"])
        try:
            raw = load_json(path)
            finite_numbers(raw)
            schema = schema_errors(raw, load_json(CONTRACT / "schema.json"))
            if schema:
                raise ValueError("; ".join(schema))
            doc = raw["document"]
            # PDF location comes from the manifest, not a guessed filename or page mapping.
            if doc["source"]["file_name"] != pdf.name:
                raise ValueError("manifest_pdf_filename_mismatch")
            _, validation = validate_handoff(path, load_json(CONTRACT / "schema.json"), pdf.parent)
            if validation:
                raise ValueError("; ".join(validation))
            for field in ("document_id", "report_year", "report_type", "financial_scope"):
                if doc[field] != row[field]:
                    raise ValueError("manifest_document_mismatch:" + field)
            if doc["source"]["sha256"] != row["pdf_sha256"]:
                raise ValueError("manifest_pdf_hash_mismatch")
            if config.get("company_id") and doc["company_id"] != config["company_id"]:
                raise ValueError("company_outside_selected_pilot")
            for record in raw["records"]:
                value = record["value"]
                # Only unambiguous plain decimal notation is mechanically recomputed.
                if (value["status"] == "available" and value["normalization_factor"] is not None and
                        re.fullmatch(r"-?\d+(?:\.\d+)?", value["original_value"] or "") and
                        not re.fullmatch(r"-?\d{1,3}\.\d{3}", value["original_value"] or "")):
                    expected = Decimal(value["original_value"]) * Decimal(str(value["normalization_factor"]))
                    if expected != Decimal(str(value["normalized_value"])):
                        raise ValueError("normalization_mismatch:" + record["record_id"])
            item["coverage"] = raw["coverage"]
            item["issue_log"] = raw["issue_log"]
            item["source_validation"] = "passed_mechanical"
            item["semantic_validation"] = "pending_human_review"
            item["status"] = "partial" if (row["status"] == "partial" or raw["coverage"]["status"] != "complete" or
                raw["coverage"]["pages_unreadable"] or any(s["status"] in {"parse_failure", "extraction_failure", "not_searched"}
                for s in raw["coverage"]["search_outcomes"]) or any(i["status"] != "resolved" for i in raw["issue_log"])) else "loaded"
        except (ValueError, OSError, KeyError, TypeError) as exc:
            item["status"] = "blocked"
            item["errors"].append(str(exc))
            continue
        slot = (doc["report_year"], doc["report_type"], doc["financial_scope"])
        slots.add(slot)
        slots.add((*slot, doc["source_document_type"]))
        source = doc["source"]
        if source["source_id"] in sources and sources[source["source_id"]]["sha256"] != source["sha256"]:
            raise ValueError("conflicting_source_id:" + source["source_id"])
        sources[source["source_id"]] = {**source, "path": str(pdf), "kind": "delivered_pdf_binary",
                                       "availability": "present", "declared_filename": pdf.name, "official_url": source["url"]}
        documents.append(raw)
        for index, record in enumerate(raw["records"]):
            if record["record_id"] in record_ids:
                raise ValueError("duplicate_record_id:" + record["record_id"])
            record_ids.add(record["record_id"])
            for ev in record["evidence"]:
                binding = digest(ev)
                if ev["evidence_id"] in evidence_bindings and evidence_bindings[ev["evidence_id"]] != binding:
                    raise ValueError("conflicting_evidence_id:" + ev["evidence_id"])
                evidence_bindings[ev["evidence_id"]] = binding
            claim = adapt(doc, record, path)
            for j, ev in enumerate(claim["evidence"]):
                ev["json_pointer"] = f"/records/{index}/evidence/{j}"
            claims.append(claim)
    missing = []
    for row in config.get("expected_reports", []):
        slot = (row["report_year"], row["report_type"], row["financial_scope"])
        if "source_document_type" in row:
            slot += (row["source_document_type"],)
        if slot not in slots:
            missing.append(row)
    return claims, documents, inventory, list(sources.values()), missing


def review_template(claims, comparisons):
    index = {c["record_id"]: c for c in claims}
    return {"schema_version": "corporate-graph-review-1.0", "record_events": [
        {"record_id": c["record_id"], "input_digest": c["input_digest"], "decision": "pending",
         "reviewer_kind": "human", "reviewer": None, "reviewed_at_utc": None, "basis": None,
         "checks": {layer: False for layer in LAYERS}} for c in claims],
        "comparison_events": [
        {"comparison_id": row["comparison_id"], "input_digest": comparison_digest(row, index),
         "record_ids": row["record_ids"], "relation": row["relation"], "decision": "pending",
         "reviewer_kind": "human", "reviewer": None, "reviewed_at_utc": None, "basis": None,
         "absolute_tolerance": None, "not_applicable_fields": [], "scope_relation_confirmed": False,
         "restatement_checked": False} for row in comparisons]}


def evaluation(findings, gold):
    result = {"status": "pending_adjudication", "extraction_precision": None, "extraction_recall": None,
              "assessment_accuracy": None, "evaluated_comparisons": 0,
              "reason": "Candidate review is not exhaustive region annotation; no extraction recall is inferred."}
    if gold is None:
        return result
    finite_numbers(gold)
    if gold.get("schema_version") != "corporate-assessment-gold-1.0":
        raise ValueError("unknown_gold_version")
    index = {f["comparison_id"]: f for f in findings}
    rows = event_index(gold.get("items", []), "comparison_id")
    judged = []
    for identity, label in rows.items():
        if not human_event(label) or label.get("split") != "held_out" or label.get("adjudication_status") != "adjudicated":
            raise ValueError("gold_not_human_adjudicated_held_out:" + identity)
        if identity not in index or label.get("input_digest") != index[identity]["input_digest"]:
            raise ValueError("gold_input_missing_or_stale:" + identity)
        if label.get("expected_status") not in {"Supported", "Contradicted", "NeedsReview"}:
            raise ValueError("invalid_gold_status")
        judged.append(label["expected_status"] == index[identity]["status"])
    if judged:
        result.update(status="evaluated_assessment_only", assessment_accuracy=sum(judged) / len(judged), evaluated_comparisons=len(judged))
    return result


def build(manifest_path, output, config=None, reviews_path=None, comparisons_path=None, gold_path=None,
          narrative_candidates_path=None):
    manifest_path, output = Path(manifest_path).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError("output_exists_choose_new_run_directory")
    config = config or {}
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".corporate-run-", dir=output.parent))
    summary = {"pipeline_version": "corporate-graph-1.0", "status": "failed", "errors": [],
               "started_at_utc": datetime.now(timezone.utc).isoformat(), "manifest_path": str(manifest_path)}
    try:
        write_json(staging / "config_snapshot.json", config)
        write_json(staging / "manifest_snapshot.json", load_json(manifest_path))
        claims, documents, inventory, sources, missing = prepare(manifest_path, config)
        reviews = load_json(reviews_path) if reviews_path else {"record_events": [], "comparison_events": []}
        if not isinstance(reviews, dict):
            raise ValueError("review_file_must_be_object")
        finite_numbers(reviews)
        if reviews_path and reviews.get("schema_version") != "corporate-graph-review-1.0":
            raise ValueError("unknown_review_version")
        record_events = event_index(reviews.get("record_events", []), "record_id")
        comparison_events = event_index(reviews.get("comparison_events", []), "comparison_id")
        explicit = load_json(comparisons_path)["comparisons"] if comparisons_path else []
        automatic, arithmetic_audit = arithmetic_candidates(claims, config.get("arithmetic_rules", []))
        comparisons = candidates(claims, explicit + automatic,
                                 auto=config.get("auto_metric_candidates", True))
        index = {c["record_id"]: c for c in claims}
        if any(i not in index for row in comparisons for i in row["record_ids"]):
            raise ValueError("comparison_refers_to_unknown_or_blocked_record")
        if set(record_events) - set(index) or set(comparison_events) - {r["comparison_id"] for r in comparisons}:
            raise ValueError("review_refers_to_unknown_input")
        findings = [assess(row, index, record_events, comparison_events,
                           require_source_basis=config.get("require_source_basis_review", False)) for row in comparisons]
        graph = new_graph()
        for source in sources:
            add_source_artifact(graph, source)
        record_audit = []
        for claim in claims:
            reasons = record_review(claim, record_events)
            claim["review_status"] = "reviewed" if not reasons else ("rejected" if "record_rejected" in reasons else "pending_human_review")
            claim["period_type_verified"] = not reasons
            claim["reporting_boundary_verified"] = not reasons
            node = add_claim(graph, claim)
            if claim["report_type"] == "Financial":
                graph.add((node, RDF.type, ESG.FinancialDisclosure))
            graph.add((node, ESG.corporateRecordJson, Literal(json.dumps(claim["raw_record"], ensure_ascii=False, sort_keys=True))))
            graph.add((node, ESG.inputDigest, Literal(claim["input_digest"])))
            graph.add((node, ESG.restatementStatus, Literal(claim["raw_record"]["restatement"]["status"])))
            period_node = uri("corporate-period", claim["record_id"])
            graph.add((node, ESG.hasObservationContext, period_node))
            graph.add((period_node, RDF.type, ESG.Period))
            for field, value in claim["raw_record"]["period"].items():
                if value is not None:
                    graph.add((period_node, ESG[field], Literal(value)))
            graph.add((uri("report", claim["report_id"]), ESG.corporateDocumentJson,
                       Literal(json.dumps(claim["raw_document"], ensure_ascii=False, sort_keys=True))))
            for ev in claim["evidence"]:
                graph.add((uri("evidence", ev["evidence_id"]), ESG.locatorContextJson,
                           Literal(json.dumps(ev, ensure_ascii=False, sort_keys=True))))
                for category, relation in (("headers", ESG.hasHeader), ("footnotes", ESG.hasFootnote)):
                    for position, locator in enumerate(ev[category]):
                        locator_node = uri("corporate-locator", digest([ev["evidence_id"], category, position]))
                        graph.add((uri("evidence", ev["evidence_id"]), relation, locator_node))
                        graph.add((locator_node, RDF.type, ESG.SourceLocator))
                        graph.add((locator_node, ESG.fromSourceArtifact, uri("source", ev["source_id"])))
                        graph.add((locator_node, ESG.sourcePage, Literal(locator["physical_page"])))
                        graph.add((locator_node, ESG.originalText, Literal(locator["text"])))
                        graph.add((locator_node, ESG.locatorContextJson, Literal(json.dumps(locator, ensure_ascii=False, sort_keys=True))))
            event = record_events.get(claim["record_id"], {})
            eligible_review = human_event(event) and event.get("input_digest") == claim["input_digest"] and event.get("decision") == "accept"
            record_audit.append({"record_id": claim["record_id"], "input_digest": claim["input_digest"],
                                 "source_locator": "passed_mechanical",
                                 **{layer: "reviewed" if eligible_review and event.get("checks", {}).get(layer) is True else "pending_review" for layer in LAYERS},
                                 "status": "accepted" if not reasons else ("rejected" if "record_rejected" in reasons else "NeedsReview"), "reasons": reasons})
        for finding in findings:
            add_finding(graph, finding)
            graph.add((uri("finding", finding["finding_id"]), ESG.comparisonAuditJson,
                       Literal(json.dumps(finding, ensure_ascii=False, sort_keys=True))))
        narrative_candidates = load_json(narrative_candidates_path) if narrative_candidates_path else None
        narrative_count = (attach_annual_narratives(graph, narrative_candidates, claims, sources)
                           if narrative_candidates is not None else 0)
        conforms, _, shacl_report = shacl_validate(graph, shacl_graph=Graph().parse(ROOT / "kg" / "shapes.ttl", format="turtle"), allow_warnings=True)
        if not conforms:
            raise ValueError("SHACL_failed:" + str(shacl_report))
        evaluation_report = evaluation(findings, load_json(gold_path) if gold_path else None)
        assessment_coverage = [{"record_id": claim["record_id"],
            "comparison_ids": [f["comparison_id"] for f in findings if claim["record_id"] in f["record_ids"]],
            "status": "compared" if any(claim["record_id"] in f["record_ids"] for f in findings) else "unassessed",
            "note": "Only configured numeric relations are assessed; narrative truth is not inferred."} for claim in claims]
        template = review_template(claims, comparisons)
        if config.get("require_source_basis_review", False):
            for event in template["comparison_events"]:
                event.update(source_basis_checked=False, source_basis_note=None)
        for name, value in {"normalized_records": claims, "source_documents": documents,
                            "inventory": {"files": inventory, "missing_expected_reports": missing},
                            "record_validation": record_audit, "findings": findings,
                            "review_template": template,
                            "review_snapshot": reviews, "comparisons": {"comparisons": comparisons},
                            "arithmetic_coverage": arithmetic_audit,
                            "assessment_coverage": assessment_coverage,
                            "graph": project_json(graph), "evaluation": evaluation_report}.items():
            write_json(staging / (name + ".json"), value)
        if narrative_candidates is not None:
            write_json(staging / "narrative_candidates.json", narrative_candidates)
        graph.serialize(destination=str(staging / "graph.ttl"), format="turtle")
        (staging / "shacl_report.txt").write_text(str(shacl_report), encoding="utf-8")
        rows = "".join("<tr><td>" + "</td><td>".join(html.escape(str(x)) for x in
                       (f["comparison_id"], ", ".join(f["record_ids"]), f["status"], f["summary"])) + "</td></tr>" for f in findings)
        source_paths = {s["source_id"]: s["path"] for s in sources}
        evidence_html = []
        for claim in claims:
            links = " ".join('<a href="' + html.escape(Path(source_paths[ev["source_id"]]).as_uri() + "#page=" + str(ev["physical_page"]), quote=True)
                             + '">PDF page ' + str(ev["physical_page"]) + '</a>' for ev in claim["evidence"])
            evidence_html.append("<details><summary>" + html.escape(claim["record_id"]) + "</summary>" + links +
                                 "<pre>" + html.escape(json.dumps(claim["raw_record"], ensure_ascii=False, indent=2)) + "</pre></details>")
        (staging / "report.html").write_text("<!doctype html><meta charset='utf-8'><title>Corporate comparison review</title>"
            "<h1>Đối chiếu bằng chứng</h1><p>Supported chỉ áp dụng cho phép kiểm tra cụ thể. Không gắn nhãn greenwashing.</p>"
            "<table border='1'><tr><th>ID</th><th>Records</th><th>Status</th><th>Reason</th></tr>" + rows + "</table><h2>Evidence</h2>" + "".join(evidence_html), encoding="utf-8")
        partial = bool(not claims or missing or any(i["status"] != "loaded" for i in inventory))
        summary.update(status="partial" if partial else "completed", records=len(claims), comparisons=len(findings),
                       narrative_candidates=narrative_count,
                       findings_by_status=dict(Counter(f["status"] for f in findings)),
                       records_pending_review=sum(bool(r["reasons"]) for r in record_audit),
                       manifest_sha256=sha256(manifest_path), missing_expected_reports=len(missing), shacl_conforms=True,
                       evaluation_status=evaluation_report["status"],
                       errors=[{"document_id": i["document_id"], "errors": i["errors"]} for i in inventory if i["errors"]])
    except (ValueError, OSError, KeyError, TypeError) as exc:
        summary["errors"].append({"error_type": type(exc).__name__, "message": str(exc)})
    summary["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    write_json(staging / "run_manifest.json", summary)
    os.replace(staging, output)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "data/config/corporate_bsr_demo.json")
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--comparisons", type=Path)
    parser.add_argument("--gold", type=Path)
    parser.add_argument("--narrative-candidates", type=Path,
                        help="Validated review-only annual-report policy/governance proposals")
    args = parser.parse_args(argv)
    try:
        result = build(args.manifest, args.output_dir, load_json(args.config), args.reviews, args.comparisons,
                       args.gold, args.narrative_candidates)
    except (ValueError, OSError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return {"completed": 0, "partial": 2, "failed": 1}[result["status"]]


if __name__ == "__main__":
    raise SystemExit(main())
