"""Build a versioned, source-bound cross-report candidate delivery.

The config carries reviewed-by-Codex candidate selection, never human approval.
Every numeric quote, PDF hash, page, year header and unit is checked again when
building. The original handoff and the 68-page 2025 PDF remain untouched.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from decimal import Decimal, InvalidOperation
import json
import os
from pathlib import Path
import shutil
import tempfile

import fitz

from handoff.bsr_extract_2023_2025_v1.validate import (
    HERE as CONTRACT, load_json, sha256, validate_handoff, validate_manifest,
)
from kg.corporate_assessment import proposal
from tools.corporate_extract_alignment import ROOT, digest, write_json


def _page_word(page, quote):
    matches = [word for word in page.get_text("words") if word[4].strip() == quote]
    if len(matches) != 1:
        raise ValueError(f"numeric_quote_not_unique_on_page:{quote}:{len(matches)}")
    return matches[0]


def _source_context(page, case):
    text = page.get_text()
    label = ("Lợi nhuận sau thuế đạt" if case["esg_report_year"] == 2025
             else "Lợi nhuận sau thuế hợp nhất")
    for expected in (case["esg_original_value"], case["esg_original_unit"], label):
        if expected not in text:
            raise ValueError("source_context_missing:" + case["case_id"] + ":" + expected)
    if case["esg_year_basis"] == "explicit_quote" and f"Năm {case['observation_year']}" not in text:
        raise ValueError("explicit_year_missing:" + case["case_id"])
    start_marker = ("Năm 2025" if case["esg_report_year"] == 2025 else
                    "STT" if case["esg_report_year"] == 2024 else
                    "BÁO CÁO THƯỜNG NIÊN BSR 2023")
    start = text.find(start_marker)
    if start < 0:
        raise ValueError("section_start_missing:" + case["case_id"])
    end = text.find("Nghiên cứu", start)
    if end < 0:
        end = text.find("GRI 201-1", start)
    context = text[start:end if end > start else None]
    if not all(value in context for value in (case["esg_original_value"], label,
                                               case["esg_original_unit"])):
        raise ValueError("bounded_context_missing_association:" + case["case_id"])
    return label, context


def _year_header(page, case, word):
    if case["esg_year_basis"] != "table_header":
        return []
    year = str(case["observation_year"])
    # The year header must be directly above the numeric cell in its column.
    candidates = [item for item in page.get_text("words") if item[4] == year
                  and item[3] < word[1] and abs((item[0] + item[2] - word[0] - word[2]) / 2) < 22]
    if len(candidates) != 1:
        raise ValueError(f"year_header_not_unique_in_column:{case['case_id']}:{len(candidates)}")
    header = candidates[0]
    return [{"role": "year", "text": "Năm " + year, "physical_page": case["esg_page"],
             "row": 0, "column": case["esg_column"], "bbox": list(header[:4])}]


def _esg_record(case, source, pdf):
    if sha256(pdf) != source["sha256"]:
        raise ValueError("source_pdf_sha256_mismatch:" + case["case_id"])
    document = fitz.open(pdf)
    if len(document) != source["page_count"] or not 1 <= case["esg_page"] <= len(document):
        raise ValueError("source_page_count_or_locator_mismatch:" + case["case_id"])
    page = document[case["esg_page"] - 1]
    label, context = _source_context(page, case)
    word = _page_word(page, case["esg_original_value"])
    headers = _year_header(page, case, word)
    headers.extend([
        {"role": "unit", "text": case["esg_original_unit"],
         "physical_page": case["esg_page"], "row": case["esg_row"],
         "column": 3 if case["esg_row"] is not None else None, "bbox": None},
        {"role": "row_label", "text": label, "physical_page": case["esg_page"],
         "row": case["esg_row"], "column": 2 if case["esg_row"] is not None else None,
         "bbox": None}])
    try:
        parsed = Decimal(case["esg_original_value"].replace(".", "").replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError("invalid_original_numeric_value:" + case["case_id"]) from exc
    if parsed * Decimal(1_000_000_000) != Decimal(case["esg_normalized_value"]):
        raise ValueError("unit_scale_inconsistent:" + case["case_id"])
    record_id = "record_" + digest([source["sha256"], case["case_id"],
                                     case["esg_page"], case["esg_original_value"]])
    evidence_id = "handoff_evidence_" + digest([record_id, source["sha256"],
                                                 case["esg_page"], list(word[:4])])
    obs = case["observation_year"] if case["esg_year_basis"] != "unknown" else None
    table_id = ("candidate_table_" + digest([source["sha256"], case["esg_page"], label])[:24]
                if case["esg_row"] is not None else None)
    return {
        "record_id": record_id, "dimension": "G", "record_type": "measurement",
        "topic": "economic_performance", "metric_id": None,
        "metric_label": label, "metric_definition": None,
        "statement": {"original_quote": case["esg_original_value"],
                      "interpretation": "Candidate consolidated net profit after tax; comparability unreviewed.",
                      "assertion_kind": "reported_result"},
        "value": {"status": "available", "original_value": case["esg_original_value"],
                  "original_unit": case["esg_original_unit"], "original_scale": "1 tỷ = 1000000000",
                  "normalized_value": case["esg_normalized_value"], "normalized_unit": "VND",
                  "normalization_factor": 1_000_000_000,
                  "normalization_note": "Vietnamese decimal/grouping parsed from source table; multiplied by 1e9 once."},
        "period": {"observation_year": obs,
                   "observation_start": f"{obs}-01-01" if obs else None,
                   "observation_end": f"{obs}-12-31" if obs else None,
                   "measurement_date": None, "period_type": "annual" if obs else "unknown",
                   "year_basis": case["esg_year_basis"], "baseline_year": None,
                   "target_deadline": None},
        "boundary": {"reporting_entity": None, "consolidation": "Consolidated",
                     "scope": None, "population": None, "counting_method": None,
                     "calculation_method": None, "verified": False},
        "restatement": {"status": "unknown", "note": None},
        "evidence": [{"evidence_id": evidence_id, "source_sha256": source["sha256"],
                      "physical_page": case["esg_page"], "printed_page": None,
                      "exact_quote": case["esg_original_value"], "context_text": context,
                      "section": "Giá trị kinh tế trực tiếp được tạo ra" if case["esg_report_year"] == 2025
                                 else "Giá trị kinh tế tạo ra",
                      "element_id": None, "char_start": None, "char_end": None,
                      "bbox": list(word[:4]), "table_id": table_id,
                      "row": case["esg_row"], "column": case["esg_column"],
                      "headers": headers, "footnotes": []}],
        "quality": {"extraction_method": "chatgpt_assisted",
                    "parser_name": "PyMuPDF word locator; source PDF text verified",
                    "model_id": None, "prompt_version": "cross-report-pilot-config-1.0",
                    "uncertainty": ["candidate_metric_mapping_unreviewed",
                                    "reporting_boundary_unverified",
                                    "restatement_unverified", "footnotes_not_exhaustively_reviewed"]
                                   + (["observation_year_unconfirmed"] if obs is None else []),
                    "review_status": "pending_human_review", "reviewer": None,
                    "reviewed_at_utc": None, "review_basis": None},
        "comparison_group_id": None,
    }


def build(source_manifest, config_path, output):
    source_manifest, config_path, output = map(lambda value: Path(value).resolve(),
                                               (source_manifest, config_path, output))
    if output.exists():
        raise ValueError("output_exists_choose_new_directory")
    config = load_json(config_path)
    if config["schema_version"] != "cross-report-pilot-config-1.0":
        raise ValueError("unknown_config_version")
    if sha256(source_manifest) != config["source_manifest_sha256"]:
        raise ValueError("source_manifest_stale")
    if output.is_relative_to(source_manifest.parent) or source_manifest.parent.is_relative_to(output):
        raise ValueError("output_must_be_separate_from_input")
    manifest, errors = validate_manifest(source_manifest, load_json(CONTRACT / "manifest_schema.json"))
    if errors:
        raise ValueError("; ".join(errors[:5]))
    canonical = config["additional_pdf"]
    canonical_path = (ROOT / canonical["path"]).resolve()
    if not canonical_path.is_file() or sha256(canonical_path) != canonical["sha256"]:
        raise ValueError("canonical_pdf_missing_or_hash_mismatch")
    if len(fitz.open(canonical_path)) != canonical["page_count"]:
        raise ValueError("canonical_pdf_page_count_mismatch")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".cross-report-pilot-", dir=output.parent))
    try:
        shutil.copytree(source_manifest.parent, staging, dirs_exist_ok=True)
        shutil.copy2(canonical_path, staging / "pdf" / canonical["file_name"])
        revised = deepcopy(manifest)
        files = {row["document_id"]: row for row in revised["files"] if row["status"] != "unavailable"}
        sources = {}
        documents = {}
        for row in files.values():
            raw = load_json(staging / row["json_path"])
            documents[row["document_id"]] = raw
            sources[raw["document"]["source"]["sha256"]] = (row, raw)
        legacy_2025 = next(raw for row, raw in sources.values()
                           if row["report_type"] == "ESG" and row["report_year"] == 2025)
        new_doc_id = "report_" + canonical["sha256"]
        new_path = "json/" + canonical["sha256"] + ".json"
        new_document = deepcopy(legacy_2025["document"])
        new_document.update(document_id=new_doc_id, report_year=canonical["report_year"],
                            reporting_period_start="2025-01-01", reporting_period_end="2025-12-31")
        new_document["source"] = {"source_id": canonical["source_id"],
                                  "file_name": canonical["file_name"], "url": canonical["url"],
                                  "downloaded_at_utc": None, "sha256": canonical["sha256"],
                                  "page_count": canonical["page_count"],
                                  "page_system": "physical_pdf_page_1_based"}
        canonical_raw = {"schema_version": "corporate-extract-1.0", "document": new_document,
                         "coverage": {"status": "partial", "scope_description":
                                      "Only the nominated economic-performance page was inspected for this cross-report pilot; this is not full ESG coverage.",
                                      "search_status": "partial_search", "pages_checked": [106],
                                      "pages_unreadable": [], "topics_searched": ["economic_performance"],
                                      "search_outcomes": [{"topic": "economic_performance", "status": "found",
                                                           "pages": [106], "reason": "Selected candidate page only; human semantic review pending."}]},
                         "records": [], "issue_log": []}
        pair_rows, review_rows, seen_ids = [], [], {r["record_id"] for raw in documents.values()
                                                   for r in raw["records"]}
        touched = set()
        for case in config["cases"]:
            source_hash = case["esg_source_sha256"]
            if source_hash == canonical["sha256"]:
                esg_raw, esg_row, esg_pdf = canonical_raw, None, staging / "pdf" / canonical["file_name"]
            else:
                esg_row, esg_raw = sources[source_hash]
                if esg_row["report_type"] != "ESG" or esg_row["report_year"] != case["esg_report_year"]:
                    raise ValueError("wrong_esg_source:" + case["case_id"])
                esg_pdf = staging / esg_row["pdf_path"]
            esg = _esg_record(case, esg_raw["document"]["source"], esg_pdf)
            if esg["record_id"] in seen_ids:
                raise ValueError("duplicate_candidate_record_id:" + esg["record_id"])
            seen_ids.add(esg["record_id"])
            esg_raw["records"].append(esg)
            if esg_row is not None:
                esg_raw["coverage"]["topics_searched"] = sorted(set(esg_raw["coverage"]["topics_searched"])
                                                               | {"economic_performance"})
                esg_raw["coverage"]["search_outcomes"].append({
                    "topic": "economic_performance", "status": "found",
                    "pages": [case["esg_page"]],
                    "reason": "Selected source page; this does not establish complete economic-performance extraction."})
                touched.add(esg_row["document_id"])
            financial = [(row, raw, record) for row, raw in sources.values()
                         if row["report_type"] == "Financial" and row["financial_scope"] == "Consolidated"
                         and row["report_year"] == case["financial_report_year"]
                         for record in raw["records"] if record["record_id"] == case["financial_record_id"]]
            if len(financial) != 1:
                raise ValueError("financial_record_not_unique:" + case["case_id"])
            fin_row, fin_raw, fin = financial[0]
            if (fin["value"]["status"] != "available" or fin["period"]["observation_year"] !=
                    case["observation_year"] or fin["evidence"][0]["physical_page"] not in (9, 11)):
                raise ValueError("financial_year_value_or_locator_mismatch:" + case["case_id"])
            for record in (esg, fin):
                record["metric_id"] = config["metric_id"]
                record["metric_definition"] = config["metric_definition"]
                record["comparison_group_id"] = case["case_id"]
            if "candidate_cross_report_mapping_unreviewed" not in fin["quality"]["uncertainty"]:
                fin["quality"]["uncertainty"].append("candidate_cross_report_mapping_unreviewed")
            touched.add(fin_row["document_id"])
            comparison = proposal([esg["record_id"], fin["record_id"]])
            comparison.update(candidate_status="pending_human_review",
                              candidate_basis="Selected consolidated profit candidates; PDF cells verified mechanically; semantic equivalence, period, boundary and restatement pending review",
                              case_id=case["case_id"])
            pair_rows.append(comparison)
            review_rows.append({"case_id": case["case_id"], "comparison_id": comparison["comparison_id"],
                                "record_ids": comparison["record_ids"],
                                "esg": {"record_id": esg["record_id"],
                                        "pdf_path": "pdf/" + esg_pdf.name,
                                        "source_sha256": source_hash, "physical_page": case["esg_page"],
                                        "quote": esg["evidence"][0]["exact_quote"],
                                        "context": esg["evidence"][0]["context_text"],
                                        "bbox": esg["evidence"][0]["bbox"],
                                        "observation_year": esg["period"]["observation_year"],
                                        "proposed_year": case["observation_year"],
                                        "year_basis": esg["period"]["year_basis"],
                                        "original_unit": esg["value"]["original_unit"],
                                        "normalized_value_vnd": esg["value"]["normalized_value"]},
                                "financial": {"record_id": fin["record_id"],
                                              "pdf_path": fin_row["pdf_path"],
                                              "source_sha256": fin_raw["document"]["source"]["sha256"],
                                              "physical_page": fin["evidence"][0]["physical_page"],
                                              "quote": fin["evidence"][0]["exact_quote"],
                                              "context": fin["evidence"][0]["context_text"],
                                              "normalized_value_vnd": fin["value"]["normalized_value"],
                                              "year_basis": fin["period"]["year_basis"]},
                                "mechanical_delta_vnd": esg["value"]["normalized_value"] - fin["value"]["normalized_value"],
                                "suggested_rounding_tolerance_vnd": case["recommended_rounding_tolerance_vnd"],
                                "suggested_tolerance_is_approved": False,
                                "technical_checks": {"pdf_hash": "passed", "quote_on_page": "passed",
                                                     "value_scale": "passed", "table_year_header":
                                                     "passed" if case["esg_year_basis"] == "table_header"
                                                     else "needs_review"},
                                "semantic_checks": {"metric_equivalence": "pending", "entity_boundary": "pending",
                                                    "observation_year": "pending" if esg["period"]["observation_year"] is None else "candidate_only",
                                                    "restatement": "pending", "rounding_tolerance": "pending"},
                                "review": {"decision": "pending", "reviewer": None,
                                           "reviewed_at_utc": None, "notes": case["year_note"]}})
        if len({item["comparison_id"] for item in pair_rows}) != len(pair_rows):
            raise ValueError("duplicate_comparison_id")
        for row in revised["files"]:
            if row["document_id"] in touched:
                target = staging / row["json_path"]
                write_json(target, documents[row["document_id"]])
                row["json_sha256"] = sha256(target)
        write_json(staging / new_path, canonical_raw)
        revised["files"].append({"document_id": new_doc_id, "report_year": canonical["report_year"],
                                 "report_type": "ESG", "financial_scope": None,
                                 "pdf_path": "pdf/" + canonical["file_name"],
                                 "pdf_sha256": canonical["sha256"], "json_path": new_path,
                                 "json_sha256": sha256(staging / new_path), "status": "partial",
                                 "reason": "Canonical 134-page pilot candidate only; semantic and human review pending."})
        revised["batch_id"] = "cross_report_" + digest([sha256(source_manifest), sha256(config_path)])[:24]
        write_json(staging / "manifest.json", revised)
        pair_pack = {"schema_version": "cross-report-pilot-pairs-1.0",
                     "source_manifest_sha256": sha256(staging / "manifest.json"),
                     "status": "pending_human_review", "comparisons": pair_rows}
        write_json(staging / "notes" / "cross_report_comparisons.json", pair_pack)
        write_json(staging / "notes" / "cross_report_review_pack.json", {
            "schema_version": "cross-report-pilot-review-1.0", "status": "pending_human_review",
            "source_manifest_sha256": sha256(staging / "manifest.json"),
            "statement": "AI-assisted candidate selection; no decision is human-adjudicated or gold.",
            "cases": review_rows})
        write_json(staging / "notes" / "cross_report_lineage.json", {
            "schema_version": "cross-report-pilot-lineage-1.0",
            "source_manifest": str(source_manifest),
            "source_manifest_sha256": sha256(source_manifest),
            "config_path": str(config_path), "config_sha256": sha256(config_path),
            "canonical_2025_pdf_sha256": canonical["sha256"],
            "legacy_2025_pdf_sha256": legacy_2025["document"]["source"]["sha256"],
            "legacy_2025_page_mapping": "not_assumed",
            "human_adjudication": "pending"})
        _, errors = validate_manifest(staging / "manifest.json", load_json(CONTRACT / "manifest_schema.json"))
        if errors:
            raise ValueError("manifest_validation_failed:" + "; ".join(errors[:5]))
        schema = load_json(CONTRACT / "schema.json")
        for row in revised["files"]:
            if row["status"] != "unavailable":
                _, errors = validate_handoff(staging / row["json_path"], schema, staging / "pdf")
                if errors:
                    raise ValueError("handoff_validation_failed:" + "; ".join(errors[:5]))
        os.replace(staging, output)
        return {"status": "built_pending_human_review", "output": str(output),
                "source_documents": len(revised["files"]), "comparison_candidates": len(pair_rows),
                "canonical_2025_pages": canonical["page_count"]}
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = build(args.source_manifest, args.config, args.output)
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(json.dumps({"status": "failed", "reason": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
