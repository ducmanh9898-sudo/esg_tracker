import re

TARGET_WORDS = ("mục tiêu", "cam kết", "đến năm", "target", "net zero")
ACHIEVEMENT_WORDS = ("đạt", "hoàn thành", "giảm được", "không có sự cố")
POLICY_WORDS = ("chính sách", "quy định", "quy trình", "hệ thống quản lý")
COMPARATIVE_WORDS = ("tăng", "giảm", "cao hơn", "thấp hơn", "so với", "cải thiện")
VAGUE_WORDS = ("xanh", "bền vững", "thân thiện", "tiên phong", "đáng kể", "hiệu quả")


def classify_claim(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in TARGET_WORDS):
        return "TARGET"
    if any(word in lower for word in ACHIEVEMENT_WORDS):
        return "ACHIEVEMENT"
    if any(word in lower for word in POLICY_WORDS):
        return "POLICY"
    if any(word in lower for word in COMPARATIVE_WORDS):
        return "COMPARATIVE"
    if re.search(r"\d", text):
        return "QUANTITATIVE"
    return "QUALITATIVE"


def extract_attributes(text: str) -> dict:
    number = re.search(r"(?<!\d)(\d{1,3}(?:[. ]\d{3})*(?:,\d+)?|\d+(?:[.,]\d+)?)\s*(tCO2e|GJ|m[³3]|tấn|%|tỷ đồng|triệu đồng|giờ)?", text, re.I)
    years = [int(y) for y in re.findall(r"\b(20\d{2})\b", text)]
    lower = text.lower()
    direction = "IMPROVE" if any(x in lower for x in ("giảm", "cải thiện", "tăng tái chế")) else "WORSEN" if any(x in lower for x in ("tăng phát thải", "xấu đi")) else "NEUTRAL"
    value = None
    unit = None
    if number:
        value = float(number.group(1).replace(".", "").replace(" ", "").replace(",", "."))
        unit = number.group(2)
    return {
        "raw_value": value, "raw_unit": unit, "baseline_year": years[0] if len(years) > 1 else None,
        "target_year": years[-1] if any(x in lower for x in TARGET_WORDS) and years else None,
        "direction": direction, "qualifier": next((x for x in VAGUE_WORDS if x in lower), None),
    }

