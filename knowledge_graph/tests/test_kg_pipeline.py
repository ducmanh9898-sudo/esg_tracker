import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator
from rdflib import Graph, Literal

from kg.adapters import ROOT, adapt_curated, adapt_separate_full, adapt_structured_esg
from kg.assessment_rules import disclosure_gap_findings, temporal_revision_findings
from kg.pipeline import _check_rule_context, _eligible_rule_records, _separate_financial_review, _shacl_report, build, financial_comparability
from kg.rdf_store import ESG, add_assessment, add_claim, add_financial, add_finding, evidence_chain, new_graph, uri
from tools.rule_engine import evaluate


def claim(record_id="A", *, value=None, status="missing", company="FIX", year=2024,
          boundary="parent", verified=False, unit="MWh"):
    return {
        "schema_version": "2.0", "record_id": record_id, "company_id": company,
        "report_id": f"{company}:{year}:ESG", "report_year": year, "report_type": "ESG",
        "reporting_entity": boundary, "observation_year": year, "period_type": "annual",
        "period_type_verified": True,
        "dimension": "E", "claim_type": "measurement", "topic": "energy",
        "metric_id": "energy_use", "metric_definition": "Energy use",
        "value": value, "value_status": status, "unit": unit, "scope": "operations",
        "reporting_boundary": boundary, "reporting_boundary_verified": verified,
        "baseline_id": None, "variant": "reported", "review_status": "unreviewed",
        "uncertainty": [], "evidence": [{"evidence_id": "E-" + record_id,
            "source_file": f"{company}_{year}.pdf", "source_pages": [4],
            "json_pointer": "/environment/energy/use/value", "original_text": None,
            "ocr_limitations": []}],
    }


class GraphPipelineTests(unittest.TestCase):
    def test_primary_outputs_exclude_demo_but_preserve_audit(self):
        """Synthetic handoff proves separation across JSON, RDF, assessments and UI."""
        fixture_id = "EX-ESG-ENERGY-2025"
        demo = {"finding_id": "FND-DEMO-SYNTHETIC", "rule_id": "R04",
                "rule_name": "Synthetic demo check", "status": "Supported",
                "company_id": "EXAMPLE", "summary": "Synthetic demo passed",
                "input_claim_ids": [fixture_id]}
        ready = {"finding_id": "FND-READY-SYNTHETIC", "rule_id": "KG-E-01",
                 "rule_name": "Synthetic ready check", "status": "NeedsReview",
                 "company_id": "EXAMPLE", "summary": "Synthetic mapping unverified",
                 "input_claim_ids": [fixture_id], "topic": "energy"}
        event = {"evaluation_id": "EVAL-SYNTHETIC", "rule_id": "KG-E-01",
                 "rule_version": "1.0", "company_id": "EXAMPLE",
                 "report_id": "EXAMPLE:2025:ESG", "report_year": 2025,
                 "observation_year": 2025, "input_claim_ids": [fixture_id],
                 "candidate_count": 1, "outcome": "NeedsReview",
                 "reasons": ["mapping_unverified"], "missing_inputs": [],
                 "finding_id": ready["finding_id"]}
        config = json.loads((ROOT / "docs/examples/corpus-config.synthetic.json").read_text(encoding="utf-8"))
        config["rule_sets"] = {"EXAMPLE": "data/config/rules.json"}
        config["ready_rule_aliases"] = "data/config/ready_rule_aliases.json"
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "corpus.synthetic.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            output = Path(temp) / "output"
            with patch("kg.pipeline.evaluate", return_value=[demo]), patch(
                "kg.pipeline.evaluate_ready_rules", return_value=([ready], [event])
            ):
                summary = build(output, config_path)
            load = lambda name: json.loads((output / name).read_text(encoding="utf-8"))
            self.assertEqual(load("findings.json"), [ready])
            self.assertEqual(load("ready_findings.json"), [ready])
            self.assertEqual(load("demo_findings.json"), [demo])
            self.assertEqual(len(load("rule_evaluations.json")), 1)
            self.assertEqual({a["finding_id"] for a in load("claim_assessments.json")}, {ready["finding_id"]})
            company = load("company_assessments.json")["company_multiyear_assessments"][0]
            self.assertEqual(company["finding_ids"], [ready["finding_id"]])
            self.assertEqual(company["coverage"]["needs_review_claim_count"], 1)
            self.assertEqual(company["coverage"]["strong_conclusion_claim_count"], 0)
            self.assertEqual(summary["claims_in_primary_findings"], 1)
            self.assertEqual(summary["claims_with_needs_review_findings"], 1)
            self.assertEqual(summary["claims_with_strong_conclusions"], 0)
            self.assertEqual(summary["findings_by_status"], {"NeedsReview": 1})
            self.assertEqual(summary["demo_findings_audit_by_status"], {"Supported": 1})
            rdf = Graph().parse(output / "graph.ttl", format="turtle")
            self.assertEqual({str(x) for x in rdf.objects(None, ESG.findingId)}, {ready["finding_id"]})
            self.assertEqual({row[0] for row in evidence_chain(rdf)}, {ready["finding_id"]})
            rendered = (output / "graph_demo.html").read_text(encoding="utf-8")
            self.assertIn("Đối soát demo — chỉ để audit", rendered)
            self.assertIn(demo["finding_id"], rendered)
            payload = json.loads(rendered.split("const DATA=", 1)[1].split(";\nconst nodes", 1)[0])
            self.assertEqual(payload["findings"], [ready])
            self.assertEqual(payload["demo_findings"], [demo])

    def test_null_and_not_applicable_validate_without_fake_numeric_literal(self):
        schema = json.loads((ROOT / "schemas" / "graph-input-v2.json").read_text(encoding="utf-8"))
        for status in ("missing", "not_applicable", "unknown"):
            item = claim(status=status)
            self.assertEqual(list(Draft202012Validator(schema).iter_errors(item)), [])
            g = new_graph()
            add_claim(g, item)
            self.assertEqual(list(g.objects(uri("measurement", "A"), ESG.numericValue)), [])
            self.assertEqual(_shacl_report(g)["structural_violations"], 0)
        self.assertEqual(_eligible_rule_records([claim(status="not_applicable")]), [])

    def test_disclosure_gap_requires_verified_applicability_and_search(self):
        item = claim(status="missing")
        profile = {"required_disclosures": [{"rule_id": "D1", "metric_id": "energy_use",
                    "applicability_status": "verified", "source_basis": "reviewed fixture requirement"}]}
        partial = [{"company_id": "FIX", "report_year": 2024, "coverage": "partial"}]
        self.assertEqual(disclosure_gap_findings([item], profile, partial), [])
        complete = [{"company_id": "FIX", "report_year": 2024, "coverage": "verified_complete"}]
        self.assertEqual(disclosure_gap_findings([item], profile, complete)[0]["status"], "DisclosureGap")
        profile["required_disclosures"][0]["applicability_status"] = "unverified"
        self.assertEqual(disclosure_gap_findings([item], profile, complete), [])

    def test_temporal_inconsistency_requires_same_period_review_and_no_restatement(self):
        earlier = claim("A", value=10, status="available", year=2023, verified=True)
        later = claim("B", value=20, status="available", year=2024, verified=True)
        later["observation_year"] = 2023
        later["variant"] = "comparative"
        for item in (earlier, later):
            item["review_status"] = "reviewed"
            item["evidence"][0]["original_text"] = "Reviewed PDF text"
        later["restatement_status"] = "not_restatement"
        profile = {"temporal_revision_rules": [{"rule_id": "T1", "metric_id": "energy_use",
                    "tolerance": 0, "source_basis": "reviewed fixture arithmetic"}]}
        self.assertEqual(temporal_revision_findings([earlier, later], profile)[0]["status"], "TemporalInconsistency")
        later["restatement_status"] = "restated"
        self.assertEqual(temporal_revision_findings([earlier, later], profile), [])
        later["restatement_status"] = "not_restatement"
        later["reporting_boundary_verified"] = False
        self.assertEqual(temporal_revision_findings([earlier, later], profile), [])

    def test_sparql_finding_chain_preserves_report_and_source(self):
        item = claim(value=12, status="available")
        g = new_graph()
        add_claim(g, item)
        add_finding(g, {"finding_id": "F-1", "rule_id": "R-1", "status": "Supported",
                        "summary": "A checked rule passed", "input_claim_ids": ["A"]})
        rows = evidence_chain(g)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1:4], ("A", "E-A", "FIX_2024.pdf"))
        self.assertEqual(rows[0][5], "FIX:2024:ESG")

    def test_company_assessment_traces_to_finding_and_claim_in_rdf(self):
        g = new_graph()
        add_claim(g, claim(value=12, status="available"))
        add_finding(g, {"finding_id": "F-1", "rule_id": "R-1", "status": "Supported",
                        "summary": "Checked", "input_claim_ids": ["A"]})
        add_assessment(g, {"assessment_id": "COA-FIX", "assessment_level": "company_multiyear",
                           "company_id": "FIX", "finding_ids": ["F-1"], "finding_count": 1,
                           "coverage": {"claim_count": 1, "assessed_claim_count": 1}})
        query = """PREFIX esg: <https://example.org/esg/core#>
        SELECT ?id WHERE { ?company esg:companyId "FIX" ; esg:hasAssessment ?a .
          ?a esg:summarizesFinding ?f . ?f esg:inputClaim ?c . ?c esg:recordId ?id . }"""
        self.assertEqual([str(row.id) for row in g.query(query)], ["A"])

    def test_business_shacl_guard_is_separate_from_structure(self):
        item = claim(value=12, status="available", verified=False)
        g = new_graph()
        add_claim(g, item)
        add_finding(g, {"finding_id": "F-2", "rule_id": "R-2", "status": "Contradicted",
                        "summary": "synthetic", "input_claim_ids": ["A"]})
        self.assertEqual(_shacl_report(g)["structural_violations"], 0)
        self.assertEqual(_shacl_report(g, "kg/business_shapes.ttl")["structural_violations"], 1)

    def test_separate_financial_null_and_scope_difference_need_review(self):
        path = ROOT / "tests" / "fixtures" / "bsr_separate_full.synthetic.json"
        source = json.loads(path.read_text(encoding="utf-8"))
        source["document"]["source_file"] = "synthetic_fixture.pdf"
        source["document"]["report_year"] = 2025
        source["document"]["company_id"] = "BSR"
        source["structured_key_metrics"][0]["value"] = None
        source["structured_key_metrics"][0]["metric_id"] = "FIN_REVENUE"
        candidate = adapt_separate_full(source, path.name)["financial_records"][0]
        self.assertEqual(candidate["value_status"], "missing")
        g = new_graph()
        add_financial(g, candidate)
        self.assertEqual(list(g.objects(uri("measurement", candidate["disclosure_id"]), ESG.numericValue)), [])
        self.assertEqual(_shacl_report(g)["structural_violations"], 0)
        candidate["value"] = 100
        peer = {"record_type": "financial_disclosure", "disclosure_id": "PEER",
                "company_id": candidate["company_id"], "report_year": candidate["observation_year"],
                "item": {"item_id": "financial.financial_context.revenue"}, "value": 101,
                "scope": {"scope_id": "consolidated_group"}}
        review = _separate_financial_review([candidate, peer])
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]["status"], "NeedsReview")
        self.assertFalse(review[0]["comparison_permitted"])

    def test_missing_peer_and_unverified_context_never_contradict(self):
        old = claim("A", value=10, status="available")
        new = claim("B", value=20, status="available")
        legacy = [{**c, "claim_id": c["record_id"]} for c in (old, new)]
        rule = {"id": "X", "name": "same value", "kind": "same_report_conflict",
                "metrics": ["energy_use"], "unit": "MWh", "tolerance": 0,
                "failure": "Contradicted", "basis": "fixture arithmetic", "guard": "same context"}
        self.assertEqual(evaluate(legacy[:1], [rule]), [])
        finding = evaluate(legacy, [rule])[0]
        self.assertEqual(finding["status"], "NeedsReview")
        old["reporting_boundary_verified"] = new["reporting_boundary_verified"] = True
        for item in (old, new):
            item["review_status"] = "reviewed"
            item["evidence"][0]["original_text"] = "Reviewed PDF text"
        legacy = [{**c, "claim_id": c["record_id"]} for c in (old, new)]
        finding = evaluate(legacy, [rule])[0]
        self.assertEqual(_check_rule_context(finding, {"A": old, "B": new})["status"], "Contradicted")
        new["unit"] = "GJ"
        self.assertEqual(_check_rule_context(finding, {"A": old, "B": new})["status"], "NeedsReview")

    def test_prior_year_measurement_keeps_source_report(self):
        item = claim(year=2025, value=11, status="available")
        item["observation_year"] = 2024
        g = new_graph()
        add_claim(g, item)
        self.assertIn(Literal(2024), list(g.objects(None, ESG.observationYear)))
        self.assertEqual(str(g.value(uri("report", "FIX:2025:ESG"), ESG.reportId)), "FIX:2025:ESG")

    def test_comparative_stays_in_containing_report(self):
        source = {"environment": {"energy": {"metric": "energy use", "value": 12,
                  "comparison_value": 11, "comparison_year": 2024, "unit": "MWh",
                  "source_pages": [4]}}}
        report = {"company_id": "PLX", "report_year": 2025, "report_type": "ESG",
                  "reporting_entity": "unknown", "report_id": "PLX:2025:ESG",
                  "path": "data/extract/esg/PLX_2025_esg.json", "source_file": "PLX_2025.pdf"}
        rows = adapt_structured_esg(report, source)
        comparison = next(c for c in rows if c["evidence"][0]["json_pointer"].endswith("/comparison_value")
                          and c["observation_year"] == 2024)
        self.assertEqual(comparison["report_year"], 2025)
        self.assertEqual(comparison["report_id"], "PLX:2025:ESG")
        self.assertEqual(comparison["evidence"][0]["source_extract_path"], "data/extract/esg/PLX_2025_esg.json")
        self.assertEqual(comparison["variant"], "comparative")

    def test_actual_pvd_prior_year_key_keeps_containing_report(self):
        source = json.loads((ROOT / "data" / "extract" / "esg" / "PVD_2023_esg_101_120.json").read_text(encoding="utf-8-sig"))
        report = {"company_id": "PVD", "report_year": 2023, "report_type": "ESG",
                  "reporting_entity": "unknown", "report_id": "PVD:2023:ESG",
                  "path": "data/extract/esg/PVD_2023_esg_101_120.json", "source_file": "PVD_2023.pdf"}
        rows = adapt_structured_esg(report, source)
        earlier = next(c for c in rows if c["evidence"][0]["json_pointer"] == "/environment/energy/electricity_kwh/2022")
        self.assertEqual(earlier["observation_year"], 2022)
        self.assertEqual(earlier["report_year"], 2023)
        self.assertEqual(earlier["report_id"], "PVD:2023:ESG")

    def test_curated_bsr_ids_remain_compatible_with_handoff(self):
        from tools.normalizer import stable_id
        selection = json.loads((ROOT / "data" / "config" / "selection.json").read_text(encoding="utf-8"))
        source = json.loads((ROOT / "data" / "extract" / "esg" / "BSR_2023_esg.json").read_text(encoding="utf-8-sig"))
        report = {"company_id": "BSR", "report_year": 2023, "report_type": "ESG",
                  "reporting_entity": "unknown", "report_id": "BSR:2023:ESG",
                  "path": "data/extract/esg/BSR_2023_esg.json", "source_file": "BSR_2023.pdf"}
        rows = adapt_curated(report, source, selection)
        self.assertEqual(rows[0]["record_id"], stable_id(selection[0]))

    def test_separate_full_is_candidate_only_with_discrepancy_and_ocr(self):
        path = ROOT / "tests" / "fixtures" / "bsr_separate_full.synthetic.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = adapt_separate_full(raw, path)
        self.assertEqual(result["claim_count_difference"], 2)
        self.assertEqual(result["records"][0]["review_status"], "unreviewed")
        self.assertEqual(result["records"][0]["confidence"], 0.7)
        self.assertEqual(result["records"][0]["extraction_notes"], "OCR candidate")
        self.assertEqual(result["records"][0]["source_dimension"], "X")
        self.assertEqual(result["records"][0]["graph_dimension"], "financial_context")
        self.assertTrue(result["ocr_pages"][0]["ocr_unverified"])
        self.assertEqual(result["unmapped_numeric_occurrences"], 1)

    def test_real_separate_financial_candidates_keep_comparative_source(self):
        path = ROOT / "data" / "extract" / "financial" / "BSR_2025_BCTC_rieng_full.json"
        source = json.loads(path.read_text(encoding="utf-8"))
        result = adapt_separate_full(source, path.name)
        self.assertEqual(result["actual_candidate_count"], 4)
        self.assertEqual(result["claim_count_difference"], -1)
        self.assertEqual(len(result["financial_records"]), 8)
        self.assertEqual(result["unmapped_monetary_groups"], 489)
        self.assertEqual(result["unmapped_numeric_occurrences"], 1615)
        self.assertEqual(len(result["ocr_pages"]), 44)
        prior = next(r for r in result["financial_records"]
                     if r["item"]["item_id"] == "FIN_REVENUE" and r["observation_year"] == 2024)
        self.assertEqual(prior["report_year"], 2025)
        self.assertEqual(prior["source_record_id"], "BSR-FS-2025-00003")
        self.assertEqual(prior["review_status"], "unreviewed")
        self.assertEqual(prior["scope"]["scope_id"], "separate_parent")
        self.assertEqual(prior["value"], 122986399077561)
        self.assertEqual(prior["source_pages"], [11])
        g = new_graph()
        add_financial(g, prior)
        query = """PREFIX esg: <https://example.org/esg/core#>
        SELECT ?reportId ?year ?page WHERE {
          ?d esg:disclosureId ?id ; esg:fromReport ?report ; esg:hasMeasurement ?m ; esg:hasEvidence ?e .
          FILTER(STRSTARTS(STR(?id), "BSR-FS-2025-00003:2024"))
          ?m esg:hasPeriod ?p . ?p esg:observationYear ?year .
          ?report esg:reportId ?reportId . ?e esg:sourcePage ?page .
        }"""
        rows = list(g.query(query))
        self.assertEqual([(str(r.reportId), int(r.year), int(r.page)) for r in rows],
                         [("BSR_2025_FS:Separate", 2024, 11)])
        self.assertEqual(_shacl_report(g)["structural_violations"], 0)

    def test_separate_and_consolidated_are_not_compared_without_matching_context(self):
        item = claim("WORK", value=1594, status="available", company="BSR", year=2025)
        record = {"company_id": "BSR", "observation_year": 2025,
                  "scope": {"scope_id": "consolidated_group", "verification_status": "verified"},
                  "measurement_date": {"value": "2025-12-31"},
                  "employee_definition": {"verification_status": "unverified"}}
        result = financial_comparability(item, record)
        self.assertFalse(result["comparable"])
        self.assertIn("boundary_unverified", result["reasons"])
        item["reporting_boundary_verified"] = True
        item["reporting_boundary"] = "separate_parent"
        self.assertIn("boundary_mismatch", financial_comparability(item, record)["reasons"])

    def test_other_company_other_profile_same_core(self):
        config = {
            "industry_profile": "tests/fixtures/other_industry_profile.json",
            "reports": [{"company_id": "FIX", "report_year": 2024, "report_type": "ESG",
                         "reporting_entity": "unknown", "path": "tests/fixtures/other_company_esg.json",
                         "adapter": "structured_esg", "coverage": "fixture_only", "reason": "test"}],
            "selection_files": {}, "rule_sets": {}, "unresolved": [],
        }
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            out = Path(temp) / "out"
            summary = build(out, config_path)
            self.assertEqual(summary["companies"], {"FIX": 1})
            self.assertEqual(summary["claims_rule_assessed"], 0)
            self.assertEqual(summary["claims_unassessed"], 1)
            self.assertTrue((out / "graph.ttl").exists())

    def test_bad_json_is_reported_while_good_file_continues(self):
        config = {
            "industry_profile": "tests/fixtures/other_industry_profile.json",
            "reports": [
                {"company_id": "BAD", "report_year": 2024, "report_type": "ESG",
                 "reporting_entity": "unknown", "path": "tests/fixtures/malformed_extract.synthetic.json",
                 "adapter": "structured_esg", "coverage": "fixture_only", "reason": "test"},
                {"company_id": "FIX", "report_year": 2024, "report_type": "ESG",
                 "reporting_entity": "unknown", "path": "tests/fixtures/other_company_esg.json",
                 "adapter": "structured_esg", "coverage": "fixture_only", "reason": "test"},
            ], "selection_files": {}, "rule_sets": {}, "unresolved": [],
        }
        with tempfile.TemporaryDirectory() as temp:
            config_path = Path(temp) / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            result = build(Path(temp) / "out", config_path)
            self.assertEqual(result["companies"], {"FIX": 1})
            self.assertEqual(result["file_errors"][0]["error_type"], "JSONDecodeError")


if __name__ == "__main__":
    unittest.main()
