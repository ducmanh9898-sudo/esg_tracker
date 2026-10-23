from pathlib import Path
import sys
import json
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.database import connect, initialize_database
from src.database.adapters import adapt_record, load_phase1_records
from src.database.output_sources import (
    artifact_rows,
    discover_output_documents,
    iter_structured_facts,
    page_rows,
    summary_claim_rows,
)
from src.database.sample_data import build_sample, write_sample_csv
from src.extraction.claims import classify_claim, extract_attributes
from src.normalization.units import normalize_value
from src.paths import CONFIG_DIR, WORKSPACE_ROOT


def execute(connection, table: str, row: dict):
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    connection.execute(f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})", tuple(row.values()))


def reset_content(connection):
    for table in ("topic_scores", "claim_scores", "rule_results", "evidence_links", "metrics", "claims", "source_artifacts", "passages", "documents", "companies"):
        connection.execute(f"DELETE FROM {table}")


def import_demo(connection):
    claims, metrics = build_sample()
    write_sample_csv(ROOT / "data" / "sample", claims, metrics)
    page_counts = {2022: 39, 2023: 39, 2024: 43, 2025: 68}
    for year in range(2022, 2026):
        for suffix, doc_type, title, filename in (
            ("ESG", "DEMO_ESG_REPORT", "Báo cáo Phát triển bền vững BSR", f"BSR_{year}.pdf"),
            ("EVIDENCE", "DEMO_SUPPORTING_REPORT", "BCTC & Tài liệu đối chiếu BSR", f"BCTC_BSR_{year}.pdf"),
        ):
            execute(connection, "documents", {
                "document_id": f"DEMO_{suffix}_{year}", "company_id": "BSR", "title": f"{title} {year}",
                "report_year": year, "document_type": doc_type, "source_file": filename,
                "source_path": f"output/json/{filename.replace('.pdf', '.json')}", "page_count": page_counts.get(year, 40),
                "extraction_method": "output_json_ocr_extraction",
                "confidence": 0.95, "is_demo_data": 1,
            })
    for claim in claims:
        passage_id = f"P_{claim['claim_id']}"
        document_id = f"DEMO_ESG_{claim['report_year']}"
        execute(connection, "passages", {
            "passage_id": passage_id, "document_id": document_id, "report_year": claim["report_year"],
            "document_type": claim["document_type"], "page_number": claim["page_number"],
            "source_text": claim["source_text"], "extraction_method": "output_json_ocr_extraction",
            "confidence": claim["confidence"], "is_demo_data": 1,
        })
        row = {k: claim.get(k) for k in (
            "claim_id", "report_year", "document_type", "page_number", "source_text", "claim_type", "pillar", "topic_id",
            "metric_code", "actor", "action", "object", "raw_value", "raw_unit", "baseline_year", "target_year", "scope",
            "boundary", "qualifier", "direction", "value_kind", "denominator")}
        row.update({"passage_id": passage_id, "document_id": document_id, "extraction_method": "output_json_ocr_extraction",
                    "confidence": claim["confidence"], "is_demo_data": 1})
        execute(connection, "claims", row)
    for metric in metrics:
        passage_id = f"P_{metric['metric_id']}"
        document_id = f"DEMO_EVIDENCE_{metric['report_year']}"
        execute(connection, "passages", {
            "passage_id": passage_id, "document_id": document_id, "report_year": metric["report_year"],
            "document_type": metric["document_type"], "page_number": metric["page_number"],
            "source_text": metric["source_text"], "extraction_method": "output_json_ocr_extraction",
            "confidence": metric["confidence"], "is_demo_data": 1,
        })
        row = {k: metric.get(k) for k in (
            "metric_id", "report_year", "document_type", "page_number", "source_text", "metric_code", "metric_name",
            "raw_value", "raw_unit", "normalized_value", "normalized_unit", "metric_year", "scope", "boundary", "denominator",
            "value_kind", "methodology", "assurance_status", "financial_class")}
        row.update({"passage_id": passage_id, "document_id": document_id, "extraction_method": "synthetic_demo_generator",
                    "confidence": metric["confidence"], "is_demo_data": 1})
        execute(connection, "metrics", row)


def import_phase1_fallback(connection):
    metric_config = yaml.safe_load((CONFIG_DIR / "metrics.yml").read_text(encoding="utf-8"))["metrics"]
    for raw in load_phase1_records(WORKSPACE_ROOT):
        item = adapt_record(raw)
        document_id = f"REAL_{Path(item['source_file']).stem}_{item['year']}"
        execute(connection, "documents", {
            "document_id": document_id, "company_id": "BSR", "title": item["source_file"], "report_year": item["year"],
            "document_type": item["report_type"], "source_file": item["source_file"], "source_path": str(WORKSPACE_ROOT),
            "page_count": None, "extraction_method": item["extraction_method"], "confidence": item["confidence"], "is_demo_data": 0,
        })
        passage_id = f"REAL_P_{item['record_id']}"
        execute(connection, "passages", {
            "passage_id": passage_id, "document_id": document_id, "report_year": item["year"],
            "document_type": item["report_type"], "page_number": item["page"], "source_text": item["text"],
            "extraction_method": item["extraction_method"], "confidence": item["confidence"], "is_demo_data": 0,
        })
        execute(connection, "claims", {
            "claim_id": f"REAL_C_{item['record_id']}", "passage_id": passage_id, "document_id": document_id,
            "report_year": item["year"], "document_type": item["report_type"], "page_number": item["page"],
            "source_text": item["text"], "extraction_method": item["extraction_method"], "confidence": item["confidence"],
            "claim_type": item["claim_type"], "pillar": item["pillar"], "topic_id": item["topic"],
            "metric_code": item["metric_code"], "actor": "BSR", "action": "công bố", "object": item["topic"],
            "raw_value": item["value"], "raw_unit": item["unit"], "scope": item["scope"], "boundary": item["boundary"],
            "direction": "NEUTRAL", "value_kind": "INTENSITY" if item["metric_code"] in {"GHG_INTENSITY", "LTIFR", "TRIR"} else "ABSOLUTE",
            "is_demo_data": 0,
        })
        if item["metric_code"] and item["value"] is not None:
            standard = metric_config[item["metric_code"]]["standard_unit"]
            normalized, normalized_unit, _status = normalize_value(item["value"], item["unit"], standard)
            execute(connection, "metrics", {
                "metric_id": f"REAL_M_{item['record_id']}", "passage_id": passage_id, "document_id": document_id,
                "report_year": item["year"], "document_type": item["report_type"], "page_number": item["page"],
                "source_text": item["text"], "extraction_method": item["extraction_method"], "confidence": item["confidence"],
                "metric_code": item["metric_code"], "metric_name": metric_config[item["metric_code"]]["name"],
                "raw_value": item["value"], "raw_unit": item["unit"], "normalized_value": normalized,
                "normalized_unit": normalized_unit, "metric_year": item["year"], "scope": item["scope"],
                "boundary": item["boundary"], "value_kind": "INTENSITY" if item["metric_code"] in {"GHG_INTENSITY", "LTIFR", "TRIR"} else "ABSOLUTE",
                "methodology": item["methodology"], "assurance_status": item["assurance_status"],
                "financial_class": "CAPEX" if item["metric_code"] == "ENV_CAPEX" else "OPEX" if item["metric_code"] == "ENV_EXPENSE" else None,
                "is_demo_data": 0,
            })


def import_output_sources(connection) -> dict:
    """Import the six BSR 2023-2025 output bundles as the primary real corpus."""
    metric_config = yaml.safe_load((CONFIG_DIR / "metrics.yml").read_text(encoding="utf-8"))["metrics"]
    output_root = WORKSPACE_ROOT / "output"
    documents = discover_output_documents(output_root)
    stats = {"documents": 0, "pages": 0, "artifacts": 0, "claims": 0, "metrics": 0}
    for document in documents:
        document_id = f"OUTPUT_{document.stem}"
        pages = page_rows(document)
        execute(connection, "documents", {
            "document_id": document_id,
            "company_id": "BSR",
            "title": f"{'Báo cáo tài chính' if document.document_type == 'financial_statements' else 'Báo cáo ESG'} BSR {document.year}",
            "report_year": document.year,
            "document_type": document.document_type,
            "source_file": f"{document.stem}.pdf",
            "source_path": str(document.page_json.resolve()),
            "page_count": len(pages),
            "extraction_method": "output_page_json_and_structured_esg",
            "confidence": 0.90,
            "is_demo_data": 0,
        })
        stats["documents"] += 1

        passage_ids = {}
        for page in pages:
            passage_id = f"OUTPUT_P_{document.stem}_{page['page_number']:04d}"
            passage_ids[page["page_number"]] = passage_id
            execute(connection, "passages", {
                "passage_id": passage_id,
                "document_id": document_id,
                "report_year": document.year,
                "document_type": document.document_type,
                "page_number": page["page_number"],
                "source_text": page["source_text"] or "[Trang không có text trích xuất]",
                "extraction_method": "output_page_json",
                "confidence": page["confidence"],
                "is_demo_data": 0,
            })
            stats["pages"] += 1

        for index, artifact in enumerate(artifact_rows(document), start=1):
            execute(connection, "source_artifacts", {
                "artifact_id": f"OUTPUT_A_{document.stem}_{index:03d}",
                "document_id": document_id,
                "artifact_type": artifact["artifact_type"],
                "source_path": artifact["source_path"],
                "content_text": artifact["content_text"],
                "sha256": artifact["sha256"],
                "page_start": artifact["page_start"],
                "page_end": artifact["page_end"],
                "record_count": artifact["record_count"],
                "report_year": document.year,
                "document_type": document.document_type,
                "is_demo_data": 0,
            })
            stats["artifacts"] += 1

        # Curated Markdown summaries become readable claims. Structured JSON is
        # used for metrics and additional explicit claim/description fields.
        facts = summary_claim_rows(document)
        facts.extend(iter_structured_facts(document))
        seen_claims = set()
        seen_metrics = set()
        claim_index = metric_index = 0
        for fact in facts:
            page = min(max(int(fact.get("page") or 1), 1), max(len(pages), 1))
            passage_id = passage_ids.get(page) or next(iter(passage_ids.values()))
            text = str(fact.get("text") or "").strip()
            metric_code = fact.get("metric_code")
            if fact["kind"] == "claim":
                key = (page, text.casefold())
                if key in seen_claims:
                    continue
                seen_claims.add(key)
                claim_index += 1
                attrs = extract_attributes(text)
                raw_value = fact.get("value") if fact.get("value") is not None else attrs.get("raw_value")
                raw_unit = fact.get("unit") or attrs.get("raw_unit")
                execute(connection, "claims", {
                    "claim_id": f"OUTPUT_C_{document.stem}_{claim_index:04d}",
                    "passage_id": passage_id,
                    "document_id": document_id,
                    "report_year": document.year,
                    "document_type": document.document_type,
                    "page_number": page,
                    "source_text": text,
                    "extraction_method": "output_summary_md" if fact.get("path") == "summary_md" else "output_structured_esg_json",
                    "confidence": 0.86 if fact.get("path") == "summary_md" else 0.80,
                    "claim_type": classify_claim(text),
                    "pillar": fact.get("pillar") or "X",
                    "topic_id": fact.get("topic") or "X_OTHER",
                    "metric_code": metric_code,
                    "actor": "BSR",
                    "action": "công bố",
                    "object": fact.get("topic"),
                    "raw_value": raw_value,
                    "raw_unit": raw_unit,
                    "time_text": str(document.year),
                    "baseline_year": attrs.get("baseline_year"),
                    "target_year": attrs.get("target_year"),
                    "scope": attrs.get("scope"),
                    "boundary": "Hợp nhất" if document.document_type == "financial_statements" else None,
                    "qualifier": attrs.get("qualifier"),
                    "direction": attrs.get("direction") or "NEUTRAL",
                    "value_kind": "INTENSITY" if metric_code in {"GHG_INTENSITY", "LTIFR", "TRIR"} else "ABSOLUTE",
                    "denominator": attrs.get("denominator"),
                    "is_demo_data": 0,
                })
                stats["claims"] += 1
                continue

            if not metric_code or metric_code not in metric_config or fact.get("value") is None:
                continue
            key = (page, metric_code, fact.get("value"), fact.get("unit"), fact.get("year"))
            if key in seen_metrics:
                continue
            seen_metrics.add(key)
            metric_index += 1
            standard = metric_config[metric_code]["standard_unit"]
            normalized, normalized_unit, _status = normalize_value(fact["value"], fact.get("unit"), standard)
            execute(connection, "metrics", {
                "metric_id": f"OUTPUT_M_{document.stem}_{metric_index:04d}",
                "passage_id": passage_id,
                "document_id": document_id,
                "report_year": document.year,
                "document_type": document.document_type,
                "page_number": page,
                "source_text": text,
                "extraction_method": "output_structured_esg_json",
                "confidence": 0.82 if normalized is not None else 0.65,
                "metric_code": metric_code,
                "metric_name": metric_config[metric_code]["name"],
                "raw_value": fact["value"],
                "raw_unit": fact.get("unit"),
                "normalized_value": normalized,
                "normalized_unit": normalized_unit,
                "metric_year": int(fact.get("year") or document.year),
                "scope": "Scope 1" if metric_code == "GHG_SCOPE_1" else "Scope 2" if metric_code == "GHG_SCOPE_2" else None,
                "boundary": "Hợp nhất" if document.document_type == "financial_statements" else None,
                "denominator": "tấn sản phẩm" if metric_code == "GHG_INTENSITY" else None,
                "value_kind": "INTENSITY" if metric_code in {"GHG_INTENSITY", "LTIFR", "TRIR"} else "ABSOLUTE",
                "methodology": f"Structured path: {fact.get('path')}",
                "assurance_status": None,
                "financial_class": "CAPEX" if metric_code == "ENV_CAPEX" else "OPEX" if metric_code == "ENV_EXPENSE" else None,
                "is_demo_data": 0,
            })
            stats["metrics"] += 1
    return stats


def main():
    initialize_database()
    with connect() as connection:
        reset_content(connection)
        execute(connection, "companies", {"company_id": "BSR", "name": "Công ty cổ phần Lọc hóa dầu Bình Sơn",
                                          "industry": "Oil and Gas", "country": "Việt Nam", "is_demo_data": 0})
        stats = import_output_sources(connection)
        if not stats["documents"]:
            import_phase1_fallback(connection)
        import_demo(connection)
    print(f"Imported output corpus and isolated demo data: {stats}")


if __name__ == "__main__":
    main()
