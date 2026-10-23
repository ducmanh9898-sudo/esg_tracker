import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.bsr_handoff_impact import merge_handoff
from tools.rule_engine import evaluate


class BsrHandoffImpactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = json.loads((ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8"))
        cls.handoff = json.loads((ROOT / "data" / "handoff" / "provenance_boundary_handoff_bsr2023_2025_strict_review.json").read_text(encoding="utf-8"))
        cls.rules = json.loads((ROOT / "data" / "config" / "rules.json").read_text(encoding="utf-8"))

    def test_merge_matches_both_ids_and_keeps_boundary_status_separate(self):
        original = copy.deepcopy(self.claims)
        merged, report = merge_handoff(self.claims, self.handoff)
        self.assertEqual(report["conflicts"], [])
        self.assertEqual(report["matched_records"], 30)
        self.assertEqual(self.claims, original)
        by_id = {claim["claim_id"]: claim for claim in merged}
        for record in self.handoff["records"]:
            claim = by_id[record["claim_id"]]
            evidence = next(e for e in claim["evidence"] if e["evidence_id"] == record["evidence_id"])
            self.assertEqual(evidence["boundary"], record["boundary"])
            self.assertEqual(evidence["extraction_status"], record["extraction_status"])
            self.assertFalse(claim["reporting_boundary_verified"])
            self.assertFalse(evidence["original_text_verbatim"])
            self.assertIsNone(evidence["source_text"])
            self.assertEqual(evidence["original_text"], record["original_text"])

    def test_wrong_evidence_id_and_source_conflicts_stop_entire_merge(self):
        for change, expected in (
            ({"evidence_id": "EVD-WRONG"}, "evidence_id does not belong"),
            ({"source_file": "BSR_2024_esg.json"}, "source_file"),
            ({"json_pointer": "/wrong"}, "json_pointer"),
            ({"report_year": 2024}, "report_year"),
        ):
            with self.subTest(change=change):
                handoff = copy.deepcopy(self.handoff)
                handoff["records"][0].update(change)
                merged, report = merge_handoff(self.claims, handoff)
                self.assertIsNone(merged)
                self.assertIn(expected, " ".join(report["conflicts"][0]["reasons"]))
        claims = copy.deepcopy(self.claims)
        claims[0]["value"] = -999
        merged, report = merge_handoff(claims, self.handoff)
        self.assertIsNone(merged)
        self.assertTrue(any("source value differs" in reason for item in report["conflicts"] for reason in item["reasons"]))

    def test_unverified_boundary_does_not_promote_r01_to_contradicted(self):
        merged, report = merge_handoff(self.claims, self.handoff)
        self.assertFalse(report["conflicts"])
        baseline = next(f for f in evaluate(self.claims, self.rules) if f["rule_id"] == "R01" and f["company_id"] == "BSR")
        after = next(f for f in evaluate(merged, self.rules) if f["rule_id"] == "R01" and f["company_id"] == "BSR")
        self.assertEqual(baseline["status"], "NeedsReview")
        self.assertEqual(after["status"], "NeedsReview")
        self.assertEqual(after["finding_id"], baseline["finding_id"])


if __name__ == "__main__":
    unittest.main()
