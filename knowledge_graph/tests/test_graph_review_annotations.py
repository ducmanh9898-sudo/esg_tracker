"""Synthetic Graph reviewer actions; no pilot-company annotation is verified here."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from kg.ready_rules import evaluate_ready_rules
from kg.review_annotations import apply_review_annotations, make_pending_template
from kg.rdf_store import ESG, add_claim, add_finding, evidence_chain, new_graph
from rdflib import Literal
from tests.test_ready_rules import config, group


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = json.loads((ROOT / "schemas/graph-review-annotations-v1.json").read_text(encoding="utf-8"))


class GraphReviewAnnotationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.source = self.folder / "synthetic-extract.json"
        self.source.write_text('{"synthetic": true, "version": 1}', encoding="utf-8")
        self.relative_source = self.source.relative_to(ROOT).as_posix()
        self.annotation_path = self.folder / "annotations.json"

    def setup_rule(self, rule_id, values=None):
        claims = group(rule_id, values=values)
        for claim in claims:
            for evidence in claim["evidence"]:
                evidence["source_extract_path"] = self.relative_source
        aliases = config()
        finding = {"rule_id": rule_id, "input_claim_ids": [c["record_id"] for c in claims]}
        template = make_pending_template(claims, [finding], aliases, ROOT)
        Draft202012Validator(SCHEMA, format_checker=FormatChecker()).validate(template)
        return claims, aliases, template

    def run_reviews(self, claims, aliases, annotations):
        self.annotation_path.write_text(json.dumps(annotations), encoding="utf-8")
        reviewed, scoped_aliases, audit = apply_review_annotations(claims, aliases, self.annotation_path, ROOT)
        findings, events = evaluate_ready_rules(reviewed, scoped_aliases)
        event = next(e for e in events if e["rule_id"] == annotations["context_reviews"][0]["rule_id"])
        return reviewed, findings, event, audit

    @staticmethod
    def verify_all(template):
        approved = copy.deepcopy(template)
        for section, status in (("source_reviews", "reviewed"), ("mapping_reviews", "verified"),
                                ("context_reviews", "verified")):
            for row in approved[section]:
                row.update(status=status, reviewer="Synthetic reviewer", reviewed_at="2026-01-02T12:00:00Z",
                           review_basis="Synthetic source sentence, page and method checked for this test")
        return approved

    def test_complete_review_allows_strong_result_for_each_existing_rule(self):
        for rule_id in ("KG-E-01", "KG-S-01", "KG-G-01"):
            with self.subTest(rule_id=rule_id):
                claims, aliases, template = self.setup_rule(rule_id)
                _, findings, event, audit = self.run_reviews(claims, aliases, self.verify_all(template))
                self.assertEqual(event["outcome"], "Supported")
                self.assertEqual(findings[0]["status"], "Supported")
                self.assertEqual(audit["counts"]["applied"], len(claims) * 3)
                self.assertEqual(claims[0]["review_status"], "reviewed")  # original input stays intact

    def test_missing_review_and_unverified_mapping_or_context_stay_needs_review(self):
        claims, aliases, template = self.setup_rule("KG-S-01")
        for section in ("source_reviews", "mapping_reviews", "context_reviews"):
            with self.subTest(section=section):
                approved = self.verify_all(template)
                approved[section][0]["status"] = "pending"
                _, _, event, _ = self.run_reviews(claims, aliases, approved)
                self.assertEqual(event["outcome"], "NeedsReview")
        reviewed, scoped_aliases, _ = apply_review_annotations(claims, aliases, None, ROOT)
        event = next(e for e in evaluate_ready_rules(reviewed, scoped_aliases)[1] if e["rule_id"] == "KG-S-01")
        self.assertEqual(event["outcome"], "NeedsReview")

    def test_wrong_reference_and_stale_fingerprint_do_not_pass(self):
        claims, aliases, template = self.setup_rule("KG-G-01")
        for defect in ("record_id", "extract_sha256", "source_file"):
            with self.subTest(defect=defect):
                approved = self.verify_all(template)
                if defect == "record_id":
                    approved["source_reviews"][0]["record_id"] = "wrong-claim"
                elif defect == "extract_sha256":
                    approved["source_reviews"][0]["extract_sha256"] = "0" * 64
                else:
                    approved["source_reviews"][0]["source_refs"][0]["source_file"] = "wrong.pdf"
                _, _, event, audit = self.run_reviews(claims, aliases, approved)
                self.assertEqual(event["outcome"], "NeedsReview")
                self.assertGreater(audit["counts"]["rejected"], 0)
        approved = self.verify_all(template)
        self.source.write_text('{"synthetic": true, "version": 2}', encoding="utf-8")
        _, _, event, audit = self.run_reviews(claims, aliases, approved)
        self.assertEqual(event["outcome"], "NeedsReview")
        self.assertTrue(any("extract_fingerprint_stale" in row["reasons"] for row in audit["rejected"]))

    def test_bad_extra_annotation_does_not_stop_valid_claims(self):
        claims, aliases, template = self.setup_rule("KG-S-01")
        approved = self.verify_all(template)
        bogus = copy.deepcopy(approved["source_reviews"][0])
        bogus["annotation_id"] = "SRC-unrelated-wrong-report"
        bogus["record_id"] = "unrelated-claim"
        approved["source_reviews"].append(bogus)
        _, findings, event, audit = self.run_reviews(claims, aliases, approved)
        self.assertEqual(event["outcome"], "Supported")
        self.assertEqual(findings[0]["status"], "Supported")
        self.assertEqual(audit["counts"]["rejected"], 1)

    def test_pending_template_never_verifies_corpus(self):
        claims, aliases, template = self.setup_rule("KG-E-01")
        reviewed, findings, event, audit = self.run_reviews(claims, aliases, template)
        self.assertEqual(event["outcome"], "NeedsReview")
        self.assertEqual(findings[0]["status"], "NeedsReview")
        self.assertEqual(audit["counts"]["applied"], 0)
        self.assertEqual(reviewed[0]["graph_context_review_status"], "pending")

    def test_reviewed_quote_reaches_rdf_and_finding_chain(self):
        claims, aliases, template = self.setup_rule("KG-S-01", [12, 10])
        claims[0]["evidence"][0]["original_text"] = None
        template = make_pending_template(claims, [{"rule_id": "KG-S-01",
            "input_claim_ids": [c["record_id"] for c in claims]}], aliases, ROOT)
        approved = self.verify_all(template)
        quote = "Synthetic source: twelve female employees."
        for section in ("source_reviews", "mapping_reviews", "context_reviews"):
            approved[section][0]["source_refs"][0]["original_text"] = quote
        reviewed, findings, event, audit = self.run_reviews(claims, aliases, approved)
        self.assertEqual(event["outcome"], "Contradicted")
        self.assertEqual(audit["counts"]["rejected"], 0)
        self.assertIsNone(claims[0]["evidence"][0]["original_text"])
        graph = new_graph()
        for claim in reviewed:
            add_claim(graph, claim)
        add_finding(graph, findings[0])
        self.assertIn(Literal(quote), set(graph.objects(None, ESG.reviewedSourceText)))
        self.assertEqual({row[1] for row in evidence_chain(graph)}, {c["record_id"] for c in claims})


if __name__ == "__main__":
    unittest.main()
