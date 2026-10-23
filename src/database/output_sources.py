from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from src.extraction.claims import classify_claim, extract_attributes


BSR_DOCUMENTS = (
    "BSR_2023", "BSR_2024", "BSR_2025",
    "BCTC_BSR_2023", "BCTC_BSR_2024", "BCTC_BSR_2025",
)


@dataclass(frozen=True)
class OutputDocument:
    stem: str
    year: int
    document_type: str
    page_json: Path
    chunk_dir: Path
    structured_json: Path
    summary_md: Path


def discover_output_documents(output_root: Path) -> list[OutputDocument]:
    documents: list[OutputDocument] = []
    for stem in BSR_DOCUMENTS:
        match = re.search(r"(20\d{2})$", stem)
        if not match:
            continue
        document_type = "financial_statements" if stem.startswith("BCTC_") else "ESG"
        item = OutputDocument(
            stem=stem,
            year=int(match.group(1)),
            document_type=document_type,
            page_json=output_root / "json" / f"{stem}.json",
            chunk_dir=output_root / "chunks" / stem,
            structured_json=output_root / "esg" / f"{stem}_esg.json",
            summary_md=output_root / "esg" / f"{stem}_esg_summary.md",
        )
        if item.page_json.exists() and item.structured_json.exists():
            documents.append(item)
    return documents


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def page_rows(document: OutputDocument) -> list[dict]:
    payload = read_json(document.page_json)
    rows = []
    for page in payload.get("pages", []):
        text = str(page.get("text") or "").strip()
        rows.append({
            "page_number": int(page.get("page_number") or len(rows) + 1),
            "source_text": text,
            "confidence": 0.92 if text else 0.35,
        })
    return rows


def artifact_rows(document: OutputDocument) -> list[dict]:
    rows: list[dict] = []
    candidates = [(document.page_json, "PAGE_JSON"), (document.structured_json, "STRUCTURED_ESG_JSON"), (document.summary_md, "SUMMARY_MD")]
    candidates.extend((path, "CHUNK_JSON") for path in sorted(document.chunk_dir.glob("chunk_*.json")))
    manifest = document.chunk_dir / "manifest.json"
    if manifest.exists():
        candidates.append((manifest, "CHUNK_MANIFEST"))
    for path, kind in candidates:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        page_start = page_end = None
        record_count = None
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(text)
                page_range = payload.get("page_range") if isinstance(payload, dict) else None
                if isinstance(page_range, list) and page_range:
                    page_start, page_end = int(page_range[0]), int(page_range[-1])
                pages = payload.get("pages") if isinstance(payload, dict) else None
                if isinstance(pages, list):
                    record_count = len(pages)
            except (ValueError, TypeError):
                pass
        rows.append({
            "artifact_type": kind,
            "source_path": str(path.resolve()),
            "content_text": text,
            "sha256": sha256(path),
            "page_start": page_start,
            "page_end": page_end,
            "record_count": record_count,
        })
    return rows


def _ascii_key(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def infer_output_metric(text: str) -> str | None:
    key = _ascii_key(text)
    if ("intensity" in key or "cuong_do" in key) and any(x in key for x in ("ghg", "co2", "phat_thai")):
        return "GHG_INTENSITY"
    if any(x in key for x in ("scope_1_plus_2", "scope_1_2", "total_scope")):
        return None
    if any(x in key for x in ("scope_1", "scope1", "phat_thai_truc_tiep")):
        return "GHG_SCOPE_1"
    if any(x in key for x in ("scope_2", "scope2", "phat_thai_gian_tiep")):
        return "GHG_SCOPE_2"
    if any(x in key for x in ("total_energy_gj", "tong_nang_luong", "energy_consumption", "energy_total")):
        return "ENERGY_TOTAL"
    if any(x in key for x in ("water_withdrawal", "seawater_withdrawal", "freshwater_use", "nuoc_khai_thac", "nuoc_dau_vao")):
        return "WATER_WITHDRAWAL"
    if any(x in key for x in ("water_discharge", "wastewater_treated", "nuoc_thai", "nuoc_xa")):
        return "WATER_DISCHARGE"
    if any(x in key for x in ("non_hazardous_waste", "chat_thai_khong_nguy_hai")):
        return "NON_HAZ_WASTE"
    if any(x in key for x in ("hazardous_waste", "chat_thai_nguy_hai")):
        return "HAZARDOUS_WASTE"
    if any(x in key for x in ("spill_count", "oil_spill", "tran_dau")):
        return "SPILL_COUNT"
    if "ltifr" in key:
        return "LTIFR"
    if any(x in key for x in ("trir", "work_related_injury_rate")):
        return "TRIR"
    if any(x in key for x in ("training_hours_per_person", "hse_training_hours_per_person", "gio_dao_tao_binh_quan")):
        return "TRAINING_HOURS"
    if any(x in key for x in ("environmental_capex", "environment_investment", "dau_tu_moi_truong")):
        return "ENV_CAPEX"
    if any(x in key for x in ("environmental_protection_cost", "waste_treatment_cost", "environmental_expense", "chi_phi_moi_truong")):
        return "ENV_EXPENSE"
    if any(x in key for x in ("environmental_fine", "material_fines", "phat_moi_truong")):
        return "ENV_FINE"
    if any(x in key for x in ("tax_paid", "income_tax_paid", "state_budget_contribution", "nop_ngan_sach")):
        return "TAX_PAID"
    return None


def infer_unit(key: str, explicit: Any = None) -> str | None:
    if isinstance(explicit, str) and explicit.strip():
        aliases = {"VND billion": "billion_VND", "billion VND": "billion_VND", "million VND": "million_VND", "tonnes": "tấn"}
        return aliases.get(explicit.strip(), explicit.strip())
    name = _ascii_key(key)
    if "billion_vnd" in name: return "billion_VND"
    if "million_vnd" in name: return "million_VND"
    if name.endswith("_vnd") or "_vnd_" in name: return "VND"
    if "kgco2e_per_tonne" in name: return "kgCO2e/tấn sản phẩm"
    if "tco2e_per_tonne" in name: return "tCO2e/tấn sản phẩm"
    if "tco2e" in name: return "tCO2e"
    if name.endswith("_gj") or "_gj_" in name: return "GJ"
    if "m3" in name: return "m3"
    if "tonnes" in name or name.endswith("_tonne"): return "tấn"
    if "percent" in name or "percentage" in name: return "%"
    if "hours_per_person" in name: return "giờ/người/năm"
    if name in {"ltifr", "trir", "work_related_injury_rate"}: return "ca/triệu giờ công"
    if "spill_count" in name or name in {"oil_spill", "oil_spills"}: return "vụ"
    if "hazardous_waste" in name: return "tấn"
    if "count" in name or "cases" in name or "incidents" in name: return "vụ"
    return None


def _first_page(node: dict, inherited: int | None = None) -> int:
    for key in ("pdf_page", "source_page", "page_number"):
        value = node.get(key)
        if isinstance(value, (int, float)): return int(value)
    for key in ("pdf_pages", "source_pages", "source_pages_pdf"):
        value = node.get(key)
        if isinstance(value, list) and value:
            try: return int(value[0])
            except (ValueError, TypeError): pass
        if isinstance(value, (int, float)): return int(value)
    return inherited or 1


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None: return None
    if isinstance(value, (int, float)): return float(value)
    if not isinstance(value, str): return None
    match = re.fullmatch(r"\s*(-?\d[\d., ]*)\s*", value)
    if not match: return None
    token = match.group(1).replace(" ", "")
    if "," in token and "." in token:
        token = token.replace(".", "").replace(",", ".")
    elif "," in token:
        parts = token.split(",")
        token = "".join(parts) if len(parts[-1]) == 3 else ".".join(parts)
    elif token.count(".") > 1:
        token = token.replace(".", "")
    try: return float(token)
    except ValueError: return None


def _pillar(path: tuple[str, ...], document_type: str) -> str:
    root = _ascii_key(path[0]) if path else ""
    if root == "environment": return "E"
    if root == "social": return "S"
    if root in {"governance", "financial_context", "financial_and_economic_value", "audit_and_assurance"}: return "G"
    return "G" if document_type == "financial_statements" else "X"


def _topic(metric_code: str | None, path: tuple[str, ...], pillar: str) -> str:
    by_metric = {
        "GHG_SCOPE_1":"E_CLIMATE", "GHG_SCOPE_2":"E_CLIMATE", "GHG_INTENSITY":"E_CLIMATE",
        "ENERGY_TOTAL":"E_ENERGY", "WATER_WITHDRAWAL":"E_WATER", "WATER_DISCHARGE":"E_WATER",
        "HAZARDOUS_WASTE":"E_WASTE", "NON_HAZ_WASTE":"E_WASTE", "SPILL_COUNT":"E_SPILLS",
        "LTIFR":"S_SAFETY", "TRIR":"S_SAFETY", "TRAINING_HOURS":"S_TRAINING",
        "ENV_CAPEX":"E_INVESTMENT", "ENV_EXPENSE":"E_INVESTMENT", "ENV_FINE":"G_COMPLIANCE", "TAX_PAID":"G_TAX",
    }
    if metric_code in by_metric: return by_metric[metric_code]
    key = _ascii_key("_".join(path[-2:]))[:48].upper() or "OTHER"
    return f"{pillar}_{key}" if not key.startswith(f"{pillar}_") else key


def iter_structured_facts(document: OutputDocument) -> Iterator[dict]:
    payload = read_json(document.structured_json)
    seen: set[tuple] = set()

    def walk(node: Any, path: tuple[str, ...] = (), inherited_page: int | None = None):
        if isinstance(node, dict):
            page = _first_page(node, inherited_page)
            pillar = _pillar(path, document.document_type)
            label = str(node.get("metric") or node.get("topic") or path[-1] if path else "ESG disclosure")
            context = " ".join(path + (label, str(node.get("claim") or ""), str(node.get("description") or "")))
            metric_code = infer_output_metric(context)

            claim_text = node.get("claim") or node.get("description") or node.get("detail")
            if isinstance(claim_text, str) and len(claim_text.strip()) >= 15:
                fingerprint = ("claim", page, claim_text.strip().lower())
                if fingerprint not in seen:
                    seen.add(fingerprint)
                    yield {"kind":"claim", "page":page, "pillar":pillar, "topic":_topic(metric_code,path,pillar), "metric_code":metric_code, "text":claim_text.strip(), "value":None, "unit":None, "path":".".join(path)}

            if metric_code and "value" in node:
                value = _number(node.get("value"))
                unit = infer_unit(context, node.get("unit"))
                if value is not None:
                    text = f"{label}: {value:g} {unit or ''}".strip()
                    fingerprint = ("metric", metric_code, page, value, unit, node.get("year") or document.year)
                    if fingerprint not in seen:
                        seen.add(fingerprint)
                        yield {"kind":"metric", "page":page, "pillar":pillar, "topic":_topic(metric_code,path,pillar), "metric_code":metric_code, "text":text, "value":value, "unit":unit, "year":int(node.get("year") or document.year), "path":".".join(path)}

            for key, value in node.items():
                # Scalar fields are classified from their own key. Using the
                # full parent path can turn spill-response equipment counts or
                # production denominators into the parent's ESG metric.
                code = infer_output_metric(key)
                number = _number(value)
                if code and number is not None and key not in {"value", "year", "pdf_page", "source_page", "page_number"}:
                    unit = infer_unit(key, node.get("unit") if key in {"value", "metric"} else None)
                    if unit == "%" and code not in {"SPILL_COUNT", "LTIFR", "TRIR"}:
                        continue
                    text = f"{key}: {number:g} {unit or ''}".strip()
                    fingerprint = ("metric", code, page, number, unit, document.year, key)
                    if fingerprint not in seen:
                        seen.add(fingerprint)
                        yield {"kind":"metric", "page":page, "pillar":pillar, "topic":_topic(code,path+(key,),pillar), "metric_code":code, "text":text, "value":number, "unit":unit, "year":document.year, "path":".".join(path+(key,))}
                yield from walk(value, path + (key,), page)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                yield from walk(value, path + (str(index),), inherited_page)

    yield from walk(payload)


def summary_claim_rows(document: OutputDocument) -> list[dict]:
    """Return human-readable claims from curated summaries, excluding QA notes."""
    if not document.summary_md.exists():
        return []
    rows: list[dict] = []
    pillar: str | None = None
    for raw_line in document.summary_md.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if line.startswith("## "):
            heading = _ascii_key(line[3:])
            if any(x in heading for x in ("doi_soat", "luu_y_su_dung", "diem_phai")):
                pillar = None
            elif any(x in heading for x in ("moi_truong", "environment")) or heading.startswith("e_"):
                pillar = "E"
            elif any(x in heading for x in ("xa_hoi", "nguoi_lao_dong", "social")) or heading.startswith("s_"):
                pillar = "S"
            elif any(x in heading for x in ("quan_tri", "tai_chinh", "dam_bao", "financial", "governance")) or heading.startswith("g_"):
                pillar = "G"
            else:
                pillar = None
            continue
        if not pillar or not line.startswith("- "):
            continue
        text = line[2:].strip()
        if len(text) < 20:
            continue
        pages = re.search(r"trang(?:\s+PDF)?\s+([0-9]+)", text, flags=re.I)
        page = int(pages.group(1)) if pages else 1
        metric_code = infer_output_metric(text)
        attributes = extract_attributes(text)
        rows.append({
            "kind": "claim",
            "page": page,
            "pillar": pillar,
            "topic": _topic(metric_code, (pillar, "summary"), pillar),
            "metric_code": metric_code,
            "text": text,
            "value": attributes.get("raw_value"),
            "unit": attributes.get("raw_unit"),
            "path": "summary_md",
        })
    return rows


def output_manifest(output_root: Path) -> dict:
    documents = discover_output_documents(output_root)
    result = {"document_count": len(documents), "page_count": 0, "chunk_count": 0, "structured_fact_count": 0, "summary_count": 0}
    for doc in documents:
        result["page_count"] += len(page_rows(doc))
        result["chunk_count"] += len(list(doc.chunk_dir.glob("chunk_*.json")))
        result["structured_fact_count"] += sum(1 for _ in iter_structured_facts(doc))
        result["summary_count"] += int(doc.summary_md.exists())
    return result
