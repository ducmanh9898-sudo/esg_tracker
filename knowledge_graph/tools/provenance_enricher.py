"""Enrich BSR 2025 claims from preserved source-page text without inference."""

import copy
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLAIMS = ROOT / "output" / "normalized_claims.json"
DEFAULT_CHUNKS = ROOT / "data" / "source" / "page_text" / "BSR_2025.json"
DEFAULT_ENRICHED = ROOT / "output" / "bsr_2025_claims_enriched.json"
DEFAULT_GAPS = ROOT / "output" / "bsr_2025_provenance_gap_report.json"


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _claim_is_bsr_2025(claim):
    return claim.get("company_id") == "BSR" and claim.get("report_year") == 2025


def _load_pages(chunk_dir):
    chunk_dir = Path(chunk_dir)
    if chunk_dir.is_file():
        source = _read(chunk_dir)
        pages = [{"chunk_file": chunk_dir.name, "page_number": page.get("page_number"),
                  "page_range": [page.get("page_number"), page.get("page_number")],
                  "text": page.get("text"), "json_pointer": f"/pages/{index}/text",
                  "source_file": source.get("source_file")}
                 for index, page in enumerate(source.get("pages", []))]
        try:
            display = chunk_dir.relative_to(ROOT).as_posix()
        except ValueError:
            display = str(chunk_dir)
        return pages, {"status": "available", "manifest": display,
                       "source_file": source.get("source_file")}
    manifest_path = chunk_dir / "manifest.json"
    if not manifest_path.exists():
        return [], {"status": "blocked", "reason": "source manifest not found"}
    manifest = _read(manifest_path)
    chunks = []
    for entry in manifest.get("chunks", []):
        chunk_path = chunk_dir / entry["file"]
        if not chunk_path.exists():
            continue
        payload = _read(chunk_path)
        for page in payload.get("pages", []):
            chunks.append({
                "chunk_file": entry["file"],
                "page_number": page.get("page_number"),
                "page_range": entry.get("page_range", []),
                "text": page.get("text"),
                "json_pointer": page.get("json_pointer"),
                "source_file": manifest.get("source_file"),
            })
    try:
        manifest_display = str(manifest_path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        manifest_display = str(manifest_path).replace("\\", "/")
    return chunks, {
        "status": "available",
        "manifest": manifest_display,
        "source_file": manifest.get("source_file"),
    }


def _number_variants(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return []
    raw = str(value)
    variants = {raw}
    if isinstance(value, int) or float(value).is_integer():
        integer = int(value)
        variants.update({f"{integer:,}", f"{integer:,}".replace(",", ".")})
    else:
        variants.add(f"{value:,}")
    return sorted(variants, key=len, reverse=True)


def _extract_matches(text, value):
    if not text:
        return []
    matches = []
    for variant in _number_variants(value):
        for match in re.finditer(re.escape(variant), text):
            matches.append((match.start(), match.end(), variant))
    return sorted(set(matches))


def _source_file_compatible(claim_source_file, chunk_source_file):
    if not claim_source_file or not chunk_source_file:
        return None
    claim_key = re.sub(r"(_esg)?\.(json|pdf)$", "", Path(claim_source_file).name, flags=re.I)
    chunk_key = re.sub(r"(_esg)?\.(json|pdf)$", "", Path(chunk_source_file).name, flags=re.I)
    return claim_key.lower() == chunk_key.lower()


def _snippet(text, start, end, radius=260):
    # Keep nearby non-empty source lines; this preserves table context without
    # inventing a sentence when the PDF extraction has large whitespace gaps.
    lines = text.splitlines()
    line_index = text[:start].count("\n")
    non_empty = [(index, re.sub(r"\s+", " ", line).strip()) for index, line in enumerate(lines) if line.strip()]
    nearby = [line for index, line in non_empty if abs(index - line_index) <= 6]
    if nearby:
        return " ".join(nearby)
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return re.sub(r"\s+", " ", text[left:right]).strip()


def _enrich_evidence(claim, evidence, pages):
    source_pages = evidence.get("source_pages") or []
    pointer = evidence.get("json_pointer")
    if not source_pages and not pointer:
        return {
            "status": "blocked",
            "reason": "evidence thiếu source page và JSON pointer",
            "pending_provenance": ["source_pages", "json_pointer", "original_text"],
            "matched_chunks": [],
        }
    source_matches = {
        _source_file_compatible(evidence.get("source_file"), page.get("source_file"))
        for page in pages if page.get("page_number") in source_pages
    }
    candidates = [
        page for page in pages
        if page.get("page_number") in source_pages
        and _source_file_compatible(evidence.get("source_file"), page.get("source_file")) is not False
    ]
    source_file_match = True if source_matches == {True} else (False if source_matches == {False} else None)
    if not candidates:
        return {
            "status": "blocked",
            "reason": "không có chunk chứa source page của evidence",
            "pending_provenance": ["original_text"],
            "matched_chunks": [],
        }
    text_candidates = [page for page in candidates if isinstance(page.get("text"), str) and page["text"].strip()]
    if not text_candidates:
        return {
            "status": "blocked",
            "reason": "chunk/page tồn tại nhưng không có source text",
            "pending_provenance": ["original_text"],
            "matched_chunks": sorted({page["chunk_file"] for page in candidates}),
        }
    all_matches = []
    for page in text_candidates:
        for start, end, variant in _extract_matches(page["text"], claim.get("value")):
            all_matches.append((page, start, end, variant))
    chunk_ids = sorted({page["chunk_file"] for page in text_candidates})
    if len(chunk_ids) != 1:
        return {
            "status": "partial",
            "reason": "nhiều chunk cùng khớp source page; không chọn một nguồn duy nhất",
            "pending_provenance": ["original_text"],
            "matched_chunks": chunk_ids,
            "match_count": len(all_matches),
        }
    if len(all_matches) != 1:
        reason = "không tìm thấy giá trị claim duy nhất trong text chunk" if not all_matches else "giá trị claim xuất hiện nhiều lần trong chunk"
        return {
            "status": "partial" if all_matches else "blocked",
            "reason": reason,
            "pending_provenance": ["original_text"],
            "matched_chunks": chunk_ids,
            "match_count": len(all_matches),
        }
    page, start, end, variant = all_matches[0]
    return {
        "status": "resolved",
        "reason": "matched by report year, source page and unique value in source chunk; JSON pointer is retained as claim provenance",
        "pending_provenance": [],
        "matched_chunks": chunk_ids,
        "source_file_match": source_file_match,
        "json_pointer_match": next((page.get("json_pointer") == pointer for page in text_candidates if page.get("json_pointer")), None),
        "matched_page": page["page_number"],
        "match_variant": variant,
        "source_text": _snippet(page["text"], start, end),
    }


def enrich_claims(claims, chunk_dir=DEFAULT_CHUNKS):
    pages, source_info = _load_pages(chunk_dir)
    enriched = []
    gaps = []
    for claim in claims:
        if not _claim_is_bsr_2025(claim):
            continue
        output_claim = copy.deepcopy(claim)
        output_claim["original_text"] = None
        evidence_results = []
        for evidence in output_claim.get("evidence", []):
            result = _enrich_evidence(output_claim, evidence, pages)
            if result.get("status") == "resolved":
                evidence["source_text"] = result["source_text"]
            else:
                evidence["source_text"] = None
            evidence_results.append(result)
        statuses = [result["status"] for result in evidence_results]
        if statuses and all(status == "resolved" for status in statuses):
            status = "resolved"
            texts = [result["source_text"] for result in evidence_results]
            output_claim["original_text"] = "\n\n".join(texts)
            reason = "all evidence matched unique source text"
        elif any(status in {"resolved", "partial"} for status in statuses):
            status = "partial"
            reason = "chỉ một phần evidence có thể match duy nhất với source chunk"
        else:
            status = "blocked"
            reason = "không có evidence nào đủ điều kiện match duy nhất với source chunk"
        output_claim["provenance"] = {
            "status": status,
            "reason": reason,
            "source_manifest": source_info,
            "evidence_results": evidence_results,
            "pending_provenance": sorted({
                field for result in evidence_results for field in result.get("pending_provenance", [])
            }),
            "reporting_boundary_status": "unverified",
            "period_type_status": "unverified",
        }
        enriched.append(output_claim)
        if status != "resolved":
            gaps.append({
                "claim_id": claim["claim_id"],
                "selection_id": claim.get("selection_id"),
                "status": status,
                "reason": reason,
                "pending_provenance": output_claim["provenance"]["pending_provenance"],
                "missing_extract_fields": ["original_text"],
            })
    return enriched, {
        "schema_version": "0.1",
        "company_id": "BSR",
        "report_year": 2025,
        "source_manifest": source_info,
        "claim_count": len(enriched),
        "resolved_count": sum(claim["provenance"]["status"] == "resolved" for claim in enriched),
        "partial_count": sum(claim["provenance"]["status"] == "partial" for claim in enriched),
        "blocked_count": sum(claim["provenance"]["status"] == "blocked" for claim in enriched),
        "gaps": gaps,
        "global_missing_extract_fields": [
            "original_text hoặc PDF text đã adjudicate",
            "reporting_boundary và reporting_boundary_verified",
            "period_type và period_type_verified",
        ],
    }


def main():
    claims = _read(DEFAULT_CLAIMS)
    enriched, gaps = enrich_claims(claims)
    DEFAULT_ENRICHED.write_text(json.dumps(enriched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    DEFAULT_GAPS.write_text(json.dumps(gaps, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Enriched {len(enriched)} BSR 2025 claims: {gaps['resolved_count']} resolved, {gaps['partial_count']} partial, {gaps['blocked_count']} blocked")


if __name__ == "__main__":
    main()
