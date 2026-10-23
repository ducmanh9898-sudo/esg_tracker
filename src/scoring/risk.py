from pathlib import Path
import yaml

from src.paths import CONFIG_DIR


COMPONENT_RULES = {
    "contradiction": {"GW04"},
    "evidence_gap": {"GW02", "GW06", "GW15"},
    "vagueness": {"GW01", "GW11"},
    "target_integrity": {"GW03", "GW07", "GW13"},
    "temporal_consistency": {"GW05", "GW08", "GW10", "GW12", "GW14"},
}


def load_scoring(path: Path | None = None) -> dict:
    return yaml.safe_load((path or CONFIG_DIR / "scoring.yml").read_text(encoding="utf-8"))


def risk_level(score: float) -> str:
    if score < 30:
        return "Thấp"
    if score < 60:
        return "Trung bình"
    if score < 80:
        return "Cao"
    return "Rất cao"


def claim_score(rule_results: list[dict], evidence_coverage: float, claim_confidence: float, config: dict | None = None) -> dict:
    config = config or load_scoring()
    severity_weights = {int(k): float(v) for k, v in config["severity_weights"].items()}
    components = {}
    for component, rule_ids in COMPONENT_RULES.items():
        relevant = [severity_weights.get(int(r["severity"]), 0) for r in rule_results if r["rule_id"] in rule_ids]
        components[component] = max(relevant, default=0.0)
    score = 100 * sum(float(config["weights"][name]) * components[name] for name in config["weights"])
    score = round(min(max(score, 0), 100), 2)
    confidence = round((float(claim_confidence) + float(evidence_coverage)) / 2, 3)
    return {**components, "risk_score": score, "risk_level": risk_level(score),
            "evidence_coverage": round(evidence_coverage, 3), "confidence": confidence}

