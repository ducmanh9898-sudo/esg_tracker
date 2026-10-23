import json
import re
from pathlib import Path

from tools.normalizer import find_source_dir

ROOT = Path(__file__).resolve().parents[1]
CLAIM_ID = re.compile(r"^CLM-[A-F0-9]{12}$")
REQUIRED = {
    "claim_id", "company_id", "report_year", "observation_year", "dimension",
    "topic", "claim_type", "metric_id", "value", "unit", "scope", "variant", "evidence"
}


def validate_claims(claims):
    source_dir = find_source_dir()
    errors = []
    review_queue = []
    seen_ids = set()
    seen_provenance_keys = set()

    for index, claim in enumerate(claims, start=1):
        ref = claim.get("claim_id", f"row:{index}")
        missing = sorted(REQUIRED - claim.keys())
        if missing:
            errors.append({"claim": ref, "field": "required", "message": f"Thiếu: {', '.join(missing)}"})
            continue

        if not CLAIM_ID.fullmatch(claim["claim_id"]):
            errors.append({"claim": ref, "field": "claim_id", "message": "ID không đúng CLM-[A-F0-9]{12}"})
        if claim["claim_id"] in seen_ids:
            errors.append({"claim": ref, "field": "claim_id", "message": "Claim ID bị trùng"})
        seen_ids.add(claim["claim_id"])

        for field in ("report_year", "observation_year"):
            value = claim[field]
            if not isinstance(value, int) or not 2000 <= value <= 2100:
                errors.append({"claim": ref, "field": field, "message": "Năm phải là số nguyên 2000–2100"})
        if claim["value"] is None or not isinstance(claim["value"], (int, float, str, bool)):
            errors.append({"claim": ref, "field": "value", "message": "Giá trị phải là number, string hoặc boolean"})
        for field in ("unit", "scope", "metric_id"):
            if not isinstance(claim[field], str) or not claim[field].strip():
                errors.append({"claim": ref, "field": field, "message": "Không được để trống"})

        # Hai disclosure cùng metric/kỳ/scope có thể là input hợp lệ để phát hiện
        # mâu thuẫn. Chỉ coi là trùng cấu trúc khi cả provenance cũng giống nhau.
        first_evidence = claim["evidence"][0] if claim.get("evidence") else {}
        provenance_key = (
            claim["company_id"], claim["report_year"], claim["observation_year"],
            claim["metric_id"], claim["unit"], claim["scope"], claim["variant"],
            first_evidence.get("source_file"), first_evidence.get("json_pointer")
        )
        if provenance_key in seen_provenance_keys:
            errors.append({"claim": ref, "field": "provenance_key", "message": "Bản ghi và provenance bị trùng hoàn toàn"})
        seen_provenance_keys.add(provenance_key)

        if not isinstance(claim["evidence"], list) or not claim["evidence"]:
            errors.append({"claim": ref, "field": "evidence", "message": "Phải có ít nhất một nguồn"})
            continue
        for evidence in claim["evidence"]:
            if not evidence.get("evidence_id"):
                errors.append({"claim": ref, "field": "evidence_id", "message": "Thiếu Evidence ID"})
            source_file = source_dir / evidence.get("source_file", "")
            if not source_file.is_file():
                errors.append({"claim": ref, "field": "source_file", "message": f"Không tìm thấy {source_file.name}"})
            pages = evidence.get("source_pages")
            if not isinstance(pages, list) or not pages or any(not isinstance(p, int) or p < 1 for p in pages):
                errors.append({"claim": ref, "field": "source_pages", "message": "Trang nguồn không hợp lệ"})
            if not evidence.get("json_pointer"):
                errors.append({"claim": ref, "field": "json_pointer", "message": "Thiếu JSON Pointer"})

        if claim.get("review_status") != "reviewed":
            review_queue.append({
                "claim_id": ref,
                "reason": "Chưa đối chiếu thủ công với câu gốc/PDF",
                "source_file": claim["evidence"][0]["source_file"],
                "source_pages": claim["evidence"][0]["source_pages"]
            })

    return {
        "claims_checked": len(claims),
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "errors": errors,
        "manual_review_count": len(review_queue),
        "manual_review_queue": review_queue
    }


def run():
    claims = json.loads((ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig"))
    report = validate_claims(claims)
    (ROOT / "output" / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


if __name__ == "__main__":
    result = run()
    print(f"Đã kiểm tra {result['claims_checked']} claim; lỗi cấu trúc: {result['error_count']}")
