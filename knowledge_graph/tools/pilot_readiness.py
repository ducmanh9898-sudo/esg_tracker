"""Build a read-only inventory for the limited ESG/financial pilot."""

import json
import re
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIMENSIONS = ("E", "S", "G")
COMPANY_NAMES = {
    "BSR": "Công ty cổ phần Lọc hóa dầu Bình Sơn (BSR)",
    "PLX": "Tập đoàn Xăng dầu Việt Nam (Petrolimex)",
    "PVD": "Tổng công ty Cổ phần Khoan và Dịch vụ Khoan Dầu khí (PV Drilling)",
}


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _manifest_inventory():
    manifests = defaultdict(list)
    for path in (ROOT / "data" / "source" / "page_text").glob("*.json"):
        match = re.match(r"(BSR|PLX|PVD)_(20\d{2})(?:_esg_.*)?$", path.stem)
        if not match:
            continue
        company, year = match.group(1), int(match.group(2))
        data = _read(path)
        partial = "_esg_" in path.stem
        page_numbers = [page.get("page_number") for page in data.get("pages", [])
                        if isinstance(page.get("page_number"), int)]
        manifests[(company, year)].append({
            "path": str(path.relative_to(ROOT)).replace("\\", "/"),
            "source_file": data.get("source_file"),
            "page_count": data.get("page_count"),
            "chunk_count": 0,
            "coverage_status": "partial" if partial else "complete",
            "page_ranges": [[min(page_numbers), max(page_numbers)]] if page_numbers else [],
        })
    # Prefer a complete manifest when a partial overlap manifest also exists.
    for key, entries in manifests.items():
        if any(entry["coverage_status"] == "complete" for entry in entries):
            manifests[key] = [entry for entry in entries if entry["coverage_status"] == "complete"]
    return manifests


def _claims_by_key():
    path = ROOT / "output" / "normalized_claims.json"
    if not path.exists():
        return defaultdict(list)
    claims = _read(path)
    result = defaultdict(list)
    for claim in claims:
        result[(claim["company_id"], int(claim["report_year"]), claim["dimension"])].append(claim)
    return result


def _financial_by_year():
    path = ROOT / "data" / "financial_disclosures_bsr.json"
    if not path.exists():
        return defaultdict(list)
    result = defaultdict(list)
    for record in _read(path).get("records", []):
        result[(record["company_id"], int(record["report_year"]))].append(record)
    return result


def _standards_context(claims):
    crosswalk_path = ROOT / "data" / "config" / "standards_crosswalk_sample.json"
    if not crosswalk_path.exists() or not claims:
        return {"status": "not_assessed", "verified_references": [], "unverified_candidates": []}
    crosswalk = _read(crosswalk_path)
    metric_ids = {claim.get("metric_id") for claim in claims}
    verified, candidates = [], []
    for concept in crosswalk.get("concepts", []):
        if not any(claim.get(field) in values for field, values in concept.get("claim_match", {}).items() for claim in claims):
            continue
        for mapping in crosswalk.get("mappings", []):
            if mapping["concept_id"] != concept["concept_id"]:
                continue
            target = {
                "reference_code": mapping["reference_code"],
                "standard_name": mapping["standard_name"],
                "standard_version": mapping["standard_version"],
                "verification_status": mapping["verification_status"],
            }
            (verified if mapping["verification_status"] == "verified" else candidates).append(target)
    return {
        "status": "partial_context" if verified or candidates else "not_mapped",
        "verified_references": verified,
        "unverified_candidates": candidates,
        "disclaimer": "Ngữ cảnh crosswalk không phải kết luận tuân thủ/vi phạm.",
    }


def _record(company, year, dimension, claims, manifests, financial):
    claim_ids = [claim["claim_id"] for claim in claims]
    evidence = [evidence for claim in claims for evidence in claim.get("evidence", [])]
    source_pages = sorted({page for evidence_item in evidence for page in evidence_item.get("source_pages", [])})
    pointers = sorted({evidence_item.get("json_pointer") for evidence_item in evidence if evidence_item.get("json_pointer")})
    has_original_text = any(bool(evidence_item.get("source_text")) for evidence_item in evidence)
    boundary_verified = bool(claims) and all(claim.get("reporting_boundary_verified") is True for claim in claims)
    period_types = {claim.get("period_type") for claim in claims if claim.get("period_type")}
    temporal_status = "not_assessed"
    temporal_blocker = None
    if claims:
        temporal_status = "needs_review"
        temporal_blocker = "period_type và reporting boundary của claim chưa được xác minh đầy đủ."
        if len(period_types) == 1 and boundary_verified:
            temporal_status = "candidate"
            temporal_blocker = None
    financial_records = financial.get((company, year), [])
    financial_info = {
        "available": bool(financial_records),
        "record_count": len(financial_records),
        "source_report_ids": sorted({record["source_report_id"] for record in financial_records}),
        "workforce_link_status": "NeedsReview" if company == "BSR" and year == 2025 else "not_run",
    }
    blockers = []
    if not claims:
        blockers.extend([
            "Chưa có normalized claim cho company/year/dimension này.",
            "Chưa có evidence linkage từ Graph/Extract.",
        ])
    if claims and not has_original_text:
        blockers.append("Evidence có trang/pointer nhưng original_text chưa được cung cấp.")
    if claims and not boundary_verified:
        blockers.append("Reporting boundary của claim chưa được xác minh.")
    if temporal_blocker:
        blockers.append(temporal_blocker)
    if not financial_info["available"]:
        blockers.append("Chưa có financial disclosure contract tương ứng.")
    elif financial_info["workforce_link_status"] == "NeedsReview" and dimension == "S":
        blockers.append("Liên kết workforce ESG ↔ BCTC 2025 đang NeedsReview do scope/định nghĩa và ngày đo chưa xác minh là tương thích.")
    source_coverage = "none" if not manifests else ("partial" if any(m["coverage_status"] == "partial" for m in manifests) else "complete")
    if source_coverage == "partial":
        blockers.append("Manifest/chunk chỉ bao phủ một phần báo cáo.")
    status = "ready" if claims and evidence and has_original_text and boundary_verified and not blockers else ("partial" if claims else "blocked")
    return {
        "company_id": company,
        "company_name": COMPANY_NAMES[company],
        "report_id": f"ESG-{company}-{year}",
        "report_year": year,
        "report_type": "sustainability_report",
        "dimension": dimension,
        "claims": {
            "claim_count": len(claims),
            "evidence_count": len(evidence),
            "has_claim": bool(claims),
            "claim_ids": claim_ids,
        },
        "reporting_period": {
            "period_type": "annual",
            "period_start": f"{year}-01-01",
            "period_end": f"{year}-12-31",
            "status": "inferred_from_report_year",
        },
        "reporting_boundary": {
            "value": None,
            "verification_status": "verified" if boundary_verified else "unverified",
            "basis": "Không tự suy diễn từ thiếu field claim.",
        },
        "provenance": {
            "original_text_available": has_original_text,
            "source_pages_available": bool(source_pages),
            "source_pointers_available": bool(pointers),
            "source_pages": source_pages,
            "source_pointers": pointers,
        },
        "temporal_comparability": {
            "status": temporal_status,
            "basis": "Cross-year assessment chưa đủ period type/boundary cho claim hiện có." if claims else "Chưa có claim để đánh giá.",
        },
        "financial_disclosure_availability": financial_info,
        "standards_context": _standards_context(claims),
        "source_manifests": manifests,
        "status": status,
        "blockers": blockers,
        "pending_manual_review": bool(blockers),
    }


def build_inventory():
    claims = _claims_by_key()
    financial = _financial_by_year()
    manifests = _manifest_inventory()
    keys = {(company, year) for company, year in manifests}
    keys.update({(company, year) for company, year, _ in claims})
    records = []
    for company, year in sorted(keys):
        for dimension in DIMENSIONS:
            records.append(_record(company, year, dimension, claims.get((company, year, dimension), []), manifests.get((company, year), []), financial))
    bsr_years = {}
    for year in sorted(year for company, year in keys if company == "BSR"):
        bsr_years[str(year)] = {
            "esg_claims": sum(item["claims"]["claim_count"] for item in records if item["company_id"] == "BSR" and item["report_year"] == year),
            "financial_records": len(financial.get(("BSR", year), [])),
            "workforce_link_status": "NeedsReview" if year == 2025 else "not_run",
        }
    return {
        "schema_version": "0.1",
        "inventory_scope": "Pilot readiness inventory only; no pilot execution, finding creation or snapshot update.",
        "records": records,
        "bsr_financial_integration": {
            "status": "partial",
            "years_with_esg_and_financial_records": [year for year in sorted(bsr_years) if bsr_years[year]["esg_claims"] and bsr_years[year]["financial_records"]],
            "by_year": bsr_years,
            "workforce_link_status": "NeedsReview",
            "fc01_status": "inactive",
            "blockers": ["The consolidated BCTC 2025 workforce boundary and measurement date are identified; the ESG metric boundary/date and equivalence of employee definitions remain unverified.", "ESG original_text is absent in current normalized claims."],
        },
    }


def main():
    output = ROOT / "data" / "pilot_readiness_inventory.json"
    output.write_text(json.dumps(build_inventory(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(build_inventory()['records'])} inventory records to {output}")


if __name__ == "__main__":
    main()
