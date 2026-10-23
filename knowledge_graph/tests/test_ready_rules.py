"""Synthetic catalogue cases; none of these records is a pilot-company finding."""
import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from kg.ready_rules import RULES, evaluate_ready_rules
from kg.rdf_store import add_assessment, add_claim, add_finding, evidence_chain, new_graph, project_json
from kg.pipeline import _shacl_report
from tools.assessment_builder import build_assessments


def config():
    return {"aliases": [
        {"rule_id": rule_id, "metric_id": role, "role": role,
         "verification_status": "verified", "review_basis": "synthetic source review"}
        for rule_id, rule in RULES.items() for role in rule["roles"]
    ]}


def group(rule_id, values=None, company="FIX", report_id=None):
    rule = RULES[rule_id]
    values = values or ([40, 60, 100] if rule_id == "KG-E-01" else [3, 9])
    report_id = report_id or company + ":2025:ESG"
    result = []
    for index, (role, value) in enumerate(zip(rule["roles"], values)):
        record_id = f"{company}-{rule_id}-{index}-{report_id}"
        item = {
            "schema_version": "2.0", "record_id": record_id,
            "company_id": company, "report_id": report_id, "report_year": 2025,
            "report_type": "ESG", "reporting_entity": "group",
            "dimension": rule["dimension"], "claim_type": "measurement", "topic": rule["topic"],
            "metric_id": role, "metric_definition": role,
            "label": role,
            "metric_definition_verified": True, "value": value,
            "value_status": "missing" if value is None else "available",
            "unit": "tCO2e" if rule_id == "KG-E-01" else "person",
            "observation_year": 2025, "period_type": "annual", "period_type_verified": True,
            "reporting_boundary": "group", "reporting_boundary_verified": True,
            "scope": ("scope1", "scope2", "scope1_plus_scope2")[index] if rule_id == "KG-E-01" else "group",
            "organizational_scope": "group operations", "emission_basis": "gross",
            "scope2_method": "location_based", "calculation_method": "inventory_v1",
            "total_definition": "scope1_plus_scope2" if rule_id == "KG-E-01" and index == 2 else None,
            "population_id": "all_employees", "board_id": "same_board",
            "counting_method": "headcount", "measurement_date": "2025-12-31",
            "review_status": "reviewed", "variant": "reported", "baseline_id": None,
            "precision": {"verification_status": "verified", "mode": "exact", "source_basis": "synthetic exact values"},
            "uncertainty": [],
            "evidence": [{"evidence_id": "EV-" + record_id,
                          "source_file": report_id + ".pdf", "source_pages": [10 + index],
                          "json_pointer": "/records/" + str(index), "original_text": "Synthetic reviewed source sentence"}],
        }
        result.append(item)
    return result


def result(claims, rule_id):
    findings, log = evaluate_ready_rules(claims, config())
    events = [event for event in log if event["rule_id"] == rule_id]
    return findings, events


class ReadyRuleTests(unittest.TestCase):
    def test_catalogue_fifteen_synthetic_cases(self):
        cases = []
        for rule_id in RULES:
            base = group(rule_id)
            cases.append((rule_id + "-PASS", rule_id, base, "Supported"))
            bad = copy.deepcopy(base)
            bad[-1]["value"] = 105 if rule_id == "KG-E-01" else 2
            if rule_id != "KG-E-01":
                bad[0]["value"] = 3
            cases.append((rule_id + "-FAIL", rule_id, bad, "Contradicted"))
            missing = copy.deepcopy(base)
            missing[0]["value"] = None
            missing[0]["value_status"] = "missing"
            cases.append((rule_id + "-NULL", rule_id, missing, "InsufficientEvidence"))
            context = copy.deepcopy(base)
            if rule_id == "KG-E-01":
                context[0]["reporting_boundary"] = "parent"
            elif rule_id == "KG-S-01":
                context[0]["counting_method"] = "FTE"
            else:
                context[0]["measurement_date"] = "2025-06-30"
            cases.append((rule_id + "-CONTEXT", rule_id, context, "NeedsReview"))
            absent = copy.deepcopy(base)
            if rule_id == "KG-E-01":
                absent = absent[:2]
                expected = "Skipped"
            else:
                absent = [
                    {**absent[0], "metric_id": "female_share" if rule_id == "KG-S-01" else None,
                     "claim_type": "policy", "value": None, "value_status": "not_applicable"}
                ]
                expected = "NotApplicable"
            cases.append((rule_id + "-ABSENT", rule_id, absent, expected))
        self.assertEqual(len(cases), 15)
        for name, rule_id, claims, expected in cases:
            with self.subTest(name=name):
                findings, events = result(claims, rule_id)
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0]["outcome"], expected)
                self.assertEqual(bool([f for f in findings if f["rule_id"] == rule_id]), expected not in {"Skipped", "NotApplicable"})

    def test_rounding_precision_and_no_demo_tolerance(self):
        claims = group("KG-E-01", [40.0, 60.0, 100.4])
        _, events = result(claims, "KG-E-01")
        self.assertEqual(events[0]["outcome"], "Contradicted")
        for c in claims:
            c["precision"] = {"verification_status": "verified", "mode": "rounded_half_up",
                              "step": "1", "source_basis": "synthetic source states rounded to whole tonne"}
        findings, events = result(claims, "KG-E-01")
        self.assertEqual(events[0]["outcome"], "Supported")
        self.assertIn("component_sum_interval", findings[0]["calculation"])
        claims[-1]["value"] = 103
        _, events = result(claims, "KG-E-01")
        self.assertEqual(events[0]["outcome"], "Contradicted")
        claims[-1]["value"] = 101.5
        _, events = result(claims, "KG-E-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("precision_interval_endpoint_contact", events[0]["reasons"])
        claims[-1]["precision"] = None
        _, events = result(claims, "KG-E-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("precision_unverified", events[0]["reasons"])

    def test_variant_and_report_identity_are_not_first_candidate(self):
        claims = group("KG-G-01")
        duplicate = copy.deepcopy(claims[0])
        duplicate["record_id"] += "-variant"
        duplicate["variant"] = "comparative"
        findings, events = result(claims + [duplicate], "KG-G-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertEqual(len(findings[0]["input_claim_ids"]), 3)
        self.assertIn("multiple_candidates_for_role", events[0]["reasons"])
        separate = copy.deepcopy(claims[1])
        separate["report_id"] = "FIX:2025:ANOTHER_ESG"
        findings, events = result([claims[0], separate], "KG-G-01")
        self.assertEqual(findings, [])
        self.assertEqual([e["outcome"] for e in events], ["Skipped", "Skipped"])
        mixed = group("KG-S-01")
        mixed[0]["variant"] = "comparative"
        _, events = result(mixed, "KG-S-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("variant_mismatch", events[0]["reasons"])
        target = group("KG-S-01")
        target[0]["variant"] = "target"
        findings, events = result(target, "KG-S-01")
        self.assertEqual(findings, [])
        self.assertEqual(events[0]["outcome"], "Skipped")

    def test_missing_plus_context_and_source_review_precedence(self):
        claims = group("KG-S-01", [None, 100])
        claims[0]["reporting_boundary"] = "unknown"
        claims[0]["review_status"] = "unreviewed"
        findings, events = result(claims, "KG-S-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("value_missing_or_uncertain", events[0]["reasons"])
        self.assertIn("reporting_boundary_unknown", events[0]["reasons"])
        self.assertEqual(findings[0]["status"], "NeedsReview")
        claims = group("KG-S-01", [45, 100])
        claims[0]["review_status"] = "unreviewed"
        _, events = result(claims, "KG-S-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        partial = group("KG-S-01", [None, 100])[:1]
        partial[0]["reporting_boundary"] = "unknown"
        _, events = result(partial, "KG-S-01")
        self.assertEqual(events[0]["outcome"], "Skipped")
        self.assertIn("missing_employees_total_count", events[0]["reasons"])
        self.assertIn("reporting_boundary_unknown_or_unverified", events[0]["reasons"])
        self.assertIn("value_missing_or_uncertain", events[0]["reasons"])

    def test_ambiguous_mapping_and_invalid_counts(self):
        claims = group("KG-S-01")
        cfg = config()
        cfg["aliases"][3]["verification_status"] = "candidate"  # S female role
        _, log = evaluate_ready_rules(claims, cfg)
        self.assertEqual(next(e for e in log if e["rule_id"] == "KG-S-01")["outcome"], "NeedsReview")
        for value in (-1, 3.5):
            claims[0]["value"] = value
            _, events = result(claims, "KG-S-01")
            self.assertEqual(events[0]["outcome"], "NeedsReview")

    def test_board_identity_and_same_context_across_company_ids(self):
        for company in ("BSR", "PLX", "PVD"):
            with self.subTest(company=company):
                claims = group("KG-G-01", company=company)
                _, events = result(claims, "KG-G-01")
                self.assertEqual(events[0]["outcome"], "Supported")
        claims = group("KG-G-01")
        claims[0]["board_id"] = "unknown"
        _, events = result(claims, "KG-G-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        claims[0]["board_id"] = "different_board"
        findings, events = result(claims, "KG-G-01")
        self.assertEqual(events[0]["outcome"], "Skipped")
        self.assertEqual(findings, [])
        self.assertIn("different_boards", events[0]["reasons"])

    def test_subset_comparison_frame_can_replace_exact_date_but_not_context(self):
        board = group("KG-G-01", [2, 7])
        for claim in board:
            claim["measurement_date"] = None
            claim["counting_method"] = None
            claim["comparison_frame_id"] = "FRAME-SAME-SOURCE-STATEMENT"
        _, events = result(board, "KG-G-01")
        self.assertEqual(events[0]["outcome"], "Supported")
        self.assertNotIn("measurement_date_unknown", events[0]["reasons"])
        self.assertNotIn("not_headcount", events[0]["reasons"])

        different_snapshot = copy.deepcopy(board)
        different_snapshot[1]["comparison_frame_id"] = "FRAME-OTHER-STATEMENT"
        _, events = result(different_snapshot, "KG-G-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("comparison_frame_id_mismatch", events[0]["reasons"])

        ambiguous = copy.deepcopy(board)
        ambiguous[0]["comparison_frame_id"] = None
        _, events = result(ambiguous, "KG-G-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("comparison_frame_unknown", events[0]["reasons"])

        unreviewed = copy.deepcopy(board)
        unreviewed[0]["graph_context_review_required"] = True
        _, events = result(unreviewed, "KG-G-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("graph_context_review_missing", events[0]["reasons"])

    def test_workforce_requires_same_population_and_counting_basis_not_gender_sum(self):
        claims = group("KG-S-01", [214, 1594])
        for claim in claims:
            claim["counting_method"] = "FTE"
            claim["measurement_date"] = None
            claim["comparison_frame_id"] = "FRAME-SAME-WORKFORCE-TABLE"
        _, events = result(claims, "KG-S-01")
        self.assertEqual(events[0]["outcome"], "Supported")
        self.assertNotIn("not_headcount", events[0]["reasons"])

        different_population = copy.deepcopy(claims)
        different_population[0]["population_id"] = "contractors"
        _, events = result(different_population, "KG-S-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("population_id_mismatch", events[0]["reasons"])

        different_method = copy.deepcopy(claims)
        different_method[0]["counting_method"] = "headcount"
        _, events = result(different_method, "KG-S-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("counting_method_mismatch", events[0]["reasons"])

        unknown_method = copy.deepcopy(claims)
        unknown_method[0]["counting_method"] = None
        _, events = result(unknown_method, "KG-S-01")
        self.assertEqual(events[0]["outcome"], "NeedsReview")
        self.assertIn("counting_method_unknown", events[0]["reasons"])

    def test_end_to_end_finding_assessment_rdf_and_log_only_outcome(self):
        claims = group("KG-S-01", [105, 100])
        schema = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "graph-input-v2.json").read_text(encoding="utf-8"))
        self.assertTrue(all(Draft202012Validator(schema).is_valid(c) for c in claims))
        findings, events = result(claims, "KG-S-01")
        self.assertEqual(findings[0]["status"], "Contradicted")
        graph = new_graph()
        for claim in claims:
            add_claim(graph, claim)
        for finding in findings:
            add_finding(graph, finding)
        legacy = [{**claim, "claim_id": claim["record_id"],
                   "evidence": [{**e, "source_text": e["original_text"]} for e in claim["evidence"]]}
                  for claim in claims]
        assessments = build_assessments(legacy, findings, project_json(graph))
        self.assertEqual(len(assessments["claim_assessments"]), 2)
        self.assertEqual(assessments["company_assessments"]["company_multiyear_assessments"][0]["finding_count"], 1)
        for assessment in assessments["claim_assessments"]:
            add_assessment(graph, assessment)
        for assessment in assessments["company_assessments"]["company_multiyear_assessments"]:
            add_assessment(graph, assessment)
        chain = evidence_chain(graph)
        self.assertEqual({row[1] for row in chain}, {claim["record_id"] for claim in claims})
        self.assertEqual(len(chain), 2)
        self.assertEqual(_shacl_report(graph)["structural_violations"], 0)
        self.assertEqual(_shacl_report(graph, "kg/business_shapes.ttl")["structural_violations"], 0)
        self.assertTrue(assessments["claim_assessments"][0]["reason"])
        policy = {**claims[0], "record_id": "POLICY", "metric_id": None,
                  "claim_type": "policy", "value": None, "value_status": "not_applicable"}
        findings, log = result([policy], "KG-S-01")
        self.assertEqual(findings, [])
        self.assertEqual(log[0]["outcome"], "NotApplicable")
        self.assertTrue(log[0]["reasons"])


if __name__ == "__main__":
    unittest.main()
