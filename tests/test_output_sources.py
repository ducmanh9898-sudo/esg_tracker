from pathlib import Path
import pytest

from src.database.output_sources import (
    BSR_DOCUMENTS,
    discover_output_documents,
    infer_output_metric,
    output_manifest,
    summary_claim_rows,
)


OUTPUT = Path(__file__).resolve().parents[2] / "output"
requires_bsr_corpus = pytest.mark.skipif(
    len(discover_output_documents(OUTPUT)) != len(BSR_DOCUMENTS),
    reason="Optional local BSR integration corpus ../output is not included in the source repository.",
)


@requires_bsr_corpus
def test_discovers_only_six_bsr_2023_2025_documents():
    documents = discover_output_documents(OUTPUT)
    assert [document.stem for document in documents] == list(BSR_DOCUMENTS)
    assert {document.year for document in documents} == {2023, 2024, 2025}


@requires_bsr_corpus
def test_output_bundle_inventory_is_complete():
    manifest = output_manifest(OUTPUT)
    assert manifest["document_count"] == 6
    assert manifest["page_count"] == 289
    assert manifest["chunk_count"] == 74
    assert manifest["summary_count"] == 6
    assert manifest["structured_fact_count"] > 50


def test_metric_inference_does_not_treat_eii_as_total_energy():
    assert infer_output_metric("EII_percent_series") is None
    assert infer_output_metric("total_energy_GJ_series") == "ENERGY_TOTAL"
    assert infer_output_metric("scope_1_tCO2e") == "GHG_SCOPE_1"
    assert infer_output_metric("state_budget_contribution_billion_VND") == "TAX_PAID"
    assert infer_output_metric("non_hazardous_waste_tonnes") == "NON_HAZ_WASTE"
    assert infer_output_metric("boom_sets") is None
    assert infer_output_metric("primary_total_scope_1_plus_2_tCO2e") is None


@requires_bsr_corpus
def test_summary_claims_exclude_data_quality_checklists():
    document = next(d for d in discover_output_documents(OUTPUT) if d.stem == "BSR_2025")
    claims = summary_claim_rows(document)
    assert claims
    assert all("điểm phải đối soát" not in claim["text"].lower() for claim in claims)
    assert {claim["pillar"] for claim in claims} <= {"E", "S", "G"}
