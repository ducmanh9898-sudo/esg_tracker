"""Single-company gate tests; accepted review data below is synthetic only."""

import copy
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.bsr_pilot_acceptance_gate import collect_context, evaluate_gate, run
from tools.bsr_review_packet import CHECK_FIELDS, response_template, validate_responses


class BsrPilotAcceptanceGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = collect_context()

    def test_current_bsr_is_not_accepted_and_roadmap_remains_separate(self):
        result = evaluate_gate(self.context)
        statuses = {item["criterion_id"]: item["status"] for item in result["criteria"]}
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["bsr_pilot_accepted"])
        self.assertEqual(statuses, {
            "input_provenance": "needs_review",
            "finding_traceability": "pass",
            "esg_two_level_assessments": "pass",
            "pdf_case_adjudication": "blocked",
            "temporal_comparability": "needs_review",
            "financial_candidate_safety": "pass",
            "standards_verification_level": "pass",
        })
        self.assertEqual(result["milestones"][1]["status"], "future_expansion")
        self.assertFalse(result["milestones"][1]["satisfied_by_bsr_gate"])
        self.assertEqual(result["status_counts"], {"pass": 4, "needs_review": 2, "blocked": 1})
        pdf = next(item for item in result["criteria"] if item["criterion_id"] == "pdf_case_adjudication")
        self.assertEqual(pdf["evidence"]["pending_count"], 4)
        self.assertEqual(pdf["evidence"]["gold_labels_created"], 0)

    def test_synthetic_verified_inputs_and_reviews_can_pass_single_company_gate(self):
        context = copy.deepcopy(self.context)
        for claim in context["claims"]:
            claim["period_type"] = "annual"
            claim["reporting_boundary"] = "Synthetic verified boundary"
            claim["reporting_boundary_verified"] = True
            claim["review_status"] = "reviewed"
            for evidence in claim["evidence"]:
                evidence["source_text"] = "Synthetic reviewed source text"
        context["dry_run"]["handoff_preflight"]["manual_review_records"] = []
        context["dry_run"]["handoff_preflight"]["summary"]["manual_review"] = 0
        responses = response_template(context["packet"])
        for entry, case in zip(responses["responses"], context["packet"]["cases"]):
            entry["status"] = "accepted"
            entry["reviewer"]["name"] = "Synthetic reviewer fixture"
            entry["source_basis"] = [{
                "source_ref_id": source["source_ref_id"],
                "source_document": source["pdf_file_name"],
                "pages": source["source_pages"],
                "observation": "Synthetic PDF observation fixture only.",
            } for source in case["sources"]]
            entry["decision"] = {
                "reviewed_outcome": "Synthetic review accepted this case.",
                "system_result_assessment": "confirmed",
                "rationale": "Synthetic source inspection fixture.",
                "checks": {field: "Synthetic verified condition." for field in CHECK_FIELDS},
            }
        context["review_validation"] = validate_responses(context["packet"], responses)
        self.assertTrue(context["review_validation"]["valid"])
        for pair in context["dry_run"]["cases"]["board_temporal"]["comparisons"]:
            pair["comparison_performed"] = True
            pair["assessment_status"] = "Comparable"
            pair["flags"]["missing_context"] = []
            pair["flags"]["incompatibilities"] = []
        result = evaluate_gate(context)
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["bsr_pilot_accepted"])
        self.assertTrue(all(item["status"] == "pass" for item in result["criteria"]))
        self.assertFalse(result["milestones"][1]["satisfied_by_bsr_gate"])
        self.assertEqual(context["review_validation"]["gold_labels_created"], 0)

    def test_null_value_is_not_a_structural_error_or_a_contradiction(self):
        context = copy.deepcopy(self.context)
        claim_id = context["claims"][0]["claim_id"]
        context["claims"][0]["value"] = None
        result = evaluate_gate(context)
        criterion = next(item for item in result["criteria"] if item["criterion_id"] == "input_provenance")
        self.assertEqual(criterion["status"], "needs_review")
        self.assertEqual(criterion["evidence"]["schema_error_count"], 0)
        self.assertIn(claim_id, criterion["evidence"]["explicit_null_value_claim_ids"])
        self.assertEqual(result["criteria"][5]["evidence"]["status"], "NeedsReview")

    def test_documented_synthetic_exceptions_cover_input_only(self):
        context = copy.deepcopy(self.context)
        fields = ("source_text", "period_type", "reporting_boundary", "source_review", "handoff_manual_review")
        context["exceptions"] = [{
            "claim_id": claim["claim_id"],
            "field": field,
            "status": "accepted",
            "reviewer": "Synthetic exception reviewer",
            "reason": "Synthetic documented waiver fixture",
            "source_basis": "Synthetic exception basis fixture",
        } for claim in context["claims"] for field in fields]
        result = evaluate_gate(context)
        statuses = {item["criterion_id"]: item["status"] for item in result["criteria"]}
        self.assertEqual(statuses["input_provenance"], "pass")
        self.assertEqual(statuses["pdf_case_adjudication"], "blocked")
        self.assertFalse(result["bsr_pilot_accepted"])
        context["exceptions"][0]["source_basis"] = ""
        invalid = evaluate_gate(context)
        self.assertEqual(invalid["criteria"][0]["status"], "blocked")

    def test_candidate_or_mapping_promotion_without_evidence_is_blocked(self):
        context = copy.deepcopy(self.context)
        context["dry_run"]["cases"]["workforce_financial"]["finding_created"] = True
        standard_row = next(row for row in context["coverage"]["claims"] if row["has_unverified_candidate"])
        standard_row["has_unverified_candidate"] = False
        result = evaluate_gate(context)
        statuses = {item["criterion_id"]: item["status"] for item in result["criteria"]}
        self.assertEqual(statuses["financial_candidate_safety"], "blocked")
        self.assertEqual(statuses["standards_verification_level"], "blocked")

    def test_gate_writes_only_to_requested_temporary_directory(self):
        protected = [ROOT / "output" / name for name in (
            "normalized_claims.json", "findings.json", "graph.json"
        )]
        before = {path: path.read_bytes() for path in protected}
        with tempfile.TemporaryDirectory(prefix="bsr_acceptance_test_") as temp:
            result = run(Path(temp) / "report")
            self.assertEqual(result["status"], "blocked")
            self.assertTrue((Path(temp) / "report" / "bsr_pilot_acceptance_gate.json").is_file())
            self.assertTrue((Path(temp) / "report" / "bsr_pilot_acceptance_gate.md").is_file())
        self.assertEqual(before, {path: path.read_bytes() for path in protected})


if __name__ == "__main__":
    unittest.main()
