import re
import unicodedata


UNIT_ALIASES = {
    "tco2e": "tCO2e", "tấn co2e": "tCO2e", "tonnes co2e": "tCO2e",
    "kgco2e": "kgCO2e", "ktco2e": "ktCO2e",
    "m3": "m3", "m³": "m3", "triệu lít": "million_litre", "lít": "litre",
    "gj": "GJ", "mj": "MJ", "mwh": "MWh",
    "tấn": "tấn", "tonne": "tấn", "kg": "kg",
    "vnd": "VND", "đồng": "VND", "triệu đồng": "million_VND", "tỷ đồng": "billion_VND",
    "%": "%", "vụ": "vụ", "giờ/người/năm": "giờ/người/năm",
    "ca/triệu giờ công": "ca/triệu giờ công", "tco2e/tấn sản phẩm": "tCO2e/tấn sản phẩm",
    "kgco2e/tấn sản phẩm": "kgCO2e/tấn sản phẩm",
}

CONVERSIONS = {
    ("kgCO2e", "tCO2e"): 0.001,
    ("ktCO2e", "tCO2e"): 1000.0,
    ("litre", "m3"): 0.001,
    ("million_litre", "m3"): 1000.0,
    ("MJ", "GJ"): 0.001,
    ("MWh", "GJ"): 3.6,
    ("kg", "tấn"): 0.001,
    ("million_VND", "VND"): 1_000_000.0,
    ("billion_VND", "VND"): 1_000_000_000.0,
    ("kgCO2e/tấn sản phẩm", "tCO2e/tấn sản phẩm"): 0.001,
}


def canonical_unit(unit: str | None) -> str | None:
    if not unit:
        return None
    cleaned = unicodedata.normalize("NFKC", str(unit)).strip().lower()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return UNIT_ALIASES.get(cleaned, str(unit).strip())


def units_convertible(from_unit: str | None, to_unit: str | None) -> bool:
    source, target = canonical_unit(from_unit), canonical_unit(to_unit)
    return bool(source and target and (source == target or (source, target) in CONVERSIONS or (target, source) in CONVERSIONS))


def normalize_value(value: float | int | None, raw_unit: str | None, standard_unit: str | None):
    if value is None:
        return None, canonical_unit(raw_unit), "MISSING_VALUE"
    source, target = canonical_unit(raw_unit), canonical_unit(standard_unit)
    if not source or not target:
        return None, target, "AMBIGUOUS_UNIT"
    if source == target:
        return float(value), target, "OK"
    factor = CONVERSIONS.get((source, target))
    if factor is None:
        return None, target, "NOT_CONVERTIBLE"
    return float(value) * factor, target, "OK"
