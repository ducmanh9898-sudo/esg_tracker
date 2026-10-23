"""Build source-bound, AI-assisted annual-report candidates for a corporate delivery."""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import fitz

from kg.corporate_adapter import digest


def write_new(path, value):
    if path.exists():
        raise ValueError("output_exists:" + str(path))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix=path.stem + "_",
                                     suffix=".part", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def file_hash(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def context_from_text(page, spec):
    text = page.get_text()
    marker = spec["original_value"]
    starts = [i for i in range(len(text)) if text.startswith(marker, i)]
    if spec.get("anchor_before"):
        starts = [i for i in starts if spec["anchor_before"] in text[max(0, i - 200):i]]
    if len(starts) != 1:
        raise ValueError(f"ambiguous_pdf_text_value:{spec['report_year']}:{spec['physical_page']}:{marker}")
    start = starts[0]
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", start)
    if line_end < 0:
        line_end = len(text)
    quote = text[line_start:line_end]
    context = text[max(0, start - 250):min(len(text), start + 300)]
    if spec["original_unit"].casefold() not in context.casefold():
        raise ValueError("unit_not_in_source_context")
    if spec["observation_year"] is not None and str(spec["observation_year"]) not in context:
        raise ValueError("year_not_in_source_context")
    locations = page.search_for(marker)
    all_starts = [i for i in range(len(text)) if text.startswith(marker, i)]
    if len(locations) != len(all_starts):
        raise ValueError("ambiguous_value_bbox")
    location = locations[all_starts.index(start)]
    return quote, context, [round(x, 3) for x in location], start, start + len(marker)


def make_record(source, spec, pdf):
    page_number = spec["physical_page"]
    if page_number < 1 or page_number > pdf.page_count:
        raise ValueError("physical_page_outside_pdf")
    page = pdf[page_number - 1]
    if spec["quote_method"] == "pdf_text":
        quote, context, bbox, char_start, char_end = context_from_text(page, spec)
    elif spec["quote_method"] == "visual_transcription":
        quote = context = spec["exact_quote"]
        if spec["original_value"] not in quote or spec["original_unit"] not in quote:
            raise ValueError("visual_quote_missing_value_or_unit")
        bbox = char_start = char_end = None
    else:
        raise ValueError("unsupported_quote_method")
    record_id = "annual_" + digest([source["sha256"], page_number,
                                   spec["metric_label"], spec["original_value"]])[:32]
    evidence_id = "annual_evidence_" + digest([record_id, quote])[:32]
    year = spec["observation_year"]
    return {
        "record_id": record_id, "dimension": spec["dimension"], "record_type": "measurement",
        "topic": spec["topic"], "metric_id": None, "metric_label": spec["metric_label"],
        "metric_definition": None,
        "statement": {"original_quote": quote, "interpretation": None,
                      "assertion_kind": "reported_result"},
        "value": {"status": "available", "original_value": spec["original_value"],
                  "original_unit": spec["original_unit"], "original_scale": None,
                  "normalized_value": spec["normalized_value"],
                  "normalized_unit": spec["normalized_unit"], "normalization_factor": 1,
                  "normalization_note": "Candidate normalization; year/unit/meaning await human review."},
        "period": {"observation_year": year, "observation_start": None,
                   "observation_end": None, "measurement_date": spec["measurement_date"],
                   "period_type": "at_date" if spec["measurement_date"] else "unknown",
                   "year_basis": "explicit_quote" if year is not None else "unknown",
                   "baseline_year": None, "target_deadline": None},
        "boundary": {"reporting_entity": None, "consolidation": "unknown",
                     "scope": None, "population": None, "counting_method": None,
                     "calculation_method": None, "verified": False},
        "restatement": {"status": "unknown", "note": None},
        "evidence": [{"evidence_id": evidence_id, "source_sha256": source["sha256"],
                      "physical_page": page_number, "printed_page": None,
                      "exact_quote": quote, "context_text": context,
                      "section": None, "element_id": None,
                      "char_start": char_start, "char_end": char_end, "bbox": bbox,
                      "table_id": None, "row": None, "column": None,
                      "headers": [], "footnotes": []}],
        "quality": {"extraction_method": "other",
                    "parser_name": ("PyMuPDF_text" if spec["quote_method"] == "pdf_text"
                                    else "PyMuPDF_render_Codex_visual"),
                    "model_id": None, "prompt_version": None,
                    "uncertainty": ["ai_assisted_candidate", "not_human_adjudicated",
                                    "source_content_origin_not_independent", *spec["uncertainty"]],
                    "review_status": "pending_human_review", "reviewer": None,
                    "reviewed_at_utc": None, "review_basis": None},
        "comparison_group_id": None,
    }


def build(base_manifest, registry_path, specs_path, output_manifest, review_dir):
    base_manifest, output_manifest = Path(base_manifest), Path(output_manifest)
    if output_manifest.exists() or Path(review_dir).exists():
        raise ValueError("output_exists_choose_versioned_paths")
    if output_manifest.parent.resolve() != base_manifest.parent.resolve():
        raise ValueError("output_manifest_must_share_base_delivery_directory")
    base = json.loads(base_manifest.read_text(encoding="utf-8"))
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    specs = json.loads(Path(specs_path).read_text(encoding="utf-8"))["records"]
    if any(s["status"] != "available" for s in registry["sources"]):
        raise ValueError("annual_source_registry_not_complete")
    sources = {s["report_year"]: s for s in registry["sources"]}
    if len(sources) != len(registry["sources"]):
        raise ValueError("duplicate_annual_report_year")
    delivery = output_manifest.parent
    (delivery / "pdf").mkdir(exist_ok=True)
    (delivery / "json").mkdir(exist_ok=True)
    review = Path(review_dir)
    review.mkdir(parents=True)
    (review / "pages").mkdir()
    manifest = deepcopy(base)
    manifest["batch_id"] = "esg_annual_" + digest([base["batch_id"], registry, specs])[:24]
    pack = {"schema_version": "annual-candidate-review-1.0", "gold_status": "pending_adjudication",
            "cases": []}
    for year, source in sorted(sources.items()):
        source_path = Path(source["path"])
        if file_hash(source_path) != source["sha256"]:
            raise ValueError("registry_pdf_hash_mismatch:" + str(year))
        target = delivery / "pdf" / source_path.name
        if target.exists():
            if file_hash(target) != source["sha256"]:
                raise ValueError("existing_delivery_pdf_conflicts:" + str(target))
        else:
            shutil.copy2(source_path, target)
        with fitz.open(target) as pdf:
            selected = [s for s in specs if s["report_year"] == year]
            records = [make_record(source, s, pdf) for s in selected]
            for spec, record in zip(selected, records):
                page_number = spec["physical_page"]
                page_image = review / "pages" / f"annual_{year}_p{page_number:03}.png"
                if not page_image.exists():
                    pdf[page_number - 1].get_pixmap(matrix=fitz.Matrix(1.5, 1.5)).save(page_image)
                pack["cases"].append({"record_id": record["record_id"], "report_year": year,
                                      "source_sha256": source["sha256"], "pdf_path": str(target.resolve()),
                                      "physical_page": page_number, "page_image": str(page_image.resolve()),
                                      "quote_method": spec["quote_method"],
                                      "candidate": record, "decision": "pending", "reviewer": None,
                                      "reviewed_at_utc": None, "notes": None})
        pages = sorted({s["physical_page"] for s in selected})
        document = {"document_id": "report_" + source["sha256"],
                    "company_id": registry["company_id"], "report_type": "ESG",
                    "source_document_type": "annual_report", "report_year": year,
                    "financial_scope": None, "reporting_entity": None,
                    "reporting_period_start": f"{year}-01-01",
                    "reporting_period_end": f"{year}-12-31",
                    "publication_date": None,
                    "source": {"source_id": source["source_id"], "file_name": target.name,
                               "url": source["url"], "downloaded_at_utc": source["downloaded_at_utc"],
                               "sha256": source["sha256"], "page_count": source["page_count"],
                               "page_system": "physical_pdf_page_1_based"}}
        handoff = {"schema_version": "corporate-extract-1.0", "document": document,
                   "coverage": {"status": "partial", "scope_description": "Selected AI-assisted annual candidates only; other pages/topics not assessed.",
                                "search_status": "partial_search", "pages_checked": pages,
                                "pages_unreadable": [], "topics_searched": sorted({s["topic"] for s in selected}),
                                "search_outcomes": [{"topic": topic, "status": "found",
                                                     "pages": sorted({s["physical_page"] for s in selected if s["topic"] == topic}),
                                                     "reason": "Selected candidate pages only; not exhaustive."}
                                                    for topic in sorted({s["topic"] for s in selected})]},
                   "records": records,
                   "issue_log": [{"issue_id": "annual_issue_" + record["record_id"],
                                  "code": "semantic_review_pending", "message": "AI-assisted candidate; source context and equivalence need human review.",
                                  "source_pages": [record["evidence"][0]["physical_page"]],
                                  "record_id": record["record_id"], "status": "needs_review"}
                                 for record in records]}
        json_path = delivery / "json" / f"{source['sha256']}.json"
        write_new(json_path, handoff)
        manifest["files"].append({"document_id": document["document_id"], "report_year": year,
                                  "report_type": "ESG", "financial_scope": None,
                                  "pdf_path": str(target.relative_to(delivery)).replace("\\", "/"),
                                  "pdf_sha256": source["sha256"],
                                  "json_path": str(json_path.relative_to(delivery)).replace("\\", "/"),
                                  "json_sha256": file_hash(json_path), "status": "partial",
                                  "reason": "Selected AI-assisted annual candidates; human review pending."})
    write_new(output_manifest, manifest)
    write_new(review / "review_pack.json", pack)
    return {"annual_sources": len(sources), "annual_records": len(pack["cases"]),
            "manifest": str(output_manifest), "review_pack": str(review / "review_pack.json")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-manifest", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--specs", type=Path, required=True)
    parser.add_argument("--output-manifest", type=Path, required=True)
    parser.add_argument("--review-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.base_manifest, args.registry, args.specs,
                           args.output_manifest, args.review_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
