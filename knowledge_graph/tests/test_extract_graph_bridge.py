"""Source selection for an all-page BSR Extract run."""
import unittest

from tools.extract_graph_bridge import DEFAULT_SOURCE, esg_bctc_config, full_bsr_config


class FullBsrConfigTest(unittest.TestCase):
    def test_selects_six_esg_and_consolidated_bctc_sources(self):
        config = esg_bctc_config(DEFAULT_SOURCE)
        self.assertEqual(len(config["documents"]), 6)
        self.assertEqual(len({row["sha256"] for row in config["documents"]}), 6)
        self.assertTrue(all("pages" not in row for row in config["documents"]))
        for year in (2023, 2024, 2025):
            rows = [row for row in config["documents"] if row["report_year"] == year]
            self.assertEqual({row["report_type"] for row in rows},
                             {"ESG", "financial_statements"})
            self.assertTrue(any(row["pdf"].endswith(f"BCTC_BSR_{year}.pdf")
                                for row in rows))

    def test_selects_twelve_unique_sources_and_all_pages(self):
        config = full_bsr_config(DEFAULT_SOURCE)
        self.assertEqual(config["company_id"], "BSR")
        self.assertEqual(len(config["documents"]), 12)
        self.assertTrue(all("pages" not in row for row in config["documents"]))
        self.assertEqual(len({row["sha256"] for row in config["documents"]}), 12)
        esg_2025 = [row for row in config["documents"]
                    if row["report_year"] == 2025 and row["report_type"] == "ESG"]
        self.assertEqual(len(esg_2025), 1)
        self.assertIn("official", esg_2025[0]["pdf"].lower())


if __name__ == "__main__":
    unittest.main()
