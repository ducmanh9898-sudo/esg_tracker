"""Small handoff fixtures against the stored normalized claims and ESG extracts."""

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.handoff_preflight import preflight


BOUNDARY_FIELDS = (
    "basis", "included_entities", "excluded_entities", "measurement_scope",
    "consolidation_approach", "source_pages",
)


class HandoffPreflightTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        claims = json.loads((ROOT / "output" / "normalized_claims.json").read_text(encoding="utf-8-sig"))
        cls.current = next(c for c in claims if c["claim_id"] == "CLM-08082F5B81CD")
        cls.prior_year = next(c for c in claims if c["report_year"] != c["observation_year"])

    def _record(self, claim):
        evidence = claim["evidence"][0]
        boundary_missing = [f"boundary.{field}" for field in BOUNDARY_FIELDS]
        return {
            "claim_id": claim["claim_id"],
            "evidence_id": evidence["evidence_id"],
            "company_id": claim["company_id"],
            "report_id": None,
            "report_year": claim["report_year"],
            "metric_period_year": claim["observation_year"],
            "period_type": None,
            "source_file": evidence["source_file"],
            "source_pages": evidence["source_pages"],
            "json_pointer": evidence["json_pointer"],
            "original_text": None,
            "extraction_status": "resolved",
            "boundary": {
                "status": "unverified",
                **{field: None for field in BOUNDARY_FIELDS},
                "missing_fields": boundary_missing,
            },
            "missing_fields": boundary_missing + ["report_id", "period_type", "original_text"],
        }

    def _run(self, *records):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "handoff.json"
            path.write_text(json.dumps({"schema_version": "0.1", "records": records}), encoding="utf-8")
            return preflight(path)

    def test_identity_fields_are_checked_against_claim_evidence_and_esg_json(self):
        changes = {
            "claim_id": ("claim_id", "CLM-AAAAAAAAAAAA"),
            "evidence_id": ("evidence_id", "EVD-AAAAAAAAAAAA"),
            "company": ("company_id", "OTHER"),
            "report_year": ("report_year", 2024),
            "source_file": ("source_file", "other.json"),
            "source_pages": ("source_pages", [1]),
            "json_pointer": ("json_pointer", "/social/other"),
        }
        for name, (field, value) in changes.items():
            with self.subTest(name=name):
                record = self._record(self.current)
                record[field] = value
                result = self._run(record)
                self.assertEqual(result["summary"]["blocking"], 1)
                self.assertEqual(result["blocking_records"][0]["claim_id"], record["claim_id"])
                self.assertTrue(any(field in reason for reason in result["blocking_records"][0]["reasons"]))

    def test_duplicate_pair_and_conflicting_evidence_id_block_ingestion(self):
        record = self._record(self.current)
        result = self._run(record, copy.deepcopy(record))
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertIn("trùng", " ".join(result["blocking_records"][0]["reasons"]))
        conflicting = self._record(self.prior_year)
        conflicting["evidence_id"] = record["evidence_id"]
        result = self._run(record, conflicting)
        self.assertIn("được dùng lại", " ".join(result["blocking_records"][0]["reasons"]))

    def test_schema_error_is_reported_under_claim_id(self):
        record = self._record(self.current)
        record["source_pages"] = "page 39"
        result = self._run(record)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertEqual(result["blocking_records"][0]["claim_id"], record["claim_id"])
        self.assertIn("schema", " ".join(result["blocking_records"][0]["reasons"]))

    def test_missing_fields_must_match_nulls_at_both_levels(self):
        record = self._record(self.current)
        record["boundary"]["missing_fields"].remove("boundary.basis")
        record["missing_fields"].remove("period_type")
        result = self._run(record)
        reasons = " ".join(result["blocking_records"][0]["reasons"])
        self.assertIn("boundary.missing_fields", reasons)
        self.assertIn("missing_fields", reasons)

    def test_partial_boundary_never_inherits_provenance_resolution(self):
        record = self._record(self.current)
        record["boundary"]["status"] = "partially_verified"
        record["reporting_boundary_verified"] = False
        result = self._run(record)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertEqual(result["summary"]["manual_review"], 1)
        record["reporting_boundary_verified"] = True
        result = self._run(record)
        self.assertEqual(result["summary"]["blocking"], 1)
        self.assertIn("reporting_boundary_verified", " ".join(result["blocking_records"][0]["reasons"]))

    def test_table_interpretation_is_not_accepted_as_verbatim_quote(self):
        record = self._record(self.current)
        record["original_text"] = "The table indicates 1,946 employees."
        record["missing_fields"].remove("original_text")
        record["original_text_type"] = "table_interpretation"
        record["original_text_verbatim"] = True
        result = self._run(record)
        self.assertEqual(result["summary"]["blocking"], 1)
        record["original_text_verbatim"] = False
        result = self._run(record)
        self.assertEqual(result["summary"]["blocking"], 0)
        self.assertTrue(any("diễn giải" in reason for reason in result["manual_review_records"][0]["reasons"]))

    def test_prior_year_metric_keeps_report_and_period_year_distinct(self):
        record = self._record(self.prior_year)
        self.assertNotEqual(record["report_year"], record["metric_period_year"])
        result = self._run(record)
        self.assertEqual(result["summary"]["blocking"], 0)
        record.pop("metric_period_year")
        result = self._run(record)
        self.assertTrue(any("metric_period_year" in reason for reason in result["manual_review_records"][0]["reasons"]))
        record["metric_period_year"] = record["report_year"]
        result = self._run(record)
        self.assertEqual(result["summary"]["blocking"], 1)

    def test_read_only_preflight_does_not_change_snapshot(self):
        paths = [ROOT / "output" / name for name in ("normalized_claims.json", "graph.json", "findings.json")]
        before = {path: path.read_bytes() for path in paths}
        result = self._run(self._record(self.current))
        self.assertEqual(result["summary"], {"records": 1, "valid": 1, "manual_review": 1, "blocking": 0})
        self.assertEqual(before, {path: path.read_bytes() for path in paths})


if __name__ == "__main__":
    unittest.main()
