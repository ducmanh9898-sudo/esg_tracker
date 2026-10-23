import pytest

from src.normalization.units import normalize_value, units_convertible


@pytest.mark.parametrize("value,unit,target,expected", [
    (1000, "kgCO2e", "tCO2e", 1),
    (2, "ktCO2e", "tCO2e", 2000),
    (1, "triệu lít", "m3", 1000),
    (3, "MWh", "GJ", 10.8),
    (2, "tỷ đồng", "VND", 2_000_000_000),
    (225, "kgCO2e/tấn sản phẩm", "tCO2e/tấn sản phẩm", 0.225),
])
def test_unit_conversion(value, unit, target, expected):
    actual, normalized_unit, status = normalize_value(value, unit, target)
    assert actual == pytest.approx(expected)
    assert normalized_unit == target
    assert status == "OK"


def test_unknown_unit_is_ambiguous():
    actual, _, status = normalize_value(1, "đơn vị lạ", "m3")
    assert actual is None
    assert status == "NOT_CONVERTIBLE"


def test_convertibility_is_explicit():
    assert units_convertible("kgCO2e", "tCO2e")
    assert not units_convertible("GJ", "m3")
