"""Normalize the BSR financial-report extracts into the Graph contract.

The adapter is deliberately narrow: it reads the three supplied BSR JSON
extracts, preserves their source pointers/pages, and never edits those inputs.
It does not activate FC01 or create findings.
"""

import argparse
import copy
import json
import re
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_DIR = ROOT / "data" / "extract" / "financial"
DEFAULT_OUTPUT = ROOT / "data" / "financial_disclosures_bsr.json"


def _pointer(parts):
    return "/" + "/".join(str(part).replace("~", "~0").replace("/", "~1") for part in parts)


def _source_info(raw):
    if "document" in raw:
        meta = raw["document"]
        year = int(meta["reporting_period_end"][:4])
        start = meta["reporting_period_start"]
        end = meta["reporting_period_end"]
        document_id = f"BSR-BCTC-{year}"
        source_file = meta["source_file"]
        report_type = meta["report_type"]
        company_name = meta["company"]
        scope = {
            "scope_id": "consolidated_group",
            "description": "BCTC hợp nhất; boundary được nêu là Hợp nhất.",
            "verification_status": "verified",
        }
        source_schema = "document_v1"
    else:
        meta = raw["metadata"]
        year = int(re.search(r"(20\d{2})", meta["reporting_period"]).group(1))
        start = f"{year}-01-01"
        end = f"{year}-12-31"
        # Normalize the source-provided identifier to the same stable namespace
        # used by the 2023–2024 extracts; do not expose the source PDF path.
        document_id = f"BSR-BCTC-{year}"
        source_file = Path(meta["source_pdf"]).name
        report_type = meta["report_type"]
        company_name = meta["entity"]
        scope = {
            "scope_id": "not_stated",
            "description": "BCTC extract không nêu reporting boundary cho workforce disclosure.",
            "verification_status": "unverified",
        }
        source_schema = "metadata_v2"
    return {
        "year": year,
        "start": start,
        "end": end,
        "document_id": document_id,
        "source_file": source_file,
        "report_type": report_type,
        "company_name": company_name,
        "scope": scope,
        "source_schema": source_schema,
        "source_uri": f"financial-report://BSR/BCTC/{year}",
    }


def _pages(container):
    if not isinstance(container, dict):
        return []
    if isinstance(container.get("source_pages"), list):
        return container["source_pages"]
    if isinstance(container.get("source_pages_pdf"), list):
        return container["source_pages_pdf"]
    if isinstance(container.get("source_page"), int):
        return [container["source_page"]]
    return []


def _leaf_records(value, parts, inherited_pages, unit, prefix):
    """Yield scalar financial values while retaining the JSON pointer."""
    if isinstance(value, dict):
        current_pages = _pages(value) or inherited_pages
        for key, child in value.items():
            if key in {"source_pages", "source_pages_pdf", "source_page"}:
                continue
            child_unit = unit
            if key.endswith("_vnd"):
                child_unit = "VND"
            yield from _leaf_records(child, parts + [key], current_pages, child_unit, prefix)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        key = parts[-1]
        label = re.sub(r"_+", " ", key).strip().capitalize()
        item_id = prefix + "." + ".".join(parts)
        yield item_id, label, value, unit, _pointer(parts), inherited_pages


def _record(info, item_id, label, value, unit, pointer, pages, *, statement=None,
            observation_year=None):
    record = {
        "schema_version": "0.1",
        "record_type": "financial_disclosure",
        "disclosure_id": f"FIN-{info['document_id']}-{item_id}",
        "company": {
            "company_id": "BSR",
            "company_name": info["company_name"],
        },
        "company_id": "BSR",
        "report_year": info["year"],
        "reporting_period": {
            "fiscal_year": info["year"],
            "period_type": "duration",
            "period_start": info["start"],
            "period_end": info["end"],
            "period_label": f"FY {info['year']}",
        },
        "item": {"item_id": item_id, "label": label, "statement": statement},
        "value": value,
        "unit": unit,
        "currency": unit if unit == "VND" else None,
        "scope": copy.deepcopy(info["scope"]),
        "report": {
            "report_id": info["document_id"],
            "title": f"{info['report_type']} — {info['year']}",
            "report_type": info["report_type"],
            "source_uri": info["source_uri"],
        },
        "source_report_id": info["document_id"],
        "source_location": {
            "source_uri": info["source_uri"],
            "location_type": "json_pointer",
            "locator": pointer,
            "source_pages": pages,
        },
        "source_pages": pages,
        "source_pointer": pointer,
        "original_text": None,
        "data_status": "reported",
        "status": "reported",
        "status_note": "Normalized from supplied BSR JSON extract; original source text was not supplied.",
        "synthetic": False,
    }
    if observation_year is not None:
        record["observation_year"] = observation_year
    return record


def _workforce_records(raw, info):
    if "document" in raw:
        source = raw["social"]["employees"]
        current_key = f"total_at_{info['year']}_12_31"
        current_pointer = ["social", "employees", current_key]
        total = source[current_key]
        pages = _pages(source)
        if not pages and isinstance(source.get("source_page"), int):
            pages = [source["source_page"]]
        yield _record(
            info, "workforce.total", "Total employees", total, "person",
            _pointer(current_pointer), pages, statement="social_workforce",
            observation_year=info["year"],
        )
    else:
        source = raw["social"]["workforce"]
        current_key = f"employees_{info['year']}_12_31"
        pages = _pages(source)
        record = _record(
            info, "workforce.total", "Total employees", source[current_key], "person",
            _pointer(["social", "workforce", current_key]), pages,
            statement="social_workforce", observation_year=info["year"],
        )
        if info["year"] == 2025:
            # The reviewed consolidated PDF describes the 1,946 figure as the
            # company plus subsidiaries at 31 December. This does not establish
            # the entity boundary or measurement date of the ESG 1,594 figure.
            record["scope"] = {
                "scope_id": "consolidated_group",
                "entity_set": "parent_plus_subsidiaries",
                "description": "Company and subsidiaries in the 2025 consolidated financial statements.",
                "verification_status": "verified",
                "source_document": info["source_file"],
                "source_pages": pages,
                "source_pointer": record["source_pointer"],
                "review_basis": "User-provided review of the consolidated BSR 2025 PDF; value and page locator also occur in the supplied Extract JSON.",
            }
            record["reporting_period"] = {
                "fiscal_year": info["year"],
                "period_type": "instant",
                "period_start": None,
                "period_end": f"{info['year']}-12-31",
                "period_label": f"As of {info['year']}-12-31",
            }
            record["measurement_date"] = {
                "value": f"{info['year']}-12-31",
                "verification_status": "verified",
                "source_document": info["source_file"],
                "source_pages": pages,
            }
            record["employee_definition"] = {
                "definition_id": "total_employees",
                "verification_status": "unverified",
                "note": "The precise employee inclusion and exclusion rules have not been verified against the ESG metric.",
            }
        yield record


def adapt_report(path):
    path = Path(path)
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    info = _source_info(raw)
    records = list(_workforce_records(raw, info))
    if "financial_and_economic_value" in raw:
        records.extend(
            _record(info, item_id, label, value, unit, pointer, pages, statement="financial_and_economic_value")
            for item_id, label, value, unit, pointer, pages in _leaf_records(
                raw["financial_and_economic_value"], ["financial_and_economic_value"], [], None, "financial"
            )
        )
    if "financial_context" in raw:
        records.extend(
            _record(info, item_id, label, value, unit or "VND", pointer, pages, statement="financial_context")
            for item_id, label, value, unit, pointer, pages in _leaf_records(
                raw["financial_context"], ["financial_context"], [], raw["financial_context"].get("unit"), "financial"
            )
        )
    return records, {
        "source_file": path.name,
        "document_id": info["document_id"],
        "source_schema": info["source_schema"],
        "schema_difference": (
            "Uses document.reporting_period_* and social.employees with explicit consolidated boundary."
            if info["source_schema"] == "document_v1" else
            "Uses metadata.reporting_period and social.workforce; 2025 workforce.total has reviewed consolidated parent-plus-subsidiaries boundary and 31 December measurement date; employee definition remains unverified."
        ),
    }


def adapt_reports(paths=None):
    paths = [Path(p) for p in paths] if paths else sorted(DEFAULT_SOURCE_DIR.glob("BCTC_BSR_*_esg.json"))
    records = []
    source_notes = []
    for path in paths:
        report_records, note = adapt_report(path)
        records.extend(report_records)
        source_notes.append(note)
    return {
        "schema_version": "0.1",
        "adapter": "tools.financial_adapter",
        "company_id": "BSR",
        "synthetic": False,
        "records": records,
        "source_schema_notes": source_notes,
    }


def add_bsr_workforce_context(graph, claims, financial_records, candidate):
    """Show separate ESG, consolidated BCTC and separate BCTC provenance without an FC01 finding."""
    check = candidate["checks"][0]
    claim = next((item for item in claims if item["claim_id"] == check["esg_claim_id"]), None)
    financial = next((item for item in financial_records if item["disclosure_id"] == check["financial_disclosure_id"]), None)
    if claim is None or financial is None:
        return graph
    nodes = {node["id"] for node in graph["nodes"]}

    def add_node(node):
        if node["id"] in nodes:
            raise ValueError(f"Duplicate financial graph node: {node['id']}")
        graph["nodes"].append(node)
        nodes.add(node["id"])

    company_node = f"company:{claim['company_id']}"
    claim_node = f"claim:{claim['claim_id']}"
    next(node for node in graph["nodes"] if node["id"] == claim_node)["workforce_context"] = copy.deepcopy(
        claim.get("workforce_context") or check["esg_measurement_context"]
    )
    report_node = "financial-report:" + financial["source_report_id"]
    disclosure_node = "financial:" + financial["disclosure_id"]
    source_node = "financial-source:" + financial["disclosure_id"]
    add_node({
        "id": report_node, "type": "FinancialReport", "label": financial["report"]["title"],
        "company_id": financial["company_id"], "report_year": financial["report_year"],
        "report_type": financial["report"]["report_type"],
        "source_uri": financial["report"]["source_uri"],
    })
    add_node({
        "id": disclosure_node, "type": "FinancialDisclosure", "label": "BCTC hợp nhất 2025: 1.946 người",
        "disclosure_id": financial["disclosure_id"], "value": financial["value"],
        "unit": financial["unit"], "scope": copy.deepcopy(financial["scope"]),
        "measurement_date": copy.deepcopy(financial.get("measurement_date")),
        "employee_definition": copy.deepcopy(financial.get("employee_definition")),
        "comparison_status": "candidate_only",
    })
    add_node({
        "id": source_node, "type": "FinancialEvidence", "label": "BCTC hợp nhất 2025 p.14",
        "source_document": financial["scope"].get("source_document"),
        "source_file": f"BCTC_BSR_{financial['report_year']}_esg.json",
        "source_pages": financial["source_pages"],
        "json_pointer": financial["source_pointer"],
        "source_uri": financial["report"]["source_uri"],
    })
    graph["edges"].extend([
        {"source": company_node, "target": report_node, "label": "HAS_FINANCIAL_REPORT"},
        {"source": report_node, "target": disclosure_node, "label": "CONTAINS_FINANCIAL_DISCLOSURE"},
        {"source": disclosure_node, "target": source_node, "label": "SOURCED_FROM_FINANCIAL"},
        {"source": claim_node, "target": disclosure_node, "label": "HAS_FINANCIAL_CANDIDATE"},
    ])
    for observation in check.get("related_financial_observations", []):
        separate_report = "financial-report:BSR-BCTC-SEPARATE-2025"
        if separate_report not in nodes:
            add_node({
                "id": separate_report, "type": "FinancialReport",
                "label": observation["source_document"], "company_id": claim["company_id"],
                "report_year": claim["report_year"], "report_type": "separate",
                "source_locator_status": "pending",
            })
            graph["edges"].append({"source": company_node, "target": separate_report, "label": "HAS_FINANCIAL_REPORT"})
        observation_node = "financial-observation:" + observation["observation_id"]
        add_node({
            "id": observation_node, "type": "FinancialObservation",
            "label": "BCTC riêng 2025: 1.594 người",
            **copy.deepcopy(observation),
            "comparison_status": "context_only_not_matched_to_esg_boundary",
        })
        graph["edges"].extend([
            {"source": separate_report, "target": observation_node, "label": "CONTAINS_FINANCIAL_OBSERVATION"},
            {"source": claim_node, "target": observation_node, "label": "RELATED_FINANCIAL_OBSERVATION"},
        ])
    return graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    result = adapt_reports(args.paths or None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(result['records'])} financial records to {args.output}")


if __name__ == "__main__":
    main()
