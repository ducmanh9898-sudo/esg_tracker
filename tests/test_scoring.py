from src.scoring import claim_score, risk_level


def test_default_formula_for_maximum_components():
    results = [
        {"rule_id":"GW04","severity":5}, {"rule_id":"GW02","severity":5}, {"rule_id":"GW01","severity":5},
        {"rule_id":"GW03","severity":5}, {"rule_id":"GW05","severity":5},
    ]
    assert claim_score(results, 1, 1)["risk_score"] == 100


def test_risk_bands():
    assert [risk_level(x) for x in (0, 30, 60, 80)] == ["Thấp", "Trung bình", "Cao", "Rất cao"]

