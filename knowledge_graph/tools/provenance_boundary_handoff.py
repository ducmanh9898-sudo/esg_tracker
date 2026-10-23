"""Create a conservative Extract handoff for BSR claim provenance/boundary."""

import copy
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLAIMS = ROOT / "output" / "normalized_claims.json"
ENRICHED = ROOT / "output" / "bsr_2025_claims_enriched.json"
OUT = ROOT / "data" / "handoff" / "provenance_boundary_handoff.json"


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def _enrichment_index():
    if not ENRICHED.exists():
        return {}
    return {claim["claim_id"]: claim for claim in _read(ENRICHED)}


def _boundary(reason):
    return {
        "status": "unverified",
        "basis": None,
        "included_entities": None,
        "excluded_entities": None,
        "measurement_scope": None,
        "consolidation_approach": None,
        "source_pages": None,
        "missing_fields": [
            "boundary.basis",
            "boundary.included_entities",
            "boundary.excluded_entities",
            "boundary.measurement_scope",
            "boundary.consolidation_approach",
            "boundary.source_pages",
        ],
        "uncertainty_reason": reason,
    }


def _record(claim, evidence, enrichment):
    year = claim["report_year"]
    enriched_evidence = None
    if enrichment:
        enriched_evidence = next(
            (
                result for result in enrichment.get("provenance", {}).get("evidence_results", [])
                if result.get("matched_page") in (evidence.get("source_pages") or [])
            ),
            None,
        )
    source_text = evidence.get("source_text")
    extraction_status = "pending_provenance"
    extraction_reason = "Claim/evidence không có boundary; không suy luận từ thiếu field."
    if enrichment:
        extraction_status = enrichment.get("provenance", {}).get("status", "pending_provenance")
        extraction_reason = enrichment.get("provenance", {}).get("reason", extraction_reason)
        # Only carry text that the enrichment tool obtained from the source chunk.
        if enrichment.get("original_text") and extraction_status == "resolved":
            source_text = enrichment["original_text"]
    missing = []
    for field, value in (
        ("report_id", None),
        ("period_type", None),
        ("original_text", source_text),
    ):
        if value is None:
            missing.append(field)
    if enriched_evidence and enriched_evidence.get("pending_provenance"):
        missing.extend(enriched_evidence["pending_provenance"])
    missing.extend([
        "boundary.basis",
        "boundary.included_entities",
        "boundary.excluded_entities",
        "boundary.measurement_scope",
        "boundary.consolidation_approach",
        "boundary.source_pages",
    ])
    return {
        "claim_id": claim["claim_id"],
        "evidence_id": evidence["evidence_id"],
        "company_id": claim["company_id"],
        "report_id": None,
        "report_year": year,
        "period_type": None,
        "source_file": evidence.get("source_file"),
        "source_pages": evidence.get("source_pages"),
        "json_pointer": evidence.get("json_pointer"),
        "original_text": source_text,
        "extraction_status": extraction_status,
        "boundary": _boundary("Claim/evidence không cung cấp reporting boundary; không suy luận từ thiếu field."),
        "missing_fields": sorted(set(missing)),
        "uncertainty_reason": extraction_reason + "; reporting boundary chưa được cung cấp/xác minh.",
    }


def build_handoff():
    claims = _read(CLAIMS)
    enrichment = _enrichment_index()
    records = []
    for claim in sorted(
        (claim for claim in claims if claim.get("company_id") == "BSR"),
        key=lambda claim: (-int(claim["report_year"]), claim["claim_id"]),
    ):
        for evidence in claim.get("evidence", []):
            records.append(_record(claim, evidence, enrichment.get(claim["claim_id"])))
    return {
        "schema_version": "0.1",
        "handoff_scope": "BSR ESG claim/evidence provenance and reporting-boundary gaps; no inferred boundary or text.",
        "priority_order": ["BSR 2025", "BSR 2024", "BSR 2023"],
        "records": records,
    }


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(build_handoff(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(build_handoff()['records'])} handoff records to {OUT}")


if __name__ == "__main__":
    main()
