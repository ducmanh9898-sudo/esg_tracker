from pathlib import Path

import pymupdf

from src.extraction.toolkit import (
    build_document_spec,
    discover_pdfs,
    extract_measurements,
    extract_financial_table_claims,
    infer_financial_statement_scope,
    infer_metrics,
    is_claim_candidate,
    load_yaml,
    run_extraction,
)


ROOT = Path(__file__).resolve().parents[1]
TOOLKIT_CONFIG = load_yaml(ROOT / "config" / "extraction_toolkit.yml")
METRICS_CONFIG = load_yaml(ROOT / "config" / "metrics.yml")


def test_filename_metadata_supports_multiple_oil_and_gas_companies(tmp_path):
    financial_dir = tmp_path / "BCTC"
    esg_dir = tmp_path / "BCESG"
    financial_dir.mkdir()
    esg_dir.mkdir()

    gas = build_document_spec(financial_dir / "BCTC_GAS_2025.pdf", TOOLKIT_CONFIG)
    plx = build_document_spec(esg_dir / "PLX_2024.pdf", TOOLKIT_CONFIG)
    pvd = build_document_spec(esg_dir / "PVD_2023.pdf", TOOLKIT_CONFIG)

    assert (gas.company_id, gas.report_year, gas.report_type) == ("GAS", 2025, "financial_statements")
    assert (plx.company_id, plx.report_year, plx.report_type) == ("PLX", 2024, "ESG")
    assert (pvd.company_id, pvd.subsector) == ("PVD", "oilfield_services")


def test_financial_report_type_can_appear_after_a_date(tmp_path):
    path = tmp_path / "20260326 - BSR - BCTC rieng da kiem toan 31.12.2025.pdf"
    spec = build_document_spec(path, TOOLKIT_CONFIG)
    assert spec.report_type == "financial_statements"
    assert spec.company_id == "BSR"
    assert spec.report_year == 2025


def test_unknown_company_is_not_mislabeled_as_oil_and_gas(tmp_path):
    path = tmp_path / "BCESG" / "ACB_2025.pdf"
    path.parent.mkdir()
    spec = build_document_spec(path, TOOLKIT_CONFIG)
    assert spec.company_id == "ACB"
    assert spec.industry == "Unknown"


def test_discovery_excludes_reference_standard_folders(tmp_path):
    esg = tmp_path / "BCESG" / "PLX_2025.pdf"
    standard = tmp_path / "Bộ tiêu chuẩn GRI" / "GRI_2021.pdf"
    esg.parent.mkdir()
    standard.parent.mkdir()
    esg.write_bytes(b"pdf")
    standard.write_bytes(b"pdf")
    assert discover_pdfs(tmp_path, TOOLKIT_CONFIG) == [esg]


def test_measurement_parser_handles_vietnamese_and_english_units():
    values = extract_measurements(
        "Phát thải Scope 1 là 1.790.388 tCO2e, tỷ lệ tái chế 41,8% và chi phí 109,2 tỷ VND."
    )
    assert [item["value"] for item in values] == [1790388.0, 41.8, 109.2]
    assert [item["unit"] for item in values] == ["tCO2e", "%", "tỷ VND"]


def test_metric_inference_prefers_specific_variant():
    catalog = {
        "GHG_SCOPE_1": {"variants": ["scope 1"]},
        "GHG_INTENSITY": {"variants": ["cường độ phát thải"]},
    }
    assert infer_metrics("Cường độ phát thải Scope 1 giảm", catalog) == ["GHG_INTENSITY", "GHG_SCOPE_1"]


def test_financial_reports_reject_generic_commitment_language():
    text = "Chúng tôi cam kết các thông tin công bố là đúng sự thật."
    assert not is_claim_candidate(text, "financial_statements", ["cam kết"], [], [])


def test_financial_scope_is_taken_from_report_title():
    separate_pages = [{"text": "BÁO CÁO TÀI CHÍNH RIÊNG cho năm tài chính 2025"}]
    consolidated_pages = [{"text": "BÁO CÁO TÀI CHÍNH HỢP NHẤT cho năm tài chính 2025"}]
    assert infer_financial_statement_scope(separate_pages) == "Separate"
    assert infer_financial_statement_scope(consolidated_pages) == "Consolidated"


def test_financial_table_inherits_vnd_and_links_current_comparative_values(tmp_path):
    path = tmp_path / "20260326_BSR_BCTC_rieng_2025.pdf"
    spec = build_document_spec(path, TOOLKIT_CONFIG)
    pages = [{
        "page_number": 11,
        "text": "\n".join([
            "BÁO CÁO KẾT QUẢ HOẠT ĐỘNG KINH DOANH",
            "Đơn vị: VND",
            "Năm nay",
            "Năm trước",
            "Lợi nhuận sau thuế thu nhập doanh nghiệp",
            "60",
            "5.207.340.928.205",
            "316.727.575.109",
        ]),
        "extraction_method": "ocr_sidecar",
        "confidence": 0.70,
    }]
    catalog = {
        "FIN_PAT": {
            "name": "Lợi nhuận sau thuế",
            "dimension": "X",
            "topic": "X_FINANCIAL_CONTEXT",
            "variants": ["lợi nhuận sau thuế", "profit after tax"],
        }
    }
    claims = extract_financial_table_claims(spec, pages, catalog, "Separate")
    assert len(claims) == 1
    assert claims[0]["value"] == 5_207_340_928_205
    assert claims[0]["comparison"]["value"] == 316_727_575_109
    assert claims[0]["unit"] == "VND"
    assert claims[0]["boundary"] == "Separate"


def test_end_to_end_run_emits_claims_and_ocr_review(tmp_path):
    source_dir = tmp_path / "BCESG"
    source_dir.mkdir()
    pdf_path = source_dir / "PLX_2025.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Scope 1 emissions were 1,250 tCO2e in 2025 and decreased compared with 2024.")
    document.new_page()
    document.save(pdf_path)
    document.close()

    spec = build_document_spec(pdf_path, TOOLKIT_CONFIG)
    run_dir = run_extraction(
        specs=[spec],
        output_root=tmp_path / "out",
        run_id="test_run",
        toolkit_config=TOOLKIT_CONFIG,
        metrics_config=METRICS_CONFIG,
    )

    claims = load_yaml_json(run_dir / "claims.json")["records"]
    review = load_yaml_json(run_dir / "review_queue.json")["items"]
    manifest = load_yaml_json(run_dir / "run_manifest.json")

    assert manifest["document_count"] == 1
    assert any(item["metric_code"] == "GHG_SCOPE_1" for item in claims)
    assert any(item["issue_type"] == "OCR_REQUIRED" and item["source_page"] == 2 for item in review)
    assert (run_dir / "claims.csv").exists()
    assert (run_dir / "company_summary.csv").exists()


def test_ocr_sidecar_recovers_scanned_page(tmp_path):
    source_dir = tmp_path / "BCTC"
    source_dir.mkdir()
    pdf_path = source_dir / "BCTC_BSR_2024.pdf"
    document = pymupdf.open()
    document.new_page()
    document.save(pdf_path)
    document.close()

    ocr_dir = tmp_path / "ocr" / "BCTC_BSR_2024"
    ocr_dir.mkdir(parents=True)
    (ocr_dir / "page-1.txt").write_text(
        "Lợi nhuận sau thuế năm 2024 là 591.091.587.455 VND theo báo cáo tài chính hợp nhất.",
        encoding="utf-8",
    )
    spec = build_document_spec(pdf_path, TOOLKIT_CONFIG)
    run_dir = run_extraction(
        specs=[spec],
        output_root=tmp_path / "out",
        run_id="ocr_run",
        toolkit_config=TOOLKIT_CONFIG,
        metrics_config=METRICS_CONFIG,
        ocr_root=tmp_path / "ocr",
    )
    pages = load_yaml_json(run_dir / "documents" / spec.document_key / "pages.json")["pages"]
    claims = load_yaml_json(run_dir / "claims.json")["records"]

    assert pages[0]["extraction_method"] == "ocr_sidecar"
    assert pages[0]["extraction_status"] == "available"
    assert any(item["metric_code"] == "FIN_PAT" for item in claims)


def test_financial_document_without_claims_is_sent_to_review(tmp_path):
    source_dir = tmp_path / "BCTC"
    source_dir.mkdir()
    pdf_path = source_dir / "BCTC_GAS_2025.pdf"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), "Bao cao tai chinh hop nhat cho nam tai chinh 2025.")
    document.save(pdf_path)
    document.close()

    spec = build_document_spec(pdf_path, TOOLKIT_CONFIG)
    run_dir = run_extraction(
        specs=[spec],
        output_root=tmp_path / "out",
        run_id="no_claims_run",
        toolkit_config=TOOLKIT_CONFIG,
        metrics_config=METRICS_CONFIG,
    )
    review = load_yaml_json(run_dir / "review_queue.json")["items"]

    item = next(entry for entry in review if entry["issue_type"] == "NO_CLAIMS_EXTRACTED")
    assert item["priority"] == "high"
    assert "do not treat" in item["recommended_action"]


def load_yaml_json(path: Path):
    import json

    return json.loads(path.read_text(encoding="utf-8"))
