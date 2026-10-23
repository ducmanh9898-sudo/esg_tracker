import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.provenance_enricher import enrich_claims


def _fixture_claim(*, pages=None, pointer="/metric/value", value=42):
    return {
        "schema_version": "1.0",
        "claim_id": "CLM-FIXTURE",
        "selection_id": "C-FIXTURE",
        "company_id": "BSR",
        "report_year": 2025,
        "observation_year": 2025,
        "dimension": "E",
        "topic": "test",
        "claim_type": "reported_measurement",
        "metric_id": "fixture_metric",
        "label": "Fixture metric",
        "value": value,
        "unit": "unit",
        "scope": "fixture",
        "evidence": [{
            "evidence_id": "EVD-FIXTURE",
            "source_file": "BSR_2025_esg.json",
            "source_pages": pages or [2],
            "json_pointer": pointer,
            "source_text": None,
        }],
    }


def _chunk_dir(temp, entries):
    path = Path(temp) / "chunks"
    path.mkdir()
    (path / "manifest.json").write_text(json.dumps({
        "source_file": "BSR_2025.pdf",
        "page_count": 8,
        "chunks": [{"file": name, "page_range": pages} for name, pages, _ in entries],
    }), encoding="utf-8")
    for name, pages, text in entries:
        payload = {"source_file": "BSR_2025.pdf", "page_range": pages, "pages": []}
        for page in range(pages[0], pages[1] + 1):
            payload["pages"].append({"page_number": page, "text": text})
        (path / name).write_text(json.dumps(payload), encoding="utf-8")
    return path


class ProvenanceEnricherTest(unittest.TestCase):
    def test_matches_one_source_chunk_and_preserves_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            chunk_dir = _chunk_dir(temp, [("chunk.json", [1, 4], "Fixture metric was 42 unit.")])
            claims, report = enrich_claims([_fixture_claim()], chunk_dir)
        self.assertEqual(report["resolved_count"], 1)
        self.assertEqual(claims[0]["provenance"]["status"], "resolved")
        self.assertIn("Fixture metric was 42", claims[0]["original_text"])
        self.assertEqual(claims[0]["claim_id"], "CLM-FIXTURE")
        self.assertEqual(claims[0]["evidence"][0]["evidence_id"], "EVD-FIXTURE")

    def test_missing_page_and_pointer_is_blocked_without_inference(self):
        claim = _fixture_claim(pages=[])
        claim["evidence"][0].pop("source_pages")
        claim["evidence"][0].pop("json_pointer")
        with tempfile.TemporaryDirectory() as temp:
            chunk_dir = _chunk_dir(temp, [("chunk.json", [1, 4], "Fixture metric was 42 unit.")])
            claims, report = enrich_claims([claim], chunk_dir)
        self.assertEqual(report["blocked_count"], 1)
        self.assertIsNone(claims[0]["original_text"])
        self.assertEqual(claims[0]["evidence"][0]["source_text"], None)
        self.assertIn("source_pages", claims[0]["provenance"]["pending_provenance"])

    def test_overlapping_chunks_are_partial(self):
        with tempfile.TemporaryDirectory() as temp:
            chunk_dir = _chunk_dir(temp, [
                ("a.json", [1, 4], "Fixture metric was 42 unit."),
                ("b.json", [2, 5], "Fixture metric was 42 unit."),
            ])
            claims, report = enrich_claims([_fixture_claim()], chunk_dir)
        self.assertEqual(report["partial_count"], 1)
        self.assertIsNone(claims[0]["original_text"])
        self.assertIn("nhiều chunk", claims[0]["provenance"]["evidence_results"][0]["reason"])

    def test_missing_source_text_is_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            chunk_dir = _chunk_dir(temp, [("chunk.json", [1, 4], None)])
            claims, report = enrich_claims([_fixture_claim()], chunk_dir)
        self.assertEqual(report["blocked_count"], 1)
        self.assertIsNone(claims[0]["original_text"])

    def test_real_enrichment_does_not_touch_findings_or_snapshot_files(self):
        findings = (ROOT / "output" / "findings.json").read_bytes()
        graph = (ROOT / "output" / "graph.json").read_bytes()
        claims = json.loads((ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig"))
        enriched, report = enrich_claims(claims)
        self.assertEqual(len(enriched), 16)
        self.assertEqual(report["company_id"], "BSR")
        self.assertEqual((ROOT / "output" / "findings.json").read_bytes(), findings)
        self.assertEqual((ROOT / "output" / "graph.json").read_bytes(), graph)
        self.assertEqual({claim["report_year"] for claim in enriched}, {2025})
        self.assertEqual({claim["company_id"] for claim in enriched}, {"BSR"})


if __name__ == "__main__":
    unittest.main()
