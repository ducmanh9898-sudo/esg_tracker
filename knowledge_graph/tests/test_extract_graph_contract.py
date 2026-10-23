"""Synthetic handoff examples: source schema, adapters, normalized ESG, and RDF."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator
from rdflib import Graph

from kg.adapters import ROOT, adapt_financial_handoff, adapt_separate_full, adapt_structured_esg
from kg.pipeline import _validate_handoff_source, build, financial_comparability
from kg.rdf_store import ESG, add_claim, add_financial, new_graph, uri


def load(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


class ExtractGraphContractTests(unittest.TestCase):
    esg_path = "docs/examples/extract-esg.synthetic.json"
    financial_path = "docs/examples/extract-financial-separate.synthetic.json"
    consolidated_path = "docs/examples/extract-financial-consolidated.synthetic.json"

    def test_examples_validate_and_manifest_hashes_match(self):
        manifest = load("docs/examples/manifest.synthetic.json")
        manifest_schema = load("schemas/extract-batch-manifest-v1.json")
        Draft202012Validator(manifest_schema).validate(manifest)
        self.assertEqual(len(manifest["files"]), 3)
        for entry in manifest["files"]:
            path = ROOT / entry["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
            schema_name = ("extract-esg-handoff-v1.json" if entry["report_type"] == "ESG"
                           else "extract-financial-handoff-v1.json")
            source = json.loads(path.read_text(encoding="utf-8"))
            self.assertTrue(source["synthetic_example"])
            Draft202012Validator(load("schemas/" + schema_name)).validate(source)
            self.assertEqual(source["document"]["company_id"], entry["company_id"])
            self.assertEqual(source["document"]["report_year"], entry["report_year"])

    def test_esg_adapter_accepts_null_and_policy_without_value(self):
        source = load(self.esg_path)
        report = {
            "path": self.esg_path, "company_id": "EXAMPLE", "report_id": "EXAMPLE:2025:ESG",
            "handoff_version": source["schema_version"],
            "report_year": 2025, "report_type": "ESG", "reporting_entity": "unknown",
            "source_file": source["document"]["source_file"], "source_file_verified": True,
            "reporting_period_start": "2025-01-01", "reporting_period_end": "2025-12-31",
            "publication_date": None, "extraction_timestamp": source["document"]["extraction_timestamp"],
            "period_type": "annual", "period_type_verified": True, "boundary_verified": False,
        }
        records = adapt_structured_esg(report, source)
        self.assertEqual(len(records), 5)
        schema = Draft202012Validator(load("schemas/graph-input-v2.json"))
        graph = new_graph()
        for record in records:
            schema.validate(record)
            add_claim(graph, record)
        by_id = {record["record_id"]: record for record in records}
        missing = by_id["EX-ESG-MISSING-2025"]
        self.assertIsNone(missing["value"])
        self.assertEqual(missing["value_status"], "missing")
        self.assertEqual(list(graph.objects(uri("measurement", missing["record_id"]), ESG.numericValue)), [])
        policy = by_id["EX-ESG-POLICY-2025"]
        self.assertIsNone(policy["value"])
        self.assertIsNone(policy["unit"])
        self.assertIsNone(policy["metric_id"])
        self.assertIsNone(policy["observation_year"])
        self.assertEqual(policy["value_status"], "not_applicable")
        self.assertEqual(list(graph.objects(uri("claim", policy["record_id"]), ESG.hasMeasurement)), [])
        self.assertEqual(list(graph.objects(uri("claim", policy["record_id"]), ESG.hasMetric)), [])
        self.assertEqual(list(graph.objects(uri("claim", policy["record_id"]), ESG.hasPeriod)), [])
        self.assertEqual([str(v) for v in graph.objects(uri("claim", policy["record_id"]), ESG.recordId)],
                         [policy["record_id"]])
        source_rows = list(graph.query("""PREFIX esg: <https://example.org/esg/core#>
            SELECT ?file ?reportId WHERE {
              ?claim esg:recordId "EX-ESG-POLICY-2025" ; esg:hasEvidence ?e ; esg:fromReport ?r .
              ?e esg:sourceFile ?file . ?r esg:reportId ?reportId .
            }"""))
        self.assertEqual([(str(file), str(report)) for file, report in source_rows],
                         [(source["document"]["source_file"], "EXAMPLE:2025:ESG")])
        self.assertEqual(policy["evidence"][0]["original_text"], source["governance"]["policy"]["records"][0]["original_text"])
        self.assertEqual(policy["evidence"][0]["source_pages"], [8])
        self.assertEqual(policy["extraction_status"], "extracted")
        self.assertEqual(by_id["EX-ESG-ENERGY-TARGET-2026"]["observation_year"], 2026)
        self.assertEqual(by_id["EX-ESG-ENERGY-TARGET-2026"]["variant"], "target")
        unknown = by_id["EX-ESG-UNKNOWN-PERIOD"]
        self.assertIsNone(unknown["observation_year"])
        self.assertIsNone(unknown["reporting_boundary"])
        self.assertFalse(unknown["assessment_eligible"])
        self.assertIn("observation_period_unknown", unknown["uncertainty"])
        self.assertIn("source_pages_missing", unknown["uncertainty"])
        self.assertIn("original_text_missing", unknown["uncertainty"])
        self.assertEqual(list(graph.objects(uri("claim", unknown["record_id"]), ESG.hasPeriod)), [])

    def test_financial_adapter_keeps_period_scale_scope_and_provenance(self):
        source = load(self.financial_path)
        result = adapt_financial_handoff(source, self.financial_path)
        records = result["financial_records"]
        self.assertEqual(len(records), 2)
        self.assertEqual(result["claim_count_difference"], 0)
        graph = new_graph()
        for record in records:
            add_financial(graph, record)
            self.assertEqual(record["report_year"], 2025)
            self.assertEqual(record["scope"]["scope_id"], "separate_parent")
            self.assertEqual(record["unit_multiplier"], 1000000)
            self.assertEqual(record["review_status"], "unreviewed")
        prior = next(record for record in records if record["observation_year"] == 2024)
        self.assertEqual(prior["variant"], "comparative")
        self.assertEqual(prior["source_report_id"], "EXAMPLE_2025_FS_SEPARATE:Separate")
        self.assertEqual(prior["source_pages"], [2])
        self.assertEqual(prior["original_text"], source["structured_key_metrics"][0]["claim_text"])
        self.assertEqual(prior["ocr_page_pointers"], ["/pages/1/text"])
        reversed_source = load(self.financial_path)
        reversed_source["structured_key_metrics"][0]["measurements"].reverse()
        self.assertEqual({r["disclosure_id"] for r in adapt_financial_handoff(reversed_source, self.financial_path)["financial_records"]},
                         {r["disclosure_id"] for r in records})
        rows = list(graph.query("""PREFIX esg: <https://example.org/esg/core#>
            SELECT ?reportYear ?period ?page ?factor WHERE {
              ?d esg:disclosureId ?id ; esg:fromReport ?r ; esg:hasMeasurement ?m ; esg:hasEvidence ?e .
              ?r esg:reportYear ?reportYear . ?m esg:hasPeriod ?p ; esg:unitMultiplier ?factor .
              ?p esg:observationYear ?period . ?e esg:sourcePage ?page .
              FILTER(?id = \"EXAMPLE_2025_FS_SEPARATE:REVENUE-2024\")
            }"""))
        self.assertEqual([(int(y), int(p), int(pg), int(f)) for y, p, pg, f in rows], [(2025, 2024, 2, 1000000)])

    def test_consolidated_uses_same_schema_and_distinct_boundary(self):
        separate = adapt_financial_handoff(load(self.financial_path), self.financial_path)["financial_records"]
        consolidated = adapt_financial_handoff(load(self.consolidated_path), self.consolidated_path)["financial_records"]
        validator = Draft202012Validator(load("schemas/financial-candidate-v1.json"))
        graph = new_graph()
        for record in separate + consolidated:
            validator.validate(record)
            add_financial(graph, record)
        self.assertEqual(len(consolidated), 2)
        self.assertEqual({r["scope"]["scope_id"] for r in consolidated}, {"consolidated_group"})
        self.assertEqual({r["scope"]["scope_id"] for r in separate}, {"separate_parent"})
        self.assertTrue({r["source_report_id"] for r in separate}.isdisjoint(
            {r["source_report_id"] for r in consolidated}))
        self.assertTrue({r["disclosure_id"] for r in separate}.isdisjoint(
            {r["disclosure_id"] for r in consolidated}))
        rows = list(graph.query("""PREFIX esg: <https://example.org/esg/core#>
            SELECT ?scope ?year ?page WHERE {
              ?d esg:disclosureId "EXAMPLE_2025_FS_CONSOLIDATED:GROUP-REVENUE-2024" ;
                 esg:fromReport ?report ; esg:hasMeasurement ?m ; esg:hasEvidence ?e .
              ?report esg:reportingEntity ?scope .
              ?m esg:hasPeriod ?period . ?period esg:observationYear ?year .
              ?e esg:sourcePage ?page .
            }"""))
        self.assertEqual([(str(scope), int(year), int(page)) for scope, year, page in rows],
                         [("consolidated_group", 2024, 3)])
        reviewed_group = dict(consolidated[0])
        reviewed_group["scope"] = {**reviewed_group["scope"], "verification_status": "verified"}
        reviewed_group["employee_definition"] = {"verification_status": "verified"}
        reviewed_group["measurement_date"] = {"value": "2025-12-31"}
        esg_context = {"company_id": "EXAMPLE", "reporting_boundary_verified": True,
                       "reporting_boundary": "separate_parent", "observation_year": 2025,
                       "measurement_date": "2025-12-31"}
        self.assertIn("boundary_mismatch", financial_comparability(esg_context, reviewed_group)["reasons"])

    def test_financial_null_and_wrong_boundary_are_handled(self):
        source = load(self.financial_path)
        source["structured_key_metrics"][0]["measurements"][1]["value"] = None
        records = adapt_financial_handoff(source, self.financial_path)["financial_records"]
        prior = next(record for record in records if record["observation_year"] == 2024)
        self.assertIsNone(prior["value"])
        self.assertEqual(prior["value_status"], "missing")
        graph = new_graph()
        add_financial(graph, prior)
        self.assertEqual(list(graph.objects(uri("measurement", prior["disclosure_id"]), ESG.numericValue)), [])
        source["document"]["financial_statement_scope"] = "Consolidated"
        with self.assertRaisesRegex(ValueError, "Separate"):
            adapt_separate_full(source, self.financial_path)

    def test_missing_policy_text_and_unknown_financial_period_stay_in_review(self):
        source = load(self.esg_path)
        policy = source["governance"]["policy"]["records"][0]
        policy.pop("original_text")
        policy.pop("source_pages")
        report = {
            "path": self.esg_path, "handoff_version": source["schema_version"],
            "company_id": "EXAMPLE", "report_id": "EXAMPLE:2025:ESG", "report_year": 2025,
            "report_type": "ESG", "reporting_entity": "unknown", "source_file": "EXAMPLE.pdf",
            "source_file_verified": True, "period_type": "annual", "period_type_verified": True,
        }
        claims = adapt_structured_esg(report, source)
        adapted_policy = next(c for c in claims if c["record_id"] == "EX-ESG-POLICY-2025")
        self.assertIn("original_text_missing", adapted_policy["uncertainty"])
        self.assertIn("source_pages_missing", adapted_policy["uncertainty"])
        self.assertEqual(adapted_policy["evidence"][0]["json_pointer"],
                         "/governance/policy/records/0")
        self.assertFalse(adapted_policy["assessment_eligible"])

        financial_source = load(self.consolidated_path)
        financial_source["structured_key_metrics"][0]["measurements"][1]["period"] = None
        financial_source["structured_key_metrics"][0]["measurements"][1].pop("period_type")
        Draft202012Validator(load("schemas/extract-financial-handoff-v1.json")).validate(financial_source)
        records = adapt_financial_handoff(financial_source, self.consolidated_path)["financial_records"]
        unknown = next(r for r in records if r["source_measurement_id"] == "GROUP-REVENUE-2024")
        Draft202012Validator(load("schemas/financial-candidate-v1.json")).validate(unknown)
        self.assertIsNone(unknown["observation_year"])
        self.assertIsNone(unknown["reporting_period"]["period_type"])
        self.assertIn("measurement_period_unknown", unknown["review_reasons"])
        graph = new_graph()
        add_financial(graph, unknown)
        self.assertEqual(list(graph.objects(uri("financial", unknown["disclosure_id"]), ESG.hasPeriod)), [])
        self.assertIn("measurement_period_unknown",
                      [str(value) for value in graph.objects(uri("financial", unknown["disclosure_id"]), ESG.uncertainty)])

    def test_versioned_source_checks_identity_and_schema(self):
        source = load(self.esg_path)
        manifest = load("docs/examples/manifest.synthetic.json")["files"][0]
        entry = {key: manifest[key] for key in ("company_id", "report_year", "report_type", "reporting_entity")}
        _validate_handoff_source(source, entry, manifest)
        source["document"]["report_year"] = 2024
        with self.assertRaisesRegex(ValueError, "report_year"):
            _validate_handoff_source(source, entry, manifest)
        source["document"].pop("company_id")
        with self.assertRaisesRegex(ValueError, "Extract handoff schema"):
            _validate_handoff_source(source, entry, manifest)

    def test_manifest_selected_examples_run_through_pipeline(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "graph_output"
            summary = build(output, ROOT / "docs/examples/corpus-config.synthetic.json")
            self.assertEqual(summary["claims_accepted"], 5)
            self.assertEqual(summary["claims_rejected"], 0)
            self.assertEqual(summary["financial_records"], 4)
            self.assertEqual(summary["file_errors"], [])
            self.assertEqual(summary["findings_by_status"], {})
            self.assertEqual(summary["shacl_quality"]["structural_violations"], 0)
            self.assertEqual(summary["shacl_business"]["structural_violations"], 0)
            self.assertTrue((output / "graph_demo.html").exists())
            self.assertGreater(len(Graph().parse(output / "graph.ttl", format="turtle")), 0)
            inventory = json.loads((output / "corpus_inventory.json").read_text(encoding="utf-8"))
            self.assertEqual([entry["status"] for entry in inventory["selected"]], ["loaded", "loaded", "loaded"])
            review = json.loads((output / "input_review.json").read_text(encoding="utf-8"))
            unknown = next(item for item in review["review"] if item["record_id"] == "EX-ESG-UNKNOWN-PERIOD")
            self.assertIn("observation_period_unknown", unknown["reasons"])
            financial = json.loads((output / "financial_records.json").read_text(encoding="utf-8"))
            self.assertEqual({record["scope"]["scope_id"] for record in financial},
                             {"separate_parent", "consolidated_group"})
            reconciliation = json.loads((output / "financial_reconciliation.json").read_text(encoding="utf-8"))
            self.assertTrue(all(not item["comparison_permitted"] for item in reconciliation))


if __name__ == "__main__":
    unittest.main()
