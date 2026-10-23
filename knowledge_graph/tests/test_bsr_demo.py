"""Integration checks for the isolated real-data BSR demo and its review limits."""
import json
import copy
import tempfile
import unittest
from pathlib import Path

from tools.bsr_demo import ROOT, run
from kg.source_corroboration import attach_corroborated_evidence
from kg.review_annotations import apply_review_annotations
from kg.ready_rules import evaluate_ready_rules
from kg.rdf_store import ESG, uri
from rdflib import Graph


class BsrDemoTests(unittest.TestCase):
    def test_real_bsr_demo_matches_pre_authored_cases_and_preserves_review_gates(self):
        with tempfile.TemporaryDirectory(prefix="bsr_demo_test_") as temp:
            output = Path(temp)
            acceptance = run(output)
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            audit = json.loads((output / "annotation_audit.json").read_text(encoding="utf-8"))
            evaluations = json.loads((output / "rule_evaluations.json").read_text(encoding="utf-8"))
            findings = json.loads((output / "findings.json").read_text(encoding="utf-8"))
            html = (output / "index.html").read_text(encoding="utf-8")

            self.assertTrue(acceptance["technical_demo_pass"])
            self.assertEqual(acceptance["evidence_acceptance"], "pending_human_adjudication")
            self.assertEqual(summary["companies"], {"BSR": 30})
            self.assertEqual(summary["financial_records"], 76)
            self.assertEqual(summary["standard_candidate_links"], 60)
            self.assertEqual(summary["financial_candidate_links"], 6)
            projection = json.loads((output / "graph.json").read_text(encoding="utf-8"))
            self.assertEqual(sum(node["type"] == "StandardCandidate" for node in projection["nodes"]), 60)
            self.assertEqual(sum(node["type"] == "FinancialComparisonCandidate" for node in projection["nodes"]), 6)
            self.assertTrue(all(node["verificationStatus"] == "unverified_candidate"
                                for node in projection["nodes"] if node["type"] == "StandardCandidate"))
            self.assertTrue(all(node["comparable"] is False for node in projection["nodes"]
                                if node["type"] == "FinancialComparisonCandidate"))
            rdf = Graph().parse(output / "graph.ttl", format="turtle")
            self.assertEqual(len(list(rdf.objects(uri("claim", "CLM-08082F5B81CD"),
                                                   ESG.hasStandardCandidate))), 2)
            self.assertEqual(len(list(rdf.objects(uri("claim", "CLM-08082F5B81CD"),
                                                   ESG.hasFinancialCandidate))), 3)
            financial_candidates = json.loads((output / "financial_candidates.json").read_text(encoding="utf-8"))
            claim_review = json.loads((output / "claim_review.json").read_text(encoding="utf-8"))
            self.assertEqual(len(claim_review["claims"]), 30)
            self.assertEqual(len({row["claim_id"] for row in claim_review["claims"]}), 30)
            self.assertEqual(claim_review["counts"], {"NotEvaluated": 19, "Skipped": 5,
                                                      "NeedsReview": 4, "Supported": 2})
            self.assertEqual(sum(row["reader_triage"] == "requires_review" for row in claim_review["claims"]), 28)
            self.assertFalse(acceptance["claim_review_coverage"]["all_claims_conclusively_assessed"])
            self.assertFalse(acceptance["claim_review_coverage"]["standards_compliance_assessed"])
            self.assertEqual(acceptance["claim_review_coverage"]["financial_comparisons_permitted"], 0)
            self.assertTrue(all(row["standards"]["reference_candidates"] for row in claim_review["claims"]))
            self.assertTrue(all(row["standards"]["compliance_status"] == "not_assessed" for row in claim_review["claims"]))
            self.assertEqual(sum(len(row["financial"]["candidates"]) for row in claim_review["claims"]), 6)
            self.assertTrue(all(not link["comparable"] for row in claim_review["claims"]
                                for link in row["financial"]["candidates"]))
            self.assertTrue(any(row["screening_signals"] for row in claim_review["claims"]))
            self.assertTrue(any(row["cross_year_candidates"] for row in claim_review["claims"]))
            locator_issue = next(row["source_locator_issue"] for row in claim_review["claims"]
                                 if row["claim_id"] == "CLM-464119395EB9")
            self.assertEqual(locator_issue["extract_source_pages"], [31, 65])
            self.assertEqual(locator_issue["archived_text_page_with_value"], 66)
            self.assertEqual(locator_issue["official_pdf_physical_page_with_value"], 130)
            standard_issue = next(row["standard_reference_issue"] for row in claim_review["claims"]
                                  if row["claim_id"] == "CLM-08082F5B81CD")
            self.assertEqual(standard_issue["source_reported_reference"], "GRI 401-1")
            self.assertEqual(standard_issue["potentially_relevant_reference"], "GRI 2-7")
            workforce_link = next(row for row in financial_candidates
                                  if row["claim_id"] == "CLM-08082F5B81CD"
                                  and row["financial_disclosure_id"] == "FIN-BSR-BCTC-2025-workforce.total")
            self.assertFalse(workforce_link["comparable"])
            self.assertIn("boundary_unverified", workforce_link["reasons"])
            self.assertEqual(summary["risk_score"], None)
            self.assertEqual(summary["missing_evidence_chains"], [])
            self.assertEqual(audit["counts"], {"applied": 20, "pending": 11, "rejected": 0, "file_errors": 0})
            self.assertEqual(len(audit["partial_applied"]), 2)
            self.assertEqual({tuple(row["fields"]) for row in audit["partial_applied"]},
                             {("comparison_frame_id", "population_id")})
            provenance = json.loads((output / "source_provenance_audit.json").read_text(encoding="utf-8"))
            chains = json.loads((output / "evidence_chain_sources.json").read_text(encoding="utf-8"))
            self.assertEqual(len(provenance["sources"]), 4)
            self.assertEqual(len(provenance["validated_page_crosswalk"]), 6)
            self.assertEqual(len(provenance["attached_evidence"]), 11)
            self.assertEqual({row["official_page"] for row in provenance["attached_evidence"]
                              if row["review_scope"] == "value_unit_source_declared_gri_code_and_label_only"}, {129})
            self.assertFalse(provenance["declared_pdf_binary_available"])
            self.assertFalse(provenance["whole_document_equivalence_verified"])
            self.assertEqual(len([row for row in chains if row.get("source_id") == "SRC-BSR-2025-OFFICIAL-PDF-134"]), 4)
            self.assertEqual(acceptance["review_packet"]["cases"], 3)
            self.assertTrue((output / "review_packet.md").is_file())
            self.assertTrue((output / "review_packet.html").is_file())
            self.assertTrue(all((output / relative).is_file() for relative in acceptance["review_packet"]["page_images"]))
            self.assertEqual({(r["rule_id"], r["outcome"]) for r in evaluations if r["report_year"] == 2025},
                             {("KG-E-01", "Skipped"), ("KG-S-01", "NeedsReview"), ("KG-G-01", "Supported")})
            self.assertEqual({r["status"] for r in findings}, {"NeedsReview", "Supported"})
            self.assertEqual(len(findings), 3)
            g = next(r for r in evaluations if r["report_year"] == 2025 and r["rule_id"] == "KG-G-01")
            self.assertEqual(g["calculation"]["comparison"], "subset <= total")
            self.assertEqual(g["reasons"], ["subset_within_total"])
            annotations = json.loads((ROOT / "data/review/bsr_demo_annotations.json").read_text(encoding="utf-8"))
            g_context = [row for row in annotations["context_reviews"]
                         if row["record_id"] in {"CLM-936FE665DA79", "CLM-ECD3B116A03A"}]
            self.assertEqual({row["status"] for row in g_context}, {"verified"})
            self.assertEqual(len({row["fields"]["comparison_frame_id"] for row in g_context}), 1)
            self.assertTrue(all(row["fields"]["measurement_date"] is None for row in g_context))
            self.assertIn("ISSUE-BSR-S-2025-GENDER-GAP-27",
                          (ROOT / "data/review/bsr_2025_s_gender_gap.issue.json").read_text(encoding="utf-8"))
            self.assertIn("Tổng số lao động Người 1.532 1.544 1.594", html)
            self.assertIn("Phát thải khí nhà kính Scope 1 tCO2e 1.780.388", html)
            self.assertIn("Báo cáo Phát triển Bền vững BSR 2025", html)
            self.assertIn("PDF vật lý 76", html)
            self.assertIn("Quy mô lao động và ổn định nhân sự", html)
            self.assertIn("Liên hệ với báo cáo tài chính", html)
            self.assertIn('id="graph"', html)
            self.assertIn('id="claims"', html)
            self.assertEqual(html.count('<tr class="claim-row"'), 30)
            self.assertEqual(html.count('<span class="claim-source corroborated">'), 11)
            self.assertIn("Đang hiển thị 30/30 claim", html)
            self.assertIn("2024 · số liệu 2023", html)
            self.assertIn("Cần xác minh thêm", html)
            self.assertIn("GRI / tiêu chuẩn", html)
            self.assertIn("BCTC / IFRS S1", html)
            self.assertIn("IFRS S1 §20–22", html)
            self.assertIn("GRI 306-3", html)
            self.assertIn("Locator Extract lệch trang", html)
            self.assertIn("Mã GRI BSR tự ghi cần review", html)
            self.assertIn("Liên kết qua các năm", html)
            self.assertEqual(html.count('<div class="kg-panel" data-graph-panel="'), 4)
            self.assertIn('data-graph-tab="F"', html)
            self.assertIn('aria-label="Đồ thị bằng chứng Khí thải nhà kính', html)
            self.assertIn('data-title="Nguồn đã đối chiếu"', html)
            self.assertIn('data-title="Nguồn BCTC"', html)
            self.assertIn('PDF BCTC không có trong workspace', html)
            self.assertIn("1.946 người", html)
            self.assertIn("1.594 người", html)
            self.assertIn("Chênh lệch quan sát được là 352 người", html)
            self.assertIn("Chưa đủ điều kiện so sánh", html)
            self.assertIn("BCTC_BSR_2025.pdf", html)
            self.assertIn("PDF BCTC không có trong workspace", html)
            self.assertIn("Cần kiểm tra thêm", html)
            self.assertIn("Phù hợp với phép kiểm tra", html)
            self.assertIn("Chưa thể kiểm tra", html)
            self.assertIn("BSR_2025_official.pdf", html)
            self.assertNotIn('href="../', html)
            self.assertNotIn('.pdf#page=', html)
            self.assertNotIn('href="review_packet.html"', html)
            self.assertEqual(html, (output / "graph_demo.html").read_text(encoding="utf-8"))
            self.assertTrue((ROOT / "data/source/pdf/BSR_2025_official.pdf").is_file())

    def test_corroboration_rejects_changed_hash_and_official_quote_without_mutating_claims(self):
        with tempfile.TemporaryDirectory(prefix="bsr_evidence_test_") as temp:
            output = Path(temp)
            run(output)
            claims = json.loads((output / "normalized_claims.json").read_text(encoding="utf-8"))
            aliases = json.loads((ROOT / "data/config/ready_rule_aliases.json").read_text(encoding="utf-8"))
            claims, _, _ = apply_review_annotations(
                claims, aliases, ROOT / "data/review/bsr_demo_annotations.json", ROOT)
            original = copy.deepcopy(claims)
            provenance_path = ROOT / "data/review/bsr_2025_provenance.json"
            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["sources"][2]["sha256"] = "0" * 64
            tampered = output / "tampered_provenance.json"
            tampered.write_text(json.dumps(provenance, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source_missing_or_hash_mismatch"):
                attach_corroborated_evidence(claims, tampered, ROOT)
            self.assertEqual(claims, original)

            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["official_evidence"][0]["display_value"] = "9.999.999"
            tampered.write_text(json.dumps(provenance, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "supplement_official_quote_mismatch"):
                attach_corroborated_evidence(claims, tampered, ROOT)
            self.assertEqual(claims, original)

            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            provenance["official_evidence"][0]["official_page"] = 130
            tampered.write_text(json.dumps(provenance, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "supplement_extract_locator_mismatch"):
                attach_corroborated_evidence(claims, tampered, ROOT)
            self.assertEqual(claims, original)

            provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
            recycled = next(row for row in provenance["official_evidence"]
                            if row["claim_id"] == "CLM-DE43C371814E")
            recycled["display_value"] = "3.171,3"
            tampered.write_text(json.dumps(provenance, ensure_ascii=False), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "supplement_claim_value_mismatch"):
                attach_corroborated_evidence(claims, tampered, ROOT)
            self.assertEqual(claims, original)

            annotations = json.loads((ROOT / "data/review/bsr_demo_annotations.json").read_text(encoding="utf-8"))
            g_context = next(row for row in annotations["context_reviews"]
                             if row["record_id"] == "CLM-936FE665DA79")
            g_context["frame_source"]["quote"] = "Ambiguous board statement without the subset phrase"
            bad_annotations = output / "tampered_annotations.json"
            bad_annotations.write_text(json.dumps(annotations, ensure_ascii=False), encoding="utf-8")
            raw_claims = json.loads((output / "normalized_claims.json").read_text(encoding="utf-8"))
            reviewed, scoped_aliases, audit = apply_review_annotations(
                raw_claims, aliases, bad_annotations, ROOT)
            self.assertTrue(any(row.get("annotation_id") == g_context["annotation_id"]
                                for row in audit["rejected"]))
            g_event = next(row for row in evaluate_ready_rules(reviewed, scoped_aliases)[1]
                           if row["rule_id"] == "KG-G-01" and row["report_year"] == 2025)
            self.assertEqual(g_event["outcome"], "NeedsReview")
            self.assertIn("graph_context_review_missing", g_event["reasons"])

            annotations = json.loads((ROOT / "data/review/bsr_demo_annotations.json").read_text(encoding="utf-8"))
            s_context = next(row for row in annotations["context_reviews"]
                             if row["record_id"] == "CLM-08082F5B81CD")
            s_context["frame_source"]["quote"] = "Unrelated workforce excerpt"
            bad_annotations.write_text(json.dumps(annotations, ensure_ascii=False), encoding="utf-8")
            reviewed, scoped_aliases, audit = apply_review_annotations(
                raw_claims, aliases, bad_annotations, ROOT)
            self.assertFalse(any(row["record_id"] == "CLM-08082F5B81CD"
                                 for row in audit["partial_applied"]))
            s_event = next(row for row in evaluate_ready_rules(reviewed, scoped_aliases)[1]
                           if row["rule_id"] == "KG-S-01" and row["report_year"] == 2025)
            self.assertEqual(s_event["outcome"], "NeedsReview")
            self.assertIn("comparison_frame_unknown", s_event["reasons"])


if __name__ == "__main__":
    unittest.main()
