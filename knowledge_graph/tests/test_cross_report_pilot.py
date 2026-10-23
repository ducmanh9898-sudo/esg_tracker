"""Mechanical checks against the actual pilot PDFs; no human decision is simulated."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

import fitz

from handoff.bsr_extract_2023_2025_v1.validate import load_json, sha256
from tools.cross_report_pilot import _esg_record, build
from tools.cross_report_review import check, select_template


ROOT = Path(__file__).resolve().parents[1]
CONFIG = load_json(ROOT / "data/config/bsr_cross_report_profit_v1.json")
PDF_2024 = ROOT / "data/handoff/bsr_corporate_aligned_v2/pdf/BSR_2024.pdf"


class CrossReportPilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = next(row for row in CONFIG["cases"]
                        if row["case_id"] == "BSR-PROFIT-2024-CURRENT")
        cls.source = {"sha256": sha256(PDF_2024), "page_count": len(fitz.open(PDF_2024))}

    def test_real_pdf_cell_year_unit_and_provenance(self):
        record = _esg_record(self.case, self.source, PDF_2024)
        evidence = record["evidence"][0]
        self.assertEqual(record["value"]["normalized_value"], 591_000_000_000)
        self.assertEqual(record["period"]["observation_year"], 2024)
        self.assertEqual(evidence["source_sha256"], self.source["sha256"])
        self.assertEqual(evidence["physical_page"], 23)
        self.assertEqual(evidence["exact_quote"], "591")
        self.assertIn("Năm 2024", [row["text"] for row in evidence["headers"]])
        self.assertEqual(record["quality"]["review_status"], "pending_human_review")

    def test_source_hash_and_quote_mismatch_block(self):
        with self.assertRaisesRegex(ValueError, "source_pdf_sha256_mismatch"):
            _esg_record(self.case, {**self.source, "sha256": "0" * 64}, PDF_2024)
        changed = deepcopy(self.case)
        changed["esg_original_value"] = "999"
        with self.assertRaisesRegex(ValueError, "source_context_missing"):
            _esg_record(changed, self.source, PDF_2024)

    def test_wrong_year_header_and_scale_block(self):
        changed = deepcopy(self.case)
        changed["observation_year"] = 2025
        with self.assertRaisesRegex(ValueError, "year_header_not_unique_in_column"):
            _esg_record(changed, self.source, PDF_2024)
        changed = deepcopy(self.case)
        changed["esg_normalized_value"] += 1_000_000_000
        with self.assertRaisesRegex(ValueError, "unit_scale_inconsistent"):
            _esg_record(changed, self.source, PDF_2024)

    def test_existing_batch_is_never_overwritten(self):
        with self.assertRaisesRegex(ValueError, "output_exists_choose_new_directory"):
            build(ROOT / "data/handoff/bsr_corporate_aligned_v2/manifest.json",
                  ROOT / "data/config/bsr_cross_report_profit_v1.json", ROOT / "data")

    def test_review_template_is_pending_and_digest_bound(self):
        run = ROOT / "output/bsr_cross_report_profit_v1"
        pack = ROOT / "data/handoff/bsr_cross_report_profit_v1/notes/cross_report_review_pack.json"
        reviews = ROOT / "data/review/bsr_cross_report_profit_v1/decisions_template.json"
        if not (run / "review_template.json").exists():
            self.skipTest("real Graph pilot output has not been generated")
        template = select_template(run, pack)
        self.assertEqual(len(template["record_events"]), 8)
        self.assertEqual(len(template["comparison_events"]), 4)
        self.assertTrue(all(row["decision"] == "pending" for key in
                            ("record_events", "comparison_events") for row in template[key]))
        self.assertEqual(check(run, pack, reviews)["status"], "valid")
        template["record_events"][0]["input_digest"] = "stale"
        with tempfile.TemporaryDirectory() as directory:
            edited = Path(directory) / "reviews.json"
            edited.write_text(json.dumps(template), encoding="utf-8")
            result = check(run, pack, edited)
            self.assertEqual(result["status"], "invalid")
            self.assertTrue(any(item.startswith("stale_input_digest:") for item in result["issues"]))


if __name__ == "__main__":
    unittest.main()
