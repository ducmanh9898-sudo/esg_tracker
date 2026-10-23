import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.standards_crosswalk import load_crosswalk
from tools.standards_coverage_report import build_report, run


class StandardsCoverageReportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = json.loads((ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig"))
        cls.assessments = json.loads((ROOT / "output" / "claim_assessments.json").read_text(encoding="utf-8-sig"))
        cls.crosswalk = load_crosswalk()
        cls.rules = json.loads((ROOT / "data" / "config" / "rule_catalogue.json").read_text(encoding="utf-8-sig"))
        cls.gaps = json.loads((ROOT / "data" / "integration_gap_status.json").read_text(encoding="utf-8-sig"))
        cls.report = build_report(cls.claims, cls.assessments, cls.crosswalk, cls.rules, cls.gaps)

    def test_claims_are_counted_once_even_with_multiple_mappings(self):
        report = self.report
        self.assertEqual(report["counts"]["unique_claims"], 30)
        self.assertEqual(len(report["claims"]), 30)
        self.assertEqual(len({row["claim_id"] for row in report["claims"]}), 30)
        self.assertEqual(report["counts"]["verified_mapping_claims"], 3)
        self.assertEqual(report["counts"]["unverified_candidate_claims"], 3)
        self.assertEqual(report["counts"]["candidate_only_claims"], 0)
        self.assertEqual(report["counts"]["unmapped_claims"], 27)
        self.assertEqual(report["counts"]["verified_mapping_relations"], 7)
        self.assertEqual(report["counts"]["unverified_candidate_relations"], 3)
        duplicate_mapping = copy.deepcopy(self.crosswalk)
        duplicate_mapping["mappings"].append(copy.deepcopy(duplicate_mapping["mappings"][0]))
        duplicated = build_report(self.claims, self.assessments, duplicate_mapping, self.rules, self.gaps)
        self.assertEqual(duplicated["counts"]["unique_claims"], 30)
        self.assertEqual(duplicated["counts"]["verified_mapping_claims"], 3)

    def test_verified_relationship_and_unverified_candidate_remain_distinct(self):
        scope1 = next(row for row in self.report["claims"] if row["claim_id"] == "CLM-0D01A0724720")
        self.assertEqual(scope1["coverage_status"], "verified_with_candidates")
        self.assertEqual({m["verification_status"] for m in scope1["mappings"]}, {"verified", "unverified"})
        sasb = next(m for m in scope1["mappings"] if m["family"] == "SASB Standard")
        self.assertEqual(sasb["verification_status"], "unverified")
        self.assertEqual(sasb["industry_applicability_status"], "unverified")
        self.assertTrue(any("SICS" in item for item in sasb["applicability_missing"]))
        chair = next(row for row in self.report["claims"] if row["metric_id"] == "chair_ceo_separate")
        self.assertEqual({m["family"] for m in chair["mappings"]}, {"GRI", "IFRS S1"})
        self.assertEqual(next(m for m in chair["mappings"] if m["family"] == "IFRS S1")["verification_status"], "unverified")
        self.assertTrue(all(row["review_status"] == "unreviewed" for row in self.report["claims"]))

    def test_sasb_standard_and_ifrs_s2_guidance_are_separate_sources(self):
        scope1 = next(row for row in self.report["claims"] if row["metric_id"] == "ghg_scope1")
        industry = [m for m in scope1["mappings"] if m["reference_code"] == "EM-RM-110a.1"]
        self.assertEqual(len(industry), 2)
        self.assertEqual({m["source_type"] for m in industry}, {"sasb_standard", "industry_based_guidance"})
        self.assertEqual({m["verification_status"] for m in industry}, {"verified", "unverified"})
        self.assertEqual({m["industry_applicability_status"] for m in industry}, {"unverified"})
        self.assertEqual(self.report["families"]["SASB Standard"]["verified_claim_count"], 0)
        self.assertEqual(self.report["families"]["IFRS S2 Industry-based Guidance"]["verified_claim_count"], 2)

    def test_output_is_temporary_and_rule_assessments_are_not_compliance(self):
        protected = [ROOT / "data" / "config" / "standards_crosswalk_sample.json", ROOT / "data" / "config" / "rule_catalogue.json"]
        protected += [ROOT / "output" / name for name in ("normalized_claims.json", "findings.json", "graph.json")]
        before = {path: path.read_bytes() for path in protected}
        with tempfile.TemporaryDirectory(prefix="bsr_coverage_test_") as temp:
            report = run(Path(temp) / "coverage")
            output = Path(temp) / "coverage"
            self.assertTrue((output / "bsr_standards_coverage.json").is_file())
            self.assertTrue((output / "bsr_standards_coverage.md").is_file())
            self.assertEqual(report["counts"]["project_rules"], 9)
            self.assertIn("not compliance tests", report["project_rule_policy"])
            self.assertIn("no compliance or violation conclusion", report["conclusion_policy"])
        self.assertEqual(before, {path: path.read_bytes() for path in protected})


if __name__ == "__main__":
    unittest.main()
