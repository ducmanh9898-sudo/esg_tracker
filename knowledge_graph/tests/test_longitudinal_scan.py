import json
from pathlib import Path
import unittest

from kg.longitudinal_scan import discover


PROFILE = json.loads((Path(__file__).resolve().parents[1] /
                      "data/config/bsr_esg_bctc_only_v1.json").read_text(encoding="utf-8"))


def record(identity, kind, observation_year, report_year, value, label, unit="people"):
    source_type = "sustainability_report" if kind == "ESG" else "financial_statement"
    return {"record_id": identity, "company_id": "BSR", "source_document_type": source_type,
            "report_type": kind, "report_year": report_year,
            "observation_year": observation_year, "dimension": "S" if kind == "ESG" else "X",
            "value_status": "available", "value": value, "unit": unit,
            "variant": "reported_result", "label": label, "metric_id": None,
            "metric_definition": None, "period_type": "at_date",
            "raw_record": {"boundary": {"reporting_entity": None, "scope": None,
                                        "population": None, "counting_method": None},
                           "period": {"measurement_date": f"{observation_year}-12-31" if observation_year else None},
                           "restatement": {"status": "unknown"}},
            "evidence": [{"source_file": f"{kind}_{report_year}.pdf", "physical_page": 12,
                          "exact_quote": str(value), "context_text": label}]}


class LongitudinalScanTest(unittest.TestCase):
    def test_keeps_esg_and_bctc_series_separate_and_computes_three_year_change(self):
        esg_label = "Tổng số lao động"
        financial_labels = ["Tng s nhân viên ca Công ty và công ty con",
                            "Tồng s nhân viên ca Công ty và công ty con"]
        claims = [record(f"e{year}", "ESG", year, 2025, value, esg_label)
                  for year, value in ((2023, 1532), (2024, 1544), (2025, 1594))]
        claims += [record(f"f{year}", "Financial", year, year, value,
                          financial_labels[0 if year == 2023 else 1])
                   for year, value in ((2023, 1855), (2024, 1840), (2025, 1946))]
        summary, series, comparisons = discover(claims, PROFILE)
        self.assertEqual(summary["series"], 2)
        self.assertEqual(summary["complete_three_year_series"], 2)
        self.assertEqual(summary["comparisons"], 6)
        self.assertEqual({s["report_type"] for s in series}, {"ESG", "BCTC"})
        esg_2024 = next(c for c in comparisons if c["from"]["record_id"] == "e2023"
                        and c["to"]["record_id"] == "e2024")
        self.assertEqual(esg_2024["delta"], "12")
        self.assertEqual(esg_2024["status"], "NeedsReview")
        self.assertFalse(esg_2024["semantic_comparison_verified"])
        self.assertIn("historical_values_from_one_report", esg_2024["review_reasons"])
        bctc_2025 = next(c for c in comparisons if c["from"]["record_id"] == "f2024"
                         and c["to"]["record_id"] == "f2025")
        self.assertEqual(bctc_2025["delta"], "106")

    def test_prefers_original_year_and_does_not_infer_unknown_year(self):
        label = "Tổng số lao động"
        claims = [record("original", "ESG", 2024, 2024, 1544, label),
                  record("comparative", "ESG", 2024, 2025, 1550, label),
                  record("later", "ESG", 2025, 2025, 1594, label),
                  record("unknown", "ESG", None, 2025, 1532, label)]
        _, series, comparisons = discover(claims, PROFILE)
        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0]["from"]["record_id"], "original")
        self.assertEqual(comparisons[0]["delta"], "50")
        self.assertEqual(series[0]["alternative_source_versions"]["2024"][0]["value"], 1550)

    def test_different_units_and_unrelated_labels_do_not_make_a_series(self):
        claims = [record("one", "ESG", 2023, 2023, 54, "Tỷ lệ lao động địa phương", "%"),
                  record("two", "ESG", 2024, 2024, 1840, "Tổng số lao động"),
                  record("three", "ESG", 2025, 2025, 55, "Tỷ lệ lao động địa phương", "people")]
        summary, _, comparisons = discover(claims, PROFILE)
        self.assertEqual(summary["series"], 0)
        self.assertEqual(comparisons, [])

    def test_bctc_comparative_workforce_note_is_a_separate_review_item(self):
        label = "Tồng s nhân viên ca Công ty và công ty con"
        earlier = record("old", "Financial", 2024, 2024, 1840, label)
        later = record("new", "Financial", 2025, 2025, 1946, label)
        later["evidence"][0]["exact_quote"] = (
            "Tồng s nhân viên ... năm 2025 là 1.946 "
            "(ti ngày 31 tháng12 năm 2024: là 1.891).")
        summary, series, comparisons = discover([earlier, later], PROFILE)
        self.assertEqual(len(comparisons), 1)
        self.assertEqual(comparisons[0]["delta"], "106")
        self.assertEqual(summary["comparative_note_differences"], 1)
        audit = series[0]["comparative_note_audit"][0]
        self.assertEqual(audit["delta"], 51)
        self.assertEqual(audit["status"], "NeedsReview")

    def test_repeated_esg_label_uses_source_row_code(self):
        claims = []
        for year, value, row in ((2023, 5601406, "1.1"), (2024, 5211095, "1.1"),
                                 (2023, 5540498, "2.1"), (2024, 5166868, "2.1")):
            item = record(f"r{year}{row}", "ESG", year,
                          2023 if row == "1.1" and year == 2023 else 2024,
                          value, "Dầu thô trong nước", "t")
            item["dimension"] = "E"
            item["evidence"][0]["context_text"] = f"{value}\nDầu thô trong nước\n{row}\n{year}\ntấn"
            claims.append(item)
        summary, series, comparisons = discover(claims, PROFILE)
        self.assertEqual(summary["series"], 2)
        self.assertEqual(summary["blocked_ambiguous_groups"], 0)
        self.assertEqual({s["metric_key"] for s in series},
                         {"label:dau tho trong nuoc:row:1.1", "label:dau tho trong nuoc:row:2.1"})
        self.assertEqual({c["delta"] for c in comparisons}, {"-390311", "-373630"})


if __name__ == "__main__":
    unittest.main()
