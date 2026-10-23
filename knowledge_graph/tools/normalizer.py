import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def resolve_pointer(document, pointer):
    value = document
    for token in pointer.lstrip("/").split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        value = value[int(token)] if isinstance(value, list) else value[token]
    return value


def stable_id(item):
    key = "|".join(str(item[k]) for k in (
        "company_id", "source_path", "source_pointer", "metric_id",
        "observation_year", "scope", "variant"
    ))
    return "CLM-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()


def evidence_id(item):
    key = f"{Path(item['source_path']).name}|{item['source_pointer']}|{item['source_pages']}"
    return "EVD-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12].upper()


def expected_evidence_class(claim_type):
    if claim_type == "governance_statement":
        return "governance_disclosure"
    if claim_type == "target":
        return "target_disclosure"
    return "quantitative_disclosure"


def find_source_dir():
    candidate = ROOT / "data" / "extract" / "esg"
    if candidate.exists():
        return candidate
    raise FileNotFoundError("Không tìm thấy data/extract/esg/")


def normalize(output_dir=None):
    source_dir = find_source_dir()
    selection = load_json(ROOT / "data" / "config" / "selection.json")
    document_cache = {}
    records = []

    for item in selection:
        source_path = source_dir / Path(item["source_path"]).name
        if source_path not in document_cache:
            document_cache[source_path] = load_json(source_path)
        document = document_cache[source_path]
        value = resolve_pointer(document, item["source_pointer"])
        report_year = int(Path(item["source_path"]).stem.split("_")[1])

        record = {
            "schema_version": "1.0",
            "claim_id": stable_id(item),
            "selection_id": item["selection_id"],
            "company_id": item["company_id"],
            "company_name": document.get("document", {}).get("company", item["company_id"]),
            "report_year": report_year,
            "observation_year": item["observation_year"],
            "dimension": item["dimension"],
            "topic": item["topic"],
            "claim_type": item["claim_type"],
            "expected_evidence_class": expected_evidence_class(item["claim_type"]),
            "metric_id": item["metric_id"],
            "label": item["label"],
            "value": value,
            "unit": item["unit"],
            "scope": item["scope"],
            "variant": item["variant"],
            "review_status": "unreviewed",
            "evidence": [{
                "evidence_id": evidence_id(item),
                "source_file": Path(item["source_path"]).name,
                "source_pages": item["source_pages"],
                "json_pointer": item["source_pointer"],
                "source_text": None
            }]
        }
        for key in ("direction", "realization"):
            if key in item:
                record[key] = item[key]
        records.append(record)

    output_dir = Path(output_dir) if output_dir else ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "normalized_claims.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    columns = ["claim_id", "company_id", "report_year", "observation_year",
               "dimension", "topic", "claim_type", "metric_id", "label",
               "value", "unit", "scope", "variant", "source_file", "source_pages"]
    with (output_dir / "normalized_claims.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for record in records:
            row = {key: record.get(key) for key in columns}
            row["source_file"] = record["evidence"][0]["source_file"]
            row["source_pages"] = ",".join(map(str, record["evidence"][0]["source_pages"]))
            writer.writerow(row)
    return records


if __name__ == "__main__":
    result = normalize()
    print(f"Đã chuẩn hóa {len(result)} claim vào output/normalized_claims.json")
