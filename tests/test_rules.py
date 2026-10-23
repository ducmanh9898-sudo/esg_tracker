from src.rules import RuleEngine


def claim(**overrides):
    data = {"claim_id":"C1","source_text":"BSR cải thiện đáng kể hoạt động bền vững.","claim_type":"QUALITATIVE",
            "raw_value":None,"metric_code":None,"baseline_year":None,"target_year":None,"scope":None,
            "direction":"NEUTRAL","document_id":"D1","page_number":1}
    data.update(overrides); return data


def test_vague_claim():
    ids = {r["rule_id"] for r in RuleEngine().evaluate(claim())}
    assert "GW01" in ids


def test_evidence_gap_not_contradiction():
    results = RuleEngine().evaluate(claim(source_text="Giảm phát thải", claim_type="COMPARATIVE"), {"relationship":"MISSING"})
    ids = {r["rule_id"] for r in results}
    assert "GW02" in ids and "GW04" not in ids


def test_weak_target():
    ids = {r["rule_id"] for r in RuleEngine().evaluate(claim(claim_type="TARGET", source_text="Mục tiêu giảm phát thải"))}
    assert "GW03" in ids


def test_scope_shift_is_explained_without_contradiction():
    link = {"relationship":"NOT_COMPARABLE","same_scope":False,"same_boundary":True,"same_value_kind":True}
    ids = {r["rule_id"] for r in RuleEngine().evaluate(claim(), link)}
    assert "GW08" in ids and "GW04" not in ids


def test_unit_mismatch_is_ambiguous():
    link = {"relationship":"AMBIGUOUS","unit_convertible":False}
    ids = {r["rule_id"] for r in RuleEngine().evaluate(claim(), link)}
    assert "GW09" in ids and "GW04" not in ids


def test_all_15_rules_configured():
    assert len(RuleEngine().rules) == 15

