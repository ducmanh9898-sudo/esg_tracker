from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import pymupdf
import yaml

from src.extraction.claims import classify_claim, extract_attributes


VALID_REPORT_TYPES = {"ESG", "annual_report", "financial_statements"}
REPORT_CODES = {"ESG": "ESG", "annual_report": "AR", "financial_statements": "FS"}

METRIC_DIMENSIONS = {
    "GHG_SCOPE_1": "E",
    "GHG_SCOPE_2": "E",
    "GHG_INTENSITY": "E",
    "ENERGY_TOTAL": "E",
    "WATER_WITHDRAWAL": "E",
    "WATER_DISCHARGE": "E",
    "HAZARDOUS_WASTE": "E",
    "NON_HAZ_WASTE": "E",
    "SPILL_COUNT": "E",
    "ENV_CAPEX": "E",
    "ENV_EXPENSE": "E",
    "LTIFR": "S",
    "TRIR": "S",
    "TRAINING_HOURS": "S",
    "ENV_FINE": "G",
    "TAX_PAID": "G",
}

METRIC_TOPICS = {
    "GHG_SCOPE_1": "E_CLIMATE",
    "GHG_SCOPE_2": "E_CLIMATE",
    "GHG_INTENSITY": "E_CLIMATE",
    "ENERGY_TOTAL": "E_ENERGY",
    "WATER_WITHDRAWAL": "E_WATER",
    "WATER_DISCHARGE": "E_WATER",
    "HAZARDOUS_WASTE": "E_WASTE",
    "NON_HAZ_WASTE": "E_WASTE",
    "SPILL_COUNT": "E_SPILLS",
    "ENV_CAPEX": "E_INVESTMENT",
    "ENV_EXPENSE": "E_INVESTMENT",
    "LTIFR": "S_SAFETY",
    "TRIR": "S_SAFETY",
    "TRAINING_HOURS": "S_TRAINING",
    "ENV_FINE": "G_COMPLIANCE",
    "TAX_PAID": "G_TAX",
}

UNIT_PATTERN = re.compile(
    r"(?<!\w)(-?\d[\d\s.,]*?)\s*"
    r"(tCO2e|kgCO2e|GJ|MWh|kWh|m[³3]|tấn|tonnes?|%|"
    r"tỷ\s*(?:đồng|VND)|triệu\s*(?:đồng|VND)|VND|"
    r"giờ(?:/người/năm)?|ca/triệu\s*giờ\s*công|vụ)(?!\w)",
    flags=re.IGNORECASE,
)

FINANCIAL_NUMBER_PATTERN = re.compile(
    r"^\(?-?\d{1,3}(?:[.,]\d{3}){2,}\)?$"
)

_OCR_ENGINE = None


@dataclass(frozen=True)
class DocumentSpec:
    source_path: Path
    company_id: str
    company_name: str
    industry: str
    subsector: str | None
    report_year: int
    report_type: str

    @property
    def document_key(self) -> str:
        return f"{self.company_id}_{self.report_year}_{REPORT_CODES[self.report_type]}"


def load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a mapping: {path}")
    return payload


def _ascii_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").upper()
    return re.sub(r"[^A-Z0-9]+", "_", ascii_text).strip("_")


def _normal_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_page_text(value: str) -> str:
    lines = [_normal_text(line) for line in str(value or "").splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _aliases(config: dict) -> list[tuple[str, str]]:
    values: list[tuple[str, str]] = []
    for company_id, company in config.get("companies", {}).items():
        for alias in [company_id, *(company.get("aliases") or [])]:
            values.append((_ascii_key(alias), company_id.upper()))
    return sorted(set(values), key=lambda item: len(item[0]), reverse=True)


def infer_company_id(path: Path, config: dict) -> str:
    stem_key = f"_{_ascii_key(path.stem)}_"
    for alias, company_id in _aliases(config):
        if f"_{alias}_" in stem_key:
            return company_id
    if not config.get("filename_rules", {}).get("allow_unknown_companies", False):
        raise ValueError(f"Unknown company in filename: {path.name}")
    tokens = [
        token
        for token in _ascii_key(path.stem).split("_")
        if token and token not in {"BCTC", "FS", "FINANCIAL", "STATEMENTS", "BCTN", "ANNUAL", "REPORT", "ESG", "PTBV", "SUSTAINABILITY"}
        and not re.fullmatch(r"20\d{2}", token)
        and not token.isdigit()
    ]
    if not tokens:
        raise ValueError(f"Cannot infer company from filename: {path.name}")
    return tokens[0]


def infer_year(path: Path) -> int:
    matches = re.findall(r"(?<!\d)(20\d{2})(?!\d)", path.stem)
    if not matches:
        raise ValueError(f"Cannot infer reporting year from filename: {path.name}")
    return int(matches[-1])


def infer_report_type(path: Path, config: dict) -> str:
    rules = config.get("filename_rules", {})
    stem = _ascii_key(path.stem)
    parent_names = {_ascii_key(parent.name) for parent in [path.parent, *path.parents[:2]]}

    def begins(prefixes: Iterable[str]) -> bool:
        return any(stem == _ascii_key(value) or stem.startswith(f"{_ascii_key(value)}_") for value in prefixes)

    def contains(prefixes: Iterable[str]) -> bool:
        padded = f"_{stem}_"
        return any(f"_{_ascii_key(value)}_" in padded for value in prefixes)

    def in_folder(folders: Iterable[str]) -> bool:
        return any(_ascii_key(value) in parent_names for value in folders)

    if begins(rules.get("financial_prefixes", [])) or contains(rules.get("financial_prefixes", [])) or in_folder(rules.get("financial_folders", [])):
        return "financial_statements"
    if begins(rules.get("annual_report_prefixes", [])) or contains(rules.get("annual_report_prefixes", [])) or in_folder(rules.get("annual_report_folders", [])):
        return "annual_report"
    if begins(rules.get("esg_prefixes", [])) or in_folder(rules.get("esg_folders", [])):
        return "ESG"
    return "ESG"


def build_document_spec(
    path: Path,
    config: dict,
    company_override: str | None = None,
    year_override: int | None = None,
    report_type_override: str | None = None,
) -> DocumentSpec:
    company_id = (company_override or infer_company_id(path, config)).upper()
    year = int(year_override or infer_year(path))
    report_type = report_type_override or infer_report_type(path, config)
    if report_type not in VALID_REPORT_TYPES:
        raise ValueError(f"Unsupported report type: {report_type}")
    company_registry = config.get("companies", {})
    company = company_registry.get(company_id, {})
    registered_company = company_id in company_registry
    return DocumentSpec(
        source_path=path.resolve(),
        company_id=company_id,
        company_name=company.get("name") or company_id,
        industry=company.get("industry") or (config.get("industry") if registered_company else "Unknown") or "Unknown",
        subsector=company.get("subsector"),
        report_year=year,
        report_type=report_type,
    )


def discover_pdfs(input_path: Path, config: dict | None = None) -> list[Path]:
    if input_path.is_file():
        return [input_path] if input_path.suffix.lower() == ".pdf" else []
    excluded = {
        _ascii_key(value)
        for value in (config or {}).get("filename_rules", {}).get("exclude_folders", [])
    }
    return sorted(
        path
        for path in input_path.rglob("*.pdf")
        if path.is_file()
        and path.stat().st_size > 0
        and not any(_ascii_key(parent.name) in excluded for parent in path.parents if parent != input_path.parent)
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _line_key(line: str) -> str:
    return _normal_text(line).casefold()


def repeated_lines(page_texts: list[str], ratio: float, minimum_pages: int) -> set[str]:
    counts: Counter[str] = Counter()
    for text in page_texts:
        unique = {_line_key(line) for line in text.splitlines() if len(_normal_text(line)) >= 20}
        counts.update(unique)
    threshold = max(minimum_pages, math.ceil(len(page_texts) * ratio))
    return {line for line, count in counts.items() if count >= threshold}


def strip_repeated_lines(text: str, repeated: set[str]) -> str:
    kept = [line for line in text.splitlines() if _line_key(line) not in repeated]
    return "\n".join(line.strip() for line in kept if line.strip()).strip()


def _sidecar_candidates(ocr_root: Path | None, stem: str, page_number: int) -> list[Path]:
    if ocr_root is None:
        return []
    names = [f"page-{page_number}.txt", f"page-{page_number:02d}.txt", f"page_{page_number}.txt"]
    return [
        *(ocr_root / stem / name for name in names),
        *(ocr_root / stem / "ocr" / name for name in names),
        *(ocr_root / name for name in names),
    ]


def _read_sidecar(ocr_root: Path | None, stem: str, page_number: int) -> str:
    for candidate in _sidecar_candidates(ocr_root, stem, page_number):
        if candidate.exists():
            return candidate.read_text(encoding="utf-8-sig", errors="replace").strip()
    return ""


def _automatic_ocr(page: pymupdf.Page, scale: float) -> str:
    global _OCR_ENGINE
    try:
        import numpy as np
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return ""
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    image = np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(
        pixmap.height, pixmap.width, pixmap.n
    )
    result, _ = _OCR_ENGINE(image)
    return "\n".join(item[1].strip() for item in (result or []) if item[1].strip())


def extract_pages(
    spec: DocumentSpec,
    extraction_config: dict,
    ocr_root: Path | None = None,
    max_pages: int | None = None,
    progress_callback=None,
) -> tuple[list[dict], dict]:
    minimum_chars = int(extraction_config.get("minimum_page_characters", 80))
    ratio = float(extraction_config.get("repeated_line_page_ratio", 0.25))
    minimum_pages = int(extraction_config.get("repeated_line_minimum_pages", 3))
    automatic_ocr = bool(extraction_config.get("automatic_ocr", True))
    ocr_scale = float(extraction_config.get("automatic_ocr_scale", 2.5))
    scan_text_threshold = int(extraction_config.get("scan_page_max_native_characters", 180))

    pdf = pymupdf.open(spec.source_path)
    page_limit = min(len(pdf), max_pages) if max_pages else len(pdf)
    native_texts = [_clean_page_text(pdf[index].get_text("text")) for index in range(page_limit)]
    repeated = repeated_lines(native_texts, ratio, minimum_pages)
    pages: list[dict] = []
    method_counts: Counter[str] = Counter()
    for index, native_text in enumerate(native_texts, start=1):
        if progress_callback:
            progress_callback({'stage': 'reading', 'page': index, 'page_total': page_limit, 'completed_pages': index - 1})
        cleaned_native = strip_repeated_lines(native_text, repeated)
        sidecar = _read_sidecar(ocr_root, spec.source_path.stem, index)
        likely_scanned = len(cleaned_native) < minimum_chars or (
            len(cleaned_native) <= scan_text_threshold and bool(pdf[index - 1].get_images(full=True))
        )
        automatic_text = ""
        if not sidecar and automatic_ocr and likely_scanned:
            if progress_callback:
                progress_callback({'stage': 'ocr', 'page': index, 'page_total': page_limit, 'completed_pages': index - 1})
            automatic_text = _automatic_ocr(pdf[index - 1], ocr_scale)
        if len(cleaned_native) >= minimum_chars and not likely_scanned:
            text = cleaned_native
            method = "pymupdf_text"
            status = "available"
            confidence = 0.92 if len(text) >= 500 else 0.80
        elif len(sidecar) >= minimum_chars:
            text = sidecar
            method = "ocr_sidecar"
            status = "available"
            confidence = 0.70
        elif len(automatic_text) >= minimum_chars:
            text = automatic_text
            method = "rapidocr_onnxruntime"
            status = "available"
            confidence = 0.68
        else:
            text = cleaned_native or sidecar or automatic_text
            method = "pymupdf_text" if cleaned_native else ("rapidocr_onnxruntime" if automatic_text else "none")
            status = "ocr_pending"
            confidence = 0.35 if text else 0.10
        method_counts[method] += 1
        pages.append({
            "page_number": index,
            "text": text,
            "character_count": len(text),
            "extraction_method": method,
            "extraction_status": status,
            "confidence": confidence,
        })
        if progress_callback:
            progress_callback({'stage': 'reading', 'page': index, 'page_total': page_limit, 'completed_pages': index})
    metadata = {
        "pdf_page_count": len(pdf),
        "processed_page_count": page_limit,
        "repeated_lines_removed": len(repeated),
        "method_counts": dict(method_counts),
    }
    pdf.close()
    return pages, metadata


def _metric_catalog(metrics_config: dict, toolkit_config: dict) -> dict[str, dict]:
    catalog: dict[str, dict] = {}
    for code, item in (metrics_config.get("metrics") or {}).items():
        catalog[code] = {
            "name": item.get("name") or code,
            "dimension": METRIC_DIMENSIONS.get(code, "X"),
            "topic": METRIC_TOPICS.get(code, f"X_{code}"),
            "standard_unit": item.get("standard_unit"),
            "variants": item.get("variants") or [],
        }
    for code, item in (toolkit_config.get("additional_metrics") or {}).items():
        catalog[code] = {
            "name": item.get("name") or code,
            "dimension": item.get("dimension") or "X",
            "topic": item.get("topic") or f"X_{code}",
            "standard_unit": item.get("standard_unit"),
            "variants": item.get("variants") or [],
        }
    return catalog


def infer_metrics(text: str, catalog: dict[str, dict]) -> list[str]:
    plain = _normal_text(text).casefold()
    ascii_text = _ascii_key(text).casefold()
    matches: list[tuple[int, str]] = []
    for code, item in catalog.items():
        best = 0
        for variant in item.get("variants", []):
            raw = _normal_text(variant).casefold()
            key = _ascii_key(variant).casefold()
            if raw and raw in plain or key and key in ascii_text:
                best = max(best, len(raw), len(key))
        if best:
            matches.append((best, code))
    matches.sort(key=lambda item: (-item[0], item[1]))
    return [code for _, code in matches]


def _parse_number(token: str) -> float | None:
    value = token.replace(" ", "").strip()
    if not value:
        return None
    sign = -1 if value.startswith("-") else 1
    value = value.lstrip("-")
    separators = [separator for separator in (".", ",") if separator in value]
    if len(separators) == 2:
        last = max(value.rfind("."), value.rfind(","))
        decimals = len(value) - last - 1
        if decimals in {1, 2}:
            decimal_sep = value[last]
            other = "," if decimal_sep == "." else "."
            value = value.replace(other, "").replace(decimal_sep, ".")
        else:
            value = value.replace(".", "").replace(",", "")
    elif separators:
        separator = separators[0]
        parts = value.split(separator)
        if len(parts) > 2 or all(len(part) == 3 for part in parts[1:]):
            value = "".join(parts)
        else:
            value = value.replace(separator, ".")
    try:
        return sign * float(value)
    except ValueError:
        return None


def extract_measurements(text: str) -> list[dict]:
    values: list[dict] = []
    for match in UNIT_PATTERN.finditer(text):
        number = _parse_number(match.group(1))
        if number is None:
            continue
        unit = re.sub(r"\s+", " ", match.group(2)).strip()
        values.append({"raw": match.group(0).strip(), "value": number, "unit": unit})
    return values


def _compact_ascii(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    plain = normalized.encode("ascii", "ignore").decode("ascii").casefold()
    return re.sub(r"[^a-z0-9]+", "", plain)


def infer_financial_statement_scope(pages: list[dict], source_name: str = "") -> str | None:
    separate_markers = ("baocaotaichinhrieng", "bctcrieng", "separatefinancialstatements")
    consolidated_markers = ("baocaotaichinhhopnhat", "bctchopnhat", "consolidatedfinancialstatements")
    samples = [source_name, *(str(page.get("text") or "") for page in pages[:15])]
    separate_score = sum(any(marker in _compact_ascii(sample) for marker in separate_markers) for sample in samples)
    consolidated_score = sum(any(marker in _compact_ascii(sample) for marker in consolidated_markers) for sample in samples)
    if separate_score > consolidated_score:
        return "Separate"
    if consolidated_score > separate_score:
        return "Consolidated"
    return None


def _financial_number(value: str) -> int | None:
    token = _normal_text(value).replace(" ", "")
    if not FINANCIAL_NUMBER_PATTERN.fullmatch(token):
        return None
    negative = token.startswith("(") and token.endswith(")")
    digits = re.sub(r"\D", "", token)
    if not digits:
        return None
    number = int(digits)
    return -number if negative else number


def extract_financial_table_claims(
    spec: DocumentSpec,
    pages: list[dict],
    catalog: dict[str, dict],
    financial_scope: str | None,
) -> list[dict]:
    wanted = {code: item for code, item in catalog.items() if code.startswith("FIN_")}
    candidates: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    statement_markers = {
        "FIN_TOTAL_ASSETS": "bangcandoiketoan",
        "FIN_REVENUE": "baocaoketquahoatdongkinhdoanh",
        "FIN_PAT": "baocaoketquahoatdongkinhdoanh",
        "FIN_OPERATING_CASH_FLOW": "baocaoluuchuyentiente",
    }
    for page in pages:
        page_text = str(page.get("text") or "")
        page_compact = _compact_ascii(page_text)
        if "vnd" not in page_compact:
            continue
        lines = [_normal_text(line) for line in page_text.splitlines() if _normal_text(line)]
        for line_index in range(len(lines)):
            raw_label = lines[line_index]
            if _financial_number(raw_label) is not None or not re.search(r"[A-Za-zÀ-ỹ]", raw_label):
                continue
            label_compact = _compact_ascii(raw_label)
            for code, metric in wanted.items():
                required_label = {
                    "FIN_TOTAL_ASSETS": "tongcongtaisan" in label_compact or "tongtaisan" in label_compact,
                    "FIN_REVENUE": "doanhthu" in label_compact and ("banhang" in label_compact or "thuan" in label_compact),
                    "FIN_PAT": "nhuansauthue" in label_compact or "profitaftertax" in label_compact,
                    "FIN_OPERATING_CASH_FLOW": "luuchuyentienthuan" in label_compact or "netcashfromoperating" in label_compact,
                }.get(code)
                if required_label is False:
                    continue
                variants = [_compact_ascii(value) for value in metric.get("variants", [])]
                exact_lengths = [len(variant) for variant in variants if len(variant) >= 8 and variant in label_compact]
                fuzzy_score = 0
                if not exact_lengths:
                    try:
                        from rapidfuzz.fuzz import partial_ratio
                        fuzzy_score = max((int(partial_ratio(variant, label_compact)) for variant in variants if len(variant) >= 8), default=0)
                    except ImportError:
                        fuzzy_score = 0
                if not exact_lengths and fuzzy_score < 82:
                    continue
                values: list[tuple[str, int]] = []
                for raw in lines[line_index + 1:line_index + 14]:
                    parsed = _financial_number(raw)
                    if parsed is not None:
                        values.append((raw, parsed))
                    if len(values) == 2:
                        break
                if len(values) < 2:
                    continue
                current_raw, current_value = values[0]
                prior_raw, prior_value = values[1]
                record = {
                    "record_id": "",
                    "company_id": spec.company_id,
                    "company_name": spec.company_name,
                    "industry": spec.industry,
                    "subsector": spec.subsector,
                    "report_year": spec.report_year,
                    "report_type": spec.report_type,
                    "financial_statement_scope": financial_scope,
                    "source_file": spec.source_path.name,
                    "source_page": int(page["page_number"]),
                    "dimension": metric.get("dimension") or "X",
                    "topic": metric.get("topic") or "X_FINANCIAL_CONTEXT",
                    "claim_text": f"{raw_label} | Năm nay/Số cuối năm: {current_raw} | Năm trước/Số đầu năm: {prior_raw} | Đơn vị: VND",
                    "claim_type": "reported_actual",
                    "evidence_type": ["metric", "financial_table_row"],
                    "metric_code": code,
                    "metric_candidates": [code],
                    "metric_name": metric.get("name") or code,
                    "value": current_value,
                    "unit": "VND",
                    "measurements": [
                        {"period": spec.report_year, "value": current_value, "unit": "VND"},
                        {"period": spec.report_year - 1, "value": prior_value, "unit": "VND"},
                    ],
                    "comparison": {"year": spec.report_year - 1, "value": prior_value, "unit": "VND"},
                    "target": None,
                    "target_year": None,
                    "baseline_year": None,
                    "scope": "Báo cáo tài chính riêng" if financial_scope == "Separate" else ("Báo cáo tài chính hợp nhất" if financial_scope == "Consolidated" else None),
                    "boundary": financial_scope,
                    "methodology": "Financial table row extraction; VND inherited from the page-level table header.",
                    "assurance_status": None,
                    "extraction_method": page["extraction_method"],
                    "extraction_status": "available",
                    "review_status": "unreviewed",
                    "confidence": min(float(page["confidence"]), 0.82),
                    "ambiguity_note": None if financial_scope else "Separate/consolidated scope was not identified from the report title.",
                    "extraction_notes": "Current and comparative values were linked by table order; human validation is required.",
                }
                score = (max(exact_lengths) if exact_lengths else fuzzy_score) + 40 * int(statement_markers.get(code, "") in page_compact)
                if code == "FIN_TOTAL_ASSETS" and "tongcongtaisan" in label_compact:
                    score += 50
                if code == "FIN_PAT" and "thunhap" in label_compact:
                    score += 30
                if code == "FIN_OPERATING_CASH_FLOW" and "luuchuyentienthuan" in label_compact:
                    score += 30
                candidates[code].append((score, record))
    claims = [max(items, key=lambda item: item[0])[1] for _, items in sorted(candidates.items()) if items]
    for sequence, item in enumerate(claims, start=1):
        item["record_id"] = f"{spec.company_id}-{REPORT_CODES[spec.report_type]}-{spec.report_year}-{sequence:05d}"
    return claims


def split_candidates(text: str, minimum: int, maximum: int) -> list[str]:
    lines = [_normal_text(line) for line in text.splitlines() if _normal_text(line)]
    candidates: list[str] = []
    for line in lines:
        parts = re.split(r"(?<=[.!?;:])\s+(?=[A-ZÀ-Ỹ0-9])", line)
        for part in parts:
            value = _normal_text(part)
            if minimum <= len(value) <= maximum:
                candidates.append(value)
            elif len(value) > maximum:
                for start in range(0, len(value), maximum):
                    chunk = value[start:start + maximum].strip()
                    if len(chunk) >= minimum:
                        candidates.append(chunk)
    return candidates


def is_claim_candidate(text: str, report_type: str, keywords: list[str], measurements: list[dict], metric_codes: list[str]) -> bool:
    lower = text.casefold()
    has_keyword = any(keyword.casefold() in lower for keyword in keywords)
    has_claim_verb = any(word in lower for word in ("cam kết", "mục tiêu", "đạt", "giảm", "tăng", "duy trì", "ghi nhận", "reported", "target", "reduced"))
    if report_type == "financial_statements":
        financial_terms = ("doanh thu", "lợi nhuận", "tài sản", "lưu chuyển tiền", "revenue", "profit", "assets", "cash flow")
        return bool(measurements and (metric_codes or any(word in lower for word in financial_terms)))
    if metric_codes and (measurements or has_claim_verb):
        return True
    if has_keyword and (measurements or has_claim_verb):
        return True
    return False


def build_claim_records(spec: DocumentSpec, pages: list[dict], toolkit_config: dict, metrics_config: dict) -> tuple[list[dict], list[dict]]:
    settings = toolkit_config.get("extraction", {})
    minimum = int(settings.get("minimum_claim_characters", 25))
    maximum = int(settings.get("maximum_claim_characters", 900))
    keywords = [str(value) for value in toolkit_config.get("claim_keywords", [])]
    catalog = _metric_catalog(metrics_config, toolkit_config)
    financial_scope = infer_financial_statement_scope(pages, spec.source_path.name) if spec.report_type == "financial_statements" else None
    claims: list[dict] = extract_financial_table_claims(spec, pages, catalog, financial_scope) if spec.report_type == "financial_statements" else []
    review: list[dict] = []
    if spec.report_type == "financial_statements" and financial_scope is None:
        review.append({
            "issue_id": f"{spec.document_key}-SCOPE",
            "company_id": spec.company_id,
            "report_year": spec.report_year,
            "report_type": spec.report_type,
            "source_file": spec.source_path.name,
            "source_page": None,
            "issue_type": "FINANCIAL_SCOPE_UNRESOLVED",
            "priority": "high",
            "status": "open",
            "details": "Could not determine whether the financial statements are separate or consolidated.",
            "recommended_action": "Verify the report title; do not infer scope from company structure.",
        })
    fingerprints: set[tuple[int, str]] = set()
    for page in pages:
        page_number = int(page["page_number"])
        if page["extraction_status"] == "ocr_pending":
            review.append({
                "issue_id": f"{spec.document_key}-OCR-{page_number:04d}",
                "company_id": spec.company_id,
                "report_year": spec.report_year,
                "report_type": spec.report_type,
                "source_file": spec.source_path.name,
                "source_page": page_number,
                "issue_type": "OCR_REQUIRED",
                "priority": "high",
                "status": "open",
                "details": "Page has insufficient usable text after repeated header/footer removal.",
                "recommended_action": "Supply page-level OCR sidecar text and rerun extraction.",
            })
        for candidate in split_candidates(page["text"], minimum, maximum):
            fingerprint = (page_number, candidate.casefold())
            if fingerprint in fingerprints:
                continue
            fingerprints.add(fingerprint)
            metric_codes = infer_metrics(candidate, catalog)
            measurements = extract_measurements(candidate)
            if not is_claim_candidate(candidate, spec.report_type, keywords, measurements, metric_codes):
                continue
            primary_code = metric_codes[0] if metric_codes else None
            if spec.report_type == "financial_statements" and primary_code and any(item.get("metric_code") == primary_code for item in claims):
                continue
            primary = catalog.get(primary_code, {})
            attrs = extract_attributes(candidate)
            sequence = len(claims) + 1
            status = "ambiguous" if len(metric_codes) > 1 else "available"
            note = f"Multiple metric candidates: {', '.join(metric_codes)}" if len(metric_codes) > 1 else None
            claims.append({
                "record_id": f"{spec.company_id}-{REPORT_CODES[spec.report_type]}-{spec.report_year}-{sequence:05d}",
                "company_id": spec.company_id,
                "company_name": spec.company_name,
                "industry": spec.industry,
                "subsector": spec.subsector,
                "report_year": spec.report_year,
                "report_type": spec.report_type,
                "source_file": spec.source_path.name,
                "source_page": page_number,
                "dimension": primary.get("dimension") or ("X" if spec.report_type == "financial_statements" else "X"),
                "topic": primary.get("topic") or "X_OTHER",
                "claim_text": candidate,
                "claim_type": classify_claim(candidate),
                "evidence_type": ["metric"] if measurements else ["claim"],
                "metric_code": primary_code,
                "metric_candidates": metric_codes,
                "metric_name": primary.get("name"),
                "value": measurements[0]["value"] if measurements else attrs.get("raw_value"),
                "unit": measurements[0]["unit"] if measurements else attrs.get("raw_unit"),
                "measurements": measurements,
                "comparison": None,
                "target": None,
                "target_year": attrs.get("target_year"),
                "baseline_year": attrs.get("baseline_year"),
                "scope": None,
                "financial_statement_scope": financial_scope if spec.report_type == "financial_statements" else None,
                "boundary": financial_scope if spec.report_type == "financial_statements" else None,
                "methodology": None,
                "assurance_status": None,
                "extraction_method": page["extraction_method"],
                "extraction_status": status,
                "review_status": "unreviewed",
                "confidence": page["confidence"],
                "ambiguity_note": note,
                "extraction_notes": "Deterministic candidate extraction; human validation required.",
            })
            if len(metric_codes) > 1:
                review.append({
                    "issue_id": f"{spec.document_key}-METRIC-{sequence:05d}",
                    "company_id": spec.company_id,
                    "report_year": spec.report_year,
                    "report_type": spec.report_type,
                    "source_file": spec.source_path.name,
                    "source_page": page_number,
                    "issue_type": "MULTIPLE_METRICS",
                    "priority": "medium",
                    "status": "open",
                    "details": note,
                    "recommended_action": "Confirm the primary metric and split the sentence if it contains separate claims.",
                })
    return claims, review


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_json_ready(payload), ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8-sig")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value for key, value in row.items()})


def extract_document(
    spec: DocumentSpec,
    output_dir: Path,
    toolkit_config: dict,
    metrics_config: dict,
    ocr_root: Path | None = None,
    max_pages: int | None = None,
    progress_callback=None,
) -> dict:
    document_dir = output_dir / "documents" / spec.document_key
    if document_dir.exists():
        raise FileExistsError(f"Output already exists: {document_dir}")
    full_document = None
    if toolkit_config.get('extraction', {}).get('engine') == 'docling':
        from src.extraction.docling_backend import convert_pdf
        pages, page_metadata, full_document = convert_pdf(spec.source_path, max_pages, progress_callback)
    else:
        pages, page_metadata = extract_pages(spec, toolkit_config.get("extraction", {}), ocr_root, max_pages, progress_callback)
    if progress_callback:
        progress_callback({'stage': 'claims', 'completed_pages': len(pages), 'page_total': len(pages)})
    if full_document is None:
        claims, review = build_claim_records(spec, pages, toolkit_config, metrics_config)
    else:
        claims, review = [], []
    if full_document is not None:
        from src.extraction.docling_backend import all_table_claims
        boundary = infer_financial_statement_scope(pages, spec.source_path.name)
        full_document['source'] = {'company_id': spec.company_id, 'report_year': spec.report_year,
                                   'financial_statement_scope': boundary,
                                   'source_file': spec.source_path.name, 'source_sha256': sha256(spec.source_path)}
        claims.extend(all_table_claims(spec, full_document, boundary))
        write_json(document_dir / 'docling_full.json', full_document)
        review.append({'issue_id': f'{spec.document_key}-DOCLING-REVIEW', 'company_id': spec.company_id,
                      'report_year': spec.report_year, 'report_type': spec.report_type,
                      'source_file': spec.source_path.name, 'source_page': None,
                      'issue_type': 'TABLE_VALIDATION_REQUIRED', 'priority': 'medium', 'status': 'open',
                      'details': 'Docling retains detected cells and table structure. Numeric interpretation and year mapping require validation.',
                      'recommended_action': 'Review structured_documents and compare table cells with source PDF.'})
    if not claims:
        review.append({
            "issue_id": f"{spec.document_key}-NO-CLAIMS",
            "company_id": spec.company_id,
            "report_year": spec.report_year,
            "report_type": spec.report_type,
            "source_file": spec.source_path.name,
            "source_page": None,
            "issue_type": "NO_CLAIMS_EXTRACTED",
            "priority": "high" if spec.report_type == "financial_statements" else "medium",
            "status": "open",
            "details": "No claim candidate passed the deterministic extraction rules.",
            "recommended_action": "Review table/layout extraction and OCR quality; do not treat the absence of candidates as absence of disclosure.",
        })
    manifest = {
        "document_key": spec.document_key,
        "company_id": spec.company_id,
        "company_name": spec.company_name,
        "industry": spec.industry,
        "subsector": spec.subsector,
        "report_year": spec.report_year,
        "report_type": spec.report_type,
        "source_file": spec.source_path.name,
        "source_path": str(spec.source_path),
        "source_sha256": sha256(spec.source_path),
        "source_bytes": spec.source_path.stat().st_size,
        "page_metadata": page_metadata,
        "claim_count": len(claims),
        "review_item_count": len(review),
        "guardrail": toolkit_config.get("guardrail"),
    }
    write_json(document_dir / "manifest.json", manifest)
    write_json(document_dir / "pages.json", {"document": manifest, "pages": pages})
    write_json(document_dir / "claims.json", {"document": manifest, "records": claims})
    write_json(document_dir / "review_queue.json", {"document": manifest, "items": review})
    return {"manifest": manifest, "claims": claims, "review": review}


def company_summary(specs: list[DocumentSpec], claims: list[dict], review: list[dict]) -> list[dict]:
    documents_by_company: dict[str, list[DocumentSpec]] = defaultdict(list)
    claims_by_company: Counter[str] = Counter(item["company_id"] for item in claims)
    review_by_company: Counter[str] = Counter(item["company_id"] for item in review if item.get("status") == "open")
    ambiguous_by_company: Counter[str] = Counter(item["company_id"] for item in claims if item.get("extraction_status") == "ambiguous")
    for spec in specs:
        documents_by_company[spec.company_id].append(spec)
    rows = []
    for company_id, documents in sorted(documents_by_company.items()):
        years = sorted({item.report_year for item in documents})
        rows.append({
            "company_id": company_id,
            "company_name": documents[0].company_name,
            "industry": documents[0].industry,
            "subsector": documents[0].subsector,
            "document_count": len(documents),
            "years": years,
            "claim_candidate_count": claims_by_company[company_id],
            "ambiguous_claim_count": ambiguous_by_company[company_id],
            "open_review_item_count": review_by_company[company_id],
        })
    return rows


def run_extraction(
    specs: list[DocumentSpec],
    output_root: Path,
    run_id: str,
    toolkit_config: dict,
    metrics_config: dict,
    ocr_root: Path | None = None,
    max_pages: int | None = None,
    progress_callback=None,
) -> Path:
    run_dir = output_root / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run already exists: {run_dir}")
    run_dir.mkdir(parents=True)
    all_claims: list[dict] = []
    all_review: list[dict] = []
    document_manifests: list[dict] = []
    failures: list[dict] = []
    completed_specs: list[DocumentSpec] = []
    for document_index, spec in enumerate(specs):
        def report_progress(event):
            if progress_callback:
                progress_callback({**event, 'document_index': document_index + 1,
                                   'document_total': len(specs), 'filename': spec.source_path.name})
        try:
            report_progress({'stage': 'document', 'completed_pages': 0, 'page_total': 0})
            result = extract_document(spec, run_dir, toolkit_config, metrics_config, ocr_root, max_pages, report_progress)
        except Exception as exc:
            failures.append({
                "source_file": spec.source_path.name,
                "company_id": spec.company_id,
                "report_year": spec.report_year,
                "report_type": spec.report_type,
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
            continue
        completed_specs.append(spec)
        document_manifests.append(result["manifest"])
        all_claims.extend(result["claims"])
        all_review.extend(result["review"])
    summaries = company_summary(completed_specs, all_claims, all_review)
    if progress_callback:
        progress_callback({'stage': 'export', 'document_index': len(specs), 'document_total': len(specs)})
    write_json(run_dir / "claims.json", {"records": all_claims, "guardrail": toolkit_config.get("guardrail")})
    write_json(run_dir / "review_queue.json", {"items": all_review, "guardrail": toolkit_config.get("guardrail")})
    write_json(run_dir / "company_summary.json", {"companies": summaries, "guardrail": toolkit_config.get("guardrail")})
    write_csv(run_dir / "claims.csv", all_claims)
    write_csv(run_dir / "review_queue.csv", all_review)
    write_csv(run_dir / "company_summary.csv", summaries)
    write_json(run_dir / "run_manifest.json", {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(completed_specs),
        "failed_document_count": len(failures),
        "claim_candidate_count": len(all_claims),
        "review_item_count": len(all_review),
        "documents": document_manifests,
        "failures": failures,
        "guardrail": toolkit_config.get("guardrail"),
    })
    return run_dir
