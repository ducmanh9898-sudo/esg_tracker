"""Regression checks for source-bound table years (no PDF or network needed)."""
from src.extraction.corporate_handoff import _period


def period(text, column, header_column):
    record = {
        "record_type": "measurement",
        "content_period": {"year": 2024, "period_type": "annual"},
        "payload": {},
    }
    uncertainties = []
    result = _period(record, [{
        "role": "year", "text": text, "column": header_column
    }], "591", uncertainties, column)
    return result, uncertainties


def test_missing_columns_do_not_prove_year_binding():
    result, issues = period("2024", None, None)
    assert result["year_basis"] == "unknown"
    assert issues


def test_multiple_years_in_header_require_review():
    result, issues = period("Năm 2023 / Năm 2024", 2, 2)
    assert result["year_basis"] == "unknown"
    assert issues


def test_year_substring_is_not_year_evidence():
    result, _ = period("20240", 2, 2)
    assert result["year_basis"] == "unknown"


def test_unique_year_with_known_same_column_is_grounded():
    result, issues = period("Năm 2024", 2, 2)
    assert result["year_basis"] == "table_header"
    assert not issues


def test_wrong_column_stays_unverified():
    result, _ = period("Năm 2024", 2, 3)
    assert result["year_basis"] == "unknown"


def test_same_page_fiscal_title_and_current_column_ground_year():
    record = {
        "record_type": "measurement",
        "content_period": {"year": 2024, "end_date": "2024-12-31", "period_type": "duration",
                           "mapping_basis": "column_label_plus_pdf_reporting_period"},
        "payload": {"period_role": "current_flow"},
    }
    headers = [
        {"role": "year", "text": "Năm nay", "physical_page": 9, "column": 4},
        {"role": "other", "text": "Cho năm tài chính kt thúc ngày 31 tháng 12 năm 2024",
         "physical_page": 9, "column": None},
    ]
    uncertainty = []
    result = _period(record, headers, "123", uncertainty, 4, source_page=9)
    assert result["observation_year"] == 2024
    assert result["year_basis"] == "same_page_title_and_column"
    assert "ocr_title_and_current_column_year_needs_human_review" in uncertainty

    for changed in (
        [{**headers[0], "column": 5}, headers[1]],
        [headers[0], {**headers[1], "physical_page": 1}],
        [headers[0], {**headers[1], "text": "Cho năm tài chính kết thúc ngày 31 tháng 12 năm 2023"}],
    ):
        result = _period(record, changed, "123", [], 4, source_page=9)
        assert result["observation_year"] is None
        assert result["year_basis"] == "unknown"
