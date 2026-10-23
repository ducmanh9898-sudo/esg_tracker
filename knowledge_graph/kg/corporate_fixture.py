"""Generate explicitly synthetic development PDFs/JSON; never labels real BSR data."""
import argparse
from copy import deepcopy
from pathlib import Path

import fitz

from kg.corporate_pipeline import CONTRACT, load_json, sha256, write_json


def create(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "pdf").mkdir()
    (directory / "json").mkdir()
    manifest = {"schema_version": "corporate-extract-manifest-1.0", "batch_id": "SYNTHETIC-DEVELOPMENT", "files": []}
    config = {"company_id": "SYNTHETIC", "expected_reports": []}
    example = load_json(CONTRACT / "example_esg.json")
    for year in (2023, 2024, 2025):
        for kind, scope in (("ESG", None), ("Financial", "Separate"), ("Financial", "Consolidated")):
            identifier = f"SYNTHETIC-{kind}-{scope or 'ESG'}-{year}"
            raw = deepcopy(example)
            doc = raw["document"]
            doc.update(document_id=identifier, company_id="SYNTHETIC", report_year=year, report_type=kind,
                       financial_scope=scope, source_document_type="sustainability_report" if kind == "ESG" else "financial_statement",
                       reporting_entity="Synthetic group" if scope == "Consolidated" else "Synthetic company",
                       reporting_period_start=f"{year}-01-01", reporting_period_end=f"{year}-12-31")
            pdf_path = directory / "pdf" / (identifier + ".pdf")
            records = []
            metrics = [("E", "ghg_scope1", 10 + year - 2023, "tCO2e"), ("S", "employees_total", 100, "person"),
                       ("G", "board_total", 5, "person")] if kind == "ESG" else [
                           ("X", "employees_total", 120 if scope == "Consolidated" else 100, "person"),
                           ("X", "revenue", 123, "VND")]
            for dimension, metric, number, unit in metrics:
                record = deepcopy(example["records"][0])
                quote = f"{metric} | 2023: {number} | Unit: {unit}"
                record.update(record_id=identifier + "-" + metric, dimension=dimension,
                              record_type="measurement" if kind == "ESG" else "financial_measurement",
                              metric_id=metric, metric_label=metric, metric_definition="Synthetic definition: " + metric)
                record["statement"].update(original_quote=quote, interpretation=None)
                record["value"].update(original_value=str(number), original_unit=unit, original_scale=None,
                                       normalized_value=number, normalized_unit=unit)
                record["boundary"].update(reporting_entity=doc["reporting_entity"], consolidation=scope or "Separate",
                                          scope="company", calculation_method="synthetic method", population=None, counting_method=None)
                record["restatement"] = {"status": "not_restatement_reported", "note": "Synthetic development assumption"}
                record["quality"]["uncertainty"] = []
                record["period"]["year_basis"] = "table_header"
                ev = record["evidence"][0]
                ev.update(evidence_id=record["record_id"] + "-EVD", physical_page=1, exact_quote=str(number),
                          context_text=quote, table_id="synthetic-table", row=len(records) + 1, column=1,
                          headers=[{"role": "year", "text": "2023", "physical_page": 1, "row": 0, "column": 1, "bbox": None},
                                   {"role": "unit", "text": unit, "physical_page": 1, "row": None, "column": None, "bbox": None}])
                records.append(record)
            pdf = fitz.open()
            page = pdf.new_page()
            page.insert_text((50, 50), "SYNTHETIC DEVELOPMENT FIXTURE - NOT BSR\n" + identifier + "\n" +
                             "\n".join(r["statement"]["original_quote"] for r in records))
            pdf.save(pdf_path)
            pdf.close()
            source_hash = sha256(pdf_path)
            doc["source"].update(source_id=identifier + "-PDF", file_name=pdf_path.name, url=None, sha256=source_hash, page_count=1)
            for record in records:
                record["evidence"][0]["source_sha256"] = source_hash
            raw.update(records=records, issue_log=[], coverage={"status": "complete", "scope_description": "Entire synthetic one-page fixture",
                "search_status": "searched", "pages_checked": [1], "pages_unreadable": [], "topics_searched": [r["metric_id"] for r in records],
                "search_outcomes": [{"topic": r["metric_id"], "status": "found", "pages": [1], "reason": None} for r in records]})
            path = directory / "json" / (identifier + ".json")
            write_json(path, raw)
            metadata = {"report_year": year, "report_type": kind, "financial_scope": scope}
            config["expected_reports"].append(metadata)
            manifest["files"].append({**metadata, "document_id": identifier, "pdf_path": "pdf/" + pdf_path.name,
                "pdf_sha256": source_hash, "json_path": "json/" + path.name, "json_sha256": sha256(path), "status": "delivered", "reason": None})
    write_json(directory / "manifest.json", manifest)
    write_json(directory / "config.json", config)
    return directory / "manifest.json", config


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    create(parser.parse_args().directory)
