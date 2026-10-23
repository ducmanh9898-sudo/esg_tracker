import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.financial_adapter import adapt_reports


class FinancialAdapterTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_paths = sorted(
            (ROOT / "data" / "extract" / "financial").glob("BCTC_BSR_*_esg.json")
        )
        cls.result = json.loads(
            (ROOT / "data" / "financial_disclosures_bsr.json").read_text(encoding="utf-8")
        )
        cls.schema = json.loads(
            (ROOT / "schemas" / "financial-disclosure-schema-v0.1.json").read_text(encoding="utf-8")
        )

    def test_all_records_match_contract_and_are_non_synthetic(self):
        self.assertEqual(len(self.source_paths), 3)
        self.assertEqual(len(self.result["records"]), 68)
        self.assertFalse(self.result["synthetic"])
        validator = Draft202012Validator(self.schema, format_checker=FormatChecker())
        for record in self.result["records"]:
            with self.subTest(disclosure_id=record["disclosure_id"]):
                errors = list(validator.iter_errors(record))
                self.assertEqual([error.message for error in errors], [])
                self.assertEqual(record["record_type"], "financial_disclosure")
                self.assertFalse(record["synthetic"])
                self.assertEqual(record["company_id"], "BSR")
                self.assertEqual(record["status"], record["data_status"])

    def test_source_pdf_is_normalized_and_no_local_path_leaks(self):
        serialized = json.dumps(self.result, ensure_ascii=False)
        self.assertNotIn("C:\\Users\\", serialized)
        self.assertNotIn("source_pdf", serialized)
        self.assertEqual(
            {record["report"]["source_uri"] for record in self.result["records"]},
            {
                "financial-report://BSR/BCTC/2023",
                "financial-report://BSR/BCTC/2024",
                "financial-report://BSR/BCTC/2025",
            },
        )

    def test_schema_difference_is_explicit_and_source_files_are_untouched(self):
        notes = {note["document_id"]: note for note in self.result["source_schema_notes"]}
        self.assertEqual(notes["BSR-BCTC-2023"]["source_schema"], "document_v1")
        self.assertEqual(notes["BSR-BCTC-2024"]["source_schema"], "document_v1")
        self.assertEqual(notes["BSR-BCTC-2025"]["source_schema"], "metadata_v2")
        self.assertIn("parent-plus-subsidiaries", notes["BSR-BCTC-2025"]["schema_difference"])
        self.assertNotIn("metadata.reporting_period", notes["BSR-BCTC-2023"]["schema_difference"])

    def test_workforce_provenance_and_company_year_isolation(self):
        workforce = [
            record for record in self.result["records"]
            if record["item"]["item_id"] == "workforce.total"
        ]
        self.assertEqual({record["report_year"] for record in workforce}, {2023, 2024, 2025})
        self.assertEqual({record["company_id"] for record in workforce}, {"BSR"})
        by_year = {record["report_year"]: record for record in workforce}
        self.assertEqual(by_year[2023]["value"], 1855)
        self.assertEqual(by_year[2023]["source_pages"], [12])
        self.assertEqual(by_year[2023]["source_pointer"], "/social/employees/total_at_2023_12_31")
        self.assertEqual(by_year[2025]["value"], 1946)
        self.assertEqual(by_year[2025]["source_pages"], [14])
        self.assertEqual(by_year[2025]["source_pointer"], "/social/workforce/employees_2025_12_31")
        self.assertEqual(by_year[2025]["scope"]["scope_id"], "consolidated_group")
        self.assertEqual(by_year[2025]["scope"]["entity_set"], "parent_plus_subsidiaries")
        self.assertEqual(by_year[2025]["scope"]["verification_status"], "verified")
        self.assertEqual(by_year[2025]["scope"]["source_document"], "BCTC_BSR_2025.pdf")
        self.assertEqual(by_year[2025]["scope"]["source_pages"], [14])
        self.assertEqual(by_year[2025]["measurement_date"]["value"], "2025-12-31")
        self.assertEqual(by_year[2025]["measurement_date"]["verification_status"], "verified")
        self.assertEqual(by_year[2025]["reporting_period"]["period_type"], "instant")
        self.assertEqual(by_year[2025]["employee_definition"]["verification_status"], "unverified")
        self.assertEqual(len({record["disclosure_id"] for record in self.result["records"]}), 68)

    def test_workforce_link_is_needs_review_when_scope_differs(self):
        link = json.loads(
            (ROOT / "data" / "config" / "financial_link_bsr_workforce_sample.json").read_text(encoding="utf-8")
        )
        check = link["checks"][0]
        self.assertEqual(check["status"], "NeedsReview")
        self.assertEqual(check["esg_claim_id"], "CLM-08082F5B81CD")
        self.assertEqual(check["financial_disclosure_id"], "FIN-BSR-BCTC-2025-workforce.total")
        self.assertEqual(check["comparison"]["performed"], False)
        self.assertTrue(check["result_policy"]["never_creates_contradicted"])
        self.assertEqual(check["result_policy"]["fc01_status"], "inactive")
        self.assertEqual(check["esg_measurement_context"]["reporting_boundary"]["entity_set"], "unknown")
        self.assertEqual(check["related_financial_observations"][0]["value"], 1594)
        self.assertEqual(check["related_financial_observations"][0]["reporting_boundary"]["entity_set"], "parent")
        self.assertIn("boundary", check["reason"])


if __name__ == "__main__":
    unittest.main()
