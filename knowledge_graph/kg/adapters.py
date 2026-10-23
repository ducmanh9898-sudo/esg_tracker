"""Adapters from source extracts to the versioned Graph input contract.

Source JSON is never edited. Missing provenance stays missing and enters review.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIMENSION_KEYS = {"environment": "E", "environmental": "E", "social": "S", "governance": "G"}
PAGE_KEYS = ("source_pages", "pdf_pages", "source_pdf_pages", "pdf_page", "source_page")
SKIP_NUMERIC_KEYS = {"year", "reporting_year", "comparison_year", "page_count", "source_page_count", "pdf_page", "source_page", "confidence"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def pointer_value(document, pointer):
    value = document
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def _id(prefix, *parts):
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix}-{digest}"


def _pages(container, inherited=()):
    if isinstance(container, dict):
        for key in PAGE_KEYS:
            value = container.get(key)
            if isinstance(value, dict):
                value = value.get("pdf") or value.get("physical")
            if isinstance(value, int) and value > 0:
                return [value]
            if isinstance(value, list) and value and all(isinstance(p, int) and p > 0 for p in value):
                return value
    return list(inherited)


def _status(value, explicit=None):
    if explicit in {"available", "missing", "ambiguous", "not_applicable", "unknown"}:
        return explicit
    return "missing" if value is None else "available"


def _claim(report, pointer, *, dimension, topic, metric_id, label, value, unit=None,
           observation_year=None, pages=None, original_text=None, claim_type="measurement",
           variant=None, record_id=None, evidence_id=None, review_status="unreviewed",
           value_status=None, metric_definition=None, scope=None, uncertainty=None,
           extraction_status=None):
    source_file = report.get("source_file") or Path(report["path"]).name
    pages = list(pages or [])
    uncertainty = list(uncertainty or [])
    if not pages:
        uncertainty.append("source_pages_missing")
    if not original_text:
        uncertainty.append("original_text_missing")
    if report.get("reporting_entity") in (None, "unknown"):
        uncertainty.append("reporting_entity_unverified")
    if not report.get("source_file_verified", False):
        uncertainty.append("source_document_unverified")
    # Moving a source JSON must not mint new claim/evidence identities.
    identity_path = report.get("identity_path", report["path"])
    record_id = record_id or _id("CLM", report["company_id"], identity_path, pointer, metric_id)
    evidence_id = evidence_id or _id("EVD", identity_path, pointer, pages)
    record = {
        "schema_version": "2.0", "record_id": record_id,
        "company_id": report["company_id"], "report_id": report["report_id"],
        "report_year": report["report_year"], "report_type": report["report_type"],
        "reporting_entity": report.get("reporting_entity"),
        "reporting_period_start": report.get("reporting_period_start"),
        "reporting_period_end": report.get("reporting_period_end"),
        "publication_date": report.get("publication_date"),
        "extraction_timestamp": report.get("extraction_timestamp"),
        "observation_year": observation_year,
        "period_type": report.get("period_type"),
        "period_type_verified": report.get("period_type_verified", False),
        "dimension": dimension, "claim_type": claim_type, "topic": topic,
        "metric_id": metric_id, "metric_definition": metric_definition,
        "label": label, "value": value, "value_status": _status(value, value_status),
        "unit": unit, "scope": scope, "reporting_boundary": report.get("reporting_entity"),
        "reporting_boundary_verified": report.get("boundary_verified", False),
        "baseline_id": None, "variant": variant, "review_status": review_status,
        "uncertainty": sorted(set(uncertainty)),
        "evidence": [{"evidence_id": evidence_id, "source_file": source_file,
                      "source_extract_path": report["path"],
                      "source_pages": pages, "json_pointer": pointer,
                      "original_text": original_text, "ocr_limitations": []}],
    }
    if extraction_status is not None:
        record["extraction_status"] = extraction_status
    return record


def adapt_curated(report, source, selection):
    from tools.normalizer import evidence_id as legacy_evidence_id, stable_id as legacy_stable_id
    records = []
    source_name = Path(report["path"]).name
    for item in selection:
        if item["company_id"] != report["company_id"] or Path(item["source_path"]).name != source_name:
            continue
        pointer = item["source_pointer"]
        try:
            value = pointer_value(source, pointer)
        except (KeyError, IndexError, TypeError, ValueError):
            value = None
            status = "unknown"
        else:
            status = None
        record = _claim(
            report, pointer, dimension=item["dimension"], topic=item["topic"],
            metric_id=item["metric_id"], label=item["label"], value=value,
            unit=item.get("unit"), observation_year=item.get("observation_year"),
            pages=item.get("source_pages"), claim_type=item.get("claim_type", "measurement"),
            variant=item.get("variant"), scope=item.get("scope"),
            value_status=status, record_id=legacy_stable_id(item), evidence_id=legacy_evidence_id(item),
        )
        record["selection_id"] = item["selection_id"]
        records.append(record)
    return records


def _slug(text):
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "unnamed_metric"


def adapt_structured_esg(report, source):
    """Conservative scalar adapter: only explicit E/S/G sections and source pointers."""
    records = []

    def walk(value, tokens, dimension, inherited_pages=(), inherited_unit=None):
        if isinstance(value, list):
            for index, child in enumerate(value):
                if isinstance(child, (dict, list)):
                    walk(child, tokens + [str(index)], dimension, inherited_pages, inherited_unit)
            return
        if not isinstance(value, dict):
            return
        pages = _pages(value, inherited_pages)
        unit = value.get("unit") if isinstance(value.get("unit"), str) else inherited_unit
        pointer = "/" + "/".join(tokens)
        handoff_record = (report.get("handoff_version") in {"extract-esg-1.0", "extract-esg-2.0"} and
                          value.get("claim_type") in {"claim", "measurement", "target", "policy", "governance_statement"} and
                          bool(value.get("record_id")))
        policy_without_value = ("value" not in value and
                                value.get("claim_type") in {"policy", "governance_statement"})
        if ("value" in value and not isinstance(value["value"], (dict, list))) or policy_without_value or handoff_record:
            if report.get("handoff_version") == "extract-esg-2.0" and value.get("evidence"):
                pages = value["evidence"][0].get("source_pages") or []
            label = (value.get("metric") or value.get("label") or value.get("name")
                     or value.get("source") or value.get("category") or value.get("type")
                     or (tokens[-2] if tokens[-1].isdigit() and len(tokens) > 1 else tokens[-1]))
            handoff_v1 = report.get("handoff_version") in {"extract-esg-1.0", "extract-esg-2.0"}
            handoff_v2 = report.get("handoff_version") == "extract-esg-2.0"
            year = (value.get("observation_year") if handoff_v2 else value.get("year")) if handoff_v1 else value.get("year", value.get("reporting_year", report["report_year"]))
            if not isinstance(year, int) or isinstance(year, bool):
                year = None if handoff_v1 else report["report_year"]
            raw_value = value.get("value")
            current = _claim(
                report, pointer + ("/original_text" if policy_without_value and "original_text" in value else
                                   "/value" if "value" in value else ""),
                dimension=dimension, topic=tokens[1] if len(tokens) > 1 else tokens[0],
                metric_id=value.get("metric_id") if handoff_v1 else value.get("metric_id") or _slug(label),
                metric_definition=value.get("metric_definition") if handoff_v1 else value.get("metric_definition") or str(label), label=str(label),
                value=raw_value, unit=unit, observation_year=year, pages=pages,
                original_text=(value["evidence"][0]["original_text"] if handoff_v2 and value.get("evidence") else
                               value.get("original_text") if isinstance(value.get("original_text"), str) else None),
                claim_type=value.get("claim_type") or "measurement",
                variant=value.get("variant") or ("target" if value.get("claim_type") == "target" or "target" in pointer.lower() else "reported"),
                scope=value.get("scope") if isinstance(value.get("scope"), str) else None,
                record_id=value.get("record_id"), evidence_id=value.get("evidence_id"),
                review_status=value.get("review_status") or "unreviewed",
                value_status=value.get("value_status") or ("not_applicable" if policy_without_value else None),
                uncertainty=value.get("uncertainty") if isinstance(value.get("uncertainty"), list) else None,
                extraction_status=value.get("extraction_status"),
            )
            if "original_value" in value:
                current["source_original_value"] = value["original_value"]
            if handoff_v2:
                current["evidence"] = [{**e, "source_file": report["source_file"],
                                        "source_extract_path": report["path"],
                                        "source_locator": report.get("source_locator"),
                                        "json_pointer": pointer} for e in value["evidence"]]
                current["reporting_entity"] = value.get("reporting_entity") or report.get("reporting_entity")
                for field in ("original_unit", "original_scale", "normalization_note", "year_basis",
                              "baseline_year", "target_deadline", "population_id", "counting_method",
                              "extraction_method", "model_id", "prompt_version"):
                    current[field] = value.get(field)
                current["baseline_id"] = value.get("baseline_id")
            if handoff_v1:
                current["period_type"] = value.get("period_type")
                current["period_type_verified"] = value.get("period_type_verified") is True
                current["reporting_boundary"] = value.get("reporting_boundary")
                current["reporting_boundary_verified"] = value.get("reporting_boundary_verified") is True
                if current["claim_type"] not in {"policy", "governance_statement"} and not current["metric_id"]:
                    current["uncertainty"].append("metric_id_unknown")
                if year is None and current["claim_type"] in {"measurement", "target"}:
                    current["uncertainty"].append("observation_period_unknown")
                if current["reporting_boundary"] is None:
                    current["uncertainty"].append("claim_boundary_unknown")
                current["assessment_eligible"] = bool(
                    current["claim_type"] in {"measurement", "target"}
                    and current["metric_id"] and year is not None
                    and current["period_type"] and current["reporting_boundary_verified"]
                    and current["review_status"] == "reviewed" and (pages or handoff_v2 and current["evidence"][0]["source_pages"])
                    and current["evidence"][0]["original_text"])
                current["uncertainty"] = sorted(set(current["uncertainty"]))
            records.append(current)
            for field, variant in (("comparison_value", "comparative"), ("restated_value", "restated")):
                if field not in value or isinstance(value[field], (dict, list)):
                    continue
                other_year = value.get("comparison_year") if field == "comparison_value" else year
                if not isinstance(other_year, int):
                    date_text = value.get("comparison_date") if field == "comparison_value" else None
                    other_year = int(date_text[:4]) if isinstance(date_text, str) and re.match(r"20\d{2}", date_text) else None
                related = _claim(
                    report, pointer + "/" + field, dimension=dimension,
                    topic=tokens[1] if len(tokens) > 1 else tokens[0],
                    metric_id=_slug(label), metric_definition=str(label), label=str(label),
                    value=value[field], unit=unit, observation_year=other_year,
                    pages=pages, variant=variant,
                    scope=value.get("scope") if isinstance(value.get("scope"), str) else None,
                    uncertainty=["comparison_period_unverified"] if other_year is None else [],
                )
                related["related_record_id"] = current["record_id"]
                records.append(related)
            return
        for key, child in value.items():
            if key in PAGE_KEYS or key in SKIP_NUMERIC_KEYS or key in {"source_text", "original_text", "unit"}:
                continue
            if isinstance(child, (dict, list)):
                walk(child, tokens + [key], dimension, pages, unit)
            elif isinstance(child, (int, float)) and not isinstance(child, bool):
                # Keyed numeric disclosures occur in the PVD extracts. Their unit
                # remains unknown unless the containing object supplies one.
                year = int(key) if key.isdigit() and len(key) == 4 and 2000 <= int(key) <= 2100 else report["report_year"]
                metric_parts = [t for t in tokens[1:] if not t.isdigit()]
                metric_name = "_".join(metric_parts + ([] if year != report["report_year"] or (key.isdigit() and len(key) == 4) else [key]))
                records.append(_claim(
                    report, pointer + "/" + key, dimension=dimension,
                    topic=tokens[1] if len(tokens) > 1 else tokens[0],
                    metric_id=_slug(metric_name),
                    label=key.replace("_", " "), value=child, unit=unit,
                    observation_year=year, pages=pages,
                    variant="target" if "target" in key.lower() else ("comparative" if year < report["report_year"] else "reported"),
                ))

    for key, dimension in DIMENSION_KEYS.items():
        if key in source:
            walk(source[key], [key], dimension)
    return records


def adapt_financial_handoff(source, path, expected_scope=None):
    """Keep each structured financial observation in its declared boundary."""
    document = source.get("document", {})
    declared_scope = document.get("financial_statement_scope")
    if declared_scope not in ("Separate", "Consolidated", None):
        raise ValueError("Unknown financial_statement_scope")
    if expected_scope and declared_scope not in (None, expected_scope):
        raise ValueError(f"Financial report scope must be {expected_scope}")
    scope = declared_scope or expected_scope
    if scope is None:
        raise ValueError("Financial report scope is missing")
    scope_id = "separate_parent" if scope == "Separate" else "consolidated_group"
    candidates = source.get("structured_key_metrics", [])
    if isinstance(candidates, dict):
        candidates = list(candidates.values())
    records = []
    financial_records = []
    for index, item in enumerate(candidates):
        if not isinstance(item, dict):
            continue
        page = item.get("source_page")
        pages = item.get("source_pages") or ([page] if page is not None else [])
        metric_id = item.get("metric_code") or item.get("metric_id") or item.get("name") or item.get("metric")
        source_id = item.get("record_id")
        records.append({
            "record_type": "financial_candidate", "source_path": str(path),
            "source_record_id": source_id,
            "reporting_entity": scope_id, "source_index": index,
            "source_dimension": item.get("dimension", "X"),
            "graph_dimension": "financial_context",
            "metric_id": metric_id,
            "value": item.get("value"), "unit": item.get("unit"),
            "unit_multiplier": item.get("unit_multiplier"),
            "review_status": item.get("review_status", "unreviewed"),
            "confidence": item.get("confidence"),
            "extraction_notes": item.get("extraction_notes"),
            "source_pages": pages,
            "source_pointer": f"/structured_key_metrics/{index}",
            "measurement_period": item.get("measurement_period"),
            "publication_date": document.get("publication_date"),
            "extraction_timestamp": document.get("extraction_timestamp"),
            "source_created_at": source.get("created_at"),
        })
        observations = item.get("measurements")
        if not isinstance(observations, list) or not observations:
            if source.get("schema_version") == "extract-financial-1.0":
                raise ValueError("Versioned financial handoff requires a measurement entry; its period/value may be null")
            observations = [{"period": item.get("measurement_period") or item.get("report_year") or document.get("report_year"),
                             "value": item.get("value"), "unit": item.get("unit")}]
        for measurement_index, observation in enumerate(observations):
            if not isinstance(observation, dict):
                continue
            period = observation.get("period")
            measurement_id = observation.get("measurement_id")
            pointer = f"/structured_key_metrics/{index}/measurements/{measurement_index}" if item.get("measurements") else f"/structured_key_metrics/{index}/value"
            review_reasons = []
            if period is None:
                review_reasons.append("measurement_period_unknown")
            if source.get("schema_version") == "extract-financial-1.0" and not observation.get("period_type"):
                review_reasons.append("period_type_unknown")
            if not metric_id:
                review_reasons.append("metric_id_unknown")
            if not pages:
                review_reasons.append("source_pages_missing")
            if not item.get("claim_text"):
                review_reasons.append("original_text_missing")
            if not (item.get("source_file") or document.get("source_file")):
                review_reasons.append("source_file_missing")
            financial_records.append({
                "schema_version": "0.1", "record_type": "financial_candidate",
                "disclosure_id": (f"{document.get('document_key')}:{measurement_id}" if measurement_id else
                                  f"{source_id or f'{document.get('document_key', 'separate')}-{index}'}:{period}:{measurement_index}"),
                "source_record_id": source_id,
                "source_measurement_id": measurement_id,
                "company_id": item.get("company_id") or document.get("company_id"),
                "report_year": item.get("report_year") or document.get("report_year"),
                "source_report_id": f"{document.get('document_key') or document.get('company_id', 'unknown') + '-FS-' + str(document.get('report_year'))}:{scope}",
                "source_dimension": item.get("dimension", "X"),
                "graph_dimension": "financial_context",
                "item": {"item_id": metric_id, "label": item.get("metric_name") or metric_id,
                         "statement": "financial_context"},
                "value": observation.get("value"),
                "value_status": observation.get("value_status") or ("available" if observation.get("value") is not None else "missing"),
                "unit": observation.get("unit") or item.get("unit"),
                "unit_multiplier": observation.get("unit_multiplier", item.get("unit_multiplier")),
                "scope": {"scope_id": scope_id, "description": item.get("scope"),
                          "verification_status": "unverified"},
                "reporting_period": {"fiscal_year": period, "period_type": observation.get("period_type") if source.get("schema_version") == "extract-financial-1.0" else "annual"},
                "observation_year": period,
                "variant": "comparative" if isinstance(period, int) and period < (item.get("report_year") or document.get("report_year") or period) else "reported",
                "review_status": item.get("review_status") or "unknown",
                "review_reasons": review_reasons,
                "confidence": item.get("confidence"),
                "extraction_notes": item.get("extraction_notes"),
                "extraction_status": item.get("extraction_status"),
                "original_text": item.get("claim_text"),
                "source_file": item.get("source_file") or document.get("source_file"),
                "extract_file": str(path), "source_pointer": pointer,
                "source_pages": pages,
                "ocr_page_pointers": [f"/pages/{p-1}/text" for p in pages if isinstance(p, int) and p > 0],
                "publication_date": document.get("publication_date"),
                "extraction_timestamp": document.get("extraction_timestamp"),
                "source_created_at": source.get("created_at"),
                "reporting_date": document.get("reporting_date"),
                "assurance_status": item.get("assurance_status"),
                "ambiguity_note": item.get("ambiguity_note"),
            })
    declared = document.get("claim_count")
    ocr_pages = [
        {"page": page.get("page_number", page.get("page")),
         "text": page.get("text"), "json_pointer": f"/pages/{index}/text",
         "ocr_unverified": True}
        for index, page in enumerate(source.get("pages", [])) if isinstance(page, dict)
    ]
    return {
        "records": records,
        "financial_records": financial_records,
        "declared_claim_count": declared,
        "actual_candidate_count": len(records),
        "claim_count_difference": declared - len(records) if isinstance(declared, int) else None,
        "unmapped_monetary_groups": len(source.get("monetary_groups", [])),
        "unmapped_numeric_occurrences": len(source.get("numeric_occurrences", [])),
        "unmapped_monetary_group_records": [
            {"json_pointer": f"/monetary_groups/{i}", "status": "unmapped", "raw": value}
            for i, value in enumerate(source.get("monetary_groups", []))],
        "unmapped_numeric_occurrence_records": [
            {"json_pointer": f"/numeric_occurrences/{i}", "status": "unmapped", "raw": value}
            for i, value in enumerate(source.get("numeric_occurrences", []))],
        "ocr_pages": ocr_pages,
        "ocr_note": "pages.text is OCR source context; it is not a verified financial metric or verbatim quotation.",
    }


def adapt_separate_full(source, path):
    """Compatibility entry point for selected historical Separate reports."""
    return adapt_financial_handoff(source, path, expected_scope="Separate")
