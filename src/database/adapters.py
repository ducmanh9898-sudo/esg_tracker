from __future__ import annotations

import json
import re
from pathlib import Path

from src.extraction.claims import classify_claim, extract_attributes


METRIC_KEYWORDS = {
    "GHG_SCOPE_1": ("scope 1", "phạm vi 1", "phát thải trực tiếp"),
    "GHG_SCOPE_2": ("scope 2", "phạm vi 2"),
    "GHG_INTENSITY": ("cường độ", "co2e trên sản phẩm"),
    "ENERGY_TOTAL": ("năng lượng", "eii"),
    "WATER_WITHDRAWAL": ("nước biển", "nước ngọt", "nước khai thác", "water withdrawal"),
    "WATER_DISCHARGE": ("nước thải", "nước xả", "wastewater"),
    "HAZARDOUS_WASTE": ("chất thải nguy hại",),
    "NON_HAZ_WASTE": ("chất thải", "waste"),
    "SPILL_COUNT": ("tràn dầu", "sự cố môi trường"),
    "LTIFR": ("mất ngày công", "ltifr"),
    "TRIR": ("thương tật", "trir"),
    "TRAINING_HOURS": ("đào tạo",),
    "ENV_CAPEX": ("capex", "đầu tư môi trường"),
    "ENV_EXPENSE": ("opex", "chi phí môi trường"),
    "ENV_FINE": ("phạt môi trường",),
    "TAX_PAID": ("nộp ngân sách", "thuế", "tax"),
}


def infer_metric_code(text: str) -> str | None:
    lower = (text or "").lower()
    for code, terms in METRIC_KEYWORDS.items():
        if any(term in lower for term in terms):
            return code
    return None


def pillar_for(dimension: str | None) -> str:
    value = (dimension or "X").upper()
    return value if value in {"E", "S", "G"} else "X"


def load_phase1_records(workspace_root: Path) -> list[dict]:
    records: list[dict] = []
    for filename in ("BSR_Phase1_Extract_Batch_v1.json", "BSR_Phase1_Extract_Financial_Crosscheck_v1.json"):
        path = workspace_root / filename
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        for item in payload.get("records", []):
            record = dict(item)
            record["adapter_source"] = filename
            records.append(record)
    return records


def numeric_value(value):
    if value is None or isinstance(value, (int, float)):
        return value
    text = str(value).strip()
    match = re.search(r"-?\d[\d. ]*(?:,\d+)?", text)
    if not match:
        return None
    token = match.group(0).replace(" ", "")
    if "," in token:
        token = token.replace(".", "").replace(",", ".")
    elif token.count(".") > 1:
        token = token.replace(".", "")
    try:
        return float(token)
    except ValueError:
        return None


def adapt_record(item: dict) -> dict:
    text = item.get("claim_text") or item.get("extraction_notes") or ""
    attributes = extract_attributes(text)
    code = infer_metric_code(" ".join(str(item.get(k) or "") for k in ("metric_name", "topic", "claim_text")))
    value = numeric_value(item.get("value"))
    return {
        "record_id": item["record_id"], "year": int(item["report_year"]),
        "report_type": item.get("report_type") or "UNKNOWN", "source_file": item.get("source_file") or "unknown",
        "page": int(re.search(r"\d+", str(item.get("source_page") or 1)).group()), "text": text, "pillar": pillar_for(item.get("dimension")),
        "topic": (item.get("topic") or "OTHER").upper().replace(" ", "_"), "metric_code": code,
        "claim_type": classify_claim(text), "value": value if value is not None else attributes["raw_value"],
        "unit": item.get("unit") or attributes["raw_unit"], "scope": item.get("scope"),
        "boundary": item.get("boundary"), "methodology": item.get("methodology"),
        "assurance_status": item.get("assurance_status"), "confidence": 0.72 if item.get("extraction_status") == "available" else 0.55,
        "ambiguity_note": item.get("ambiguity_note"), "extraction_method": "phase1_json_adapter",
    }
