# Hợp đồng bàn giao Extract → Graph (v1)

**Đầu ra Extract:** một báo cáo nguồn và một reporting entity/boundary → **một JSON** tại `data/extract/esg/` hoặc `data/extract/financial/`. Mỗi batch → **một** `data/extract/manifest.json`. PDF đặt tại `data/source/` hoặc có `document.source_locator` truy cập được. Coverage và `issue_log` nằm trong JSON; không cần giao chunk/Markdown trùng. BCTC riêng và hợp nhất là hai JSON, hai report ID. Số so sánh kỳ trước vẫn nằm trong JSON của báo cáo chứa nó.

**Đầu vào Graph:** `data/config/corpus_config.json` chọn file và adapter. `kg.pipeline` kiểm tra path/SHA-256 của file được chọn trong manifest; adapter chuyển raw JSON thành Graph input. Extract **không** phải tạo RDF, normalized claims, findings hay assessments. [`graph-input-v2.json`](../schemas/graph-input-v2.json) kiểm tra **claim ESG sau adapter**; [`financial-candidate-v1.json`](../schemas/financial-candidate-v1.json) kiểm tra financial candidate của handoff mới. Hai schema normalized này không phải schema JSON Extract bàn giao.

## Hai định dạng nguồn đang đọc được

| Loại | Schema bàn giao mới | Adapter và mapping | Lưu ý |
| --- | --- | --- | --- |
| ESG có cấu trúc | [`extract-esg-handoff-v1.json`](../schemas/extract-esg-handoff-v1.json) | `kg.adapters.adapt_structured_esg`: `environment`/`social`/`governance` → E/S/G claims; `<topic>.records[]` → claims; target → target RDF; policy/governance không cần metric/value/unit/target. | Corpus cũ BSR còn dùng `curated_selection`; không áp schema mới hồi tố cho JSON lịch sử. |
| BCTC riêng **và** hợp nhất mới | [`extract-financial-handoff-v1.json`](../schemas/extract-financial-handoff-v1.json) | `kg.adapters.adapt_financial_handoff`, corpus adapter `financial_handoff`: `structured_key_metrics[].measurements[]` → financial candidates/RDF. | Một cấu trúc; `document.financial_statement_scope` phải là `Separate` hoặc `Consolidated`. Report ID, boundary và measurement ID giữ riêng. OCR chưa căn chỉnh không thành metric. |
| BCTC lịch sử | Format legacy khác | `adapt_separate_full`/`bsr_separate_full` cho BCTC riêng cũ; `tools.financial_adapter.adapt_report`/`bsr_financial` cho hợp nhất cũ. | Corpus thật giữ nguyên adapter hiện tại; không đổi nhãn boundary để ép nạp. |
| Batch | [`extract-batch-manifest-v1.json`](../schemas/extract-batch-manifest-v1.json) | `kg.pipeline.build`: `files[].path` và `sha256` phải khớp file được chọn. | Manifest có thể liệt kê file chưa được chọn; config quyết định file nào nạp. |

Ví dụ **synthetic/example**, không thuộc corpus thật: [`extract-esg.synthetic.json`](examples/extract-esg.synthetic.json), [`extract-financial-separate.synthetic.json`](examples/extract-financial-separate.synthetic.json), [`extract-financial-consolidated.synthetic.json`](examples/extract-financial-consolidated.synthetic.json), [`manifest.synthetic.json`](examples/manifest.synthetic.json). [`corpus-config.synthetic.json`](examples/corpus-config.synthetic.json) chọn đúng ba JSON này để chạy pipeline mẫu; không sửa corpus chính. `synthetic://` chỉ là ký hiệu, không phải locator PDF thật.

## Envelope và field bàn giao

Các tên sau là tên adapter **thực sự đọc**. `schema_version`, `document`, `coverage`, `issue_log` là bắt buộc trong handoff v1. `document.company_id`, `report_year`, `source_file`, `reporting_entity` (ESG) hoặc `financial_statement_scope` (BCTC) là định danh cấu trúc. Thiếu định danh báo cáo là lỗi cấu trúc; thiếu field nghiệp vụ của từng claim/measurement được tiếp nhận và đưa vào review, không suy đoán. `source_locator` có thể null để không chặn batch thử nghiệm; PDF/locator truy cập được vẫn cần cho kiểm tra bằng chứng thật.

| Field raw Extract | Kiểu; null | Áp dụng và mapping |
| --- | --- | --- |
| `document.company_id`, `report_year`, `report_type` | string, integer, `"ESG"`; không null | ESG; phải khớp manifest/config. BCTC dùng `document_key`, `company_id`, `report_year`, `financial_statement_scope=Separate/Consolidated`. |
| `document.source_file`, `source_locator` | string không null; string/null | Cả hai; tên PDF vào evidence/RDF. Locator hiện giữ ở raw JSON, chưa RDF hóa. |
| `document.reporting_period_start/end`, `reporting_date` | string/null | ESG dùng start/end; BCTC dùng reporting_date. Đây là kỳ báo cáo, không thay kỳ measurement. |
| `document.publication_date`, `extraction_timestamp` | string/null | Cả hai; tách ngày phát hành, thời gian trích, năm báo cáo và kỳ đo. |
| `environment`/`social`/`governance`.`<topic>.records[]` | object/array | ESG; nhánh đầu quyết định E/S/G, `<topic>` thành topic Graph. Chỉ cần nhánh có dữ liệu. |
| `record_id`, `evidence_id`, `claim_type` | string/string/enum; không null | Mỗi record ESG; giữ ID ổn định. `claim_type`: `measurement`, `target`, `policy`, `governance_statement`. |
| `metric_id`, `metric_definition` | string/null; string/null | ESG; có thể vắng/null. Policy/governance không cần metric. Claim không metric vẫn có ID và evidence/RDF, nhưng không vào phép so metric. |
| `year`, `period_type`, `period_type_verified` | integer/null; string/null; boolean | ESG từng claim; tách khỏi kỳ/năm của báo cáo. Vắng/null nghĩa chưa biết, không tự lấy `document.report_year`. |
| `reporting_boundary`, `reporting_boundary_verified`, `scope` | string/null; boolean; string/null | ESG từng claim; tách khỏi `document.reporting_entity`. Không lấy boundary báo cáo làm boundary đã xác minh cho claim. |
| `value`, `value_status`, `unit` | number/string/bool/null; enum; string/null | ESG measurement/target; value vắng/null được nhận là thiếu. Policy/governance không cần value/unit/target và mặc định `not_applicable`. |
| `source_pages`, `original_text` | integer[]; string/null; có thể vắng | ESG; trang và nguyên văn vào evidence, JSON Pointer do adapter tạo. Thiếu được ghi `source_pages_missing`/`original_text_missing` ở input review. |
| `review_status`, `extraction_status`, `uncertainty` | string; string; string[] | ESG; adapter giữ ở normalized claim, RDF giữ status và uncertainty. |
| `structured_key_metrics[].record_id`, `metric_code`, `measurements[]` | string/string/array | Cả hai BCTC; một record nguồn tạo nhiều candidate. Mỗi measurement có `measurement_id` string ổn định, `period` integer/null, `period_type` string/null, `value` number/null, `unit` string/null, `unit_multiplier` number/null. Graph dùng `document_key:measurement_id`; file legacy thiếu field này giữ ID cũ. |
| `structured_key_metrics[].source_page`, `claim_text` | integer/null; string/null | Cả hai BCTC; trang, OCR gốc. Thiếu trang/text vào `review_reasons` của normalized candidate; OCR chưa là trích dẫn đã review. |
| `structured_key_metrics[].review_status`, `confidence`, `extraction_notes` | string; number/null; string/null | Cả hai BCTC; giữ nguyên ở candidate/RDF. Kiểm toán báo cáo không tự làm extraction được review. |
| `monetary_groups`, `numeric_occurrences`, `pages` | array; array; `{page_number,text}[]` | Cả hai BCTC; bảo tồn ở raw JSON. Hai nhóm OCR không căn cột/kỳ không tự thành measurement; `pages.text` là OCR context. |
| `coverage`, `issue_log` | object, array; không null | Cả hai; vùng đã trích/kiểm tra và vấn đề. Graph hiện giữ ở raw JSON/manifest, chưa chuyển toàn bộ issue log vào RDF. |
| Manifest `files[]` | array object; không null | Mỗi file có `path`, `company_id`, `report_year`, `report_type`, `reporting_entity`, `coverage`, `sha256`; path tương đối root repository. |

**Trạng thái thiếu:** `available` = giá trị đọc được; `missing` = trường phù hợp nhưng không có giá trị; `ambiguous` = có nhiều cách đọc; `unknown` = chưa rõ; `not_applicable` = field không áp dụng. Không dùng `0` hoặc chuỗi rỗng thay null. Giữ các phương án khác nhau bằng record/variant riêng. Trong BCTC, `dimension="X"` chỉ là financial context; Graph dùng `financial_context`, không tạo dimension ESG thứ tư. Có thể đặt `value_status` trên từng measurement; nếu bỏ, adapter suy `missing` khi value null. Kỳ không rõ giữ null và không tạo Period RDF giả.

**Điều kiện nhận:** JSON đúng cú pháp, đúng schema bàn giao mới và hash/path trong manifest khớp; config chọn đúng adapter và boundary. Với `schema_version` bàn giao v1, pipeline tự kiểm tra raw schema và đối chiếu company/year/report type/boundary với config và manifest; file legacy giữ adapter cũ. Thiếu value/kỳ/trang/nguyên văn nghiệp vụ không loại cả batch. Pipeline kiểm tra normalized ESG và financial candidates bằng `jsonschema`, chạy SHACL chất lượng và lưu review.

**Điều kiện đánh giá:** claim ESG handoff v1 chỉ vào phép đánh giá số khi có metric, kỳ claim, loại kỳ, trang, nguyên văn, boundary đã xác minh và `review_status=reviewed`; việc có value hay không do rule xử lý. Thiếu một trong các điều kiện này vẫn giữ claim/RDF nhưng `assessment_eligible=false` và ghi review; không sinh kết luận mạnh. `DisclosureGap` còn cần applicability và coverage tìm kiếm đã xác minh. Policy không metric/value không thành gap. Financial candidates unreviewed và boundary chưa xác minh không tự tạo finding ESG–tài chính; Separate/Consolidated không được so trực tiếp.

## Chạy kiểm tra mẫu

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_extract_graph_contract -v
.\.venv\Scripts\python.exe -B -m kg.test_runner
.\.venv\Scripts\python.exe -B -m kg.pipeline --config docs/examples/corpus-config.synthetic.json --output-dir .tmp/contract-sample
```

Test đầu kiểm tra JSON Schema nguồn, manifest SHA-256, adapter, normalized schema, RDF/SPARQL và pipeline với output tạm. Lệnh cuối tạo output mẫu dưới `.tmp/`, không thay `output/kg_v2`. Contract không buộc file legacy đổi định dạng; batch mới theo schema mới cần được chọn trong `data/config/corpus_config.json` trước khi pipeline chính nạp.
