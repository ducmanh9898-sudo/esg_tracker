import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.pilot_readiness import build_inventory


class PilotReadinessInventoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(
            (ROOT / "data" / "pilot_readiness_inventory.json").read_text(encoding="utf-8")
        )
        cls.schema = json.loads(
            (ROOT / "schemas" / "pilot-readiness-inventory-schema-v0.1.json").read_text(encoding="utf-8")
        )

    def test_inventory_schema_and_company_year_dimension_isolation(self):
        errors = list(Draft202012Validator(self.schema).iter_errors(self.inventory))
        self.assertEqual([error.message for error in errors], [])
        records = self.inventory["records"]
        self.assertEqual(len(records), 27)
        self.assertEqual(
            {(record["company_id"], record["report_year"], record["dimension"]) for record in records},
            {(company, year, dimension) for company in ("BSR", "PLX", "PVD") for year in (2023, 2024, 2025) for dimension in ("E", "S", "G")},
        )
        for record in records:
            self.assertEqual(record["report_id"], f"ESG-{record['company_id']}-{record['report_year']}")
            self.assertEqual(record["reporting_period"]["period_end"], f"{record['report_year']}-12-31")

    def test_bsr_has_esg_and_financial_records_for_all_three_years(self):
        bsr = [record for record in self.inventory["records"] if record["company_id"] == "BSR"]
        self.assertTrue(all(record["claims"]["claim_count"] > 0 for record in bsr))
        self.assertTrue(all(record["claims"]["evidence_count"] > 0 for record in bsr))
        self.assertTrue(all(record["financial_disclosure_availability"]["available"] for record in bsr))
        integration = self.inventory["bsr_financial_integration"]
        self.assertEqual(integration["years_with_esg_and_financial_records"], ["2023", "2024", "2025"])
        self.assertEqual(integration["fc01_status"], "inactive")

    def test_plx_and_pvd_have_no_financial_disclosure_counterpart(self):
        for company in ("PLX", "PVD"):
            with self.subTest(company=company):
                records = [record for record in self.inventory["records"] if record["company_id"] == company]
                self.assertTrue(all(not record["financial_disclosure_availability"]["available"] for record in records))
                self.assertTrue(all(record["status"] == "blocked" for record in records))
                self.assertTrue(all(any("financial disclosure" in blocker for blocker in record["blockers"]) for record in records))

    def test_missing_provenance_is_explicit(self):
        for record in self.inventory["records"]:
            if record["company_id"] == "BSR":
                self.assertFalse(record["provenance"]["original_text_available"])
                self.assertTrue(record["provenance"]["source_pages_available"])
                self.assertTrue(record["provenance"]["source_pointers_available"])
                self.assertIn("original_text", " ".join(record["blockers"]))
            else:
                self.assertFalse(record["provenance"]["source_pages_available"])
                self.assertFalse(record["provenance"]["source_pointers_available"])

    def test_bsr_boundary_and_workforce_link_remain_unverified_needs_review(self):
        bsr = [record for record in self.inventory["records"] if record["company_id"] == "BSR"]
        self.assertTrue(all(record["reporting_boundary"]["verification_status"] == "unverified" for record in bsr))
        self.assertTrue(all(record["temporal_comparability"]["status"] == "needs_review" for record in bsr))
        workforce_2025 = next(record for record in bsr if record["report_year"] == 2025 and record["dimension"] == "S")
        self.assertEqual(workforce_2025["financial_disclosure_availability"]["workforce_link_status"], "NeedsReview")
        self.assertIn("scope/định nghĩa", " ".join(workforce_2025["blockers"]))


if __name__ == "__main__":
    unittest.main()
