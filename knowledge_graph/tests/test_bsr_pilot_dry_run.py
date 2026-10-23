import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from build_demo import build
from tools.bsr_pilot_dry_run import _workforce_case, assemble_report, run, trace_findings
from tools.financial_adapter import adapt_reports
from tools.pilot_readiness import build_inventory
from tools.rule_engine import evaluate


class BsrPilotDryRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline_temp = tempfile.TemporaryDirectory(prefix="bsr_stage17_test_")
        cls.pipeline = build(Path(cls.pipeline_temp.name))
        cls.claims = [claim for claim in cls.pipeline["claims"] if claim["company_id"] == "BSR"]
        claim_ids = {claim["claim_id"] for claim in cls.claims}
        cls.findings = [finding for finding in cls.pipeline["findings"]
                        if set(finding["input_claim_ids"]).intersection(claim_ids)]
        cls.financial = adapt_reports()
        cls.inventory = build_inventory()
        cls.candidate = json.loads((ROOT / "data" / "config" / "financial_link_bsr_workforce_sample.json").read_text(encoding="utf-8"))
        cls.validation_cases = json.loads((ROOT / "data" / "config" / "validation_cases.json").read_text(encoding="utf-8"))["cases"]

    @classmethod
    def tearDownClass(cls):
        cls.pipeline_temp.cleanup()

    def test_every_finding_traces_to_claim_evidence_report_and_locator(self):
        trace = trace_findings(self.claims, self.findings, self.pipeline["graph"])
        self.assertEqual(trace["fully_traceable_findings"], len(self.findings))
        self.assertGreater(trace["path_count"], len(self.findings))
        self.assertEqual(trace["complete_paths"], trace["path_count"])
        self.assertTrue(all(path["source_pages"] and path["json_pointer"]
                            for finding in trace["findings"] for path in finding["paths"]))
        broken = copy.deepcopy(self.pipeline["graph"])
        first = trace["findings"][0]["paths"][0]
        broken["edges"] = [edge for edge in broken["edges"] if not (
            edge["source"] == "finding:" + first["finding_id"]
            and edge["target"] == "evidence:" + first["evidence_id"]
            and edge["label"] == "BASED_ON_EVIDENCE"
        )]
        broken_trace = trace_findings(self.claims, self.findings, broken)
        self.assertEqual(broken_trace["fully_traceable_findings"], len(self.findings) - 1)
        self.assertIn("edge_missing:BASED_ON_EVIDENCE", " ".join(
            item for finding in broken_trace["findings"] for item in finding["issues"]
        ))

    def test_absent_input_explicit_null_and_numeric_difference_are_distinct(self):
        r01 = next(rule for rule in json.loads((ROOT / "data" / "config" / "rules.json").read_text(encoding="utf-8"))
                   if rule["id"] == "R01")
        r01_finding = next(item for item in self.findings if item["rule_id"] == "R01")
        pair = [claim for claim in self.claims if claim["claim_id"] in r01_finding["input_claim_ids"]]
        self.assertEqual(evaluate(pair[:1], [r01]), [])
        self.assertEqual(evaluate(pair, [r01])[0]["status"], "NeedsReview")
        with_null = copy.deepcopy(pair)
        with_null[1]["value"] = None
        self.assertEqual(evaluate(with_null, [r01])[0]["status"], "InsufficientEvidence")

    def test_inactive_financial_candidate_never_becomes_a_finding(self):
        before = copy.deepcopy(self.pipeline["findings"])
        report = assemble_report(self.pipeline, self.financial, self.inventory,
                                 self.candidate, self.validation_cases)
        workforce = report["cases"]["workforce_financial"]
        self.assertEqual(workforce["status"], "NeedsReview")
        self.assertEqual(workforce["fc01_status"], "inactive")
        self.assertFalse(workforce["comparison_performed"])
        self.assertFalse(workforce["comparison_eligible"])
        self.assertFalse(workforce["finding_created"])
        self.assertFalse(workforce["join_checks"]["verified_scope_match"])
        self.assertEqual(workforce["financial"]["scope"]["entity_set"], "parent_plus_subsidiaries")
        self.assertEqual(workforce["esg"]["workforce_context"]["reporting_boundary"]["entity_set"], "unknown")
        self.assertEqual(workforce["difference_interpretation"], "arithmetic_only_not_comparable")
        self.assertEqual(self.pipeline["findings"], before)
        self.assertFalse(any(finding["rule_id"] == "FC01" for finding in self.pipeline["findings"]))
        financial_without_workforce = [record for record in self.financial["records"]
                                       if record["disclosure_id"] != self.candidate["checks"][0]["financial_disclosure_id"]]
        missing = _workforce_case(self.claims, financial_without_workforce, self.candidate)
        self.assertEqual(missing["status"], "not_run_missing_data")
        self.assertFalse(missing["finding_created"])

    def test_workforce_guard_requires_verified_same_boundary_date_and_definition(self):
        esg = next(claim for claim in self.claims if claim["claim_id"] == self.candidate["checks"][0]["esg_claim_id"])
        financial = next(record for record in self.financial["records"] if record["disclosure_id"] == self.candidate["checks"][0]["financial_disclosure_id"])

        # A synthetic fully documented equivalent scope is eligible for review,
        # while FC01 still requires separate activation and creates no finding.
        same = copy.deepcopy(esg)
        same["workforce_context"] = {
            "reporting_boundary": {"entity_set": "parent_plus_subsidiaries", "verification_status": "verified"},
            "measurement_date": {"value": "2025-12-31", "verification_status": "verified"},
            "employee_definition": {"definition_id": "total_employees", "verification_status": "verified"},
        }
        verified_financial = copy.deepcopy(financial)
        verified_financial["employee_definition"]["verification_status"] = "verified"
        equivalent = _workforce_case([same], [verified_financial], self.candidate)
        self.assertTrue(equivalent["comparison_eligible"])
        self.assertTrue(all(equivalent["join_checks"].values()))
        self.assertEqual(equivalent["difference_interpretation"], "reviewable_on_equivalent_basis")
        self.assertFalse(equivalent["comparison_performed"])
        self.assertFalse(equivalent["finding_created"])

        separate = copy.deepcopy(same)
        separate["workforce_context"]["reporting_boundary"]["entity_set"] = "parent"
        mismatch = _workforce_case([separate], [verified_financial], self.candidate)
        self.assertFalse(mismatch["comparison_eligible"])
        self.assertFalse(mismatch["join_checks"]["verified_scope_match"])
        self.assertIn("reporting_boundary_mismatch", mismatch["missing_conditions"])
        self.assertEqual(mismatch["difference_interpretation"], "arithmetic_only_not_comparable")

        different_date = copy.deepcopy(same)
        different_date["workforce_context"]["measurement_date"]["value"] = "2025-06-30"
        date_result = _workforce_case([different_date], [verified_financial], self.candidate)
        self.assertFalse(date_result["comparison_eligible"])
        self.assertIn("measurement_date_mismatch", date_result["missing_conditions"])

        different_definition = copy.deepcopy(same)
        different_definition["workforce_context"]["employee_definition"]["definition_id"] = "average_employees"
        definition_result = _workforce_case([different_definition], [verified_financial], self.candidate)
        self.assertFalse(definition_result["comparison_eligible"])
        self.assertIn("employee_definition_mismatch", definition_result["missing_conditions"])

        unknown = _workforce_case([esg], [verified_financial], self.candidate)
        self.assertFalse(unknown["comparison_eligible"])
        self.assertIn("reporting_boundary_unverified", unknown["missing_conditions"])
        self.assertIn("measurement_date_unverified", unknown["missing_conditions"])
        self.assertFalse(unknown["comparison_performed"])

    def test_graph_keeps_esg_consolidated_and_separate_workforce_sources_distinct(self):
        nodes = {node["id"]: node for node in self.pipeline["graph"]["nodes"]}
        edges = {(edge["source"], edge["target"], edge["label"]) for edge in self.pipeline["graph"]["edges"]}
        claim_id = "claim:CLM-08082F5B81CD"
        consolidated_id = "financial:FIN-BSR-BCTC-2025-workforce.total"
        separate_id = "financial-observation:OBS-BSR-BCTC-SEPARATE-2025-workforce.total"
        self.assertEqual(nodes["measurement:CLM-08082F5B81CD"]["value"], 1594)
        self.assertEqual(nodes[claim_id]["workforce_context"]["reporting_boundary"]["entity_set"], "unknown")
        self.assertEqual(nodes[consolidated_id]["value"], 1946)
        self.assertEqual(nodes[consolidated_id]["scope"]["entity_set"], "parent_plus_subsidiaries")
        self.assertEqual(nodes[separate_id]["value"], 1594)
        self.assertEqual(nodes[separate_id]["reporting_boundary"]["entity_set"], "parent")
        self.assertEqual(nodes[separate_id]["source_pages"], None)
        self.assertIn((claim_id, consolidated_id, "HAS_FINANCIAL_CANDIDATE"), edges)
        self.assertIn((claim_id, separate_id, "RELATED_FINANCIAL_OBSERVATION"), edges)
        source_id = "financial-source:FIN-BSR-BCTC-2025-workforce.total"
        self.assertEqual(nodes[source_id]["json_pointer"], "/social/workforce/employees_2025_12_31")
        self.assertEqual(nodes[source_id]["source_pages"], [14])

    def test_optional_handoff_is_preflighted_without_merging_or_changing_output(self):
        protected = [ROOT / "output" / name for name in ("normalized_claims.json", "findings.json", "graph.json")]
        before = {path: path.read_bytes() for path in protected}
        with tempfile.TemporaryDirectory(prefix="bsr_stage17_report_test_") as temp:
            report = run(Path(temp) / "report", ROOT / "data" / "handoff" / "provenance_boundary_handoff.json")
            self.assertEqual(report["handoff_preflight"]["summary"]["blocking"], 0)
            self.assertEqual(report["handoff_status"], "preflight_only_not_ingested")
            self.assertEqual(report["counts"]["claims"], len(self.claims))
            self.assertTrue((Path(temp) / "report" / "bsr_dry_run_report.md").is_file())
        self.assertEqual(before, {path: path.read_bytes() for path in protected})


if __name__ == "__main__":
    unittest.main()
