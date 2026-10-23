"""Attach supplementary source evidence after independently checking source identity.

This module never changes an Extract value or a Graph context review status. A
crosswalk establishes correspondence for selected excerpts only; it does not
establish that two report binaries are the same edition or byte-identical.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

import fitz


def _compact(value):
    return re.sub(r"\s+", " ", value or "").strip()


def _inside(root, relative):
    path = (Path(root) / relative).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError("source_path_outside_repository")
    return path


def _display_number(value):
    """Parse Vietnamese grouped/decimal display without changing source values."""
    token = str(value).replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(token)
    except InvalidOperation as exc:
        raise ValueError("non_numeric_display_value") from exc


def attach_corroborated_evidence(claims, provenance_path, root):
    """Validate selected page correspondence and return reviewed claim copies.

    Fails closed if source bytes, page text, claim identity, quote, value, or
    evidence locator change. The missing declared PDF remains a separate source.
    """
    root = Path(root).resolve()
    config = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
    if config.get("schema_version") != "1.0":
        raise ValueError("unsupported_source_provenance_version")
    sources = config.get("sources") or []
    by_source = {row["source_id"]: row for row in sources}
    if len(by_source) != len(sources):
        raise ValueError("duplicate_source_id")
    by_kind = {}
    for row in sources:
        kind = row["kind"]
        if kind in by_kind:
            raise ValueError("duplicate_source_kind:" + kind)
        by_kind[kind] = row
        if row["availability"] == "missing":
            if row.get("path") is not None or row.get("sha256") is not None:
                raise ValueError("missing_source_must_not_have_path_or_hash")
            continue
        path = _inside(root, row["path"])
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row["sha256"]:
            raise ValueError("source_missing_or_hash_mismatch:" + row["source_id"])
    required = {"declared_pdf_binary", "archived_page_text_json", "official_pdf_binary", "extract_json"}
    if set(by_kind) != required:
        raise ValueError("source_inventory_incomplete")
    declared = by_kind["declared_pdf_binary"]
    archived = by_kind["archived_page_text_json"]
    official = by_kind["official_pdf_binary"]
    archive_data = json.loads(_inside(root, archived["path"]).read_text(encoding="utf-8"))
    if (archive_data.get("source_file") != declared["declared_filename"]
            or archive_data.get("page_count") != archived["page_count"]
            or len(archive_data.get("pages", [])) != archived["page_count"]):
        raise ValueError("archived_page_text_identity_mismatch")
    pdf = fitz.open(_inside(root, official["path"]))
    try:
        if len(pdf) != official["page_count"]:
            raise ValueError("official_pdf_page_count_mismatch")
        page_map = {}
        validated_pages = []
        for mapping in config.get("page_crosswalk", []):
            archive_page = mapping["archived_page"]
            pair = mapping["official_page_pair"]
            if archive_page in page_map or not 1 <= archive_page <= len(archive_data["pages"]):
                raise ValueError("duplicate_or_invalid_archived_page")
            if len(pair) != 2 or pair[1] != pair[0] + 1 or not 1 <= pair[0] < pair[1] <= len(pdf):
                raise ValueError("invalid_official_page_pair")
            page = archive_data["pages"][archive_page - 1]
            if page.get("page_number") != archive_page:
                raise ValueError("archived_page_number_mismatch")
            # The 68-page text artifact records double-width spread geometry.
            width = sum(pdf[index - 1].rect.width for index in pair)
            if abs(page["width_points"] - width) > 2:
                raise ValueError("spread_geometry_mismatch:" + str(archive_page))
            archive_text = _compact(page["text"])
            if any(_compact(term) not in archive_text for term in mapping["archived_terms"]):
                raise ValueError("archive_excerpt_mismatch:" + str(archive_page))
            for check in mapping["official_checks"]:
                if check["page"] not in pair:
                    raise ValueError("official_check_outside_page_pair")
                official_text = _compact(pdf[check["page"] - 1].get_text())
                if any(_compact(term) not in official_text for term in check["terms"]):
                    raise ValueError("official_excerpt_mismatch:" + str(check["page"]))
            page_map[archive_page] = mapping
            validated_pages.append({"archived_page": archive_page, "official_page_pair": pair,
                                    "correspondence": mapping["correspondence"],
                                    "scope": "selected_excerpts_only"})
        reviewed = copy.deepcopy(claims)
        by_claim = {row["record_id"]: row for row in reviewed}
        if len(by_claim) != len(reviewed):
            raise ValueError("duplicate_claim_id")
        for claim in reviewed:
            for evidence in claim.get("evidence", []):
                if evidence.get("source_file") == declared["declared_filename"]:
                    evidence["source_id"] = declared["source_id"]
                    evidence["page_system"] = "extract_declared_page"
        prepared = []
        seen_evidence = {ev["evidence_id"] for c in reviewed for ev in c.get("evidence", [])}
        for entry in config.get("official_evidence", []):
            claim = by_claim.get(entry["claim_id"])
            if claim is None or claim["company_id"] != "BSR" or claim["report_year"] != 2025:
                raise ValueError("supplement_claim_identity_mismatch")
            if claim.get("review_status") != "reviewed":
                raise ValueError("supplement_source_review_missing:" + claim["record_id"])
            original = next((ev for ev in claim["evidence"] if ev["evidence_id"] == entry["extract_evidence_id"]), None)
            archive_page = entry["archived_support_page"]
            page = entry["official_page"]
            if (original is None or original.get("source_file") != declared["declared_filename"]
                    or archive_page not in original["source_pages"]
                    or archive_page not in page_map or page not in page_map[archive_page]["official_page_pair"]):
                raise ValueError("supplement_extract_locator_mismatch:" + entry["evidence_id"])
            if entry["evidence_id"] in seen_evidence:
                raise ValueError("duplicate_supplement_evidence_id")
            seen_evidence.add(entry["evidence_id"])
            quote = _compact(entry["quote"])
            official_text = _compact(pdf[page - 1].get_text())
            archive_text = _compact(archive_data["pages"][archive_page - 1]["text"])
            if quote not in official_text or entry["display_value"] not in quote:
                raise ValueError("supplement_official_quote_mismatch:" + entry["evidence_id"])
            if entry["display_value"] not in archive_text:
                raise ValueError("supplement_archived_value_mismatch:" + entry["evidence_id"])
            if _display_number(entry["display_value"]) != Decimal(str(claim.get("value"))):
                raise ValueError("supplement_claim_value_mismatch:" + entry["evidence_id"])
            prepared.append((claim, {
                "evidence_id": entry["evidence_id"], "source_file": official["declared_filename"],
                "source_pages": [page], "json_pointer": "", "original_text": quote,
                "source_id": official["source_id"], "source_sha256": official["sha256"],
                "page_system": official["page_system"],
                "corroborates_evidence_id": original["evidence_id"],
                "reviewer_kind": "AI", "review_scope": entry["review_scope"],
                "ocr_limitations": [],
            }))
        for claim, evidence in prepared:
            claim["evidence"].append(evidence)
    finally:
        pdf.close()
    audit = {
        "schema_version": "1.0", "provenance_file": str(provenance_path),
        "sources": sources, "validated_page_crosswalk": validated_pages,
        "page_crosswalk": config["page_crosswalk"],
        "official_evidence": config["official_evidence"],
        "attached_evidence": [{"claim_id": c["record_id"], "evidence_id": e["evidence_id"],
                                "source_id": e["source_id"], "official_page": e["source_pages"][0],
                                "corroborates_evidence_id": e["corroborates_evidence_id"],
                                "review_scope": e["review_scope"]} for c, e in prepared],
        "relation_policy": config["relation_policy"],
        "declared_pdf_binary_available": False,
        "whole_document_equivalence_verified": False,
        "context_review_status_changed": False,
    }
    return reviewed, audit
