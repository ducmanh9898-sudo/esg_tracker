"""Standalone mechanical validator for corporate-extract-1.0 deliveries.

Requires only packages in requirements.txt; imports no project modules.
Semantic accuracy and human adjudication remain separate.
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
from pathlib import Path
import sys
import unicodedata

from jsonschema import Draft202012Validator
from pypdf import PdfReader


HERE = Path(__file__).resolve().parent


def plain(text: str) -> str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD', text)
                   if not unicodedata.combining(ch)).casefold().replace('đ', 'd')


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def schema_errors(document: dict, schema: dict) -> list[str]:
    validator = Draft202012Validator(schema)
    return [f"schema/{'/'.join(map(str, error.absolute_path))}: {error.message}"
            for error in sorted(validator.iter_errors(document), key=lambda e: list(map(str, e.absolute_path)))]


def validate_handoff(path: Path, schema: dict, pdf_dir: Path | None = None) -> tuple[dict | None, list[str]]:
    errors: list[str] = []
    try:
        handoff = load_json(path)
    except (OSError, ValueError) as exc:
        return None, [f"{path}: unreadable_json: {exc}"]
    errors.extend(schema_errors(handoff, schema))
    if errors:
        return handoff, [f"{path}: {message}" for message in errors]

    document = handoff["document"]
    source = document["source"]
    page_count = source["page_count"]
    if pdf_dir is not None:
        pdf_path = pdf_dir / source["file_name"]
        if not pdf_path.is_file():
            errors.append(f"pdf_missing: {pdf_path}")
        else:
            with pdf_path.open("rb") as stream:
                pdf_signature = stream.read(5)
            if pdf_signature != b"%PDF-":
                errors.append("source_file_is_not_pdf")
            if sha256(pdf_path) != source["sha256"]:
                errors.append("source_pdf_sha256_mismatch")
            try:
                actual_pages = len(PdfReader(str(pdf_path), strict=False).pages)
                if actual_pages != page_count:
                    errors.append(f"source_page_count_mismatch: {actual_pages} != {page_count}")
            except Exception as exc:  # corrupt PDF and parser errors are delivery failures
                errors.append(f"source_pdf_unreadable: {type(exc).__name__}: {exc}")

    record_ids: set[str] = set()
    evidence_bindings: dict[str, tuple] = {}
    checked_pages = set(handoff["coverage"]["pages_checked"])
    for label, pages in (("pages_checked", checked_pages),
                         ("pages_unreadable", handoff["coverage"]["pages_unreadable"])):
        for page in pages:
            if page > page_count:
                errors.append(f"coverage/{label}: page {page} outside PDF")
    for index, outcome in enumerate(handoff["coverage"]["search_outcomes"]):
        for page in outcome["pages"]:
            if page > page_count:
                errors.append(f"coverage/search_outcomes/{index}: page {page} outside PDF")

    for index, record in enumerate(handoff["records"]):
        prefix = f"records/{index}/{record['record_id']}"
        if record["record_id"] in record_ids:
            errors.append(f"{prefix}: duplicate_record_id")
        record_ids.add(record["record_id"])
        if document["report_type"] == "Financial":
            if record["dimension"] != "X" or record["record_type"] != "financial_measurement":
                errors.append(f"{prefix}: financial_report_record_type_mismatch")
            if record["boundary"]["consolidation"] not in {document["financial_scope"], "unknown"}:
                errors.append(f"{prefix}: financial_boundary_scope_mismatch")
        elif record["dimension"] == "X" or record["record_type"] == "financial_measurement":
            errors.append(f"{prefix}: esg_report_record_type_mismatch")

        value = record["value"]
        if value["status"] == "available" and value["normalized_value"] is None:
            errors.append(f"{prefix}: available_value_requires_normalized_value")
        if value["status"] != "available" and value["normalized_value"] is not None:
            errors.append(f"{prefix}: nonavailable_value_has_normalized_value")
        if value["status"] == "available" and value["original_value"] is None:
            errors.append(f"{prefix}: available_value_requires_original_value")

        quality = record["quality"]
        if quality["review_status"] == "reviewed" and not all(
                quality.get(field) for field in ("reviewer", "reviewed_at_utc", "review_basis")):
            errors.append(f"{prefix}: reviewed_requires_human_identity_time_and_basis")
        if record["boundary"]["verified"] and quality["review_status"] != "reviewed":
            errors.append(f"{prefix}: verified_boundary_requires_reviewed_record")

        period = record["period"]
        evidence = record["evidence"]
        if period["year_basis"] == "table_header" and period["observation_year"] is not None:
            year_text = str(period["observation_year"])
            associated = any(
                year_text in header["text"] and
                (ev["column"] is None or header["column"] is None or ev["column"] == header["column"])
                for ev in evidence for header in ev["headers"] if header["role"] == "year"
            )
            if not associated:
                errors.append(f"{prefix}: year_header_missing_or_wrong_column")
        if (period["year_basis"] == "explicit_quote" and document["report_type"] == "Financial"
                and period["observation_year"] is not None):
            year = period["observation_year"]
            associated = (period["measurement_date"] == f"{year}-12-31" and
                any(value["original_value"] and
                    f"31 thang 12 nam {year}" in plain(ev["exact_quote"]) and
                    value["original_value"] in ev["exact_quote"]
                    for ev in evidence))
            if not associated:
                errors.append(f"{prefix}: explicit_quote_year_evidence_missing")
        if period["year_basis"] == "same_page_title_and_column":
            year = period["observation_year"]
            associated = (document["report_type"] == "Financial" and
                isinstance(year, int) and not isinstance(year, bool) and
                period["observation_end"] == f"{year}-12-31" and
                any(isinstance(ev["column"], int) and not isinstance(ev["column"], bool) and
                    any(h["role"] == "year" and h["physical_page"] == ev["physical_page"] and
                        h["column"] == ev["column"] and plain(h["text"]).strip() == "nam nay"
                        for h in ev["headers"]) and
                    any(h["physical_page"] == ev["physical_page"] and
                        "cho nam tai chinh" in plain(h["text"]) and
                        f"31 thang 12 nam {year}" in plain(h["text"])
                        for h in ev["headers"])
                    for ev in evidence))
            if not associated:
                errors.append(f"{prefix}: same_page_title_and_column_year_evidence_missing")

        for ev in evidence:
            if ev["source_sha256"] != source["sha256"]:
                errors.append(f"{prefix}: evidence_source_sha256_mismatch")
            if ev["physical_page"] > page_count:
                errors.append(f"{prefix}: evidence_page_outside_pdf")
            if ev["physical_page"] not in checked_pages:
                errors.append(f"{prefix}: evidence_page_not_in_coverage")
            if ev["exact_quote"] not in ev["context_text"]:
                errors.append(f"{prefix}: quote_not_in_context")
            if ev["char_start"] is not None and ev["char_end"] is not None and ev["char_end"] <= ev["char_start"]:
                errors.append(f"{prefix}: invalid_char_interval")
            binding = (ev["source_sha256"], ev["physical_page"], ev["exact_quote"],
                       ev["table_id"], ev["row"], ev["column"])
            previous = evidence_bindings.setdefault(ev["evidence_id"], binding)
            if previous != binding:
                errors.append(f"{prefix}: duplicate_evidence_id_conflict")
            for header in ev["headers"]:
                if header["physical_page"] > page_count:
                    errors.append(f"{prefix}: header_page_outside_pdf")
            for footnote in ev["footnotes"]:
                if footnote["physical_page"] > page_count:
                    errors.append(f"{prefix}: footnote_page_outside_pdf")
        if value["status"] == "available":
            source_text = " ".join(ev["context_text"] for ev in evidence)
            if value["original_value"] not in source_text:
                errors.append(f"{prefix}: original_value_not_in_context")
            if value["original_unit"] and value["original_unit"].casefold() not in (
                    source_text + " " + " ".join(h["text"] for ev in evidence for h in ev["headers"])).casefold():
                errors.append(f"{prefix}: original_unit_not_in_context_or_header")
    for issue in handoff["issue_log"]:
        if issue["record_id"] is not None and issue["record_id"] not in record_ids:
            errors.append(f"issue_log/{issue['issue_id']}: unknown_record_id")
        if any(page > page_count for page in issue["source_pages"]):
            errors.append(f"issue_log/{issue['issue_id']}: page_outside_pdf")
    return handoff, [f"{path}: {message}" for message in errors]


def validate_manifest(path: Path, schema: dict) -> tuple[dict | None, list[str]]:
    try:
        manifest = load_json(path)
    except (OSError, ValueError) as exc:
        return None, [f"{path}: unreadable_json: {exc}"]
    errors = schema_errors(manifest, schema)
    if errors:
        return manifest, [f"{path}: {message}" for message in errors]
    seen = set()
    for row in manifest["files"]:
        if row["document_id"] in seen:
            errors.append(f"duplicate_manifest_document_id: {row['document_id']}")
        seen.add(row["document_id"])
        if row["status"] == "unavailable":
            if not row["reason"]:
                errors.append(f"unavailable_requires_reason: {row['document_id']}")
            continue
        for field, digest_field in (("pdf_path", "pdf_sha256"), ("json_path", "json_sha256")):
            relative = row[field]
            digest = row[digest_field]
            if not relative or not digest:
                errors.append(f"{row['document_id']}: {field}_and_hash_required")
                continue
            candidate = (path.parent / relative).resolve()
            if not candidate.is_relative_to(path.parent.resolve()):
                errors.append(f"{row['document_id']}: path_outside_delivery: {relative}")
            elif not candidate.is_file():
                errors.append(f"{row['document_id']}: missing_file: {relative}")
            elif sha256(candidate) != digest:
                errors.append(f"{row['document_id']}: hash_mismatch: {relative}")
    return manifest, [f"{path}: {message}" for message in errors]


def expand_paths(patterns: list[str]) -> list[Path]:
    paths = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        paths.extend(Path(item) for item in (matches or [pattern]))
    return paths


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="JSON handoffs or quoted glob patterns")
    parser.add_argument("--pdf-dir", type=Path, help="Directory containing original PDF filenames")
    parser.add_argument("--manifest", type=Path, help="Optional delivery manifest to validate")
    args = parser.parse_args(argv)
    schema = load_json(HERE / "schema.json")
    errors: list[str] = []
    manifest = None
    if args.manifest:
        manifest, manifest_errors = validate_manifest(args.manifest, load_json(HERE / "manifest_schema.json"))
        errors.extend(manifest_errors)
    manifest_rows = {row["document_id"]: row for row in manifest["files"]} if manifest and not schema_errors(
        manifest, load_json(HERE / "manifest_schema.json")) else {}
    paths = expand_paths(args.files)
    if manifest and not paths:
        paths = [args.manifest.parent / row["json_path"] for row in manifest["files"]
                 if row["status"] != "unavailable" and row["json_path"]]
    if not paths:
        parser.error("supply JSON files or --manifest")
    documents = set()
    records = set()
    count = 0
    for path in paths:
        handoff, file_errors = validate_handoff(path, schema, args.pdf_dir)
        errors.extend(file_errors)
        if handoff and not schema_errors(handoff, schema):
            document = handoff["document"]
            document_id = document["document_id"]
            if document_id in documents:
                errors.append(f"duplicate_document_id_across_files: {document_id}")
            documents.add(document_id)
            if manifest:
                row = manifest_rows.get(document_id)
                if row is None:
                    errors.append(f"document_not_in_manifest: {document_id}")
                else:
                    for field in ("report_year", "report_type", "financial_scope"):
                        if document[field] != row[field]:
                            errors.append(f"manifest_document_{field}_mismatch: {document_id}")
                    if document["source"]["sha256"] != row["pdf_sha256"]:
                        errors.append(f"manifest_document_pdf_hash_mismatch: {document_id}")
                    if row["json_path"] and path.resolve() != (args.manifest.parent / row["json_path"]).resolve():
                        errors.append(f"manifest_json_path_mismatch: {document_id}")
            for record in handoff["records"]:
                if record["record_id"] in records:
                    errors.append(f"duplicate_record_id_across_files: {record['record_id']}")
                records.add(record["record_id"])
            count += len(handoff["records"])
    if manifest:
        for row in manifest["files"]:
            if row["status"] != "unavailable" and row["document_id"] not in documents:
                errors.append(f"manifest_delivered_document_not_validated: {row['document_id']}")
    if errors:
        for error in errors:
            print("ERROR", error, file=sys.stderr)
        print(f"FAIL files={len(paths)} records={count} errors={len(errors)}")
        return 1
    print(f"PASS files={len(paths)} records={count}; mechanical checks only, semantic review pending")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
