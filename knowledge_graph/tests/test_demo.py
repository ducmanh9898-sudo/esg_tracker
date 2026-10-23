import json
import sys
import unittest
from collections import Counter
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.deduplicate_pvd import compare_overlapping_pvd_extracts
from tools.graph_builder import build_graph, render_html
from tools.normalizer import normalize
from tools.rule_engine import evaluate
from tools.standards_crosswalk import apply_crosswalk, load_crosswalk
from tools.temporal_assessment import (
    apply_temporal_assessment,
    assess_temporal_pair,
    load_temporal_config,
)
from tools.validator import validate_claims


class DemoPipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = normalize()
        cls.rules = json.loads((ROOT / "data" / "config" / "rules.json").read_text(encoding="utf-8"))
        cls.findings = evaluate(cls.claims, cls.rules)
        cls.graph = build_graph(cls.claims, cls.findings)

    def test_taxonomy_sample_has_30_esg_records(self):
        self.assertEqual(len(self.claims), 30)
        self.assertEqual({c["dimension"] for c in self.claims}, {"E", "S", "G"})
        self.assertTrue(all(c["expected_evidence_class"] for c in self.claims))

    def test_common_schema_validation(self):
        validation = validate_claims(self.claims)
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["error_count"], 0)

    def test_expected_rule_results(self):
        self.assertEqual(
            Counter(f["status"] for f in self.findings),
            Counter({"Supported": 6, "NeedsReview": 4}),
        )

    def test_r01_keeps_both_scope1_values_and_provenance(self):
        r01 = next(f for f in self.findings if f["rule_id"] == "R01")
        inputs = [c for c in self.claims if c["claim_id"] in r01["input_claim_ids"]]
        self.assertEqual({c["value"] for c in inputs}, {1780388, 1790388})
        self.assertEqual(len({c["evidence"][0]["evidence_id"] for c in inputs}), 2)
        self.assertEqual(r01["status"], "NeedsReview")
        self.assertIn("reporting boundary chưa được xác minh", r01["summary"])
        self.assertIn("10,000.00", r01["calculation"])

    def test_graph_has_complete_explanation_chain(self):
        node_counts = Counter(n["type"] for n in self.graph["nodes"])
        self.assertEqual(node_counts["Company"], 1)
        self.assertEqual(node_counts["Report"], 3)
        self.assertEqual(node_counts["Claim"], 30)
        self.assertEqual(node_counts["Measurement"], 30)
        self.assertEqual(node_counts["Evidence"], 30)
        self.assertEqual(node_counts["Finding"], 10)
        self.assertEqual(node_counts["Rule"], 9)
        edge_counts = Counter(e["label"] for e in self.graph["edges"])
        self.assertEqual(edge_counts["HAS_MEASUREMENT"], 30)
        self.assertEqual(edge_counts["SOURCED_FROM"], 30)
        self.assertEqual(edge_counts["GENERATED_BY"], 10)

    def test_pvd_overlap_is_retained_as_provenance(self):
        rows = compare_overlapping_pvd_extracts()
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(row["same_value"] for row in rows))
        self.assertTrue(all(row["canonical_source"] == "PVD_2025_esg.json" for row in rows))


class RuleApplicabilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.claims = json.loads(
            (ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig")
        )
        rules = json.loads((ROOT / "data" / "config" / "rules.json").read_text(encoding="utf-8"))
        cls.rules = {rule["id"]: rule for rule in rules}
        cls.r01_claims = [c for c in cls.claims if c["selection_id"] in {"C15", "C16"}]

    def evaluate_rule(self, claims, rule_id):
        return evaluate(claims, [self.rules[rule_id]])

    def test_r01_current_pair_is_candidate_not_contradiction(self):
        findings = self.evaluate_rule(self.r01_claims, "R01")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["status"], "NeedsReview")
        self.assertEqual(set(findings[0]["input_claim_ids"]), {c["claim_id"] for c in self.r01_claims})
        self.assertIn("reporting boundary chưa được xác minh", findings[0]["summary"])

    def test_r01_does_not_mix_different_company_period_or_unit(self):
        mutations = {
            "company": ("company_id", "OTHER"),
            "report year": ("report_year", 2024),
            "observation year": ("observation_year", 2024),
            "unit": ("unit", "kgCO2e"),
        }
        for label, (field, value) in mutations.items():
            with self.subTest(label=label):
                claims = deepcopy(self.r01_claims)
                for claim in claims:
                    claim["reporting_boundary"] = "BSR consolidated operations"
                    claim["reporting_boundary_verified"] = True
                claims[1][field] = value
                self.assertEqual(self.evaluate_rule(claims, "R01"), [])

    def test_r01_does_not_mix_different_scope(self):
        claims = deepcopy(self.r01_claims)
        for claim in claims:
            claim["reporting_boundary"] = "BSR consolidated operations"
            claim["reporting_boundary_verified"] = True
        claims[1]["scope"] = "scope1_other_boundary"
        self.assertEqual(self.evaluate_rule(claims, "R01"), [])

    def test_boundary_value_without_verification_stays_needs_review(self):
        claims = deepcopy(self.r01_claims)
        for claim in claims:
            claim["reporting_boundary"] = "BSR consolidated operations"
        findings = self.evaluate_rule(claims, "R01")
        self.assertEqual(findings[0]["status"], "NeedsReview")

    def test_verified_same_boundary_allows_contradicted(self):
        claims = deepcopy(self.r01_claims)
        for claim in claims:
            claim["reporting_boundary"] = "BSR consolidated operations"
            claim["reporting_boundary_verified"] = True
        findings = self.evaluate_rule(claims, "R01")
        self.assertEqual(findings[0]["status"], "Contradicted")

    def test_missing_input_is_not_an_evidence_gap(self):
        total_only = [c for c in self.claims if c["selection_id"] == "C21"]
        self.assertEqual(self.evaluate_rule(total_only, "R02"), [])

    def test_null_input_is_a_confirmed_evidence_gap(self):
        claims = [
            deepcopy(c) for c in self.claims
            if c["selection_id"] in {"C21", "C22", "C23"}
        ]
        next(c for c in claims if c["selection_id"] == "C23")["value"] = None
        findings = self.evaluate_rule(claims, "R02")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["status"], "InsufficientEvidence")
        self.assertIn("Evidence gap đã được xác nhận", findings[0]["summary"])


class GraphBuilderTest(unittest.TestCase):
    def test_finding_provenance_semantics_for_supported_contradicted_and_needs_review(self):
        claims = [{
            "schema_version": "1.0",
            "claim_id": "CLM-PROVENANCE",
            "company_id": "ACME",
            "report_year": 2025,
            "observation_year": 2025,
            "dimension": "E",
            "topic": "climate",
            "claim_type": "reported_measurement",
            "metric_id": "ghg_scope1",
            "label": "Scope 1",
            "value": 100,
            "unit": "tCO2e",
            "scope": "scope1",
            "evidence": [{
                "evidence_id": "EVD-PROVENANCE",
                "source_file": "acme-report.json",
                "source_pages": [12],
                "json_pointer": "/claims/0/value",
                "source_text": "Scope 1 emissions were 100 tCO2e.",
            }],
        }]
        findings = [{
            "finding_id": f"FND-{status.upper()}",
            "rule_id": f"R-{index}",
            "rule_name": "Synthetic provenance rule",
            "status": status,
            "summary": "Synthetic finding",
            "calculation": "Synthetic calculation",
            "guard": "Synthetic guard",
            "basis": "Synthetic basis",
            "input_claim_ids": ["CLM-PROVENANCE"],
        } for index, status in enumerate(
            ("Supported", "Contradicted", "NeedsReview"), start=1
        )]

        graph = build_graph(claims, findings)
        edges = {
            (edge["source"], edge["target"], edge["label"])
            for edge in graph["edges"]
        }
        evidence_node = next(
            node for node in graph["nodes"] if node["id"] == "evidence:EVD-PROVENANCE"
        )

        self.assertIn(("report:ACME:2025", "claim:CLM-PROVENANCE", "CONTAINS"), edges)
        self.assertIn(("claim:CLM-PROVENANCE", "measurement:CLM-PROVENANCE", "HAS_MEASUREMENT"), edges)
        self.assertIn(("measurement:CLM-PROVENANCE", "evidence:EVD-PROVENANCE", "SOURCED_FROM"), edges)
        self.assertEqual(evidence_node["source_file"], "acme-report.json")
        self.assertEqual(evidence_node["source_pages"], [12])
        self.assertEqual(evidence_node["json_pointer"], "/claims/0/value")

        for finding in findings:
            finding_id = "finding:" + finding["finding_id"]
            self.assertIn((finding_id, "claim:CLM-PROVENANCE", "BASED_ON_CLAIM"), edges)
            self.assertIn((finding_id, "evidence:EVD-PROVENANCE", "BASED_ON_EVIDENCE"), edges)
            self.assertIn((finding_id, "report:ACME:2025", "DERIVED_FROM_REPORT"), edges)
            self.assertNotIn(("evidence:EVD-PROVENANCE", finding_id, "BASED_ON_EVIDENCE"), edges)
            self.assertNotIn(("report:ACME:2025", finding_id, "DERIVED_FROM_REPORT"), edges)
            self.assertNotIn((finding_id, "evidence:EVD-PROVENANCE", "SUPPORTED_BY"), edges)
            self.assertNotIn((finding_id, "report:ACME:2025", "REPORTED_IN"), edges)

    def test_all_demo_findings_have_direct_provenance_edges(self):
        claims = json.loads(
            (ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig")
        )
        findings = json.loads(
            (ROOT / "output" / "findings.json").read_text(encoding="utf-8-sig")
        )
        by_id = {claim["claim_id"]: claim for claim in claims}
        graph = build_graph(claims, findings)
        edges = {
            (edge["source"], edge["target"], edge["label"])
            for edge in graph["edges"]
        }

        for finding in findings:
            finding_id = "finding:" + finding["finding_id"]
            for claim_id in finding["input_claim_ids"]:
                claim = by_id[claim_id]
                self.assertIn((finding_id, "claim:" + claim_id, "BASED_ON_CLAIM"), edges)
                self.assertIn((
                    finding_id,
                    f"report:{claim['company_id']}:{claim['report_year']}",
                    "DERIVED_FROM_REPORT",
                ), edges)
                for evidence in claim["evidence"]:
                    evidence_id = "evidence:" + evidence["evidence_id"]
                    self.assertIn((finding_id, evidence_id, "BASED_ON_EVIDENCE"), edges)
                    evidence_node = next(n for n in graph["nodes"] if n["id"] == evidence_id)
                    self.assertEqual(evidence_node["source_file"], evidence["source_file"])
                    self.assertEqual(evidence_node["source_pages"], evidence["source_pages"])
                    self.assertEqual(evidence_node["json_pointer"], evidence["json_pointer"])

    def test_multiple_companies_and_all_evidence_are_linked(self):
        claims = [
            {
                "schema_version": "1.0",
                "claim_id": "CLM-ALPHA",
                "company_id": "ALPHA",
                "company_name": "Alpha Energy",
                "report_year": 2025,
                "observation_year": 2025,
                "dimension": "E",
                "topic": "climate",
                "claim_type": "reported_measurement",
                "expected_evidence_class": "quantitative_disclosure",
                "metric_id": "ghg_scope1",
                "label": "Scope 1",
                "value": 100,
                "unit": "tCO2e",
                "scope": "scope1",
                "variant": "reported",
                "evidence": [
                    {
                        "evidence_id": "EVD-ALPHA-1",
                        "source_file": "alpha-main.json",
                        "source_pages": [10],
                        "json_pointer": "/scope1/value",
                        "source_text": "Scope 1 is 100 tCO2e.",
                    },
                    {
                        "evidence_id": "EVD-ALPHA-2",
                        "source_file": "alpha-appendix.json",
                        "source_pages": [40, 41],
                        "json_pointer": "/appendix/scope1",
                    },
                ],
            },
            {
                "schema_version": "1.0",
                "claim_id": "CLM-BETA",
                "company_id": "BETA",
                "report_year": 2024,
                "observation_year": 2024,
                "dimension": "S",
                "topic": "workforce",
                "claim_type": "reported_measurement",
                "metric_id": "employees_total",
                "label": "Employees",
                "value": 50,
                "unit": "person",
                "scope": "reported_workforce",
                "evidence": [{
                    "evidence_id": "EVD-BETA-1",
                    "source_file": "beta.json",
                    "source_pages": [7],
                    "json_pointer": "/workforce/total",
                }],
            },
        ]
        findings = [{
            "finding_id": "FND-ALPHA",
            "rule_id": "R-TEST",
            "rule_name": "Synthetic rule",
            "status": "NeedsReview",
            "summary": "Synthetic finding",
            "calculation": "100 vs reference",
            "guard": "Synthetic guard",
            "basis": "Synthetic basis",
            "input_claim_ids": ["CLM-ALPHA", "CLM-BETA"],
            "source_files": ["alpha-main.json", "alpha-appendix.json", "beta.json"],
            "source_pages": [7, 10, 40, 41],
        }]
        original_claims = deepcopy(claims)

        graph = build_graph(claims, findings)
        nodes = {node["id"]: node for node in graph["nodes"]}
        edges = {(edge["source"], edge["target"], edge["label"]) for edge in graph["edges"]}

        self.assertEqual(claims, original_claims)
        self.assertEqual(nodes["company:ALPHA"]["label"], "Alpha Energy")
        self.assertEqual(nodes["company:BETA"]["label"], "BETA")
        self.assertNotIn("expected_evidence_class", nodes["claim:CLM-BETA"])
        self.assertNotIn("variant", nodes["measurement:CLM-BETA"])
        self.assertIn(("company:ALPHA", "report:ALPHA:2025", "HAS_REPORT"), edges)
        self.assertIn(("company:BETA", "report:BETA:2024", "HAS_REPORT"), edges)
        self.assertIn(("report:ALPHA:2025", "claim:CLM-ALPHA", "CONTAINS"), edges)
        self.assertIn(("report:BETA:2024", "claim:CLM-BETA", "CONTAINS"), edges)

        alpha_evidence = {
            edge[1] for edge in edges
            if edge[0] == "measurement:CLM-ALPHA" and edge[2] == "SOURCED_FROM"
        }
        self.assertEqual(alpha_evidence, {"evidence:EVD-ALPHA-1", "evidence:EVD-ALPHA-2"})
        self.assertEqual(nodes["evidence:EVD-ALPHA-2"]["source_pages"], [40, 41])
        self.assertNotIn("details", nodes["evidence:EVD-ALPHA-2"])
        self.assertIn(("claim:CLM-ALPHA", "finding:FND-ALPHA", "INPUT_TO"), edges)
        self.assertIn(("finding:FND-ALPHA", "claim:CLM-ALPHA", "BASED_ON_CLAIM"), edges)
        self.assertIn(("finding:FND-ALPHA", "report:ALPHA:2025", "DERIVED_FROM_REPORT"), edges)
        self.assertIn(("finding:FND-ALPHA", "evidence:EVD-ALPHA-1", "BASED_ON_EVIDENCE"), edges)
        self.assertIn(("finding:FND-ALPHA", "evidence:EVD-ALPHA-2", "BASED_ON_EVIDENCE"), edges)
        self.assertIn(("finding:FND-ALPHA", "claim:CLM-BETA", "BASED_ON_CLAIM"), edges)
        self.assertIn(("finding:FND-ALPHA", "report:BETA:2024", "DERIVED_FROM_REPORT"), edges)
        self.assertIn(("finding:FND-ALPHA", "evidence:EVD-BETA-1", "BASED_ON_EVIDENCE"), edges)
        self.assertEqual(nodes["evidence:EVD-ALPHA-1"]["json_pointer"], "/scope1/value")
        self.assertEqual(nodes["evidence:EVD-BETA-1"]["source_pages"], [7])
        self.assertEqual(nodes["finding:FND-ALPHA"]["source_pages"], [7, 10, 40, 41])
        self.assertEqual(
            nodes["finding:FND-ALPHA"]["source_files"],
            ["alpha-main.json", "alpha-appendix.json", "beta.json"],
        )

    def test_conflicting_metadata_for_same_evidence_id_is_rejected(self):
        claim = {
            "schema_version": "1.0",
            "claim_id": "CLM-FIRST",
            "company_id": "ALPHA",
            "report_year": 2025,
            "observation_year": 2025,
            "dimension": "E",
            "topic": "climate",
            "claim_type": "reported_measurement",
            "metric_id": "ghg_scope1",
            "label": "Scope 1",
            "value": 100,
            "unit": "tCO2e",
            "scope": "scope1",
            "evidence": [{
                "evidence_id": "EVD-CONFLICT",
                "source_file": "first.json",
                "source_pages": [10],
                "json_pointer": "/scope1/value",
            }],
        }
        conflicting = deepcopy(claim)
        conflicting["claim_id"] = "CLM-SECOND"
        conflicting["evidence"][0]["source_file"] = "second.json"
        conflicting["evidence"][0]["source_pages"] = [20]

        with self.assertRaisesRegex(
            ValueError,
            "Conflicting metadata for evidence_id 'EVD-CONFLICT'.*source_file, source_pages",
        ):
            build_graph([claim, conflicting], [])


class StandardsCrosswalkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        claims = json.loads(
            (ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig")
        )
        cls.claims = [
            claim for claim in claims
            if claim["selection_id"] in {"C05", "C15", "C16"}
        ]
        findings = json.loads(
            (ROOT / "output" / "findings.json").read_text(encoding="utf-8-sig")
        )
        cls.findings = [finding for finding in findings if finding["rule_id"] == "R01"]
        cls.crosswalk = load_crosswalk()
        cls.base_graph = build_graph(cls.claims, cls.findings)
        cls.graph = apply_crosswalk(cls.base_graph, cls.claims, cls.crosswalk)
        cls.nodes = {node["id"]: node for node in cls.graph["nodes"]}
        cls.edges = cls.graph["edges"]

    def test_crosswalk_schema_accepts_explicit_source_and_applicability_metadata(self):
        schema = json.loads(
            (ROOT / "schemas" / "standards-crosswalk-schema-v0.1.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(
                schema, format_checker=FormatChecker()
            ).iter_errors(self.crosswalk),
            key=lambda error: list(error.path),
        )
        self.assertEqual([error.message for error in errors], [])

    def test_one_concept_maps_to_multiple_verified_standards(self):
        concept_edges = [edge for edge in self.edges if edge["label"] == "HAS_CONCEPT"]
        self.assertEqual(len(concept_edges), 3)
        mapped = {
            edge["target"] for edge in self.edges
            if edge["source"] == "concept:scope1_ghg_emissions"
            and edge["label"] == "MAPPED_TO"
        }
        self.assertEqual(mapped, {
            "standard:gri-305-1-2016",
            "standard:ifrs-s2-29-a-i-1-2023",
            "standard:ifrs-s2-ibg-em-rm-110a-1-2023",
        })
        self.assertTrue(all(
            edge["verification_status"] == "verified"
            and edge["relationship_type"] in {
                "equivalent", "related", "broader", "narrower", "complementary",
                "partially_addresses",
            }
            for edge in self.edges if edge["label"] == "MAPPED_TO"
        ))
        partial_edges = [
            edge for edge in self.edges
            if edge.get("relationship_type") == "partially_addresses"
        ]
        self.assertEqual(len(partial_edges), 3)
        self.assertTrue(all(edge["covered_aspects"] for edge in partial_edges))
        self.assertTrue(all(edge["unverified_aspects"] for edge in partial_edges))
        guidance = self.nodes["standard:ifrs-s2-ibg-em-rm-110a-1-2023"]
        self.assertEqual(guidance["source_type"], "industry_based_guidance")
        self.assertNotIn("SASB", guidance["standard_name"])
        guidance_edge = next(
            edge for edge in partial_edges
            if edge["target"] == "standard:ifrs-s2-ibg-em-rm-110a-1-2023"
        )
        self.assertEqual(guidance_edge["industry_applicability_status"], "unverified")

    def test_ifrs_s1_candidate_is_unverified_and_not_forced_from_role_separation(self):
        candidate = next(
            mapping for mapping in self.crosswalk["mappings"]
            if mapping["mapping_id"] == "map-chair-ceo-ifrs-s1-governance"
        )
        self.assertEqual(candidate["verification_status"], "unverified")
        self.assertEqual(candidate["standard_version"], "June 2023")
        self.assertEqual(candidate["source_locator"], "IFRS S1 paragraphs 26–27")
        self.assertEqual(candidate["applicability_status"], "unverified")
        self.assertTrue(candidate["source_url"].startswith("https://www.ifrs.org/"))
        self.assertTrue(any(
            "does not identify the governance body" in blocker
            for blocker in candidate["verification_blockers"]
        ))
        self.assertNotIn("standard:ifrs-s1-26-27-2023", self.nodes)
        self.assertFalse(any(
            edge.get("mapping_id") == "map-chair-ceo-ifrs-s1-governance"
            for edge in self.edges
        ))

    def test_sasb_candidate_uses_sasb_standard_but_requires_industry_applicability(self):
        candidate = next(
            mapping for mapping in self.crosswalk["mappings"]
            if mapping["mapping_id"] == "map-scope1-sasb-em-rm-110a-1"
        )
        self.assertEqual(candidate["verification_status"], "unverified")
        self.assertEqual(candidate["source_type"], "sasb_standard")
        self.assertEqual(candidate["standard_version"], "Version 2023-12")
        self.assertEqual(candidate["reference_code"], "EM-RM-110a.1")
        self.assertIn("SASB Standard", candidate["standard_name"])
        self.assertEqual(candidate["industry_applicability_status"], "unverified")
        self.assertEqual(candidate["applicability_status"], "unverified")
        self.assertTrue(candidate["source_url"].startswith("https://sasb.ifrs.org/"))
        self.assertTrue(any(
            "SICS classification" in blocker
            for blocker in candidate["verification_blockers"]
        ))
        self.assertNotIn("standard:sasb-em-rm-110a-1-2023-12", self.nodes)
        self.assertFalse(any(
            edge.get("mapping_id") == "map-scope1-sasb-em-rm-110a-1"
            for edge in self.edges
        ))

    def test_unverified_mappings_create_no_compliance_or_violation_conclusion(self):
        self.assertFalse(any(
            node["type"] in {"ComplianceConclusion", "ViolationConclusion"}
            for node in self.nodes.values()
        ))

    def test_crosswalk_does_not_change_rule_finding(self):
        before = {
            node["id"]: node for node in self.base_graph["nodes"]
            if node["type"] == "Finding"
        }
        after = {
            node["id"]: node for node in self.graph["nodes"]
            if node["type"] == "Finding"
        }
        self.assertEqual(after, before)

    def test_crosswalk_preserves_claim_evidence_source_path(self):
        claim = next(c for c in self.claims if c["selection_id"] == "C15")
        claim_node_id = "claim:" + claim["claim_id"]
        measurement_node_id = "measurement:" + claim["claim_id"]
        evidence = claim["evidence"][0]
        evidence_node_id = "evidence:" + evidence["evidence_id"]
        edge_keys = {
            (edge["source"], edge["target"], edge["label"])
            for edge in self.edges
        }

        self.assertIn((claim_node_id, measurement_node_id, "HAS_MEASUREMENT"), edge_keys)
        self.assertIn((measurement_node_id, evidence_node_id, "SOURCED_FROM"), edge_keys)
        self.assertEqual(self.nodes[evidence_node_id]["source_file"], evidence["source_file"])
        self.assertEqual(self.nodes[evidence_node_id]["source_pages"], evidence["source_pages"])


class RuleCatalogueAndFinancialContractTest(unittest.TestCase):
    @staticmethod
    def assert_schema_valid(test_case, instance, schema):
        Draft202012Validator.check_schema(schema)
        errors = sorted(
            Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(instance),
            key=lambda error: list(error.path),
        )
        test_case.assertEqual([error.message for error in errors], [])

    def test_rule_catalogue_matches_all_engine_rules_without_unverified_standard_links(self):
        schema = json.loads(
            (ROOT / "schemas" / "rule-catalogue-schema-v0.1.json").read_text(encoding="utf-8")
        )
        catalogue = json.loads(
            (ROOT / "data" / "config" / "rule_catalogue.json").read_text(encoding="utf-8")
        )
        engine_rules = {
            rule["id"]: rule
            for rule in json.loads((ROOT / "data" / "config" / "rules.json").read_text(encoding="utf-8"))
        }

        self.assert_schema_valid(self, catalogue, schema)
        entries = {entry["rule_id"]: entry for entry in catalogue["rules"]}
        self.assertEqual(set(entries), {f"R{number:02d}" for number in range(1, 10)})
        self.assertEqual(set(entries), set(engine_rules))
        for rule_id, entry in entries.items():
            with self.subTest(rule_id=rule_id):
                self.assertEqual(entry["engine_kind"], engine_rules[rule_id]["kind"])
                self.assertEqual(
                    entry["finding_policy"]["failure_status"],
                    engine_rules[rule_id]["failure"],
                )
                self.assertEqual(entry["finding_policy"]["missing_record_result"], "not_run_no_finding")
                self.assertEqual(entry["basis"]["basis_type"], "project_defined_reconciliation")
                self.assertEqual(entry["basis"]["standard_reference_ids"], [])

    def test_financial_contract_distinguishes_search_miss_and_confirmed_absence(self):
        schema = json.loads(
            (ROOT / "schemas" / "financial-disclosure-schema-v0.1.json").read_text(encoding="utf-8")
        )
        fixture_path = ROOT / "tests" / "fixtures" / "financial_disclosures.synthetic.json"
        records = json.loads(fixture_path.read_text(encoding="utf-8"))

        self.assertEqual(len(records), 2)
        self.assertNotIn(ROOT / "output", fixture_path.parents)
        self.assertEqual(
            {record["data_status"] for record in records},
            {"reported", "not_found_by_extract"},
        )
        self.assertIn("uncertain", schema["properties"]["data_status"]["enum"])
        self.assertIn("confirmed_not_disclosed", schema["properties"]["data_status"]["enum"])
        for record in records:
            with self.subTest(disclosure_id=record["disclosure_id"]):
                self.assert_schema_valid(self, record, schema)
                self.assertEqual(record["record_type"], "financial_disclosure")
                self.assertTrue(record["synthetic"])
                self.assertTrue(record["report"]["source_uri"].startswith("synthetic://"))
                self.assertTrue(record["source_location"]["source_uri"].startswith("synthetic://"))
                self.assertNotIn("source_pages", record["source_location"])

        invalid = deepcopy(records[0])
        del invalid["source_location"]["locator"]
        errors = list(Draft202012Validator(schema).iter_errors(invalid))
        self.assertTrue(any("locator" in error.message for error in errors))

        unconfirmed_absence = deepcopy(records[1])
        unconfirmed_absence["data_status"] = "confirmed_not_disclosed"
        errors = list(Draft202012Validator(schema).iter_errors(unconfirmed_absence))
        self.assertTrue(any("absence_confirmation" in error.message for error in errors))

        confirmed_absence = deepcopy(unconfirmed_absence)
        confirmed_absence["absence_confirmation"] = {
            "review_scope": "Synthetic report and notes",
            "method": "Manual full-report review",
            "confirmed_by": "synthetic-reviewer",
        }
        self.assert_schema_valid(self, confirmed_absence, schema)

    def test_financial_link_example_is_inactive_and_cannot_create_contradiction(self):
        candidates = json.loads(
            (ROOT / "data" / "config" / "financial_link_candidates_sample.json").read_text(encoding="utf-8")
        )
        self.assertEqual(len(candidates["checks"]), 1)
        check = candidates["checks"][0]
        self.assertEqual(check["status"], "candidate_inactive")
        joins = {
            (condition["esg_field"], condition["financial_field"], condition["operator"])
            for condition in check["join_conditions"]
        }
        self.assertIn(("company_id", "company.company_id", "equal"), joins)
        self.assertIn(("report_year", "reporting_period.fiscal_year", "equal"), joins)
        self.assertIn(("scope", "scope.scope_id", "equal_verified"), joins)
        self.assertEqual(check["result_policy"]["current_result"], "not_run_no_finding")
        self.assertEqual(
            check["result_policy"]["extract_not_found"],
            "not_run_no_finding",
        )
        self.assertEqual(
            check["result_policy"]["confirmed_not_disclosed"],
            "not_run_no_finding",
        )
        self.assertEqual(check["result_policy"]["failed_comparison_if_activated"], "NeedsReview")
        self.assertIn("never creates Contradicted", check["result_policy"]["contradiction_policy"])

    def test_catalogue_work_does_not_change_current_findings(self):
        claims = json.loads(
            (ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig")
        )
        rules = json.loads((ROOT / "data" / "config" / "rules.json").read_text(encoding="utf-8"))
        findings = evaluate(claims, rules)
        self.assertEqual(len(rules), 9)
        self.assertEqual(len(findings), 10)
        self.assertEqual(
            Counter(finding["status"] for finding in findings),
            Counter({"Supported": 6, "NeedsReview": 4}),
        )


class TemporalAssessmentTest(unittest.TestCase):
    @staticmethod
    def make_claim(year, value, *, claim_suffix=None, boundary="group", variant="reported"):
        suffix = claim_suffix or str(year)
        return {
            "schema_version": "1.0",
            "claim_id": f"CLM-TEMP-{suffix}",
            "company_id": "ACME",
            "company_name": "ACME",
            "report_year": year,
            "observation_year": year,
            "dimension": "G",
            "topic": "board",
            "claim_type": "target" if variant == "target" else "reported_measurement",
            "metric_id": "board_total",
            "label": "Board members",
            "value": value,
            "unit": "person",
            "scope": "board",
            "variant": variant,
            "period_type": "annual",
            "reporting_boundary": boundary,
            "reporting_boundary_verified": True,
            "boundary_change_status": "unchanged",
            "scope_change_status": "unchanged",
            "baseline_id": "consistent_basis",
            "baseline_change_status": "unchanged",
            "restatement_status": "not_restatement",
            "evidence": [{
                "evidence_id": f"EVD-TEMP-{suffix}",
                "source_file": f"acme-{year}.json",
                "source_pages": [10],
                "json_pointer": "/board/total",
                "source_text": f"Board total for {year} was {value}.",
            }],
        }

    @staticmethod
    def make_config(claims):
        return {
            "schema_version": "0.1",
            "scope_note": "Synthetic temporal test only.",
            "series": [{
                "series_id": "TS-ACME-BOARD",
                "concept_id": "board_total",
                "company_id": "ACME",
                "metric_id": "board_total",
                "claim_ids": [claim["claim_id"] for claim in claims],
                "comparison_mode": "consecutive_observation_years",
                "known_limitations": [],
            }],
        }

    def test_valid_target_pair_has_directed_links_and_complete_provenance(self):
        earlier = self.make_claim(2024, 5, variant="target")
        later = self.make_claim(2025, 6, variant="target")
        claim_schema = json.loads(
            (ROOT / "schemas" / "common-input-schema-v1.0.json").read_text(encoding="utf-8")
        )
        RuleCatalogueAndFinancialContractTest.assert_schema_valid(self, earlier, claim_schema)
        RuleCatalogueAndFinancialContractTest.assert_schema_valid(self, later, claim_schema)
        assessment = assess_temporal_pair(earlier, later)
        self.assertEqual(assessment["assessment_status"], "Comparable")
        self.assertTrue(assessment["comparison_performed"])
        self.assertEqual(assessment["change_type"], "target_change")
        self.assertEqual(assessment["numeric_change"]["absolute"], 1)

        graph = apply_temporal_assessment(
            build_graph([earlier, later], []),
            [earlier, later],
            self.make_config([earlier, later]),
        )
        edges = {
            (edge["source"], edge["target"], edge["label"])
            for edge in graph["edges"]
        }
        comparison = next(node for node in graph["nodes"] if node["type"] == "TemporalComparison")
        comparison_id = comparison["id"]

        self.assertIn(("claim:CLM-TEMP-2024", "claim:CLM-TEMP-2025", "NEXT_YEAR_CLAIM"), edges)
        self.assertIn((
            "measurement:CLM-TEMP-2024",
            "measurement:CLM-TEMP-2025",
            "NEXT_YEAR_TARGET",
        ), edges)
        self.assertIn((comparison_id, "report:ACME:2024", "DERIVED_FROM_REPORT"), edges)
        self.assertIn((comparison_id, "report:ACME:2025", "DERIVED_FROM_REPORT"), edges)
        self.assertIn((comparison_id, "evidence:EVD-TEMP-2024", "BASED_ON_EVIDENCE"), edges)
        self.assertIn((comparison_id, "evidence:EVD-TEMP-2025", "BASED_ON_EVIDENCE"), edges)
        self.assertEqual(comparison["from_report_year"], 2024)
        self.assertEqual(comparison["from_observation_year"], 2024)
        self.assertEqual(comparison["from_original_texts"], ["Board total for 2024 was 5."])
        self.assertFalse(any(node["type"] == "Finding" for node in graph["nodes"]))
        html = render_html(graph, [])
        self.assertIn("TemporalSeries", html)
        self.assertIn("TemporalComparison", html)

    def test_different_unexplained_boundary_is_needs_review_without_comparison(self):
        earlier = self.make_claim(2024, 5, boundary="parent_only")
        later = self.make_claim(2025, 6, boundary="consolidated_group")
        later["boundary_change_status"] = "unknown"

        assessment = assess_temporal_pair(earlier, later)
        self.assertEqual(assessment["assessment_status"], "NeedsReview")
        self.assertFalse(assessment["comparison_performed"])
        self.assertEqual(assessment["flags"]["boundary_change"], "changed_unexplained")
        self.assertIn("reporting_boundary_mismatch", assessment["flags"]["incompatibilities"])

        later["boundary_change_status"] = "changed"
        later["boundary_change_explanation"] = "The new consolidated boundary was reconciled."
        explained = assess_temporal_pair(earlier, later)
        self.assertEqual(explained["assessment_status"], "NeedsReview")
        self.assertTrue(explained["comparison_performed"])
        self.assertEqual(explained["flags"]["boundary_change"], "changed_explained")

    def test_explained_baseline_change_is_compared_but_remains_needs_review(self):
        earlier = self.make_claim(2024, 5)
        later = self.make_claim(2025, 6)
        later["baseline_id"] = "new_basis"
        later["baseline_change_status"] = "changed"
        later["baseline_change_explanation"] = "Classification basis changed and was reconciled."

        assessment = assess_temporal_pair(earlier, later)
        self.assertEqual(assessment["assessment_status"], "NeedsReview")
        self.assertTrue(assessment["comparison_performed"])
        self.assertEqual(assessment["flags"]["baseline_change"], "changed_explained")
        self.assertEqual(assessment["flags"]["restatement"], "not_restatement")
        self.assertEqual(assessment["change_type"], "numeric_change")

    def test_missing_value_is_needs_review_not_temporal_inconsistency(self):
        earlier = self.make_claim(2024, 5)
        later = self.make_claim(2025, None)
        later["evidence"][0]["source_text"] = None

        assessment = assess_temporal_pair(earlier, later)
        self.assertEqual(assessment["assessment_status"], "NeedsReview")
        self.assertFalse(assessment["comparison_performed"])
        self.assertEqual(assessment["change_type"], "not_assessed")
        self.assertIn("value_missing_or_non_numeric", assessment["flags"]["incompatibilities"])
        self.assertIn("original_text", assessment["flags"]["missing_context"])
        self.assertIn("not, by itself, a Temporal Inconsistency", assessment["disclaimer"])

    def test_explained_restatement_is_marked_and_remains_needs_review(self):
        earlier = self.make_claim(2024, 5)
        later = self.make_claim(2025, 5)
        later["restatement_status"] = "restated"
        later["restatement_explanation"] = "Prior classification was restated and reconciled."

        assessment = assess_temporal_pair(earlier, later)
        self.assertEqual(assessment["assessment_status"], "NeedsReview")
        self.assertTrue(assessment["comparison_performed"])
        self.assertEqual(assessment["flags"]["restatement"], "restated_explained")
        self.assertEqual(assessment["change_type"], "unchanged")

    def test_real_bsr_board_series_is_linked_but_not_compared_without_context(self):
        schema = json.loads(
            (ROOT / "schemas" / "temporal-assessment-schema-v0.1.json").read_text(encoding="utf-8")
        )
        config = load_temporal_config()
        RuleCatalogueAndFinancialContractTest.assert_schema_valid(self, config, schema)
        claims = json.loads(
            (ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig")
        )
        graph = apply_temporal_assessment(build_graph(claims, []), claims, config)
        comparisons = [
            node for node in graph["nodes"] if node["type"] == "TemporalComparison"
        ]

        self.assertEqual(len(comparisons), 2)
        self.assertEqual(
            [(node["from_value"], node["to_value"]) for node in comparisons],
            [(5, 5), (5, 7)],
        )
        self.assertTrue(all(node["assessment_status"] == "NeedsReview" for node in comparisons))
        self.assertTrue(all(not node["comparison_performed"] for node in comparisons))
        self.assertTrue(all(node["from_original_texts"] == [None] for node in comparisons))
        self.assertTrue(all(node["to_original_texts"] == [None] for node in comparisons))


if __name__ == "__main__":
    unittest.main()
