import tempfile
import unittest
from pathlib import Path

import fitz

from tools.annual_report_sources import file_hash, inspect_pdf


class AnnualSourceInspectionTest(unittest.TestCase):
    def test_rejects_html_and_wrong_reporting_year(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.pdf"
            path.write_text("<html>not a PDF</html>", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "response_is_not_pdf"):
                inspect_pdf(path, 2024, "BSR")
            pdf = fitz.open()
            pdf.new_page().insert_text((40, 40), "BSR annual report 2023")
            pdf.new_page()
            pdf.save(path)
            pdf.close()
            with self.assertRaisesRegex(ValueError, "annual_report_identity_not_established"):
                inspect_pdf(path, 2024, "BSR")

    def test_visual_identity_requires_exact_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.pdf"
            pdf = fitz.open()
            pdf.new_page().insert_text((40, 40), "annual report 2023")
            pdf.new_page()
            pdf.save(path)
            pdf.close()
            with self.assertRaisesRegex(ValueError, "annual_report_identity_not_established"):
                inspect_pdf(path, 2023, "BSR")
            self.assertEqual(inspect_pdf(path, 2023, "BSR", file_hash(path)),
                             (2, "visual_cover_sha256"))


if __name__ == "__main__":
    unittest.main()
