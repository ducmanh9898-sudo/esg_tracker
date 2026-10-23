"""Versioned, source-preserving refinement of corporate-extract-1.0 deliveries.

The technical quarantine is deliberately narrow. It does not assert that a
candidate is a code: it prevents a likely code cell from being used as an
available monetary measurement until a person checks the source table.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import unicodedata

from handoff.bsr_extract_2023_2025_v1.validate import (
    HERE as CONTRACT, load_json, sha256, validate_handoff,
    validate_manifest,
)
from kg.corporate_table_context import table_row_number, table_rows_compatible


ROOT = Path(__file__).resolve().parents[1]
LAYERS = ("source_quote", "value", "association", "semantic_context")
EDITABLE = {"metric_id", "metric_definition", "metric_label", "statement", "value",
            "period", "boundary", "restatement", "evidence", "comparison_group_id"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".alignment-json-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def checked_delivery(manifest_path):
    manifest_path = Path(manifest_path).resolve()
    manifest, errors = validate_manifest(manifest_path, load_json(CONTRACT / "manifest_schema.json"))
    if errors:
        raise ValueError("; ".join(errors[:8]))
    schema = load_json(CONTRACT / "schema.json")
    documents = []
    seen_records = set()
    for row in manifest["files"]:
        if row["status"] == "unavailable":
            continue
        path = (manifest_path.parent / row["json_path"]).resolve()
        pdf = (manifest_path.parent / row["pdf_path"]).resolve()
        if not path.is_relative_to(manifest_path.parent) or not pdf.is_relative_to(manifest_path.parent):
            raise ValueError("path_outside_delivery")
        raw, errors = validate_handoff(path, schema, pdf.parent)
        if errors:
            raise ValueError("; ".join(errors[:8]))
        doc = raw["document"]
        if (doc["document_id"], doc["report_year"], doc["report_type"],
                doc["financial_scope"], doc["source"]["sha256"]) != (
                row["document_id"], row["report_year"], row["report_type"],
                row["financial_scope"], row["pdf_sha256"]):
            raise ValueError("manifest_document_identity_mismatch:" + row["document_id"])
        for record in raw["records"]:
            if record["record_id"] in seen_records:
                raise ValueError("duplicate_record_id_across_files:" + record["record_id"])
            seen_records.add(record["record_id"])
        documents.append((row, raw))
    return manifest_path, manifest, documents


def code_column_suspects(document):
    """Find code-like cells with a same-row amount in a later year column."""
    if document["document"]["report_type"] != "Financial":
        return []
    by_row = defaultdict(list)
    for record in document["records"]:
        for ev in record["evidence"]:
            if ev["table_id"] is not None and ev["row"] is not None and ev["column"] is not None:
                by_row[(ev["table_id"], ev["physical_page"], ev["row"])].append((record, ev))
    suspects = []
    for record in document["records"]:
        value, period = record["value"], record["period"]
        if (record["record_type"] != "financial_measurement" or value["status"] != "available"
                or period["observation_year"] is not None
                or not re.fullmatch(r"\d{2,3}", (value["original_value"] or "").strip())):
            continue
        for ev in record["evidence"]:
            col = ev["column"]
            if not (ev["table_id"] and ev["row"] is not None and isinstance(col, int) and col <= 3):
                continue
            if any(h["role"] == "year" and h["column"] == col and
                   re.search(r"(?:19|20)\d{2}|số\s+(?:cuối|đầu)\s+năm|current year|prior year|năm nay|năm trước",
                             h["text"].casefold()) for h in ev["headers"]):
                continue
            peers = [other for other, other_ev in by_row[(ev["table_id"], ev["physical_page"], ev["row"])]
                     if other["record_id"] != record["record_id"] and other_ev["column"] > col
                     and other["value"]["status"] == "available"
                     and other["period"]["observation_year"] is not None]
            if peers:
                suspects.append({"record_id": record["record_id"], "source_page": ev["physical_page"],
                                 "table_id": ev["table_id"], "row": ev["row"], "column": col,
                                 "original_value": value["original_value"],
                                 "same_row_amount_record_ids": sorted(p["record_id"] for p in peers)})
                break
    return suspects


def code_column_watchlist(document):
    """Broader signal for human review; insufficient for automatic quarantine."""
    if document["document"]["report_type"] != "Financial":
        return []
    found = []
    for record in document["records"]:
        value = record["value"]
        if (value["status"] != "available" or record["period"]["observation_year"] is not None
                or not re.fullmatch(r"\d{2,3}", (value["original_value"] or "").strip())):
            continue
        for ev in record["evidence"]:
            if ev["table_id"] and isinstance(ev["column"], int) and ev["column"] <= 3:
                found.append({"record_id": record["record_id"], "physical_page": ev["physical_page"],
                              "column": ev["column"], "original_value": value["original_value"]})
                break
    return found


def quarantine(record):
    value = record["value"]
    if "possible_table_code_column" in record["quality"]["uncertainty"]:
        return
    if record["quality"]["review_status"] != "pending_human_review":
        raise ValueError("cannot_quarantine_previously_reviewed_record:" + record["record_id"])
    value.update(status="ambiguous", original_unit=None, original_scale=None,
                 normalized_value=None, normalized_unit=None, normalization_factor=None,
                 normalization_note="Possible table code column; amount withheld pending human source review.")
    record["quality"]["uncertainty"] = sorted(set(record["quality"]["uncertainty"] +
                                                  ["possible_table_code_column", "year_amount_association_unreviewed"]))
    record["quality"].update(review_status="pending_human_review", reviewer=None,
                             reviewed_at_utc=None, review_basis=None)


def review_candidates(documents, limit=50):
    """A fixed-size review queue, not an exhaustive gold set or validated pairs."""
    buckets = defaultdict(list)
    for row, raw in documents:
        suspects = {s["record_id"] for s in code_column_suspects(raw)}
        watchlist = {s["record_id"] for s in code_column_watchlist(raw)}
        for record in raw["records"]:
            ev = record["evidence"][0]
            score = (10 if record["record_id"] in suspects else
                     5 if record["record_id"] in watchlist else 0)
            score += 7 if record["value"]["status"] == "available" else 0
            score += 3 if ev["table_id"] else 0
            score += 2 if record["record_type"] in {"policy", "governance_evidence", "target"} else 0
            score += 1 if record["period"]["year_basis"] != "unknown" else 0
            key = (row["report_year"], row["report_type"], row["financial_scope"],
                   record["dimension"] if row["report_type"] == "ESG" else "X")
            buckets[key].append((score, row, raw, record))
    for bucket in buckets.values():
        bucket.sort(key=lambda t: (-t[0], t[3]["record_id"]))
    selected = []
    # Give narrative claim, target, policy and governance evidence a place in
    # the review pack even though numeric table cells score higher.
    for year in sorted({key[0] for key in buckets}):
        for kind in ("claim", "target", "policy", "governance_evidence"):
            choices = [(key, index, candidate) for key, bucket in buckets.items()
                       if key[0] == year and key[1] == "ESG"
                       for index, candidate in enumerate(bucket) if candidate[3]["record_type"] == kind]
            if choices and len(selected) < limit:
                key, index, _ = min(choices, key=lambda item: (-item[2][0], item[2][3]["record_id"]))
                _, row, raw, record = buckets[key].pop(index)
                selected.append((row, raw, record))
    # Round robin keeps all years/report types/dimensions visible in the pilot.
    while len(selected) < limit and any(buckets.values()):
        for key in sorted(buckets, key=str):
            if buckets[key] and len(selected) < limit:
                _, row, raw, record = buckets[key].pop(0)
                selected.append((row, raw, record))
    result = []
    for row, raw, record in selected:
        source = raw["document"]["source"]
        selected_suspects = {s["record_id"] for s in code_column_suspects(raw)}
        selected_watchlist = {s["record_id"] for s in code_column_watchlist(raw)}
        result.append({"record_id": record["record_id"], "input_digest": digest(record),
                       "document_id": row["document_id"], "report_year": row["report_year"],
                       "report_type": row["report_type"], "financial_scope": row["financial_scope"],
                       "dimension": record["dimension"], "record_type": record["record_type"],
                       "source_sha256": source["sha256"], "pdf_path": row["pdf_path"],
                       "physical_pages": sorted({ev["physical_page"] for ev in record["evidence"]}),
                       "quote": record["statement"]["original_quote"],
                       "context": [ev["context_text"] for ev in record["evidence"]],
                       "evidence": deepcopy(record["evidence"]),
                       "headers": [h for ev in record["evidence"] for h in ev["headers"]],
                       "parser_name": record["quality"]["parser_name"],
                       "extraction_method": record["quality"]["extraction_method"],
                       "original_review_status": record["quality"]["review_status"],
                       "technical_flag": ("quarantine_candidate" if record["record_id"] in selected_suspects else
                                          "code_column_watchlist" if record["record_id"] in selected_watchlist else None),
                       "technical_effect": ("aligned_value_becomes_ambiguous_pending_review"
                                            if record["record_id"] in selected_suspects else
                                            "audit_watchlist_only" if record["record_id"] in selected_watchlist else None),
                       "proposed": {field: deepcopy(record[field]) for field in
                                    ("metric_id", "metric_definition", "metric_label", "value", "period", "boundary")},
                       "uncertainty": record["quality"]["uncertainty"],
                       "decision": "pending", "reviewer": None, "reviewed_at_utc": None,
                       "basis": None, "checks": {layer: False for layer in LAYERS},
                       "corrections": {}, "notes": None})
    return result


def make_review_pack(manifest_path, output, limit=50):
    manifest_path, manifest, documents = checked_delivery(manifest_path)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("output_exists_choose_new_path")
    queue = review_candidates(documents, limit)
    result = {"schema_version": "corporate-extract-alignment-review-1.0",
              "source_manifest_sha256": sha256(manifest_path),
              "status": "pending_adjudication", "candidate_selection": "stratified_priority_not_recall_gold",
              "records": queue}
    write_json(output, result)
    return {"review_pack": str(output), "records": len(queue), "status": "pending_adjudication"}


def make_audit(manifest_path, output):
    manifest_path, _, documents = checked_delivery(manifest_path)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("output_exists_choose_new_path")
    rows = []
    for entry, raw in documents:
        suspects = code_column_suspects(raw)
        watchlist = [s for s in code_column_watchlist(raw)
                     if s["record_id"] not in {item["record_id"] for item in suspects}]
        rows.append({"document_id": entry["document_id"], "report_year": entry["report_year"],
                     "report_type": entry["report_type"], "financial_scope": entry["financial_scope"],
                     "source_sha256": entry["pdf_sha256"], "record_count": len(raw["records"]),
                     "suspect_count": len(suspects), "suspects": suspects,
                     "additional_watchlist_count": len(watchlist), "additional_watchlist": watchlist})
    report = {"schema_version": "corporate-extract-alignment-audit-1.0",
              "source_manifest_sha256": sha256(manifest_path), "documents": rows,
              "technical_suspects": sum(row["suspect_count"] for row in rows),
              "additional_watchlist": sum(row["additional_watchlist_count"] for row in rows),
              "semantic_status": "pending_human_review"}
    write_json(output, report)
    return {"audit": str(output), "technical_suspects": report["technical_suspects"],
            "additional_watchlist": report["additional_watchlist"]}


def _label_key(label):
    folded = unicodedata.normalize("NFKD", label.casefold())
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return " ".join(re.findall(r"[a-z0-9]+", folded.replace("đ", "d")))


def make_pair_pack(manifest_path, output, limit=30, pairing="cross-type"):
    """Propose source-grounded review leads for a selected report-type relation."""
    if pairing not in {"cross-type", "same-type"}:
        raise ValueError("invalid_pairing_mode")
    manifest_path, _, documents = checked_delivery(manifest_path)
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("output_exists_choose_new_path")
    groups = defaultdict(list)
    eligible_by_type = defaultdict(int)
    report_years = [row["report_year"] for row, _ in documents]
    window = (min(report_years), max(report_years)) if report_years else None
    for row, raw in documents:
        for record in raw["records"]:
            value, period = record["value"], record["period"]
            label = _label_key(record["metric_label"])
            letters = sum(char.isalpha() for char in label)
            if (record["record_type"] not in {"measurement", "financial_measurement"}
                    or value["status"] != "available" or period["observation_year"] is None
                    or not (window[0] <= period["observation_year"] <= window[1])
                    or not value["normalized_unit"] or len(label) < 5 or letters < 4
                    or letters / len(label) < 0.55):
                continue
            eligible_by_type[row["report_type"]] += 1
            common = (raw["document"]["company_id"], label,
                      period["observation_year"], value["normalized_unit"].casefold())
            key = ((row["report_type"], row["financial_scope"], record["dimension"]) + common
                   if pairing == "same-type" else common)
            groups[key].append((row, raw, record))
    proposals = {}
    for key, group in sorted(groups.items(), key=lambda item: str(item[0])):
        group.sort(key=lambda item: (item[0]["report_year"], item[2]["record_id"]))
        by_document = defaultdict(list)
        for item in group:
            if len(by_document[item[0]["document_id"]]) < 3:
                by_document[item[0]["document_id"]].append(item)
        limited = [item for items in by_document.values() for item in items]
        added_for_label = False
        for left, right in combinations(limited[:30], 2):
            if left[0]["document_id"] == right[0]["document_id"]:
                continue
            if (left[0]["report_type"] == right[0]["report_type"]) != (pairing == "same-type"):
                continue
            # Repeated labels can belong to different parent categories.
            # Matching row numbers remain a review hint, not proof of equivalence.
            if pairing == "same-type" and not table_rows_compatible(left[2], right[2]):
                continue
            ids = sorted((left[2]["record_id"], right[2]["record_id"]))
            pair_id = "CMP-" + digest(["equal", ids])[:20]
            def side(item):
                row, raw, record = item
                return {"record_id": record["record_id"], "document_id": row["document_id"],
                        "report_type": row["report_type"], "financial_scope": row["financial_scope"],
                        "report_year": row["report_year"], "observation_year": record["period"]["observation_year"],
                        "year_basis": record["period"]["year_basis"],
                        "value": record["value"]["normalized_value"],
                        "unit": record["value"]["normalized_unit"],
                        "metric_label": record["metric_label"],
                        "source_sha256": raw["document"]["source"]["sha256"],
                        "pdf_path": row["pdf_path"],
                        "physical_pages": sorted({e["physical_page"] for e in record["evidence"]}),
                        "quotes": [e["exact_quote"] for e in record["evidence"]],
                        "table_row_number": table_row_number(record),
                        "boundary": record["boundary"], "restatement": record["restatement"]}
            proposals[pair_id] = {"comparison_id": pair_id, "record_ids": ids, "relation": "equal",
                                  "candidate_status": "pending_human_review",
                                  "candidate_basis": (
                                      "same normalized label, observation year and unit across ESG and Financial; definition, boundary and accounting relation remain unverified"
                                      if pairing == "cross-type" else
                                      "same normalized label, observation year and unit; explicit table row numbers agree where available; parent heading, definition, boundary and restatement remain unverified"),
                                  "sources": [side(left), side(right)],
                                  "review": {"decision": "pending", "reviewer": None,
                                             "reviewed_at_utc": None, "notes": None}}
            added_for_label = True
            break
        if added_for_label and len(proposals) >= limit:
            break
    status = "pending_human_review" if proposals else "no_source_grounded_pair_candidates"
    pack = {"schema_version": "corporate-extract-pair-candidates-1.1",
            "source_manifest_sha256": sha256(manifest_path), "status": status,
            "pairing_mode": pairing, "eligible_records_by_report_type": dict(eligible_by_type),
            "observation_year_window": list(window),
            "selection_basis": (
                "ESG versus Financial: exact normalized label/year/unit review leads only; zero leads does not mean disclosure absence"
                if pairing == "cross-type" else
                "within report type: normalized label/year/unit and no conflicting explicit table row numbers; diagnostic review leads only"),
            "comparisons": list(proposals.values())}
    write_json(output, pack)
    return {"pair_pack": str(output), "candidate_pairs": len(proposals),
            "pairing_mode": pairing, "status": status}


def _human_decision(item):
    if item["decision"] not in {"accept", "correct", "reject"}:
        return False
    for field in ("reviewer", "reviewed_at_utc", "basis"):
        if not isinstance(item.get(field), str) or not item[field].strip():
            raise ValueError("human_decision_missing_" + field + ":" + item["record_id"])
    try:
        parsed = datetime.fromisoformat(item["reviewed_at_utc"].replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid_review_time:" + item["record_id"]) from exc
    if parsed.utcoffset() is None:
        raise ValueError("review_time_requires_timezone:" + item["record_id"])
    if not isinstance(item.get("checks"), dict) or any(item["checks"].get(k) is not True for k in LAYERS):
        raise ValueError("human_decision_requires_four_checks:" + item["record_id"])
    return True


def decisions_index(review_path, source_hash, records):
    if review_path is None:
        return {}
    pack = load_json(Path(review_path))
    if pack.get("schema_version") != "corporate-extract-alignment-review-1.0" or pack.get("source_manifest_sha256") != source_hash:
        raise ValueError("review_pack_version_or_source_manifest_mismatch")
    indexed = {}
    for item in pack.get("records", []):
        identity = item.get("record_id")
        if identity in indexed:
            raise ValueError("duplicate_review_record_id:" + str(identity))
        if identity not in records or item.get("input_digest") != digest(records[identity]):
            raise ValueError("review_record_missing_or_stale:" + str(identity))
        decision = item.get("decision")
        if decision not in {"pending", "uncertain", "accept", "correct", "reject"}:
            raise ValueError("invalid_decision:" + str(identity))
        if decision in {"pending", "uncertain"}:
            if item.get("corrections"):
                raise ValueError("pending_decision_cannot_apply_corrections:" + identity)
        else:
            _human_decision(item)
            changes = item.get("corrections") or {}
            if decision == "correct" and not changes:
                raise ValueError("correct_requires_corrections:" + identity)
            if decision != "correct" and changes:
                raise ValueError("only_correct_may_change_fields:" + identity)
            if not isinstance(changes, dict) or set(changes) - EDITABLE:
                raise ValueError("forbidden_correction_field:" + identity)
        indexed[identity] = item
    return indexed


def _apply_decision(record, item):
    if item is None or item["decision"] in {"pending", "uncertain"}:
        return
    if item["decision"] == "correct":
        for key, value in item["corrections"].items():
            record[key] = deepcopy(value)
    status = "rejected" if item["decision"] == "reject" else "reviewed"
    record["quality"].update(review_status=status, reviewer=item["reviewer"],
                             reviewed_at_utc=item["reviewed_at_utc"], review_basis=item["basis"])
    if status == "rejected":
        record["metric_id"] = None
        record["comparison_group_id"] = None


def align(manifest_path, destination, review_path=None):
    manifest_path, manifest, documents = checked_delivery(manifest_path)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("output_exists_choose_new_directory")
    if destination.is_relative_to(manifest_path.parent) or manifest_path.parent.is_relative_to(destination):
        raise ValueError("destination_must_be_separate_from_source_delivery")
    source_hash = sha256(manifest_path)
    original = {record["record_id"]: record for _, raw in documents for record in raw["records"]}
    decisions = decisions_index(review_path, source_hash, original)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".extract-alignment-", dir=destination.parent))
    audit = {"schema_version": "corporate-extract-alignment-audit-1.0",
             "source_manifest_sha256": source_hash, "source_manifest_path": str(manifest_path),
             "technical_quarantine": [], "technical_watchlist": [], "human_decisions": [],
             "status": "pending_adjudication"}
    try:
        shutil.copytree(manifest_path.parent, staging, dirs_exist_ok=True)
        aligned_records = {}
        for row, raw in documents:
            updated = deepcopy(raw)
            suspects = {s["record_id"]: s for s in code_column_suspects(raw)}
            audit["technical_watchlist"].extend(s for s in code_column_watchlist(raw)
                                                if s["record_id"] not in suspects)
            for record in updated["records"]:
                identity = record["record_id"]
                if identity in suspects:
                    quarantine(record)
                    audit["technical_quarantine"].append(suspects[identity])
                    updated["issue_log"].append({"issue_id": "ALIGN-CODE-" + digest(identity)[:20],
                        "code": "POSSIBLE_TABLE_CODE_COLUMN",
                        "message": "A code-like cell has a same-row amount in a later year column; source review required.",
                        "source_pages": [suspects[identity]["source_page"]], "record_id": identity,
                        "status": "needs_review"})
                item = decisions.get(identity)
                if item and item["decision"] not in {"pending", "uncertain"}:
                    # Decisions are bound to the original record digest, and the
                    # technical quarantine is visible in the lineage audit.
                    _apply_decision(record, item)
                    audit["human_decisions"].append({"record_id": identity, "decision": item["decision"],
                                                       "reviewer": item["reviewer"],
                                                       "reviewed_at_utc": item["reviewed_at_utc"]})
                aligned_records[identity] = record
            target = staging / row["json_path"]
            write_json(target, updated)
            row["json_sha256"] = sha256(target)
        manifest["batch_id"] = "aligned_" + digest([source_hash, sorted(audit["technical_quarantine"], key=lambda s: s["record_id"]),
                                                     audit["human_decisions"]])[:32]
        write_json(staging / "manifest.json", manifest)
        _, errors = validate_manifest(staging / "manifest.json", load_json(CONTRACT / "manifest_schema.json"))
        if errors:
            raise ValueError("; ".join(errors[:8]))
        schema = load_json(CONTRACT / "schema.json")
        for row in manifest["files"]:
            if row["status"] != "unavailable":
                _, errors = validate_handoff(staging / row["json_path"], schema, staging / "pdf")
                if errors:
                    raise ValueError("; ".join(errors[:8]))
        write_json(staging / "notes" / "alignment_audit.json", audit)
        queue_path = staging / "notes" / "demo_review_queue.json"
        if queue_path.exists():
            queue = load_json(queue_path)
            queue_path.rename(staging / "notes" / "upstream_demo_review_queue.json")
            for item in queue:
                record = aligned_records.get(item["record_id"])
                if record:
                    item.update(value=deepcopy(record["value"]), period=deepcopy(record["period"]),
                                metric_label=record["metric_label"],
                                review_status=record["quality"]["review_status"])
            write_json(queue_path, queue)
        upstream_report = staging / "validation" / "report.json"
        if upstream_report.exists():
            upstream_report.rename(staging / "validation" / "upstream_report.json")
        upstream_checks = staging / "validation" / "extra_checks.json"
        if upstream_checks.exists():
            upstream_checks.rename(staging / "validation" / "upstream_extra_checks.json")
        report = {"mechanical_valid": True, "complete_handoff": False,
                  "human_review_pending": len(audit["human_decisions"]) < len(original),
                  "source_manifest_sha256": source_hash,
                  "manifest_sha256": sha256(staging / "manifest.json"),
                  "records": len(original), "technical_quarantine_count": len(audit["technical_quarantine"]),
                  "technical_watchlist_count": len(audit["technical_watchlist"]),
                  "human_decision_count": len(audit["human_decisions"]),
                  "semantic_validation": "pending_human_review"}
        write_json(staging / "validation" / "report.json", report)
        os.replace(staging, destination)
        return {"destination": str(destination), **report}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def graph_review_from_extract(aligned_manifest_path, graph_run_dir, review_path, output):
    """Translate actual human Extract decisions into Graph's record review layer.

    Comparison decisions remain pending because equal metric names do not prove
    equivalent scope, restatement treatment, or relation.
    """
    aligned_manifest_path = Path(aligned_manifest_path).resolve()
    graph_run_dir = Path(graph_run_dir).resolve()
    output = Path(output).resolve()
    if output.exists():
        raise ValueError("output_exists_choose_new_path")
    audit = load_json(aligned_manifest_path.parent / "notes" / "alignment_audit.json")
    pack = load_json(Path(review_path))
    run = load_json(graph_run_dir / "run_manifest.json")
    template = load_json(graph_run_dir / "review_template.json")
    if run.get("manifest_sha256") != sha256(aligned_manifest_path):
        raise ValueError("graph_run_does_not_match_aligned_manifest")
    if (pack.get("schema_version") != "corporate-extract-alignment-review-1.0" or
            pack.get("source_manifest_sha256") != audit["source_manifest_sha256"]):
        raise ValueError("review_pack_source_mismatch")
    attested = {item["record_id"]: item for item in audit["human_decisions"]}
    decided = {}
    for item in pack["records"]:
        identity = item["record_id"]
        if identity in decided:
            raise ValueError("duplicate_review_record_id:" + identity)
        if item["decision"] in {"accept", "correct", "reject"}:
            _human_decision(item)
            confirmation = attested.get(identity)
            if confirmation is None or any(confirmation[k] != item[k] for k in ("decision", "reviewer", "reviewed_at_utc")):
                raise ValueError("review_decision_not_in_aligned_package:" + identity)
            decided[identity] = item
    if set(decided) != set(attested):
        raise ValueError("aligned_decisions_missing_from_review_pack")
    for event in template["record_events"]:
        item = decided.get(event["record_id"])
        if item is None:
            continue
        event.update(decision="reject" if item["decision"] == "reject" else "accept",
                     reviewer_kind="human", reviewer=item["reviewer"],
                     reviewed_at_utc=item["reviewed_at_utc"], basis=item["basis"],
                     checks={layer: item["checks"][layer] for layer in LAYERS})
    template_ids = {e["record_id"] for e in template["record_events"]}
    if set(decided) - template_ids:
        raise ValueError("reviewed_record_not_in_graph_run")
    write_json(output, template)
    return {"graph_review": str(output), "record_decisions": len(decided),
            "comparison_decisions": 0, "status": "comparisons_pending_human_review"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "review-pack", "pair-pack", "align", "graph-review"))
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--review", type=Path, help="Human-edited review pack (align only)")
    parser.add_argument("--graph-run", type=Path, help="Graph run directory (graph-review only)")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--pairing", choices=("cross-type", "same-type"),
                        default="cross-type", help="pair-pack only; cross-type is the BCTC versus ESG demo")
    args = parser.parse_args(argv)
    try:
        if args.command == "audit":
            result = make_audit(args.manifest, args.output)
        elif args.command == "review-pack":
            result = make_review_pack(args.manifest, args.output, args.limit)
        elif args.command == "pair-pack":
            result = make_pair_pack(args.manifest, args.output, args.limit, args.pairing)
        elif args.command == "align":
            result = align(args.manifest, args.output, args.review)
        else:
            if args.review is None or args.graph_run is None:
                raise ValueError("graph-review_requires_review_and_graph-run")
            result = graph_review_from_extract(args.manifest, args.graph_run, args.review, args.output)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
