from pathlib import Path
import sys
import json
import uuid
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import connect
from src.matching.evidence import candidate_score, relationship_for, checks_json
from src.rules import RuleEngine
from src.scoring import claim_score
from src.paths import CONFIG_DIR


def as_dict(row):
    return dict(row) if row is not None else None


def demo_context(claim: dict) -> dict:
    if not claim["is_demo_data"]:
        return {"methodology": None}
    cid = claim.get("claim_id", "")
    n = int(cid.split("C")[-1]) if "C" in cid else 1
    topic = claim.get("topic_id", "")
    is_waste_gap = (topic == "E_WASTE" and claim.get("raw_value") is None)
    is_target = (claim.get("claim_type") == "TARGET")
    return {
        "methodology": "Phương pháp kiểm kê BSR" if n % 2 == 0 else None,
        "baseline_changed": n % 11 == 0,
        "restatement_explained": False,
        "target_repeated": is_target and n % 2 == 0,
        "progress_present": False,
        "related_metric_worsens": n % 13 == 0,
        "prior_value_changed": n % 17 == 0,
        "within_rounding": False,
        "gri11_material_topic": is_waste_gap or n % 19 == 0,
        "disclosure_missing": is_waste_gap,
        "documented_not_material": False,
        "two_prior_years_present": False,
        "current_year_missing": False,
        "observed_direction": "WORSEN" if n % 10 == 2 else "NEUTRAL",
    }


def main():
    metric_cfg = yaml.safe_load((CONFIG_DIR / "metrics.yml").read_text(encoding="utf-8"))["metrics"]
    engine = RuleEngine()
    with connect() as connection:
        connection.execute("DELETE FROM topic_scores")
        connection.execute("DELETE FROM claim_scores")
        connection.execute("DELETE FROM rule_results")
        connection.execute("DELETE FROM evidence_links")
        claims = [dict(r) for r in connection.execute("SELECT * FROM claims")]
        metrics = [dict(r) for r in connection.execute("SELECT * FROM metrics")]
        for claim in claims:
            candidates = [m for m in metrics if claim.get("metric_code") and m["metric_code"] == claim["metric_code"] and m["is_demo_data"] == claim["is_demo_data"]]
            candidates.sort(key=lambda m: candidate_score(claim, m), reverse=True)
            metric = candidates[0] if candidates else None
            tolerance = metric_cfg.get(claim.get("metric_code"), {}).get("tolerance", 0.02)
            relationship, checks = relationship_for(claim, metric, float(tolerance))
            link_id = f"EL_{claim['claim_id']}"
            link = {**checks, "relationship": relationship, "comparable": checks.get("comparable", False)}
            connection.execute(
                "INSERT INTO evidence_links VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (link_id, claim["claim_id"], metric["metric_id"] if metric else None, relationship,
                 candidate_score(claim, metric) if metric else 0.0,
                 "Kết quả matching sau kiểm tra metric, kỳ, đơn vị, scope, boundary, định nghĩa và loại giá trị.",
                 int(checks.get("same_metric", False)), int(checks.get("same_period", False)), int(checks.get("same_unit", False)),
                 int(checks.get("unit_convertible", False)), int(checks.get("same_scope", False)), int(checks.get("same_boundary", False)),
                 int(checks.get("same_definition", False)), int(checks.get("same_value_kind", False)), checks_json(checks), claim["is_demo_data"]),
            )
            results = engine.evaluate(claim, link, demo_context(claim))
            for result in results:
                result_id = f"RR_{claim['claim_id']}_{result['rule_id']}"
                connection.execute(
                    "INSERT INTO rule_results VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (result_id, claim["claim_id"], link_id, result["rule_id"], result["risk_type"], result["severity"],
                     result["severity"] * 20, result["explanation"], metric["source_text"] if metric else "Không có bằng chứng ứng viên",
                     checks_json(checks), claim["document_id"], claim["report_year"], claim["page_number"], claim["confidence"], claim["is_demo_data"]),
                )
            coverage = 1.0 if relationship in {"SUPPORTS", "CONTRADICTS"} else 0.5 if relationship == "PARTIAL_SUPPORT" else 0.0
            score = claim_score(results, coverage, claim["confidence"])
            connection.execute(
                "INSERT INTO claim_scores VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (claim["claim_id"], score["contradiction"], score["evidence_gap"], score["vagueness"], score["target_integrity"],
                 score["temporal_consistency"], score["risk_score"], score["risk_level"], score["evidence_coverage"], score["confidence"], claim["is_demo_data"]),
            )
        rows = connection.execute("""
            SELECT c.report_year, c.pillar, c.topic_id, c.is_demo_data,
                   AVG(s.risk_score) risk_score, COUNT(*) claim_count,
                   SUM(CASE WHEN rr.claim_id IS NOT NULL THEN 1 ELSE 0 END) warning_count,
                   AVG(s.evidence_coverage) evidence_coverage, AVG(s.confidence) confidence
            FROM claims c JOIN claim_scores s ON s.claim_id=c.claim_id
            LEFT JOIN (SELECT DISTINCT claim_id FROM rule_results) rr ON rr.claim_id=c.claim_id
            GROUP BY c.report_year,c.pillar,c.topic_id,c.is_demo_data
        """).fetchall()
        topic_gri = {"E_CLIMATE": "GRI 11.1", "E_ENERGY": "GRI 11.1", "E_WATER": "GRI 11.6", "E_WASTE": "GRI 11.5",
                     "E_SPILLS": "GRI 11.8", "S_SAFETY": "GRI 11.9", "G_TAX": "GRI 11.21"}
        for row in rows:
            connection.execute("INSERT INTO topic_scores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (
                f"TS_{row['report_year']}_{row['pillar']}_{row['topic_id']}_{row['is_demo_data']}", "BSR", row["report_year"],
                row["pillar"], row["topic_id"], round(row["risk_score"], 2), row["claim_count"], row["warning_count"],
                round(row["evidence_coverage"], 3), round(row["confidence"], 3), topic_gri.get(row["topic_id"], "GRI 11 / liên quan"), row["is_demo_data"]
            ))
    print("Pipeline complete: evidence matching, 15-rule screening, claim/topic scoring.")


if __name__ == "__main__":
    main()
