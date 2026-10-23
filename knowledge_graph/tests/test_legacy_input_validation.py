"""Graph still validates preserved Extract v2 inputs without an Extract runtime."""
from copy import deepcopy
import unittest

from kg.extract_v2_validation import check_batch
from kg.source_identity import ROOT, read_json


class LegacyInputValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.paths = sorted((ROOT / 'data/review/bsr_esg_extract_pilot_review_v10/audit_v2').glob('handoff_*.json'))
        cls.registry = ROOT / 'data/source/esg_pilot_registry.json'

    def test_all_40_preserved_candidates_still_validate(self):
        self.assertEqual(len(self.paths), 5)
        count = 0
        for path in self.paths:
            result = check_batch(read_json(path), self.registry, allow_partial=True)
            self.assertTrue(result['ok'], result)
            count += result['record_count']
        self.assertEqual(count, 40)

    def test_source_hash_mismatch_blocked(self):
        batch = deepcopy(read_json(self.paths[0]))
        batch['document']['source_sha256'] = 'f' * 64
        result = check_batch(batch, self.registry, allow_partial=True)
        self.assertFalse(result['ok'])
        self.assertIn('document_source_hash_mismatch', result['mechanical_errors'])

    def test_partial_requires_explicit_option(self):
        result = check_batch(read_json(self.paths[0]), self.registry)
        self.assertFalse(result['ok'])
        self.assertIn('batch_not_complete', result['mechanical_errors'])
