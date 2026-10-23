import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.bsr_review_packet import CHECK_FIELDS, create_packet, response_template, validate_responses


class BsrReviewPacketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="bsr_review_packet_test_")
        cls.packet = create_packet(Path(cls.temp.name) / "packet")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def _completed_first_response(self):
        responses = response_template(self.packet)
        entry = responses["responses"][0]
        entry["status"] = "accepted"
        entry["reviewer"]["name"] = "Reviewer fixture"
        entry["source_basis"] = [
            {
                "source_ref_id": source["source_ref_id"],
                "source_document": source["pdf_file_name"],
                "pages": source["source_pages"],
                "observation": "Fixture: reviewer transcribed and checked this source location.",
            }
            for source in self.packet["cases"][0]["sources"]
        ]
        entry["decision"] = {
            "reviewed_outcome": "Fixture: both values require a documented source distinction.",
            "system_result_assessment": "confirmed",
            "rationale": "Fixture: PDF pages were examined for both inputs.",
            "checks": {field: "Fixture: reviewed against cited pages." for field in CHECK_FIELDS},
        }
        return responses

    def test_all_four_cases_start_pending_and_have_source_locators(self):
        cases = self.packet["cases"]
        self.assertEqual(len(cases), 4)
        self.assertEqual([case["adjudication_status"] for case in cases], ["pending_adjudication"] * 4)
        self.assertFalse(self.packet["gold_label_created"])
        self.assertEqual(len([case for case in cases if "TEMPORAL-BOARD" in case["case_id"]]), 2)
        for case in cases:
            self.assertEqual(len(case["sources"]), 2)
            for source in case["sources"]:
                self.assertIsNotNone(source["value"])
                self.assertIsInstance(source["observation_year"], int)
                self.assertTrue(source["source_pages"])
                self.assertTrue(source["json_pointer"].startswith("/"))
                self.assertTrue(Path(source["extract_json_path"]).is_file())
                self.assertIsNone(source["pdf_local_path"])
        workforce = next(case for case in cases if case["case_id"] == "VC-REAL-WORKFORCE-2025")
        self.assertFalse(workforce["system_result"]["comparison_performed"])
        self.assertEqual(workforce["system_result"]["fc01_status"], "inactive")
        self.assertEqual(self.packet["packet_id"], "BSR-STAGE17-937B200A0CB36E34")
        financial = next(source for source in workforce["sources"] if source["record_type"] == "financial_disclosure")
        self.assertEqual(financial["scope"]["entity_set"], "parent_plus_subsidiaries")
        self.assertEqual(financial["measurement_date"]["value"], "2025-12-31")
        self.assertEqual(workforce["system_result"]["esg_measurement_context"]["reporting_boundary"]["entity_set"], "unknown")
        self.assertEqual(workforce["system_result"]["related_financial_observations"][0]["source_pages"], None)

    def test_blank_template_is_valid_but_remains_pending(self):
        result = validate_responses(self.packet, response_template(self.packet))
        self.assertTrue(result["valid"])
        self.assertEqual(result["pending_count"], 4)
        self.assertEqual(result["accepted_count"], 0)
        self.assertEqual(result["gold_labels_created"], 0)

    def test_accepted_requires_reviewer_pdf_basis_and_specific_decision(self):
        completed = self._completed_first_response()
        result = validate_responses(self.packet, completed)
        self.assertTrue(result["valid"])
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["pending_count"], 3)
        self.assertEqual(result["gold_labels_created"], 0)
        self.assertEqual(self.packet["cases"][0]["adjudication_status"], "pending_adjudication")
        for name, change in (
            ("reviewer", lambda entry: entry["reviewer"].update(name=None)),
            ("source", lambda entry: entry.update(source_basis=[])),
            ("decision", lambda entry: entry["decision"].update(reviewed_outcome=None)),
            ("rationale", lambda entry: entry["decision"].update(rationale=None)),
            ("check", lambda entry: entry["decision"]["checks"].update(reporting_boundary=None)),
            ("pdf", lambda entry: entry["source_basis"][0].update(source_document="extract.json")),
        ):
            with self.subTest(name=name):
                incomplete = copy.deepcopy(completed)
                change(incomplete["responses"][0])
                result = validate_responses(self.packet, incomplete)
                self.assertFalse(result["valid"])
                self.assertEqual(result["accepted_count"], 0)
                self.assertEqual(result["cases"][0]["effective_status"], "pending_adjudication")

    def test_stale_packet_id_cannot_accept_a_review(self):
        response = self._completed_first_response()
        response["packet_id"] = "different-packet"
        result = validate_responses(self.packet, response)
        self.assertFalse(result["valid"])
        self.assertEqual(result["accepted_count"], 0)

    def test_create_does_not_change_main_snapshot_or_catalogue(self):
        protected = [ROOT / "data" / "config" / "validation_cases.json"] + [
            ROOT / "output" / name for name in ("normalized_claims.json", "findings.json", "graph.json")
        ]
        before = {path: path.read_bytes() for path in protected}
        with tempfile.TemporaryDirectory(prefix="bsr_review_packet_output_test_") as temp:
            packet = create_packet(Path(temp) / "packet")
            result = validate_responses(packet, response_template(packet))
            self.assertEqual(result["pending_count"], 4)
        self.assertEqual(before, {path: path.read_bytes() for path in protected})


if __name__ == "__main__":
    unittest.main()
