"""Regression tests for source-bound technical Extract refinement."""
from __future__ import annotations

from copy import deepcopy
import unittest
from unittest.mock import patch

from tools.corporate_extract_alignment import (
    code_column_suspects, code_column_watchlist, decisions_index, digest, make_pair_pack,
    quarantine, review_candidates,
)
from kg.corporate_table_context import table_row_number, table_rows_compatible


def record(identity, value, column, year=None):
    return {
        "record_id": identity, "record_type": "financial_measurement", "dimension": "X",
        "value": {"status": "available", "original_value": value, "original_unit": "VND",
                  "original_scale": None, "normalized_value": int(value),
                  "normalized_unit": "VND", "normalization_factor": 1,
                  "normalization_note": "source value"},
        "period": {"observation_year": year, "year_basis": "unknown"},
        "evidence": [{"physical_page": 7, "table_id": "t1", "row": 1,
                      "column": column, "headers": [], "exact_quote": value,
                      "context_text": value}],
        "quality": {"uncertainty": [], "review_status": "pending_human_review",
                    "parser_name": "fixture", "extraction_method": "rule",
                    "reviewer": None, "reviewed_at_utc": None, "review_basis": None},
    }


class ExtractAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.code = record("code-100", "100", 2)
        self.amount = record("amount-2023", "68680527655901", 4, 2023)
        self.document = {"document": {"report_type": "Financial"},
                         "records": [self.code, self.amount]}

    def test_code_cell_with_same_row_amount_is_quarantined_but_keeps_quote(self):
        suspects = code_column_suspects(self.document)
        self.assertEqual([s["record_id"] for s in suspects], ["code-100"])
        old_evidence = deepcopy(self.code["evidence"])
        quarantine(self.code)
        self.assertEqual(self.code["value"]["status"], "ambiguous")
        self.assertIsNone(self.code["value"]["normalized_value"])
        self.assertIsNone(self.code["value"]["original_unit"])
        self.assertEqual(self.code["evidence"], old_evidence)
        self.assertEqual(self.code["quality"]["review_status"], "pending_human_review")

    def test_signal_without_same_row_year_amount_remains_watchlist_only(self):
        self.document["records"] = [self.code]
        self.assertEqual(code_column_suspects(self.document), [])
        self.assertEqual(len(code_column_watchlist(self.document)), 1)

    def test_ocr_noise_labelled_as_year_does_not_hide_code_column(self):
        self.code["evidence"][0]["headers"] = [{"role": "year", "column": 2, "text": "ileal"}]
        self.assertEqual(len(code_column_suspects(self.document)), 1)
        self.code["evidence"][0]["headers"][0]["text"] = "Số cuối năm"
        self.assertEqual(code_column_suspects(self.document), [])

    def test_review_decisions_are_bound_to_original_record_and_human_checks(self):
        base = {"schema_version": "corporate-extract-alignment-review-1.0",
                "source_manifest_sha256": "sourcehash", "records": [{
                    "record_id": "code-100", "input_digest": digest(self.code),
                    "decision": "correct", "reviewer": "Reviewer", "reviewed_at_utc": "2026-10-20T10:00:00Z",
                    "basis": "PDF page 7 table header", "checks": {
                        "source_quote": True, "value": True, "association": True, "semantic_context": True},
                    "corrections": {"metric_id": None}}]}
        self.assertEqual(len(decisions_index(None, "sourcehash", {"code-100": self.code})), 0)
        # Read from an actual JSON file because this is the assistant/user exchange format.
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as temp:
            path = Path(temp) / "review.json"
            path.write_text(json.dumps(base), encoding="utf-8")
            self.assertIn("code-100", decisions_index(path, "sourcehash", {"code-100": self.code}))
            base["records"][0]["checks"]["association"] = False
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "four_checks"):
                decisions_index(path, "sourcehash", {"code-100": self.code})
            base["records"][0]["checks"]["association"] = True
            base["records"][0]["input_digest"] = "stale"
            path.write_text(json.dumps(base), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "stale"):
                decisions_index(path, "sourcehash", {"code-100": self.code})

    def test_review_selection_is_cross_document_and_not_gold(self):
        def row(year, dimension):
            item = deepcopy(self.code)
            item.update(record_id=f"{year}-{dimension}", dimension=dimension,
                        record_type="measurement", metric_id=None, metric_definition=None,
                        metric_label="candidate", boundary={}, statement={"original_quote": "100"})
            return ({"report_year": year, "report_type": "ESG", "financial_scope": None,
                     "document_id": f"doc-{year}", "pdf_path": f"pdf/{year}.pdf"},
                    {"document": {"report_type": "ESG", "source": {"sha256": "a" * 64}},
                     "records": [item]})
        queue = review_candidates([row(2023, "E"), row(2024, "S")], limit=2)
        self.assertEqual({r["dimension"] for r in queue}, {"E", "S"})

    def test_repeated_table_label_in_different_parent_group_is_not_paired(self):
        def table_record(row_number, value):
            item = deepcopy(self.amount)
            item["metric_label"] = "Dầu thô trong nước"
            item["evidence"][0]["context_text"] = (
                f"{value}\nDầu thô trong nước\n{row_number}\n2023\ntấn")
            return item

        processed = table_record("2.1", "5.540.498")
        feedstock_input = table_record("1.1", "5.601.406")
        processed_other_report = table_record("2.1", "5.540.498")
        self.assertEqual(table_row_number(processed), "2.1")
        self.assertFalse(table_rows_compatible(processed, feedstock_input))
        self.assertTrue(table_rows_compatible(processed, processed_other_report))
        feedstock_input["evidence"][0]["context_text"] = "5.601.406\nDầu thô trong nước\n2023\ntấn"
        self.assertFalse(table_rows_compatible(processed, feedstock_input))

    def test_pair_pack_selects_matching_table_group_instead_of_first_label_match(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        def item(identity, row_number, value):
            result = deepcopy(self.amount)
            result.update(record_id=identity, record_type="measurement", dimension="E",
                          metric_label="Dầu thô trong nước", boundary={}, restatement={})
            result["value"].update(status="available", normalized_value=value,
                                   normalized_unit="t")
            result["period"]["observation_year"] = 2023
            result["evidence"][0]["context_text"] = (
                f"{value}\nDầu thô trong nước\n{row_number}\n2023\ntấn")
            result["evidence"][0]["exact_quote"] = str(value)
            result["evidence"][0]["physical_page"] = 25 if identity == "processed-2023" else 24
            return result

        def document(report_year, records):
            row = {"report_year": report_year, "report_type": "ESG", "financial_scope": None,
                   "document_id": f"doc-{report_year}", "pdf_path": f"pdf/{report_year}.pdf"}
            raw = {"document": {"company_id": "PILOT", "source": {"sha256": "a" * 64}},
                   "records": records}
            return row, raw

        docs = [document(2023, [item("processed-2023", "2.1", 5540498)]),
                document(2024, [item("input-2024", "1.1", 5601406),
                                item("processed-2024", "2.1", 5540498)])]
        with TemporaryDirectory() as temp, \
                patch("tools.corporate_extract_alignment.checked_delivery",
                      return_value=(Path(temp) / "manifest.json", {}, docs)), \
                patch("tools.corporate_extract_alignment.sha256", return_value="b" * 64):
            output = Path(temp) / "pairs.json"
            make_pair_pack(Path(temp) / "manifest.json", output, limit=1,
                           pairing="same-type")
            pairs = json.loads(output.read_text(encoding="utf-8"))["comparisons"]
        self.assertEqual(len(pairs), 1)
        self.assertEqual(set(pairs[0]["record_ids"]), {"processed-2023", "processed-2024"})

    def test_cross_type_pack_does_not_present_same_type_as_demo_comparison(self):
        import json
        from pathlib import Path
        from tempfile import TemporaryDirectory

        base = deepcopy(self.amount)
        base.update(record_type="measurement", metric_label="Chỉ tiêu chung", dimension="E",
                    boundary={}, restatement={})
        base["value"].update(status="available", normalized_value=10, normalized_unit="VND")
        base["period"]["observation_year"] = 2023
        docs = []
        for year, report_type in ((2023, "ESG"), (2024, "ESG"), (2024, "Financial")):
            item = deepcopy(base)
            item["record_id"] = f"{year}-{report_type}"
            item["record_type"] = "financial_measurement" if report_type == "Financial" else "measurement"
            docs.append((
                {"report_year": year, "report_type": report_type, "financial_scope": None,
                 "document_id": f"doc-{year}-{report_type}", "pdf_path": f"pdf/{year}-{report_type}.pdf"},
                {"document": {"company_id": "PILOT", "source": {"sha256": "a" * 64}},
                 "records": [item]}))
        with TemporaryDirectory() as temp, \
                patch("tools.corporate_extract_alignment.checked_delivery",
                      return_value=(Path(temp) / "manifest.json", {}, docs)), \
                patch("tools.corporate_extract_alignment.sha256", return_value="b" * 64):
            output = Path(temp) / "pairs.json"
            make_pair_pack(Path(temp) / "manifest.json", output, limit=5)
            pack = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(pack["pairing_mode"], "cross-type")
        self.assertEqual(len(pack["comparisons"]), 1)
        self.assertEqual({side["report_type"] for side in pack["comparisons"][0]["sources"]},
                         {"ESG", "Financial"})


if __name__ == "__main__":
    unittest.main()
