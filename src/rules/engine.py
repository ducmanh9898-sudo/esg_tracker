from __future__ import annotations

from pathlib import Path
import yaml

from src.paths import CONFIG_DIR


VAGUE_TERMS = {"xanh", "bền vững", "thân thiện", "tiên phong", "đáng kể", "hiệu quả", "hàng đầu"}


class RuleEngine:
    """Deterministic screening rules. Results are signals for manual review, not accusations."""

    def __init__(self, rules_path: Path | None = None):
        payload = yaml.safe_load((rules_path or CONFIG_DIR / "rules.yml").read_text(encoding="utf-8"))
        self.rules = {item["rule_id"]: item for item in payload["rules"] if item.get("enabled", True)}

    def _result(self, rule_id: str, explanation: str, relationship: str | None = None) -> dict:
        rule = self.rules[rule_id]
        return {"rule_id": rule_id, "risk_type": rule["name"], "severity": int(rule["severity"]),
                "explanation": explanation, "relationship": relationship}

    def evaluate(self, claim: dict, link: dict | None = None, context: dict | None = None) -> list[dict]:
        link, context = link or {}, context or {}
        results: list[dict] = []
        text = (claim.get("source_text") or "").lower()
        claim_type = claim.get("claim_type")
        relationship = link.get("relationship")

        if any(term in text for term in VAGUE_TERMS) and claim.get("raw_value") is None and claim_type != "POLICY":
            results.append(self._result("GW01", "Claim dùng diễn đạt quảng bá hoặc mơ hồ nhưng chưa nêu chỉ số có thể kiểm chứng.", relationship))
        if relationship == "MISSING" and claim_type != "POLICY":
            results.append(self._result("GW02", "Chưa tìm thấy bằng chứng ứng viên đủ điều kiện; đây là khoảng trống bằng chứng, không phải mâu thuẫn.", relationship))
        if claim_type == "TARGET" and any(claim.get(k) in (None, "") for k in ("baseline_year", "target_year", "scope")):
            results.append(self._result("GW03", "Mục tiêu thiếu năm cơ sở, thời hạn hoặc phạm vi nên tính toàn vẹn mục tiêu còn yếu.", relationship))
        if relationship == "CONTRADICTS" and link.get("comparable", False):
            results.append(self._result("GW04", "Giá trị khác nhau vượt tolerance sau khi xác nhận cùng metric, kỳ, đơn vị, scope, boundary và loại giá trị.", relationship))
        if context.get("observed_direction") == "WORSEN" and claim.get("direction") == "IMPROVE" and link.get("comparable", False):
            results.append(self._result("GW05", "Claim mô tả cải thiện nhưng chuỗi số liệu có thể so sánh cho thấy chiều hướng xấu đi.", relationship))
        if context.get("two_prior_years_present") and context.get("current_year_missing"):
            results.append(self._result("GW06", "Chỉ số từng xuất hiện ít nhất hai năm nhưng thiếu ở năm hiện tại; cần rà soát lý do.", relationship))
        if context.get("baseline_changed") and not context.get("restatement_explained"):
            results.append(self._result("GW07", "Năm cơ sở thay đổi nhưng chưa thấy giải thích hoặc restatement minh bạch.", relationship))
        if relationship == "NOT_COMPARABLE" and (not link.get("same_scope", True) or not link.get("same_boundary", True)):
            results.append(self._result("GW08", "Scope hoặc boundary khác nhau; hệ thống không kết luận mâu thuẫn và yêu cầu rà soát thay đổi phạm vi.", relationship))
        if relationship == "AMBIGUOUS" and not link.get("unit_convertible", False):
            results.append(self._result("GW09", "Đơn vị khác nhau và chưa có phép quy đổi hợp lệ; trạng thái được giữ là AMBIGUOUS.", relationship))
        if relationship == "NOT_COMPARABLE" and not link.get("same_value_kind", True):
            results.append(self._result("GW10", "Giá trị tuyệt đối và cường độ không được đối chiếu trực tiếp khi thiếu mẫu số tương thích.", relationship))
        if claim.get("metric_code") and not context.get("methodology") and claim.get("raw_value") is not None:
            results.append(self._result("GW11", "Chỉ số định lượng chưa nêu rõ phương pháp hoặc ranh giới tính toán.", relationship))
        if context.get("related_metric_worsens") and claim.get("direction") == "IMPROVE":
            results.append(self._result("GW12", "Claim tích cực cần được đọc cùng chỉ số chính liên quan có chiều hướng xấu đi.", relationship))
        if claim_type == "TARGET" and context.get("target_repeated") and not context.get("progress_present"):
            results.append(self._result("GW13", "Cam kết tương lai lặp lại nhưng chưa đi kèm số liệu tiến độ.", relationship))
        if context.get("prior_value_changed") and not context.get("restatement_explained") and not context.get("within_rounding"):
            results.append(self._result("GW14", "Giá trị quá khứ bị thay đổi vượt sai số làm tròn nhưng chưa thấy giải thích điều chỉnh.", relationship))
        if context.get("gri11_material_topic") and context.get("disclosure_missing") and not context.get("documented_not_material"):
            results.append(self._result("GW15", "Chưa thấy công bố hoặc giải trình cho chủ đề GRI 11 có khả năng trọng yếu.", relationship))
        return results

