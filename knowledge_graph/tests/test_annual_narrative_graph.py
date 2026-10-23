import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

import fitz

from kg.annual_narrative_graph import attach
from kg.rdf_store import ESG, new_graph, project_json, uri


class AnnualNarrativeGraphTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pdf_path = Path(self.tmp.name) / "annual.pdf"
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((40, 40), "Board approved the environmental policy for 2024.")
        pdf.save(self.pdf_path)
        pdf.close()
        self.text = fitz.open(self.pdf_path)[0].get_text()
        self.sha = hashlib.sha256(self.pdf_path.read_bytes()).hexdigest()
        self.claims = [{"record_id": "ESG-1", "input_digest": "digest-1", "report_year": 2024,
                        "company_id": "DEMO", "source_document_type": "sustainability_report",
                        "claim_type": "policy", "raw_record": {"statement": {
                            "original_quote": "Board approved the environmental policy for 2024."}}}]
        self.sources = [{"source_id": "ANNUAL-1", "sha256": self.sha,
                         "path": str(self.pdf_path)}]
        self.case = {"candidate_id": "NAR-1", "relation": "exact_normalized_text_overlap",
                     "assessment_status": "review_only_not_graph_verdict", "decision": "pending",
                     "esg_record_id": "ESG-1", "esg_input_digest": "digest-1", "company_id": "DEMO",
                     "annual_report_year": 2024, "annual_source_id": "ANNUAL-1",
                     "annual_source_sha256": self.sha, "annual_pdf_path": str(self.pdf_path),
                     "annual_physical_page": 1, "annual_char_start": 0,
                     "annual_char_end": len(self.text), "annual_exact_quote": self.text}

    def proposals(self, cases=None):
        return {"schema_version": "annual-narrative-review-1.0",
                "cases": cases if cases is not None else [self.case]}

    def test_attaches_review_only_source_located_node(self):
        graph = new_graph()
        self.assertEqual(attach(graph, self.proposals(), self.claims, self.sources), 1)
        self.assertIn((uri("narrative-candidate", "NAR-1"), ESG.inputClaim,
                       uri("claim", "ESG-1")), graph)
        self.assertEqual([str(value) for value in graph.objects(uri("narrative-candidate", "NAR-1"), ESG.status)],
                         ["NeedsReview"])
        self.assertTrue(any(node["id"] == "narrative-candidate:NAR-1"
                            for node in project_json(graph)["nodes"]))

    def test_rejects_wrong_source_hash_and_quote_span(self):
        bad = copy.deepcopy(self.case)
        bad["annual_source_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "narrative_annual_source_mismatch"):
            attach(new_graph(), self.proposals([bad]), self.claims, self.sources)
        bad = copy.deepcopy(self.case)
        bad["annual_char_start"] = 1
        with self.assertRaisesRegex(ValueError, "narrative_quote_span_mismatch"):
            attach(new_graph(), self.proposals([bad]), self.claims, self.sources)

    def test_rejects_duplicate_id_and_unreviewed_semantics(self):
        with self.assertRaisesRegex(ValueError, "duplicate_narrative_candidate_id"):
            attach(new_graph(), self.proposals([self.case, self.case]), self.claims, self.sources)
        bad = copy.deepcopy(self.case)
        bad["decision"] = "accept"
        with self.assertRaisesRegex(ValueError, "narrative_candidate_not_pending"):
            attach(new_graph(), self.proposals([bad]), self.claims, self.sources)


if __name__ == "__main__":
    unittest.main()
