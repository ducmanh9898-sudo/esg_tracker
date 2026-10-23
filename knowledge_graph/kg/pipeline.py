"""One Graph pipeline: selected extracts -> normalized claims -> RDF -> assessments."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from jsonschema import Draft202012Validator
from pyshacl import validate as shacl_validate
from rdflib import Graph, RDF
from rdflib.namespace import SH

from kg.adapters import ROOT, adapt_curated, adapt_financial_handoff, adapt_separate_full, adapt_structured_esg, read_json
from kg.ready_rules import RULES as READY_RULES, evaluate_ready_rules
from kg.review_annotations import apply_review_annotations
from kg.source_corroboration import attach_corroborated_evidence
from kg.rdf_store import ESG, add_assessment, add_claim, add_financial, add_financial_candidate_links, add_finding, add_source_artifact, add_standard_candidates, add_standards, evidence_chain, link_cross_year, new_graph, project_json
from tools.assessment_builder import build_assessments
from tools.financial_adapter import adapt_report
from tools.report_renderer import render_report_html
from tools.rule_engine import evaluate


def _write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")


def _report_meta(entry, source):
    doc = source.get("document") or source.get("metadata") or {}
    report = dict(entry)
    report["handoff_version"] = source.get("schema_version")
    report["report_id"] = f"{entry['company_id']}:{entry['report_year']}:{entry['report_type']}:{entry['reporting_entity']}:{Path(entry['path']).name}"
    declared_source = doc.get("source_file") or (Path(str(doc["source_pdf"])).name if doc.get("source_pdf") else None)
    report["source_file"] = declared_source or Path(entry["path"]).name
    report["source_file_verified"] = bool(declared_source)
    report["source_locator"] = doc.get("source_locator")
    report["publication_date"] = doc.get("publication_date")
    source_period = doc.get("reporting_period")
    report["reporting_period_start"] = doc.get("reporting_period_start") or (source_period.get("from") if isinstance(source_period, dict) else None)
    report["reporting_period_end"] = doc.get("reporting_period_end") or (source_period.get("to") if isinstance(source_period, dict) else None)
    if isinstance(source_period, str) and "/" in source_period:
        report["reporting_period_start"], report["reporting_period_end"] = source_period.split("/", 1)
    extraction = doc.get("extraction")
    report["extraction_timestamp"] = doc.get("extraction_timestamp") or (extraction.get("timestamp") if isinstance(extraction, dict) else None)
    report["source_created_at"] = source.get("created_at")
    report["reporting_date"] = doc.get("reporting_date")
    report["period_type"] = "annual" if entry["report_type"] == "ESG" else None
    report["period_type_verified"] = bool(source_period or doc.get("reporting_period_start"))
    report["boundary_verified"] = False
    return report


def _validate_claim(record, validator):
    return [f"{list(error.absolute_path)}: {error.message}" for error in validator.iter_errors(record)]


def _validate_handoff_source(source, entry, manifest_entry, source_registry=None, allow_partial=False):
    """Validate only versioned new handoffs; legacy extracts keep their adapters."""
    schema_files = {
        "extract-esg-1.0": "extract-esg-handoff-v1.json",
        "extract-esg-2.0": "extract-esg-handoff-v2.json",
        "extract-financial-1.0": "extract-financial-handoff-v1.json",
        "extract-financial-separate-1.0": "extract-financial-handoff-v1.json",
    }
    version = source.get("schema_version")
    if version not in schema_files:
        return
    schema = read_json(ROOT / "schemas" / schema_files[version])
    errors = sorted(Draft202012Validator(schema).iter_errors(source), key=lambda error: list(map(str, error.absolute_path)))
    if errors:
        raise ValueError("Extract handoff schema: " + "; ".join(
            f"{list(error.absolute_path)}: {error.message}" for error in errors[:5]))
    if version == "extract-esg-2.0":
        if not source_registry:
            raise ValueError("Extract v2 source_registry is required")
        from kg.extract_v2_validation import check_batch
        result = check_batch(source, ROOT / source_registry, allow_partial=allow_partial)
        if not result["ok"]:
            raise ValueError("Extract v2 provenance: " + "; ".join(result["mechanical_errors"][:5]))
    document = source["document"]
    boundary = document.get("reporting_entity") if version.startswith("extract-esg-") else document.get("financial_statement_scope")
    expected = {"company_id": document["company_id"], "report_year": document["report_year"],
                "report_type": "ESG" if version.startswith("extract-esg-") else "Financial",
                "reporting_entity": boundary}
    for field, actual in expected.items():
        if entry.get(field) != actual or (manifest_entry and manifest_entry.get(field) != actual):
            raise ValueError(f"Extract handoff {field} differs from corpus config or manifest")


def _legacy(claim):
    """Data-only compatibility adapter for the existing arithmetic rule catalogue."""
    record = copy.deepcopy(claim)
    record["claim_id"] = claim["record_id"]
    record["evidence"] = [
        {**e, "source_text": e.get("original_text") or e.get("reviewed_source_text")} for e in claim["evidence"]
    ]
    return record


def _eligible_rule_records(claims):
    # Not-applicable and unknown data do not become evidence gaps merely because
    # the arithmetic catalogue happens to mention the same metric.
    return [c for c in claims if c["value_status"] in {"available", "missing"}
            and c.get("assessment_eligible", True)]


def _check_rule_context(finding, claims_by_id):
    """Prevent a strong result when metric/period/scope/unit/boundary differ."""
    selected = [claims_by_id[cid] for cid in finding["input_claim_ids"] if cid in claims_by_id]
    if len(selected) != len(finding["input_claim_ids"]):
        finding["status"] = "NeedsReview"
        finding["summary"] += " Missing input claim in normalized corpus."
        return finding
    if finding["status"] == "Contradicted":
        blockers = []
        for field in ("unit", "scope", "period_type", "baseline_id", "metric_definition"):
            values = {str(c.get(field)) for c in selected}
            if len(values) > 1 or (field in {"unit", "period_type", "metric_definition"} and "None" in values):
                blockers.append(field)
        if any(c.get("period_type_verified") is not True for c in selected):
            blockers.append("period_type_unverified")
        if any(not c.get("reporting_boundary_verified") for c in selected):
            blockers.append("reporting_boundary")
        if any(c.get("review_status") != "reviewed" or
               any(not e.get("original_text") for e in c.get("evidence", [])) for c in selected):
            blockers.append("source_review")
        if blockers:
            finding["status"] = "NeedsReview"
            finding["summary"] += " Context unverified: " + ", ".join(sorted(set(blockers)))
    return finding


def _profile(path):
    profile = read_json(ROOT / path)
    required = {"profile_id", "applicable_topics", "relevant_metrics", "expected_evidence", "industry_constraints"}
    if not required.issubset(profile):
        raise ValueError("Industry profile is missing required keys")
    return profile


def _shacl_report(graph, shapes_path="kg/shapes.ttl"):
    shapes = Graph().parse(ROOT / shapes_path, format="turtle")
    conforms, report_graph, _ = shacl_validate(graph, shacl_graph=shapes, inference="none", abort_on_first=False)
    rows = []
    for result in report_graph.subjects(RDF.type, SH.ValidationResult):
        rows.append({
            "focus_node": str(report_graph.value(result, SH.focusNode)),
            "severity": str(report_graph.value(result, SH.resultSeverity)).split("#")[-1],
            "message": str(report_graph.value(result, SH.resultMessage) or ""),
            "source_shape": str(report_graph.value(result, SH.sourceShape) or ""),
        })
    return {"conforms": bool(conforms), "results": rows,
            "quality_warnings": sum(r["severity"] == "Warning" for r in rows),
            "structural_violations": sum(r["severity"] == "Violation" for r in rows)}


def _financial_records(entry, source):
    if entry["adapter"] == "bsr_financial":
        records, note = adapt_report(ROOT / entry["path"])
        for record in records:
            record["extract_file"] = Path(entry["path"]).name
            doc = source.get("document") or source.get("metadata") or {}
            record["source_file"] = doc.get("source_file") or Path(str(doc.get("source_pdf", ""))).name
            # A value labelled with a prior year belongs to that observation
            # period while the source_report_id stays the containing report.
            years = re.findall(r"(?<!\d)(20\d{2})(?!\d)", record["item"]["item_id"])
            if years and "observation_year" not in record:
                record["observation_year"] = int(years[-1])
        return records, {"source_note": note, "candidate_only": False}
    if entry["adapter"] in {"bsr_separate_full", "financial_handoff"}:
        result = (adapt_separate_full(source, entry["path"]) if entry["adapter"] == "bsr_separate_full"
                  else adapt_financial_handoff(source, entry["path"]))
        records = result.pop("financial_records")
        if source.get("schema_version") == "extract-financial-1.0":
            validator = Draft202012Validator(read_json(ROOT / "schemas" / "financial-candidate-v1.json"))
            for record in records:
                errors = _validate_claim(record, validator)
                if errors:
                    raise ValueError("Normalized financial candidate: " + "; ".join(errors))
        # The raw OCR remains in the immutable source JSON. Inventory points to it
        # without duplicating all 44 pages and 2,104 unaligned OCR groups.
        for key in ("unmapped_monetary_group_records", "unmapped_numeric_occurrence_records", "ocr_pages"):
            result.pop(key, None)
        result.pop("records", None)
        return records, {"candidate_only": True, **result,
                         "structured_records": len(source.get("structured_key_metrics", [])),
                         "measurement_candidates": len(records),
                         "raw_source_path": entry["path"],
                         "ocr_pages_pointer": "/pages"}
    return [], {"candidate_only": True, "reason": "No adapter for this financial format"}


def financial_comparability(esg_claim, financial_record):
    """Guard an ESG-financial candidate; never infer ESG financial impact."""
    reasons = []
    if esg_claim["company_id"] != financial_record["company_id"]:
        reasons.append("company_mismatch")
    boundary = financial_record.get("scope", {})
    if not esg_claim.get("reporting_boundary_verified") or boundary.get("verification_status") != "verified":
        reasons.append("boundary_unverified")
    elif esg_claim.get("reporting_boundary") != boundary.get("scope_id"):
        reasons.append("boundary_mismatch")
    if esg_claim.get("observation_year") != financial_record.get("observation_year"):
        reasons.append("measurement_period_mismatch")
    esg_date = esg_claim.get("measurement_date")
    financial_date = financial_record.get("measurement_date", {}).get("value")
    if not esg_date or not financial_date:
        reasons.append("measurement_date_unverified")
    elif esg_date != financial_date:
        reasons.append("measurement_date_mismatch")
    if financial_record.get("employee_definition", {}).get("verification_status") != "verified":
        reasons.append("metric_definition_unverified")
    if financial_record.get("review_reasons"):
        reasons.extend(financial_record["review_reasons"])
    return {"comparable": not reasons, "status": "candidate_only" if reasons else "comparable",
            "reasons": sorted(set(reasons))}


def _separate_financial_review(financial):
    """Locate possible same-metric amounts without equating reporting boundaries."""
    aliases = {
        "FIN_OPERATING_CASH_FLOW": {"operating_cash_flow", "operating_cash_flow_vnd"},
        "FIN_PAT": {"profit_after_tax", "profit_after_tax_vnd"},
        "FIN_REVENUE": {"revenue", "revenue_vnd"},
        "FIN_TOTAL_ASSETS": {"total_assets", "total_assets_vnd"},
    }
    separate = [r for r in financial if r.get("record_type") == "financial_candidate"
                and r.get("scope", {}).get("scope_id") == "separate_parent"]
    previous = [r for r in financial if r not in separate]
    rows = []
    for source in separate:
        if source.get("observation_year") is None or source.get("value") is None:
            continue
        metric = source.get("item", {}).get("item_id")
        for peer in previous:
            if (peer.get("company_id") != source.get("company_id")
                    or peer.get("value") is None
                    or (peer.get("observation_year") or peer.get("report_year")) != source.get("observation_year")
                    or peer.get("item", {}).get("item_id", "").rsplit(".", 1)[-1] not in aliases.get(metric, set())):
                continue
            rows.append({
                "separate_disclosure_id": source["disclosure_id"],
                "other_disclosure_id": peer["disclosure_id"],
                "observation_year": source["observation_year"],
                "metric_alias_candidate": metric,
                "separate_value": source.get("value"), "other_value": peer.get("value"),
                "numeric_values_differ": source.get("value") != peer.get("value"),
                "separate_scope": source["scope"]["scope_id"],
                "other_scope": peer.get("scope", {}).get("scope_id"),
                "status": "NeedsReview", "comparison_permitted": False,
                "blockers": ["reporting_boundary_mismatch_or_unverified", "metric_definition_unverified",
                             "separate_source_unreviewed"],
                "interpretation": "Different reporting entities may legitimately report different amounts; no ESG finding follows.",
            })
    return rows


def _profile_coverage(profile, claims, inventory):
    rows = []
    for report in inventory["selected"]:
        if report["report_type"] != "ESG" or report["status"] != "loaded":
            continue
        selected = [c for c in claims if c["company_id"] == report["company_id"] and c["report_year"] == report["report_year"]]
        present = {c["metric_id"] for c in selected}
        rows.append({"company_id": report["company_id"], "report_year": report["report_year"],
                     "coverage": report["coverage"], "present_profile_metrics": sorted(present.intersection(profile["relevant_metrics"])),
                     "unobserved_profile_metrics": sorted(set(profile["relevant_metrics"]) - present),
                     "finding_policy": "No DisclosureGap: report completeness and metric applicability are not verified."})
    return rows


def build(output_dir, config_path=None):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config_path = Path(config_path) if config_path else ROOT / "data" / "config" / "corpus_config.json"
    config = read_json(config_path)
    profile = _profile(config["industry_profile"])
    schema = read_json(ROOT / "schemas" / "graph-input-v2.json")
    validator = Draft202012Validator(schema)
    selection = {company: read_json(ROOT / path) for company, path in config.get("selection_files", {}).items()}
    inventory = {"schema_version": "1.0", "profile_id": profile["profile_id"],
                 "selected": [], "errors": [], "unresolved": config.get("unresolved", []),
                 "generated_at_utc": datetime.now(timezone.utc).isoformat()}
    manifest_path = config.get("extract_manifest")
    manifest_files = {}
    if manifest_path:
        manifest = read_json(ROOT / manifest_path)
        for file in manifest.get("files", []):
            path = file["path"]
            if path in manifest_files:
                raise ValueError("Duplicate path in Extract batch manifest: " + path)
            manifest_files[path] = file
        inventory["extract_batch"] = {"manifest": manifest_path,
                                      "batch_id": manifest.get("batch_id"),
                                      "files": len(manifest_files)}
    selected_paths = {entry["path"] for entry in config["reports"]}
    overlap_paths = {path for entry in config["reports"] for path in entry.get("overlaps", [])}
    source_files = sorted(list((ROOT / "data" / "extract" / "esg").glob("*.json"))
                          + list((ROOT / "data" / "extract" / "financial").glob("*.json")))
    inventory["source_inventory"] = [
        {"path": p.relative_to(ROOT).as_posix(),
         "selection_status": "selected" if p.relative_to(ROOT).as_posix() in selected_paths else
             "overlap_retained" if p.relative_to(ROOT).as_posix() in overlap_paths else "unselected_review"}
        for p in source_files
    ]
    inventory["supporting_sources"] = {
        "pdf_page_json": [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / "data" / "source" / "page_text").glob("*.json"))],
        "chunk_manifests": [],
        "role": "Preserved source-page/OCR context; legacy chunks duplicate these pages and are not Graph input.",
    }
    claims, financial = [], []
    for entry in config["reports"]:
        path = ROOT / entry["path"]
        item = {key: entry[key] for key in ("company_id", "report_year", "report_type", "reporting_entity", "path", "coverage", "reason")}
        item["overlaps"] = entry.get("overlaps", [])
        try:
            if manifest_path:
                listed = manifest_files.get(entry["path"])
                if listed is None:
                    raise ValueError("Selected Extract file absent from batch manifest")
                if hashlib.sha256(path.read_bytes()).hexdigest() != listed.get("sha256"):
                    raise ValueError("Extract file SHA-256 differs from batch manifest")
            source = read_json(path)
            _validate_handoff_source(source, entry, manifest_files.get(entry["path"]),
                                     config.get("source_registry"), config.get("allow_partial_extract", False))
            report = _report_meta(entry, source)
            if source.get("schema_version") == "extract-esg-2.0":
                item["extract_coverage"] = source["coverage"]
            item["source_file"] = report["source_file"]
            item["reporting_period_start"] = report["reporting_period_start"]
            item["reporting_period_end"] = report["reporting_period_end"]
            item["selection_key"] = [entry["company_id"], report["reporting_period_start"] or entry["report_year"],
                                      report["reporting_period_end"] or entry["report_year"],
                                      entry["report_type"], entry["reporting_entity"]]
            item["publication_date"] = report["publication_date"]
            item["extraction_timestamp"] = report["extraction_timestamp"]
            item["source_created_at"] = report["source_created_at"]
            item["reporting_date"] = report["reporting_date"]
            if entry["report_type"] == "Financial":
                records, meta = _financial_records(entry, source)
                financial.extend(records)
                item["financial_record_count"] = len(records)
                item["adapter_report"] = meta
            elif entry["adapter"] == "curated_selection":
                rows = adapt_curated(report, source, selection[entry["company_id"]])
                claims.extend(rows)
                item["claim_count"] = len(rows)
            elif entry["adapter"] == "structured_esg":
                rows = adapt_structured_esg(report, source)
                claims.extend(rows)
                item["claim_count"] = len(rows)
            else:
                raise ValueError("Unknown adapter: " + entry["adapter"])
            item["status"] = "loaded"
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            item["status"] = "technical_error"
            inventory["errors"].append({"path": entry["path"], "error_type": type(exc).__name__, "message": str(exc)})
        inventory["selected"].append(item)

    loaded_esg = {(item["company_id"], item["report_year"]) for item in inventory["selected"]
                  if item["report_type"] == "ESG" and item["status"] == "loaded"}
    loaded_financial = {(item["company_id"], item["report_year"]) for item in inventory["selected"]
                        if item["report_type"] == "Financial" and item["status"] == "loaded"}
    inventory["gaps"] = []
    for company, year in sorted(loaded_esg):
        if (company, year) not in loaded_financial:
            inventory["gaps"].append({"company_id": company, "report_year": year,
                                      "type": "financial_counterpart_absent",
                                      "effect": "ESG assessments continue; financial connectivity is not run."})
    for item in inventory["selected"]:
        if item["report_type"] == "ESG" and item["coverage"].startswith("partial"):
            inventory["gaps"].append({"company_id": item["company_id"], "report_year": item["report_year"],
                                      "type": "partial_esg_extract", "path": item["path"]})

    # RDF URIs are derived from IDs; duplicates must never merge silently.
    seen_claim_ids, seen_evidence_ids = set(), {}
    for claim in claims:
        if claim["record_id"] in seen_claim_ids:
            raise ValueError("duplicate_claim_id:" + claim["record_id"])
        seen_claim_ids.add(claim["record_id"])
        for evidence in claim.get("evidence", []):
            key = evidence["evidence_id"]
            binding = (evidence.get("source_id"), evidence.get("source_sha256"),
                       evidence.get("source_file"), tuple(evidence.get("source_pages", [])),
                       evidence.get("chunk_id"), evidence.get("char_start"), evidence.get("char_end"),
                       evidence.get("original_text"))
            if key in seen_evidence_ids and seen_evidence_ids[key] != binding:
                raise ValueError("evidence_id_conflict:" + key)
            seen_evidence_ids[key] = binding
    accepted, review, rejected = [], [], []
    for claim in claims:
        errors = _validate_claim(claim, validator)
        if errors:
            rejected.append({"record_id": claim.get("record_id"), "errors": errors})
            continue
        accepted.append(claim)
        expected = profile.get("expected_evidence", {}).get(claim["claim_type"], [])
        for field in expected:
            if not all(e.get(field) for e in claim.get("evidence", [])):
                claim["uncertainty"].append("expected_evidence_" + field + "_missing")
        needs_value_review = claim["value_status"] in {"missing", "ambiguous", "unknown"}
        if claim["uncertainty"] or claim.get("review_status") != "reviewed" or needs_value_review:
            review.append({"record_id": claim["record_id"], "reasons": claim["uncertainty"] +
                           (["value_" + claim["value_status"]] if needs_value_review else [])})

    ready_config_path = config.get("ready_rule_aliases")
    review_path = config.get("graph_review_annotations")
    reviewed_claims, reviewed_aliases, annotation_audit = apply_review_annotations(
        accepted, read_json(ROOT / ready_config_path) if ready_config_path else {"aliases": []},
        ROOT / review_path if review_path else None, ROOT)
    source_provenance_audit = None
    if config.get("source_corroboration"):
        reviewed_claims, source_provenance_audit = attach_corroborated_evidence(
            reviewed_claims, ROOT / config["source_corroboration"], ROOT)
    graph = new_graph()
    if config.get("source_registry"):
        registry = read_json(ROOT / config["source_registry"])
        for source in registry.get("sources", []):
            if source["source_id"] in {e.get("source_id") for c in accepted for e in c.get("evidence", [])}:
                add_source_artifact(graph, {**source, "kind": "official_pdf_binary",
                                            "availability": "present", "declared_filename": Path(source["path"]).name,
                                            "official_url": source.get("url")})
    if source_provenance_audit:
        for source in source_provenance_audit["sources"]:
            add_source_artifact(graph, source)
    for claim in reviewed_claims:
        add_claim(graph, claim)
    for record in financial:
        add_financial(graph, record)
    financial_candidates = []
    for claim in accepted:
        if claim["metric_id"] != "employees_total":
            continue
        for record in financial:
            if record["company_id"] == claim["company_id"] and record["item"]["item_id"] == "workforce.total":
                financial_candidates.append({"claim_id": claim["record_id"], "financial_disclosure_id": record["disclosure_id"],
                                             **financial_comparability(claim, record)})
    financial_reconciliation = _separate_financial_review(financial)
    crosswalk = read_json(ROOT / "data" / "config" / "standards_crosswalk_sample.json")
    standard_links = add_standards(graph, accepted, crosswalk)
    standard_candidate_links = financial_candidate_links = 0
    if config.get("standard_candidate_references"):
        reference_candidates = read_json(ROOT / config["standard_candidate_references"])
        standard_candidate_links = add_standard_candidates(graph, accepted, reference_candidates)
        financial_candidate_links = add_financial_candidate_links(graph, financial_candidates)
    temporal = link_cross_year(graph, accepted)

    demo_findings = []
    by_company = defaultdict(list)
    for claim in accepted:
        by_company[claim["company_id"]].append(claim)
    for company, rule_file in config.get("rule_sets", {}).items():
        rules = read_json(ROOT / rule_file)
        candidates = evaluate([_legacy(c) for c in _eligible_rule_records(by_company[company])], rules)
        index = {c["record_id"]: c for c in by_company[company]}
        for candidate in candidates:
            demo_findings.append(_check_rule_context(candidate, index))
    ready_findings, rule_evaluations = (evaluate_ready_rules(reviewed_claims, reviewed_aliases)
                                        if ready_config_path else ([], []))
    # The primary graph and assessments contain only catalogue rules. All
    # legacy demo findings, including R06, remain unchanged in the audit file.
    findings = ready_findings
    coverage = _profile_coverage(profile, accepted, inventory)
    for finding in findings:
        add_finding(graph, finding)

    projection = project_json(graph)
    assessments = build_assessments([_legacy(c) for c in reviewed_claims], findings, projection)
    claims_by_id = {c["record_id"]: c for c in accepted}
    for summary in (assessments["company_assessments"]["company_year_assessments"]
                    + assessments["company_assessments"]["company_multiyear_assessments"]):
        summary["temporal_patterns"] = [
            p for p in temporal
            if claims_by_id[p["from_claim_id"]]["company_id"] == summary["company_id"]
            and (summary["assessment_level"] != "company_year"
                 or summary["report_years"][0] in {
                     claims_by_id[p["from_claim_id"]]["report_year"],
                     claims_by_id[p["to_claim_id"]]["report_year"]})
        ]
    assessed_ids = {cid for finding in findings for cid in finding["input_claim_ids"]}
    review_ids = {cid for finding in findings if finding["status"] == "NeedsReview"
                  for cid in finding["input_claim_ids"]}
    strong_ids = {cid for finding in findings if finding["status"] in {"Supported", "Contradicted"}
                  for cid in finding["input_claim_ids"]}
    # Explicitly record unassessed coverage without calling it a passed rule.
    assessments["unassessed_claims"] = [
        {"claim_id": c["record_id"], "company_id": c["company_id"],
         "status": "NeedsReview", "reason": "No applicable reviewed business rule produced a finding."}
        for c in accepted if c["record_id"] not in assessed_ids
    ]
    for item in assessments["claim_assessments"]:
        add_assessment(graph, item)
    for item in assessments["company_assessments"]["company_year_assessments"] + assessments["company_assessments"]["company_multiyear_assessments"]:
        add_assessment(graph, item)
    projection = project_json(graph)
    quality = _shacl_report(graph)
    business = _shacl_report(graph, "kg/business_shapes.ttl")
    chain = evidence_chain(graph)
    linked = {row[0] for row in chain}
    missing_chains = [f["finding_id"] for f in findings if f["finding_id"] not in linked]

    _write(output_dir / "corpus_inventory.json", inventory)
    _write(output_dir / "normalized_claims.json", accepted)
    _write(output_dir / "input_review.json", {"review": review, "rejected": rejected})
    _write(output_dir / "financial_records.json", financial)
    _write(output_dir / "financial_candidates.json", financial_candidates)
    _write(output_dir / "financial_reconciliation.json", financial_reconciliation)
    _write(output_dir / "profile_coverage.json", coverage)
    _write(output_dir / "findings.json", findings)
    _write(output_dir / "demo_findings.json", demo_findings)
    _write(output_dir / "ready_findings.json", ready_findings)
    _write(output_dir / "rule_evaluations.json", rule_evaluations)
    _write(output_dir / "annotation_audit.json", annotation_audit)
    if source_provenance_audit:
        _write(output_dir / "source_provenance_audit.json", source_provenance_audit)
    _write(output_dir / "temporal_comparisons.json", temporal)
    _write(output_dir / "claim_assessments.json", assessments["claim_assessments"])
    _write(output_dir / "company_assessments.json", assessments["company_assessments"])
    _write(output_dir / "unassessed_claims.json", assessments["unassessed_claims"])
    _write(output_dir / "shacl_quality_report.json", quality)
    _write(output_dir / "shacl_business_report.json", business)
    _write(output_dir / "evidence_chains.json", chain)
    if source_provenance_audit:
        reviewed_by_id = {claim["record_id"]: claim for claim in reviewed_claims}
        source_chains = []
        for finding in findings:
            for claim_id in finding["input_claim_ids"]:
                claim = reviewed_by_id[claim_id]
                for evidence in claim["evidence"]:
                    source_chains.append({
                        "finding_id": finding["finding_id"], "claim_id": claim_id,
                        "report_id": claim["report_id"], "evidence_id": evidence["evidence_id"],
                        "source_id": evidence.get("source_id"), "source_file": evidence["source_file"],
                        "source_sha256": evidence.get("source_sha256"),
                        "source_pages": evidence.get("source_pages", []),
                        "page_system": evidence.get("page_system"),
                        "json_pointer": evidence.get("json_pointer"),
                        "source_text": evidence.get("original_text") or evidence.get("reviewed_source_text"),
                        "corroborates_evidence_id": evidence.get("corroborates_evidence_id"),
                    })
        _write(output_dir / "evidence_chain_sources.json", source_chains)
    _write(output_dir / "graph.json", projection)
    graph.serialize(destination=output_dir / "graph.ttl", format="turtle")
    (output_dir / "graph_demo.html").write_text(
        render_report_html(projection, findings, assessments, demo_findings=demo_findings), encoding="utf-8")
    evaluation_outcomes = Counter(item["outcome"] for item in rule_evaluations)
    summary = {
        "schema_version": "1.0", "source_config": str(config_path),
        "claims_accepted": len(accepted), "claims_rejected": len(rejected),
        "claims_needing_review": len(review), "claims_rule_assessed": len(assessed_ids),
        "claims_rule_assessed_meaning": "Unique claim IDs in primary findings, including NeedsReview; not a verified conclusion count.",
        "claims_in_primary_findings": len(assessed_ids),
        "claims_with_needs_review_findings": len(review_ids),
        "claims_with_strong_conclusions": len(strong_ids),
        "claims_unassessed": len(assessments["unassessed_claims"]),
        "findings_by_status": dict(Counter(f["status"] for f in findings)),
        "enabled_ready_rules": list(READY_RULES) if ready_config_path else [],
        "enabled_demo_rules": [],
        "demo_rules_audit": sorted({rule["id"] for path in config.get("rule_sets", {}).values()
                                     for rule in read_json(ROOT / path)}),
        "demo_findings_audit_count": len(demo_findings),
        "demo_findings_audit_by_status": dict(Counter(f["status"] for f in demo_findings)),
        "ready_findings_count": len(ready_findings),
        "graph_review_annotations": review_path,
        "annotation_audit_counts": annotation_audit["counts"],
        "source_corroboration_evidence_count": len(source_provenance_audit["attached_evidence"]) if source_provenance_audit else 0,
        "source_binary_equivalence_verified": source_provenance_audit["whole_document_equivalence_verified"] if source_provenance_audit else None,
        "rule_evaluation_count": len(rule_evaluations),
        "rule_evaluations_with_candidates": sum(item["candidate_count"] > 0 for item in rule_evaluations),
        "rule_evaluations_without_candidates": sum(item["candidate_count"] == 0 for item in rule_evaluations),
        "rule_evaluations_by_outcome": dict(evaluation_outcomes),
        "companies": dict(Counter(c["company_id"] for c in accepted)),
        "financial_records": len(financial), "financial_candidates": len(financial_candidates),
        "financial_separate_measurement_candidates": sum(r.get("record_type") == "financial_candidate" for r in financial),
        "financial_duplicate_ids": len(financial) - len({r["disclosure_id"] for r in financial}),
        "financial_scope_review_candidates": len(financial_reconciliation),
        "standard_links": standard_links,
        "standard_candidate_links": standard_candidate_links,
        "financial_candidate_links": financial_candidate_links,
        "temporal_candidates": len(temporal), "shacl_quality": quality,
        "shacl_business": business,
        "missing_evidence_chains": missing_chains,
        "file_errors": inventory["errors"],
        "build_status": ("partial" if inventory["errors"] or rejected or any(
            item.get("extract_coverage", {}).get("status") != "complete"
            for item in inventory["selected"] if item.get("extract_coverage")) else "complete"),
        "risk_score": None,
    }
    _write(output_dir / "summary.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Build the RDF ESG knowledge graph")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--config", type=Path)
    args = parser.parse_args(argv)
    summary = build(args.output_dir, args.config)
    print(json.dumps({k: summary[k] for k in ("claims_accepted", "claims_rejected", "claims_needing_review", "claims_rule_assessed", "findings_by_status", "companies", "financial_records", "file_errors")}, ensure_ascii=False))
    if summary["build_status"] != "complete":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
