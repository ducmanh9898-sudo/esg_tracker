"""Structural and mechanical evidence validation; semantic review stays separate."""
from __future__ import annotations

from collections import defaultdict

from jsonschema import Draft202012Validator

from .source_identity import ROOT, file_digest, inside_root, read_json, checked_source


def records_with_paths(batch):
    for dimension in ("environment", "social", "governance"):
        for topic, payload in batch.get(dimension, {}).items():
            for index, record in enumerate(payload.get("records", [])):
                yield f"/{dimension}/{topic}/records/{index}", dimension, topic, record


def _verified_human_review(record, source_sha256):
    info = record.get("human_review")
    if not isinstance(info, dict):
        return False
    try:
        pack_path = inside_root(info["candidate_pack_path"])
        if file_digest(pack_path) != info["candidate_pack_sha256"]:
            return False
        pack = read_json(pack_path)
        candidate = next(c for c in pack["candidates"] if c["candidate_id"] == info["candidate_id"])
        if candidate.get("record_id") != record["record_id"] or candidate["source_sha256"] != source_sha256:
            return False
        history = read_json(inside_root(info["decision_history_path"]))
        event = next(e for e in reversed(history["events"]) if e["candidate_id"] == info["candidate_id"])
        if (event["decision_sha256"] != info["decision_sha256"] or
                event["status"] != info["decision_status"] or
                event["status"] not in {"accepted", "corrected"} or
                event["reviewer"] != info["reviewer"] or
                event["reviewed_at_utc"] != info["reviewed_at_utc"] or
                event["source_sha256"] != source_sha256):
            return False
        return all(record.get(key) == value for key, value in event.get("corrected_fields", {}).items()
                   if key not in {"header_spans", "context_spans", "dimension", "topic"})
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        return False


def check_batch(batch, registry_path, *, allow_partial=False):
    schema = read_json(ROOT / "schemas/extract-esg-handoff-v2.json")
    errors = [f"schema:{list(e.absolute_path)}:{e.message}"
              for e in Draft202012Validator(schema).iter_errors(batch)]
    if errors:
        return {"ok": False, "mechanical_errors": errors, "semantic_review": [],
                "record_count": 0}
    doc = batch["document"]
    source = checked_source(registry_path, doc["source_id"])
    for field in ("company_id", "report_year", "report_type", "page_count", "page_system"):
        if doc[field] != source[field]:
            errors.append("document_source_" + field + "_mismatch")
    if doc["source_sha256"] != source["sha256"]:
        errors.append("document_source_hash_mismatch")
    if doc["source_pdf_path"] != source["path"] or doc["source_file"] != source["path"].split("/")[-1]:
        errors.append("document_source_path_mismatch")
    chunks_path = inside_root(doc["canonical_chunks_path"])
    if not chunks_path.is_file() or file_digest(chunks_path) != doc["canonical_chunks_sha256"]:
        errors.append("canonical_chunks_hash_mismatch")
        return {"ok": False, "mechanical_errors": errors, "semantic_review": [],
                "record_count": 0}
    artifact = read_json(chunks_path)
    if artifact.get("source_id") != source["source_id"] or artifact.get("source_sha256") != source["sha256"]:
        errors.append("canonical_chunks_source_mismatch")
    chunks = {c["chunk_id"]: c for c in artifact["chunks"]}
    if len(chunks) != len(artifact["chunks"]):
        errors.append("duplicate_chunk_id")
    if batch["coverage"]["status"] != "complete" and not allow_partial:
        errors.append("batch_not_complete")
    for index, outcome in enumerate(batch["coverage"].get("search_outcomes", [])):
        if outcome["status"] == "disclosure_absence_confirmed":
            if not outcome.get("reviewer") or batch["coverage"]["status"] != "complete":
                errors.append(f"search_outcomes/{index}:absence_requires_reviewer_and_complete_coverage")
        if any(p > source["page_count"] for p in outcome.get("source_pages", [])):
            errors.append(f"search_outcomes/{index}:page_outside_pdf")
    record_bindings, evidence_bindings = {}, {}
    semantic = []
    count = 0
    for pointer, dimension, topic, record in records_with_paths(batch):
        count += 1
        identity = (dimension, topic, str(record))
        if record["record_id"] in record_bindings:
            errors.append(pointer + ":duplicate_record_id")
        else:
            record_bindings[record["record_id"]] = identity
        if record["review_status"] == "reviewed" and not _verified_human_review(record, source["sha256"]):
            errors.append(pointer + ":reviewed_requires_verifiable_human_decision")
        if record.get("observation_year") is not None:
            basis = record.get("year_basis", "unknown")
            if basis == "unknown":
                semantic.append(pointer + ":observation_year_basis_unknown")
            elif basis == "explicit_quote" and not any(str(record["observation_year"]) in ev["original_text"] for ev in record["evidence"]):
                errors.append(pointer + ":year_not_in_quote")
            elif basis == "table_header":
                ids = {ref for ev in record["evidence"] for ref in ev.get("header_evidence_ids", [])}
                headers = [ev for ev in record["evidence"] if ev["evidence_id"] in ids]
                if not headers or not any(str(record["observation_year"]) in ev["original_text"] for ev in headers):
                    errors.append(pointer + ":year_header_locator_missing_or_wrong_year")
                for value_ev in (ev for ev in record["evidence"] if ev.get("header_evidence_ids")):
                    year_headers = [ev for ev in headers if ev["evidence_id"] in value_ev["header_evidence_ids"]
                                    and str(record["observation_year"]) in ev["original_text"]]
                    if not any(ev.get("table_id") == value_ev.get("table_id") and ev.get("table_id")
                               and ev.get("column") == value_ev.get("column")
                               and isinstance(ev.get("row"), int) and isinstance(value_ev.get("row"), int)
                               and ev["row"] < value_ev["row"] for ev in year_headers):
                        errors.append(pointer + ":year_header_column_association_unverified")
        if record.get("value_status") == "available" and record.get("original_value"):
            header_ids = {ref for ev in record["evidence"] for ref in ev.get("header_evidence_ids", [])}
            if not any(record["original_value"] in ev["original_text"] for ev in record["evidence"]
                       if ev["evidence_id"] not in header_ids):
                errors.append(pointer + ":original_value_not_in_quote")
        if record.get("original_unit"):
            original_unit = record["original_unit"].lower()
            if not any(original_unit in ev["original_text"].lower() for ev in record["evidence"]):
                errors.append(pointer + ":original_unit_not_grounded")
            for value_ev in (ev for ev in record["evidence"] if ev.get("header_evidence_ids")):
                if original_unit in value_ev["original_text"].lower():
                    continue
                unit_headers = [ev for ev in record["evidence"] if ev["evidence_id"] in value_ev["header_evidence_ids"]
                                and original_unit in ev["original_text"].lower()]
                if unit_headers and not any(ev.get("table_id") == value_ev.get("table_id") and ev.get("table_id")
                                            and ev.get("column") == value_ev.get("column")
                                            and isinstance(ev.get("row"), int) and isinstance(value_ev.get("row"), int)
                                            and ev["row"] < value_ev["row"] for ev in unit_headers):
                    errors.append(pointer + ":unit_header_column_association_unverified")
        if record.get("unit") and not any(record["unit"].lower() in ev["original_text"].lower() for ev in record["evidence"]):
            semantic.append(pointer + ":unit_not_in_quote_check_header_or_context")
        if record.get("reporting_boundary_verified"):
            semantic.append(pointer + ":boundary_verification_requires_human_review")
        for evidence in record["evidence"]:
            binding = (evidence["source_id"], evidence["source_sha256"],
                       evidence["chunk_id"], evidence["char_start"], evidence["char_end"])
            old = evidence_bindings.setdefault(evidence["evidence_id"], binding)
            if old != binding:
                errors.append(pointer + ":evidence_id_conflict")
            if evidence["source_id"] != source["source_id"] or evidence["source_sha256"] != source["sha256"]:
                errors.append(pointer + ":evidence_source_mismatch")
            if any(p < 1 or p > source["page_count"] for p in evidence["source_pages"]):
                errors.append(pointer + ":page_outside_pdf")
            chunk = chunks.get(evidence["chunk_id"])
            if chunk is None:
                errors.append(pointer + ":chunk_missing")
                continue
            start, end = evidence["char_start"], evidence["char_end"]
            if start >= end or end > len(chunk["text"]) or chunk["text"][start:end] != evidence["original_text"]:
                errors.append(pointer + ":quote_span_mismatch")
                continue
            overlaps = [s for s in chunk["segments"] if s["start"] <= start and end <= s["end"]]
            if len(overlaps) != 1:
                errors.append(pointer + ":span_not_within_one_source_element_or_cell")
                continue
            seg = overlaps[0]
            if (evidence["source_pages"] != [seg["physical_page"]]
                    or evidence["element_id"] != seg["element_id"]
                    or evidence.get("table_id") != seg.get("table_id")
                    or evidence.get("row") != seg.get("row")
                    or evidence.get("column") != seg.get("column")):
                errors.append(pointer + ":locator_segment_mismatch")
            if evidence.get("alignment_status") != "exact":
                semantic.append(pointer + ":alignment_not_exact")
        if record["review_status"] != "reviewed":
            semantic.append(pointer + ":pending_human_review")
    return {"ok": not errors, "mechanical_errors": sorted(set(errors)),
            "semantic_review": sorted(set(semantic)), "record_count": count,
            "source_sha256": source["sha256"]}
