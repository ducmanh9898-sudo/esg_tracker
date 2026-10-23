import unittest
import csv
import json
from pathlib import Path
import tempfile
from kg.cross_report_scan import discover, diagnostic, keys, normalized_label
from tools.cross_report_triage import ingest


def claim(identity, report_type, year=2024, company="A", value=10, unit="VND"):
    return dict(record_id=identity, report_type=report_type, observation_year=year,
                report_year=2024, company_id=company, value=value, value_status="available",
                variant="reported_result", label="Lợi nhuận sau thuế", metric_id=None, unit=unit,
                report_id="report_" + identity, dimension="G")


class CrossReportDiscoveryTests(unittest.TestCase):
    def test_no_same_type_or_company_or_year_comparison(self):
        rows, _ = discover([claim("a", "ESG"), claim("b", "Financial"),
                            claim("c", "Financial", company="B"),
                            claim("d", "Financial", year=2023)], {})
        self.assertEqual([r["record_ids"] for r in rows], [["a", "b"]])

    def test_annual_route_is_opt_in_and_excludes_annual_financial_pair(self):
        profile = {"comparison_routes": [
            {"id": "esg_financial", "left": "sustainability_report",
             "right": "financial_statement", "dimensions": ["E", "S", "G"]},
            {"id": "esg_annual", "left": "sustainability_report",
             "right": "annual_report", "dimensions": ["E", "S", "G"]}]}
        esg = claim("esg", "ESG")
        annual = claim("annual", "ESG")
        annual["source_document_type"] = "annual_report"
        financial = claim("financial", "Financial")
        rows, _ = discover([esg, annual, financial], profile)
        self.assertEqual({frozenset(row["record_ids"]) for row in rows},
                         {frozenset({"esg", "annual"}), frozenset({"esg", "financial"})})
        self.assertEqual({r["comparison_route"] for r in rows}, {"esg_annual", "esg_financial"})
        with self.assertRaisesRegex(ValueError, "explicit_pair"):
            discover([esg, annual, financial], profile,
                     [{"record_ids": ["annual", "financial"], "relation": "equal"}])
        old, _ = discover([esg, annual, financial], {})
        self.assertEqual([r["record_ids"] for r in old], [["esg", "financial"]])

    def test_local_metric_id_does_not_pair_profit_with_ratio(self):
        profit = claim("profit", "ESG")
        ratio = claim("ratio", "Financial")
        profit["metric_id"] = ratio["metric_id"] = "local:profit_after_tax:v1"
        ratio["label"] = "Return on assets ratio"
        rows, _ = discover([profit, ratio], {})
        self.assertEqual(rows, [])

    def test_unknown_year_is_not_inferred(self):
        a = claim("a", "ESG", year=None)
        rows, _ = discover([a, claim("b", "Financial")], {})
        self.assertEqual(len(rows), 0)
        self.assertIsNone(a["observation_year"])
        explicit, _ = discover([a, claim("b", "Financial")], {},
                               [{"record_ids": ["a", "b"], "relation": "equal"}])
        self.assertEqual(len(explicit), 1)

    def test_report_year_hint_keeps_unknown_observation_year(self):
        esg = claim("esg", "ESG", year=None)
        financial = claim("financial", "Financial", year=2024)
        profile = {"include_report_year_hints": True}
        rows, _ = discover([esg, financial], profile)
        self.assertEqual(len(rows), 1)
        self.assertIn("report_year_hint_unverified", rows[0]["match_basis"])
        self.assertIsNone(esg["observation_year"])
        financial["observation_year"] = 2023
        self.assertEqual(discover([esg, financial], profile)[0], [])
        financial["observation_year"] = 2024
        financial["report_year"] = 2025
        self.assertEqual(discover([esg, financial], profile)[0], [])
        esg["observation_year"] = 2024
        financial["observation_year"] = None
        financial["report_year"] = 2024
        self.assertEqual(discover([esg, financial], profile)[0], [])

    def test_known_consolidation_mismatch_not_auto_compared(self):
        a = claim("a", "ESG")
        b = claim("b", "Financial")
        a["raw_record"] = {"boundary": {"consolidation": "Consolidated"}}
        b["raw_record"] = {"boundary": {"consolidation": "Separate"}}
        rows, _ = discover([a, b], {})
        self.assertEqual(rows, [])
        explicit, _ = discover([a, b], {},
                               [{"record_ids": ["a", "b"], "relation": "equal"}])
        self.assertEqual(len(explicit), 1)

    def test_duplicate_and_invalid_explicit(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            discover([claim("a", "ESG"), claim("a", "ESG")], {})
        with self.assertRaisesRegex(ValueError, "explicit_pair"):
            discover([claim("a", "ESG"), claim("b", "ESG")], {},
                     [{"record_ids": ["a", "b"], "relation": "equal"}])

    def test_family_is_retrieval_only_deduplicated(self):
        rows, _ = discover([claim("a", "ESG"), claim("b", "Financial")],
                           {"metric_families": [{"id": "profit", "patterns": ["loi nhuan"]}]})
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["match_basis"]), 2)
        self.assertEqual(normalized_label("ĐỒNG"), "dong")

    def test_bsr_ocr_profit_row_is_retrieved_only_with_statement_code_60(self):
        profile = json.loads((Path(__file__).resolve().parents[1] /
                              "data/config/bsr_cross_report_discovery_extract_v4.json").read_text(encoding="utf-8"))
        esg = claim("esg", "ESG")
        esg["label"] = "Lợi nhuận sau thuế hợp nhất"
        financial = claim("financial", "Financial")
        financial["label"] = "Li nhun sau thu thu nhp doanh nghip (60=50-51-52) Trong đó:"
        other = claim("other", "Financial")
        other["label"] = "Li nhun sau thu ca c đông ca Công ty mẹ"
        rows, _ = discover([esg, financial, other], profile)
        self.assertEqual([row["record_ids"] for row in rows], [["esg", "financial"]])
        financial["label"] = "Li nhun sau thu thu nhp doanh nghiep (60=50-51-52) Trong đó:"
        self.assertEqual(len(discover([esg, financial, other], profile)[0]), 1)
        financial["label"] = "Li nhun sau thu thu nhp doanh nghiep (61=50-51-52)"
        self.assertEqual(discover([esg, financial, other], profile)[0], [])

    def test_bsr_ocr_profit_before_tax_code_50_is_review_candidate(self):
        profile = json.loads((Path(__file__).resolve().parents[1] /
                              "data/config/bsr_esg_bctc_only_v1.json").read_text(encoding="utf-8"))
        esg = claim("esg", "ESG", year=None)
        esg["report_year"] = 2025
        esg["label"] = "Lợi nhuận trước thuế"
        financial = claim("financial", "Financial", year=2025)
        financial["report_year"] = 2025
        financial["label"] = "Tng li nhun k toán trưc thu (50=30+40)"
        rows, _ = discover([esg, financial], profile)
        self.assertEqual(len(rows), 1)
        self.assertIn("report_year_hint_unverified", rows[0]["match_basis"])
        esg["variant"] = "unknown"
        esg["metric_id"] = "local:profit_before_tax:v1"
        rows, _ = discover([esg, financial], profile)
        self.assertEqual(len(rows), 1)
        self.assertIn("variant_unknown_unverified", rows[0]["match_basis"])
        esg["metric_id"] = "local:other_metric:v1"
        self.assertEqual(discover([esg, financial], profile)[0], [])
        esg["metric_id"] = "local:profit_before_tax:v1"
        financial["label"] = "Tng li nhun k toán trưc thu (51=30+40)"
        self.assertEqual(discover([esg, financial], profile)[0], [])

    def test_family_exclusion_keeps_direct_profit_and_explicit_pairs(self):
        profile = {"metric_families": [{
            "id": "profit_after_tax",
            "patterns": [r"^loi nhuan sau thue(?: |$)"],
            "exclude_patterns": [r"\bco dong\b", r"\btrich quy\b"],
        }]}
        esg = claim("esg", "ESG")
        esg["label"] = "Lợi nhuận sau thuế hợp nhất"
        direct = claim("direct", "Financial")
        direct["label"] = "Lợi nhuận sau thuế thu nhập doanh nghiệp"
        fund = claim("fund", "Financial")
        fund["label"] = "Tạm trích Quỹ khen thưởng từ lợi nhuận sau thuế"
        parent = claim("parent", "Financial")
        parent["label"] = "Lợi nhuận sau thuế của cổ đông Công ty mẹ"
        self.assertIn("family:profit_after_tax", keys(direct, profile))
        self.assertNotIn("family:profit_after_tax", keys(fund, profile))
        self.assertNotIn("family:profit_after_tax", keys(parent, profile))
        rows, coverage = discover([esg, direct, fund, parent], profile)
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]["record_ids"]), {"esg", "direct"})
        self.assertFalse(next(c for c in coverage if c["record_id"] == "fund")["candidate_ids"])
        explicit, _ = discover([esg, direct, fund, parent], profile,
                               [{"record_ids": ["esg", "parent"], "relation": "equal"}])
        self.assertEqual(len(explicit), 2)

    def test_bsr_profile_v2_rejects_profit_phrase_in_other_metrics(self):
        profile = json.loads((Path(__file__).resolve().parents[1] /
                              "data/config/bsr_cross_report_discovery_v2.json").read_text(encoding="utf-8"))
        direct = claim("direct", "Financial")
        direct["label"] = "Lợi nhuận sau thuế thu nhập doanh nghiệp (60=50-51-52) Trong đó:"
        fund = claim("fund", "Financial")
        fund["label"] = "Tạm trích Quỹ khen thưởng, phúc lợi từ lợi nhuận sau thuế năm 2022"
        parent = claim("parent", "Financial")
        parent["label"] = "Lợi nhuận sau thuế của cổ đông của Công ty mẹ"
        for item, expected in ((direct, True), (fund, False), (parent, False)):
            self.assertEqual("family:profit_after_tax" in keys(item, profile), expected)

    def test_numeric_diagnostic_not_verdict(self):
        index = {"a": claim("a", "ESG", value=591000000000),
                 "b": claim("b", "Financial", value=591091587455)}
        row = {"comparison_id": "c", "record_ids": ["a", "b"]}
        result = diagnostic(row, index, {"c": 500000000})
        self.assertEqual(result["status"], "within_proposed_rounding")
        self.assertFalse(result["semantic_equivalence_established"])
        self.assertFalse(result["tolerance_human_approved"])
        self.assertEqual(diagnostic(row, index, {})["status"], "difference_precision_unknown")
        index["b"]["unit"] = None
        self.assertIn("not_computed", diagnostic(row, index, {})["status"])

    def test_bad_tolerance_rejected(self):
        index = {"a": claim("a", "ESG"), "b": claim("b", "Financial")}
        for tol in (True, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                diagnostic({"comparison_id": "c", "record_ids": ["a", "b"]}, index, {"c": tol})

    def test_triage_requires_identity_preserves_history_and_is_not_gold(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "findings.json").write_text(json.dumps([{"comparison_id": "c", "input_digest": "hash"}]))
            row = dict(comparison_id="c", input_digest="hash", decision="potential_contradiction",
                       reviewer="", reviewed_at_utc="", notes="Synthetic test only")
            def write():
                with (root / "decisions.csv").open("w", newline="", encoding="utf-8") as stream:
                    writer = csv.DictWriter(stream, fieldnames=list(row))
                    writer.writeheader()
                    writer.writerow(row)
            write()
            with self.assertRaisesRegex(ValueError, "required"):
                ingest(root, root / "decisions.csv", root / "history.json")
            row.update(reviewer="synthetic reviewer", reviewed_at_utc="2026-01-01T00:00:00Z")
            write()
            ingest(root, root / "decisions.csv", root / "history.json")
            self.assertEqual(json.loads((root / "history.json").read_text())["gold_status"], "not_adjudicated")
            with self.assertRaisesRegex(ValueError, "output_exists"):
                ingest(root, root / "decisions.csv", root / "history.json")
            row["input_digest"] = "stale"
            write()
            with self.assertRaisesRegex(ValueError, "stale"):
                ingest(root, root / "decisions.csv", root / "other.json")


if __name__ == "__main__":
    unittest.main()
