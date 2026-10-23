"""Lossless mapping of independent corporate-extract-1.0 deliveries to RDF claims."""
from copy import deepcopy
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def adapt(document, record, extract_path):
    source, period, boundary = document["source"], record["period"], record["boundary"]
    value, quality = record["value"], record["quality"]
    evidence = []
    for index, item in enumerate(record["evidence"]):
        evidence.append({**deepcopy(item), "source_id": source["source_id"],
                         "source_file": source["file_name"], "source_extract_path": str(extract_path),
                         "page_system": source["page_system"], "source_pages": [item["physical_page"]],
                         "original_text": item["exact_quote"], "json_pointer": f"/records/{record['record_id']}/evidence/{index}"})
    return {
        "record_id": record["record_id"], "company_id": document["company_id"],
        "report_id": document["document_id"], "report_year": document["report_year"],
        "report_type": document["report_type"],
        "source_document_type": document["source_document_type"],
        "reporting_entity": document["reporting_entity"],
        "reporting_period_start": document["reporting_period_start"],
        "reporting_period_end": document["reporting_period_end"],
        "publication_date": document["publication_date"],
        "observation_year": period["observation_year"], "period_type": period["period_type"],
        "period_type_verified": False, "dimension": record["dimension"],
        "claim_type": {"governance_evidence": "governance_statement", "financial_measurement": "measurement"}.get(record["record_type"], record["record_type"]),
        "topic": record["topic"], "metric_id": record["metric_id"],
        "metric_definition": record["metric_definition"], "label": record["metric_label"],
        "value": value["normalized_value"], "value_status": value["status"],
        "unit": value["normalized_unit"], "source_original_value": value["original_value"],
        "original_unit": value["original_unit"], "original_scale": value["original_scale"],
        "normalization_note": value["normalization_note"],
        "scope": boundary["scope"], "reporting_boundary": boundary["reporting_entity"],
        "reporting_boundary_verified": False, "variant": record["statement"]["assertion_kind"],
        "baseline_year": period["baseline_year"], "target_deadline": period["target_deadline"],
        "year_basis": period["year_basis"], "population_id": boundary["population"],
        "counting_method": boundary["counting_method"], "extraction_method": quality["extraction_method"],
        "model_id": quality["model_id"], "prompt_version": quality["prompt_version"],
        "review_status": "pending_human_review", "extract_review_status": quality["review_status"],
        "uncertainty": list(quality["uncertainty"]), "evidence": evidence,
        "input_digest": digest({"document": document, "record": record}),
        "raw_record": deepcopy(record), "raw_document": deepcopy(document),
    }
