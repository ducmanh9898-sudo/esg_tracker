from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from rdflib import Graph, Literal

from kg.corporate_adapter import digest
from kg.corporate_assessment import arithmetic_candidates, assess, candidates, proposal, comparison_digest
from kg.corporate_fixture import create
from kg.corporate_pipeline import build, evaluation, load_json, prepare, sha256, write_json
from kg.rdf_store import ESG, uri


class CorporateGraphTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.manifest, self.config = create(self.root / "delivery")
        self.claims, _, _, _, _ = prepare(self.manifest, self.config)

    def tearDown(self):
        self.temp.cleanup()

    def pair(self, metric="ghg_scope1", suffix="ESG-ESG"):
        records = [c for c in self.claims if c["metric_id"] == metric and suffix in c["report_id"]][:2]
        return records, proposal([c["record_id"] for c in records])

    def reviewed(self, records, row):
        identity = {"reviewer_kind": "human", "reviewer": "SYNTHETIC TEST REVIEWER",
                    "reviewed_at_utc": "2026-01-01T00:00:00Z", "basis": "Synthetic test expectation only"}
        record_events = {c["record_id"]: {**identity, "decision": "accept", "input_digest": c["input_digest"],
            "checks": {k: True for k in ("source_quote", "value", "association", "semantic_context")}} for c in records}
        index = {c["record_id"]: c for c in records}
        comparisons = {row["comparison_id"]: {**identity, "decision": "comparable", "input_digest": comparison_digest(row, index),
            "absolute_tolerance": 0, "not_applicable_fields": ["population", "counting_method"], "restatement_checked": True}}
        return index, record_events, comparisons

    def test_pdf_json_rdf_pending_and_idempotent(self):
        first = build(self.manifest, self.root / "run1", self.config)
        second = build(self.manifest, self.root / "run2", self.config)
        self.assertEqual(first["status"], "completed")
        self.assertEqual(first["records"], 21)
        self.assertEqual(first["findings_by_status"].keys(), {"NeedsReview"})
        self.assertEqual(first["findings_by_status"], second["findings_by_status"])
        self.assertEqual(load_json(self.root / "run1/findings.json"), load_json(self.root / "run2/findings.json"))
        graph = Graph().parse(self.root / "run1/graph.ttl")
        c = self.claims[0]
        ev = c["evidence"][0]
        self.assertIn((uri("evidence", ev["evidence_id"]), ESG.sourceSha256, Literal(ev["source_sha256"])), graph)
        self.assertTrue(list(graph.objects(uri("claim", c["record_id"]), ESG.corporateRecordJson)))
        self.assertIsNone(load_json(self.root / "run1/evaluation.json")["extraction_recall"])

    def test_reviewed_same_period_difference_and_equal(self):
        records, row = self.pair()
        self.assertEqual(assess(row, *self.reviewed(records, row))["status"], "Contradicted")
        records, row = self.pair("employees_total")
        self.assertEqual(assess(row, *self.reviewed(records, row))["status"], "Supported")

    def test_source_basis_guard_and_nonfinite_tolerance(self):
        records, row = self.pair()
        index, events, comparisons = self.reviewed(records, row)
        result = assess(row, index, events, comparisons, require_source_basis=True)
        self.assertIn("source_version_audit_basis_unreviewed", result["reasons"])
        event = comparisons[row["comparison_id"]]
        event.update(source_basis_checked=True, source_basis_note="Synthetic audited basis checked")
        self.assertEqual(assess(row, index, events, comparisons, require_source_basis=True)["status"], "Contradicted")
        event["absolute_tolerance"] = float("nan")
        self.assertIn("rounding_tolerance_unreviewed", assess(row, index, events, comparisons)["reasons"])

    def test_explicit_comparison_cannot_override_different_table_parent_rows(self):
        records, row = deepcopy(self.pair())
        for record, row_number in zip(records, ("1.1", "2.1")):
            raw = record["raw_record"]
            raw["evidence"][0]["context_text"] = f"{raw['metric_label']}\n{row_number}\n2023"
        result = assess(row, *self.reviewed(records, row))
        self.assertEqual(result["status"], "NeedsReview")
        self.assertIn("table_row_context_mismatch", result["reasons"])

    def test_unknown_observation_year_is_not_auto_paired(self):
        records, row = deepcopy(self.pair())
        records[0]["observation_year"] = None
        self.assertEqual(candidates(records, [], auto=True), [])
        self.assertEqual(candidates(records, [row], auto=False), [row])

    def test_blocked_context(self):
        for mutation, reason in (("year", "observation_year_unknown"), ("restatement", "restatement_unresolved_or_present"),
                                 ("scope", "scope_mismatch"), ("unit", "unit_mismatch"), ("target", "not_reported_numeric_result")):
            with self.subTest(mutation=mutation):
                records, row = deepcopy(self.pair())
                if mutation == "year": records[0]["observation_year"] = None
                if mutation == "restatement": records[0]["raw_record"]["restatement"]["status"] = "restated"
                if mutation == "scope": records[0]["raw_record"]["boundary"]["scope"] = "different"
                if mutation == "unit": records[0]["unit"] = "kg"
                if mutation == "target": records[0]["raw_record"]["record_type"] = "target"
                result = assess(row, *self.reviewed(records, row))
                self.assertEqual(result["status"], "NeedsReview")
                self.assertIn(reason, result["reasons"])

    def test_separate_consolidated_never_compare_as_same(self):
        records = [c for c in self.claims if c["report_year"] == 2023 and c["report_type"] == "Financial" and c["metric_id"] == "employees_total"]
        row = proposal([c["record_id"] for c in records])
        result = assess(row, *self.reviewed(records, row))
        self.assertIn("consolidation_mismatch", result["reasons"])
        self.assertEqual(result["status"], "NeedsReview")

    def test_stale_and_ai_review_cannot_promote(self):
        records, row = self.pair()
        index, events, comparisons = self.reviewed(records, row)
        events[records[0]["record_id"]]["input_digest"] = "stale"
        self.assertIn("stale_record_review", assess(row, index, events, comparisons)["reasons"])
        _, events, comparisons = self.reviewed(records, row)
        comparisons[row["comparison_id"]]["reviewer_kind"] = "chatgpt_assisted"
        self.assertEqual(assess(row, index, events, comparisons)["status"], "NeedsReview")

    def mutate_file(self, change):
        manifest = load_json(self.manifest)
        row = manifest["files"][0]
        path = self.manifest.parent / row["json_path"]
        raw = load_json(path)
        change(raw)
        write_json(path, raw)
        row["json_sha256"] = sha256(path)
        write_json(self.manifest, manifest)

    def test_bad_source_page_quote_year_unit_are_blocked(self):
        for mutation in ("hash", "page", "quote", "year", "unit"):
            original = self.manifest.read_bytes()
            row = load_json(self.manifest)["files"][0]
            path = self.manifest.parent / row["json_path"]
            raw_bytes = path.read_bytes()
            def change(raw):
                r = raw["records"][0]
                if mutation == "hash": r["evidence"][0]["source_sha256"] = "f" * 64
                if mutation == "page": r["evidence"][0]["physical_page"] = 2
                if mutation == "quote": r["evidence"][0]["exact_quote"] = "fabricated"
                if mutation == "year": r["period"]["observation_year"] = 2025
                if mutation == "unit": r["value"]["original_unit"] = "invented unit"
            self.mutate_file(change)
            result = build(self.manifest, self.root / mutation, self.config)
            self.assertEqual(result["status"], "partial")
            self.assertTrue(result["errors"])
            self.assertNotIn("Contradicted", result["findings_by_status"])
            path.write_bytes(raw_bytes)
            self.manifest.write_bytes(original)

    def test_duplicate_and_pdf_hash_fail(self):
        self.mutate_file(lambda raw: raw["records"].append(deepcopy(raw["records"][0])))
        self.assertEqual(build(self.manifest, self.root / "dup", self.config)["status"], "partial")
        pdf = next((self.manifest.parent / "pdf").glob("*.pdf"))
        with pdf.open("ab") as stream: stream.write(b"changed")
        self.assertEqual(build(self.manifest, self.root / "badpdf", self.config)["status"], "failed")

    def test_partial_never_becomes_disclosure_absence(self):
        self.mutate_file(lambda raw: raw["coverage"]["search_outcomes"][0].update(status="extraction_failure"))
        result = build(self.manifest, self.root / "partial", self.config)
        self.assertEqual(result["status"], "partial")
        self.assertNotIn("DisclosureGap", result["findings_by_status"])

    def test_output_not_overwritten(self):
        output = self.root / "existing"
        output.mkdir()
        (output / "sentinel").write_text("keep")
        with self.assertRaisesRegex(ValueError, "output_exists"):
            build(self.manifest, output, self.config)
        self.assertEqual((output / "sentinel").read_text(), "keep")

    def test_same_report_arithmetic(self):
        records = deepcopy(self.claims[:3])
        for c in records:
            c["unit"] = "person"
        records[0]["value"], records[1]["value"], records[2]["value"] = 2, 3, 5
        row = proposal([c["record_id"] for c in records], "sum_equals")
        self.assertEqual(assess(row, *self.reviewed(records, row))["status"], "Supported")
        records[2]["value"] = 8
        self.assertEqual(assess(row, *self.reviewed(records, row))["status"], "Contradicted")

    def test_arithmetic_mapping_ambiguity_is_logged(self):
        records = deepcopy(self.claims[:3])
        template = {"rule_id": "SYNTHETIC-SUM", "relation": "sum_equals",
                    "operand_metrics": [[c["metric_id"]] for c in records]}
        rows, audit = arithmetic_candidates(records, [template])
        self.assertEqual(len(rows), 1)
        self.assertEqual(audit[0]["status"], "candidate_pending_review")
        duplicate = deepcopy(records[0])
        duplicate["record_id"] += "-OTHER"
        rows, audit = arithmetic_candidates(records + [duplicate], [template])
        self.assertEqual(rows, [])
        self.assertEqual(audit[0]["status"], "missing_or_ambiguous_operands")

    def test_full_review_file_flow_and_gold_gate(self):
        build(self.manifest, self.root / "pending", self.config)
        review = load_json(self.root / "pending/review_template.json")
        records, row = self.pair()
        _, record_events, comparison_events = self.reviewed(records, row)
        review["record_events"] = [{"record_id": key, **value} for key, value in record_events.items()]
        review["comparison_events"] = [{"comparison_id": key, **value} for key, value in comparison_events.items()]
        path = self.root / "synthetic-test-review.json"
        write_json(path, review)
        summary = build(self.manifest, self.root / "reviewed", self.config, path)
        self.assertEqual(summary["status"], "completed")
        self.assertEqual(summary["findings_by_status"]["Contradicted"], 1)
        findings = load_json(self.root / "reviewed/findings.json")
        gold = {"schema_version": "corporate-assessment-gold-1.0", "items": [
            {**review["comparison_events"][0], "split": "held_out", "adjudication_status": "adjudicated", "expected_status": "Contradicted"}]}
        self.assertEqual(evaluation(findings, gold)["assessment_accuracy"], 1)
        gold["items"][0]["reviewer_kind"] = "ai"
        with self.assertRaisesRegex(ValueError, "not_human_adjudicated"):
            evaluation(findings, gold)

    def test_normalization_is_not_multiplied_twice(self):
        self.mutate_file(lambda raw: raw["records"][0]["value"].update(normalized_value=10000000))
        result = build(self.manifest, self.root / "badscale", self.config)
        self.assertEqual(result["status"], "partial")
        self.assertIn("normalization_mismatch", str(result["errors"]))

    def test_duplicate_across_reports_never_merges(self):
        foreign_id = self.claims[3]["record_id"]
        self.mutate_file(lambda raw: raw["records"][0].update(record_id=foreign_id))
        result = build(self.manifest, self.root / "duplicate", self.config)
        self.assertEqual(result["status"], "failed")
        self.assertIn("duplicate_record_id", str(result["errors"]))

    def test_layer_checks_remain_separate(self):
        records, row = self.pair()
        _, records_events, _ = self.reviewed(records, row)
        event = records_events[records[0]["record_id"]]
        event["checks"]["association"] = False
        path = self.root / "review.json"
        write_json(path, {"schema_version": "corporate-graph-review-1.0", "record_events": [
            {"record_id": records[0]["record_id"], **event}], "comparison_events": []})
        build(self.manifest, self.root / "layers", self.config, path)
        audit = load_json(self.root / "layers/record_validation.json")[0]
        self.assertEqual(audit["source_quote"], "reviewed")
        self.assertEqual(audit["association"], "pending_review")
        self.assertEqual(audit["status"], "NeedsReview")


if __name__ == "__main__":
    unittest.main()
