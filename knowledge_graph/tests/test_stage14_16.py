import hashlib
import json
import sys
import tempfile
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.assessment_builder import apply_assessment_graph, build_assessments
from tools.graph_builder import build_graph, render_html
from tools.rule_engine import evaluate
from tools.standards_crosswalk import apply_crosswalk, load_crosswalk
from tools.temporal_assessment import apply_temporal_assessment, load_temporal_config
from tools.temporal_assessment import assess_temporal_pair
from tools.validation_protocol import LAYERS, validate_system


class AssessmentBuilderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = json.loads(
            (ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig")
        )
        cls.rules = json.loads((ROOT / "data" / "config" / "rules.json").read_text(encoding="utf-8"))
        cls.findings = evaluate(cls.claims, cls.rules)
        graph = build_graph(cls.claims, cls.findings)
        graph = apply_crosswalk(graph, cls.claims, load_crosswalk())
        cls.graph = apply_temporal_assessment(
            graph, cls.claims, load_temporal_config()
        )
        cls.assessments = build_assessments(cls.claims, cls.findings, cls.graph)
        cls.enriched_graph = apply_assessment_graph(
            cls.graph,
            cls.assessments["claim_assessments"],
            cls.assessments["company_assessments"],
        )

    def test_claim_assessment_is_fully_traceable(self):
        claim_assessments = self.assessments["claim_assessments"]
        self.assertEqual(
            len(claim_assessments),
            sum(len(finding["input_claim_ids"]) for finding in self.findings),
        )
        findings_by_id = {finding["finding_id"]: finding for finding in self.findings}
        claims_by_id = {claim["claim_id"]: claim for claim in self.claims}
        for assessment in claim_assessments:
            with self.subTest(assessment_id=assessment["assessment_id"]):
                finding = findings_by_id[assessment["finding_id"]]
                self.assertEqual(assessment["status"], finding["status"])
                self.assertEqual(assessment["rule_id"], finding["rule_id"])
                self.assertEqual(
                    {fact["claim_id"] for fact in assessment["facts"]},
                    set(finding["input_claim_ids"]),
                )
                expected_evidence = {
                    evidence["evidence_id"]
                    for claim_id in finding["input_claim_ids"]
                    for evidence in claims_by_id[claim_id]["evidence"]
                }
                actual_evidence = {
                    evidence["evidence_id"]
                    for fact in assessment["facts"]
                    for evidence in fact["evidence"]
                }
                self.assertEqual(actual_evidence, expected_evidence)
                self.assertTrue(all(
                    context["verification_status"] == "verified"
                    and "not a compliance or violation" in context["disclaimer"]
                    for context in assessment["standard_context"]
                ))

    def test_company_summary_counts_unique_findings_without_score(self):
        summary = self.assessments["company_assessments"][
            "company_multiyear_assessments"
        ][0]
        self.assertEqual(summary["company_id"], "BSR")
        self.assertEqual(summary["finding_count"], 10)
        self.assertEqual(len(summary["finding_ids"]), len(set(summary["finding_ids"])))
        self.assertEqual(
            summary["finding_status_distribution"],
            dict(sorted(Counter(finding["status"] for finding in self.findings).items())),
        )
        self.assertIsNone(summary["risk_score"])
        self.assertIn("corresponding rule", summary["supported_note"])
        expected_dimensions = Counter(claim["dimension"] for claim in self.claims)
        self.assertEqual(
            {dimension: item["claim_count"] for dimension, item in summary["dimension_distribution"].items()},
            {dimension: expected_dimensions[dimension] for dimension in ("E", "S", "G")},
        )
        self.assertTrue(all(
            item["finding_ids"] for item in summary["dimension_distribution"].values()
        ))
        self.assertTrue(all(
            item["finding_ids"] for item in summary["coverage"]["limitations"]
        ))
        self.assertEqual(len(summary["temporal_patterns"]), 2)
        self.assertTrue(all(item["finding_ids"] for item in summary["temporal_patterns"]))
        yearly = {
            item["report_years"][0]: len(item["temporal_patterns"])
            for item in self.assessments["company_assessments"]["company_year_assessments"]
        }
        self.assertEqual(yearly, {2023: 1, 2024: 2, 2025: 1})

    def test_exact_duplicate_is_removed_and_paraphrase_remains_unverified(self):
        duplicate = deepcopy(self.findings[0])
        duplicate["finding_id"] = "FND-EXACT-DUPLICATE"
        assessments = build_assessments(
            self.claims, self.findings + [duplicate], self.graph
        )
        summary = assessments["company_assessments"][
            "company_multiyear_assessments"
        ][0]
        self.assertEqual(summary["finding_count"], 10)
        self.assertEqual(
            assessments["deduplication"]["paraphrase_deduplication_status"],
            "unverified",
        )
        self.assertEqual(
            assessments["deduplication"]["exact_duplicates_removed"],
            [{
                "finding_id": "FND-EXACT-DUPLICATE",
                "duplicate_of": self.findings[0]["finding_id"],
            }],
        )

    def test_assessment_nodes_trace_to_findings_claims_evidence_and_standards(self):
        enriched = apply_assessment_graph(
            self.graph,
            self.assessments["claim_assessments"],
            self.assessments["company_assessments"],
        )
        edges = {
            (edge["source"], edge["target"], edge["label"])
            for edge in enriched["edges"]
        }
        for assessment in self.assessments["claim_assessments"]:
            node_id = "claim-assessment:" + assessment["assessment_id"]
            self.assertIn((
                node_id,
                "finding:" + assessment["finding_id"],
                "DERIVED_FROM_FINDING",
            ), edges)
            self.assertIn((
                node_id,
                "claim:" + assessment["claim_id"],
                "ASSESSES_CLAIM",
            ), edges)
        summary = self.assessments["company_assessments"][
            "company_multiyear_assessments"
        ][0]
        summary_node_id = "company-assessment:" + summary["assessment_id"]
        self.assertTrue(all(
            (summary_node_id, "finding:" + finding_id, "SUMMARIZES_FINDING") in edges
            for finding_id in summary["finding_ids"]
        ))


class ReportRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        AssessmentBuilderTest.setUpClass()
        cls.claims = AssessmentBuilderTest.claims
        cls.findings = AssessmentBuilderTest.findings
        cls.assessments = AssessmentBuilderTest.assessments
        cls.enriched_graph = AssessmentBuilderTest.enriched_graph

    def test_report_has_progressive_traceability_and_explicit_sections(self):
        rendered = render_html(
            self.enriched_graph, self.findings, self.assessments
        )
        for element_id in (
            "company-filter", "finding-select", "claim-select", "evidence-select",
        ):
            self.assertIn(f'id="{element_id}"', rendered)
        self.assertIn("Fact", rendered)
        self.assertIn("Suy luận theo rule", rendered)
        self.assertIn("Điều kiện chưa xác minh", rendered)
        self.assertIn("Giới hạn dữ liệu", rendered)
        self.assertIn("Standard context only; not a compliance or violation conclusion.", rendered)
        self.assertIn("Không có finding phù hợp với bộ lọc đã chọn.", rendered)
        self.assertIn("JSON pointer", rendered)
        self.assertIn("const forward=new Set", rendered)
        self.assertIn("const reverse=new Set", rendered)
        self.assertNotIn("three.js", rendered.lower())

    def test_synthetic_banner_is_explicit_and_synthetic_is_not_aggregated(self):
        graph = deepcopy(self.enriched_graph)
        graph["nodes"].append({
            "id": "financial:FIN-SYN-ONLY",
            "type": "FinancialDisclosure",
            "label": "Synthetic finance fixture",
            "synthetic": True,
            "source_uri": "synthetic://fixture",
        })
        rendered = render_html(graph, self.findings, self.assessments)
        self.assertIn("SYNTHETIC", rendered)
        companies = self.assessments["company_assessments"][
            "company_multiyear_assessments"
        ]
        self.assertEqual({assessment["company_id"] for assessment in companies}, {"BSR"})
        self.assertFalse(any(
            "SYN" in assessment["company_id"] for assessment in companies
        ))

    def test_fc01_remains_inactive(self):
        candidates = json.loads(
            (ROOT / "data" / "config" / "financial_link_candidates_sample.json").read_text(encoding="utf-8")
        )
        self.assertEqual(candidates["checks"][0]["check_id"], "FC01")
        self.assertEqual(candidates["checks"][0]["status"], "candidate_inactive")
        self.assertEqual(
            candidates["checks"][0]["result_policy"]["current_result"],
            "not_run_no_finding",
        )


class ValidationProtocolTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        AssessmentBuilderTest.setUpClass()
        cls.claims = AssessmentBuilderTest.claims
        cls.rules = AssessmentBuilderTest.rules
        cls.findings = AssessmentBuilderTest.findings
        cls.assessments = AssessmentBuilderTest.assessments
        cls.graph = AssessmentBuilderTest.enriched_graph

    def test_validation_layers_are_separate_and_pass(self):
        report = validate_system(
            self.claims, self.findings, self.graph, self.assessments
        )
        self.assertTrue(report["valid"])
        self.assertEqual(report["error_count"], 0)
        self.assertEqual(tuple(report["layers"]), LAYERS)
        self.assertTrue(all(layer["valid"] for layer in report["layers"].values()))

    def test_missing_rule_record_does_not_create_contradiction_or_evidence_gap(self):
        r02 = next(rule for rule in self.rules if rule["id"] == "R02")
        total_only = [
            claim for claim in self.claims if claim["selection_id"] == "C21"
        ]
        self.assertEqual(evaluate(total_only, [r02]), [])

    def test_cross_year_boundary_mismatch_does_not_compare(self):
        earlier = TemporalFixtureFactory.claim(2024, 5, boundary="parent")
        later = TemporalFixtureFactory.claim(2025, 7, boundary="group")
        later["boundary_change_status"] = "unknown"
        result = assess_temporal_pair(earlier, later)
        self.assertEqual(result["assessment_status"], "NeedsReview")
        self.assertFalse(result["comparison_performed"])

    def test_company_summary_matches_unique_claim_findings(self):
        summary = self.assessments["company_assessments"][
            "company_multiyear_assessments"
        ][0]
        self.assertEqual(summary["finding_count"], len(self.findings))
        self.assertEqual(set(summary["finding_ids"]), {
            finding["finding_id"] for finding in self.findings
        })

    def test_validation_case_catalogue_marks_real_cases_pending(self):
        catalogue = json.loads(
            (ROOT / "data" / "config" / "validation_cases.json").read_text(encoding="utf-8")
        )
        schema = json.loads(
            (ROOT / "schemas" / "validation-case-schema-v0.1.json").read_text(encoding="utf-8")
        )
        errors = list(Draft202012Validator(schema).iter_errors(catalogue))
        self.assertEqual([error.message for error in errors], [])
        real_cases = [case for case in catalogue["cases"] if case["data_class"] == "real"]
        self.assertTrue(real_cases)
        self.assertTrue(all(
            case["adjudication_status"] == "pending_adjudication"
            for case in real_cases
        ))
        self.assertFalse(any(
            case["adjudication_status"] == "adjudicated"
            for case in real_cases
        ))


class TemporalFixtureFactory:
    @staticmethod
    def claim(year, value, boundary="group"):
        claim = {
            "claim_id": f"CLM-VALIDATION-{year}",
            "company_id": "ACME",
            "report_year": year,
            "observation_year": year,
            "metric_id": "board_total",
            "unit": "person",
            "scope": "board",
            "variant": "reported",
            "period_type": "annual",
            "reporting_boundary": boundary,
            "reporting_boundary_verified": True,
            "boundary_change_status": "unchanged",
            "baseline_id": "same",
            "baseline_change_status": "unchanged",
            "restatement_status": "not_restatement",
            "value": value,
            "evidence": [{"source_text": "Synthetic validation text."}],
        }
        return claim


class TemporaryBuildTest(unittest.TestCase):
    @staticmethod
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def test_build_to_temporary_directory_preserves_main_snapshots(self):
        from build_demo import build

        snapshot_paths = [
            ROOT / "output" / name
            for name in ("findings.json", "findings.csv", "graph.json", "graph_demo.html")
        ]
        before = {path: self.digest(path) for path in snapshot_paths}
        with tempfile.TemporaryDirectory(prefix="esg-demo-validation-") as temp_dir:
            result = build(temp_dir)
            temp_path = Path(temp_dir)
            expected_files = {
                "normalized_claims.json", "findings.json", "graph.json", "graph_demo.html",
                "claim_assessments.json", "company_assessments.json",
                "assessment_metadata.json", "validation_report.json",
                "system_validation_report.json",
            }
            self.assertTrue(expected_files.issubset({path.name for path in temp_path.iterdir()}))
            self.assertEqual(len(result["claims"]), 30)
            self.assertEqual(len(result["findings"]), 10)
            self.assertTrue(result["system_validation"]["valid"])
            self.assertEqual(
                Counter(finding["status"] for finding in result["findings"]),
                Counter({"Supported": 6, "NeedsReview": 4}),
            )
            self.assertFalse(any(
                node.get("synthetic") for node in result["graph"]["nodes"]
            ))
        after = {path: self.digest(path) for path in snapshot_paths}
        self.assertEqual(after, before)


class IntegrationGapStatusTest(unittest.TestCase):
    def test_four_components_are_explicit_without_new_unverified_mapping(self):
        status = json.loads(
            (ROOT / "data" / "integration_gap_status.json").read_text(encoding="utf-8")
        )
        components = status["components"]
        self.assertEqual(set(components), {"GRI", "IFRS_S1", "SASB", "financial_linkage"})
        self.assertEqual(components["GRI"]["status"], "verified_partial_context")
        self.assertEqual(components["IFRS_S1"]["verified"], [])
        self.assertEqual(components["SASB"]["verified"], [])
        self.assertIn("IFRS S2 Industry-based Guidance", components["SASB"]["clarification"])
        self.assertEqual(
            components["SASB"]["industry_applicability_status"], "unverified"
        )
        self.assertEqual(
            components["financial_linkage"]["candidate_status"], "candidate_inactive"
        )

    def test_extract_handoff_names_comparability_and_source_fields(self):
        status = json.loads(
            (ROOT / "data" / "integration_gap_status.json").read_text(encoding="utf-8")
        )
        handoff = status["extract_handoff_required"]
        comparability = set(handoff["period_and_comparability"])
        self.assertTrue({
            "report_year", "observation_year", "period_type", "scope",
            "reporting_boundary", "reporting_boundary_verified",
            "baseline_change_status", "restatement_status",
        }.issubset(comparability))
        source = set(handoff["evidence_and_source"])
        self.assertIn("original source_text", source)
        self.assertIn("manual PDF adjudication status", source)


if __name__ == "__main__":
    unittest.main()
