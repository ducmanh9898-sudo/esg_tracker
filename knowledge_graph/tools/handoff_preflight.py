"""Read-only checks for an Extract provenance/boundary handoff before Graph ingestion."""

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.normalizer import find_source_dir, load_json, resolve_pointer


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLAIMS = ROOT / "output" / "normalized_claims.json"
SCHEMA = ROOT / "schemas" / "provenance-boundary-handoff-schema-v0.1.json"
BOUNDARY_FIELDS = (
    "basis", "included_entities", "excluded_entities", "measurement_scope",
    "consolidation_approach", "source_pages",
)
RECORD_NULLABLE_FIELDS = ("report_id", "period_type", "original_text")


def _missing_field_errors(record):
    boundary = record["boundary"]
    expected_boundary = {f"boundary.{key}" for key in BOUNDARY_FIELDS if boundary.get(key) is None}
    actual_boundary = set(boundary["missing_fields"])
    expected_record = expected_boundary | {
        key for key in RECORD_NULLABLE_FIELDS if record.get(key) is None
    }
    actual_record = set(record["missing_fields"])
    errors = []
    for field, expected, actual in (
        ("boundary.missing_fields", expected_boundary, actual_boundary),
        ("missing_fields", expected_record, actual_record),
    ):
        if expected != actual:
            errors.append(
                f"{field} không khớp giá trị null: thiếu {sorted(expected - actual)}; "
                f"khai báo thừa {sorted(actual - expected)}"
            )
    return errors


def _check_identity(record, claim, source_dir, source_cache):
    errors = []
    for field in ("company_id", "report_year"):
        if record[field] != claim[field]:
            errors.append(f"{field}={record[field]!r} khác claim hiện có {claim[field]!r}")
    evidence = next(
        (item for item in claim.get("evidence", []) if item.get("evidence_id") == record["evidence_id"]),
        None,
    )
    if evidence is None:
        return [f"evidence_id={record['evidence_id']!r} không thuộc claim_id này"] + errors
    for field in ("source_file", "source_pages", "json_pointer"):
        if record[field] != evidence.get(field):
            errors.append(f"{field}={record[field]!r} khác evidence hiện có {evidence.get(field)!r}")
    # The stored ESG extract is a second check on the pointer and value. It is
    # never regenerated here, because normalizer.normalize() writes output/.
    source_file = evidence.get("source_file")
    if isinstance(source_file, str):
        path = source_dir / source_file
        if not path.is_file():
            errors.append(f"không tìm thấy dữ liệu ESG hiện có: {source_file}")
        else:
            try:
                if path not in source_cache:
                    source_cache[path] = load_json(path)
                value = resolve_pointer(source_cache[path], evidence["json_pointer"])
                if value != claim.get("value") or type(value) is not type(claim.get("value")):
                    errors.append("json_pointer trong ESG hiện có không trỏ tới value của claim")
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                errors.append(f"json_pointer không phân giải được trong dữ liệu ESG: {exc}")
    return errors


def preflight(handoff_path, claims_path=DEFAULT_CLAIMS, source_dir=None):
    """Return a report without changing the handoff, claims, graph, or output/."""
    handoff = load_json(handoff_path)
    schema = load_json(SCHEMA)
    claims = load_json(claims_path)
    source_dir = Path(source_dir) if source_dir is not None else find_source_dir()
    if not isinstance(claims, list):
        raise ValueError("normalized_claims.json phải là một danh sách claim")
    claim_index = {claim["claim_id"]: claim for claim in claims}
    report = {
        "handoff_file": str(handoff_path),
        "claims_file": str(claims_path),
        "dry_run": True,
        "valid_records": [],
        "manual_review_records": [],
        "blocking_records": [],
    }
    validator = Draft202012Validator(schema)
    if not isinstance(handoff, dict):
        report["blocking_records"].append({
            "claim_id": "<handoff>", "evidence_id": None,
            "reasons": ["JSON gốc phải là object theo schema handoff"],
        })
        report["summary"] = {"records": 0, "valid": 0, "manual_review": 0, "blocking": 1}
        return report
    records = handoff.get("records")
    if not isinstance(records, list):
        report["blocking_records"].append({
            "claim_id": "<handoff>", "evidence_id": None,
            "reasons": ["records phải là một danh sách theo schema handoff"],
        })
        records = []
    for error in validator.iter_errors(handoff):
        if not error.absolute_path or error.absolute_path[0] != "records":
            report["blocking_records"].append({
                "claim_id": "<handoff>", "evidence_id": None,
                "reasons": [f"schema {list(error.absolute_path)}: {error.message}"],
            })
    schema_errors = {}
    for error in validator.iter_errors(handoff):
        path = list(error.absolute_path)
        if len(path) >= 2 and path[0] == "records" and isinstance(path[1], int):
            schema_errors.setdefault(path[1], []).append(
                f"schema {path[2:]}: {error.message}"
            )
    seen_pairs = set()
    evidence_bindings = {}
    source_cache = {}
    for index, record in enumerate(records):
        ref = record.get("claim_id", f"row:{index + 1}") if isinstance(record, dict) else f"row:{index + 1}"
        evidence_id = record.get("evidence_id") if isinstance(record, dict) else None
        item = {"claim_id": ref, "evidence_id": evidence_id, "reasons": []}
        errors = schema_errors.get(index, [])[:]
        review = []
        if errors or not isinstance(record, dict):
            item["reasons"] = errors
            report["blocking_records"].append(item)
            continue
        pair = (ref, evidence_id)
        if pair in seen_pairs:
            errors.append("cặp claim_id/evidence_id bị trùng trong handoff")
        seen_pairs.add(pair)
        binding = (record["source_file"], tuple(record["source_pages"]), record["json_pointer"])
        if evidence_id in evidence_bindings and evidence_bindings[evidence_id] != binding:
            errors.append("evidence_id được dùng lại với source_file/source_pages/json_pointer khác")
        evidence_bindings[evidence_id] = binding
        claim = claim_index.get(ref)
        if claim is None:
            errors.append("claim_id không tồn tại trong normalized_claims.json")
        else:
            errors.extend(_check_identity(record, claim, source_dir, source_cache))
            metric_year = record.get("metric_period_year")
            observation_year = claim.get("observation_year")
            if metric_year is not None and metric_year != observation_year:
                errors.append(
                    f"metric_period_year={metric_year} khác observation_year={observation_year} của claim"
                )
            elif metric_year is None and observation_year != claim.get("report_year"):
                review.append(
                    f"claim có metric_period_year={observation_year} trong báo cáo {claim['report_year']}; "
                    "handoff cần ghi rõ năm của chỉ tiêu"
                )
        errors.extend(_missing_field_errors(record))
        boundary = record["boundary"]
        boundary_status = boundary["status"]
        if boundary_status == "verified" and any(boundary.get(key) is None for key in BOUNDARY_FIELDS):
            errors.append("boundary.status=verified nhưng còn field boundary=null")
        if record.get("reporting_boundary_verified") is True:
            if boundary_status != "verified" or any(boundary.get(key) is None for key in BOUNDARY_FIELDS):
                errors.append(
                    "reporting_boundary_verified=true đòi hỏi boundary.status=verified "
                    "và đủ các field boundary; extraction_status không xác minh boundary"
                )
            else:
                review.append("cần đối chiếu bằng người căn cứ và trang PDF của reporting boundary")
        elif boundary_status != "verified":
            review.append(f"reporting boundary chưa xác minh đầy đủ (status={boundary_status})")
        else:
            review.append("boundary.status=verified nhưng reporting_boundary_verified chưa được xác nhận")
        original_text = record.get("original_text")
        text_type = record.get("original_text_type")
        if original_text is None:
            if record.get("original_text_verbatim") is True:
                errors.append("original_text_verbatim=true nhưng original_text=null")
            review.append("chưa có original_text để đối chiếu PDF")
        else:
            if text_type in {"table_interpretation", "chart_interpretation", "paraphrase"}:
                if record.get("original_text_verbatim") is True:
                    errors.append("câu diễn giải bảng/biểu đồ không thể khai báo trích nguyên văn")
                review.append("original_text là diễn giải; cần đối chiếu bảng/biểu đồ gốc")
            else:
                review.append("chưa xác minh máy móc original_text là trích nguyên văn PDF")
        if errors:
            item["reasons"] = errors
            report["blocking_records"].append(item)
        else:
            report["valid_records"].append({"claim_id": ref, "evidence_id": evidence_id, "reasons": []})
            if review:
                item["reasons"] = review
                report["manual_review_records"].append(item)
    report["summary"] = {
        "records": len(records),
        "valid": len(report["valid_records"]),
        "manual_review": len(report["manual_review_records"]),
        "blocking": len(report["blocking_records"]),
    }
    return report


def format_report(report):
    counts = report["summary"]
    lines = [
        f"Preflight dry-run: {report['handoff_file']}",
        f"Records: {counts['records']} | hợp lệ cấu trúc/provenance: {counts['valid']} | cần rà: "
        f"{counts['manual_review']} | chặn nhập: {counts['blocking']}",
        "Danh sách cần rà là tập con của record hợp lệ; chưa record nào được nhập vào snapshot.",
    ]
    for title, key in (
        ("HỢP LỆ", "valid_records"),
        ("CẦN RÀ THỦ CÔNG", "manual_review_records"),
        ("LỖI CHẶN NHẬP", "blocking_records"),
    ):
        lines.append(f"\n{title} ({len(report[key])})")
        for item in report[key]:
            lines.append(f"- {item['claim_id']} / {item['evidence_id'] or '?'}")
            lines.extend(f"  · {reason}" for reason in item["reasons"])
    return "\n".join(lines)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("handoff", type=Path, help="Extract handoff JSON path")
    parser.add_argument("--claims", type=Path, default=DEFAULT_CLAIMS)
    parser.add_argument("--json", action="store_true", help="Print machine-readable report to stdout")
    args = parser.parse_args(argv)
    try:
        report = preflight(args.handoff, args.claims)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        parser.exit(2, f"Preflight không đọc được input: {exc}\n")
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report))
    return 2 if report["summary"]["blocking"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
