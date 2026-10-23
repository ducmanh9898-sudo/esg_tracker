from src.matching.evidence import relationship_for


def base_claim(**overrides):
    value = {"metric_code":"GHG_SCOPE_1","report_year":2024,"raw_value":100.0,"raw_unit":"tCO2e",
             "scope":"Scope 1","boundary":"Hợp nhất","value_kind":"ABSOLUTE"}
    value.update(overrides); return value


def base_metric(**overrides):
    value = {"metric_code":"GHG_SCOPE_1","metric_year":2024,"normalized_value":100.0,"normalized_unit":"tCO2e",
             "scope":"Scope 1","boundary":"Hợp nhất","value_kind":"ABSOLUTE"}
    value.update(overrides); return value


def test_supports_within_tolerance():
    status, checks = relationship_for(base_claim(raw_value=100.5), base_metric(), 0.01)
    assert status == "SUPPORTS" and checks["comparable"]


def test_contradiction_only_when_comparable():
    status, checks = relationship_for(base_claim(raw_value=150), base_metric(), 0.01)
    assert status == "CONTRADICTS" and checks["comparable"]


def test_capex_is_not_compared_with_opex():
    status, _ = relationship_for(base_claim(metric_code="ENV_CAPEX"), base_metric(metric_code="ENV_EXPENSE"))
    assert status != "CONTRADICTS"


def test_consolidated_not_compared_with_separate():
    status, _ = relationship_for(base_claim(boundary="Hợp nhất", raw_value=500), base_metric(boundary="Công ty mẹ"))
    assert status == "NOT_COMPARABLE"


def test_absolute_not_compared_with_intensity():
    status, _ = relationship_for(base_claim(raw_value=500), base_metric(value_kind="INTENSITY"))
    assert status == "NOT_COMPARABLE"


def test_unconvertible_unit_is_not_contradiction():
    status, _ = relationship_for(base_claim(raw_unit="GJ", raw_value=500), base_metric(normalized_unit="m3"))
    assert status == "AMBIGUOUS"


def test_scope_mismatch_is_not_contradiction():
    status, _ = relationship_for(base_claim(scope="Scope 1", raw_value=500), base_metric(scope="Scope 2"))
    assert status == "NOT_COMPARABLE"


def test_missing_is_not_contradiction():
    status, _ = relationship_for(base_claim(), None)
    assert status == "MISSING"


def test_values_are_compared_after_unit_conversion():
    claim = base_claim(metric_code="TAX_PAID", raw_value=14.719, raw_unit="billion_VND", scope=None)
    metric = base_metric(metric_code="TAX_PAID", normalized_value=14_719_000_000, normalized_unit="VND", scope=None)
    status, checks = relationship_for(claim, metric, 0.001)
    assert status == "SUPPORTS"
    assert checks["unit_convertible"]
