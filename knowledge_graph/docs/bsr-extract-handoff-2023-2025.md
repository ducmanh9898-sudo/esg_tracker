# Yêu cầu bàn giao Extract cho demo đối chiếu BSR 2023–2025

> Cập nhật tích hợp: format độc lập `corporate-extract-1.0` đã có entry point `kg.corporate_pipeline`. Xem [hướng dẫn nhận batch và review](corporate-graph-runbook.md). Những khoảng trống adapter mô tả bên dưới áp dụng cho luồng/schema legacy; batch mới dùng entry point độc lập và cùng RDF core.

> **Ghi chú tích hợp nội bộ Graph:** tài liệu này mô tả schema và adapter đang có trong repository. Người làm Extract độc lập không cần đọc hoặc thực hiện theo các đường dẫn nội bộ bên dưới. Hãy gửi cho họ [gói bàn giao độc lập](../handoff/bsr_extract_2023_2025_v1/README.md); phía Graph chịu trách nhiệm chuyển format đó sang schema nội bộ sau khi nhận dữ liệu.

**Mục tiêu:** tìm và giải thích các số liệu hoặc phát biểu *có vẻ mâu thuẫn* giữa báo cáo ESG và BCTC của BSR, trong cùng báo cáo hoặc qua các năm. Kết quả cuối là `Supported`, `Contradicted` hoặc `NeedsReview` trong phạm vi phép kiểm tra cụ thể; không gắn nhãn doanh nghiệp greenwashing.

**Quyết định đã chốt:** dùng cả BCTC **riêng và hợp nhất** của từng năm 2023–2025; giữ chúng thành hai boundary tách biệt. Ưu tiên (1) số học trong một báo cáo, (2) cùng observation period được công bố khác nhau qua các báo cáo, (3) cặp ESG–BCTC sau khi xác minh cùng định nghĩa, kỳ và boundary. Mạnh xác nhận record và cặp so sánh trước kết luận mạnh. Extractor và LLM chỉ tạo candidate `unreviewed`; không tự đặt `reviewed` hoặc gold.

**Phân công:** bên Extract giao dữ liệu nguồn theo format dưới đây; Graph tiếp nhận, kiểm tra và xây rule/guard còn thiếu. Extract không tạo RDF, finding, nhãn greenwashing hay quyết định `Contradicted`.

## Bộ file cần giao

1. **PDF gốc chính thức**, một file cho mỗi báo cáo và boundary, kèm bảng nguồn: `source_id`, tên công ty, loại báo cáo, năm báo cáo, hợp nhất/riêng nếu là BCTC, URL công bố, ngày tải, SHA-256, số trang vật lý. Tra [trang báo cáo BSR](https://bsr.com.vn/bao-cao) và [trang BCTC BSR](https://bsr.com.vn/bao-cao-tai-chinh), rồi kiểm tra cover/kỳ bên trong từng PDF. BSR ESG 2024 và 2025 đã có PDF canonical trong `data/source/pdf/`; 2023 và các PDF BCTC 2023–2025 chưa có trong thư mục này. Không dùng số trang của artifact text 68 trang để định vị PDF 2025 canonical 134 trang.
2. **Chín JSON UTF-8**, một file cho mỗi PDF và mỗi reporting boundary: ba ESG JSON (2023, 2024, 2025), ba BCTC riêng và ba BCTC hợp nhất. Nếu ESG 2023 nằm trong một chương của báo cáo thường niên, giữ đúng tên/loại PDF vật lý và đánh dấu coverage là chương/vùng đã trích; không gọi PDF đó là báo cáo ESG độc lập nếu nguồn không nói vậy. Số so sánh của năm trước nằm trong JSON của báo cáo chứa bảng đó dưới dạng observation riêng, không bị gộp với số công bố trong báo cáo năm trước.
3. **Một batch manifest** theo [`extract-batch-manifest-v1.json`](../schemas/extract-batch-manifest-v1.json): mỗi JSON có path, company/year/type/boundary, coverage và SHA-256 của **JSON**. Hash PDF là trường nguồn riêng; hai loại hash không thay thế nhau. Config Graph sẽ chọn file cần nạp.
4. **Issue log và coverage** trong từng JSON: trang/vùng đã tìm, chưa tìm, parse lỗi, extract lỗi, không tìm thấy, và phần thực sự đã được reviewer xác nhận. `not_found` hoặc lỗi kỹ thuật không đồng nghĩa `disclosure_absence`.

## Format ESG mà Graph hiện đọc

**Format ưu tiên để nạp ngay:** [`extract-esg-handoff-v2.json`](../schemas/extract-esg-handoff-v2.json), `schema_version="extract-esg-2.0"`, với canonical chunks và source registry do parser dự án tạo. Bên Extract có thể dùng công cụ trích xuất khác, nhưng phải gắn record vào đúng `chunk_id` và span của artifact canonical đã bàn giao; không đoán locator bằng cách tìm lại chuỗi sau khi mất cấu trúc. Validator v2 kiểm tra PDF hash, source ID, chunk, exact span, element/cell và trang. Với ESG 2024–2025, PDF và parse artifact đã có. Với 2023, phải xác minh PDF vật lý trước, rồi tạo artifact canonical cùng quy ước.

Nếu bên Extract **không thể** gắn vào canonical chunks, có thể bàn giao [`extract-esg-handoff-v1.json`](../schemas/extract-esg-handoff-v1.json) cùng PDF, hash, exact quote và metadata trang/bảng bổ sung. Graph đọc được v1 nhưng **v1 chưa tự kiểm chứng hash PDF/span và không biểu diễn claim tự do như v2**; đây là đường tạm để tôi viết adapter/provenance check trước khi đưa vào đánh giá mạnh. Không báo rằng v1 có cùng mức kiểm chứng với v2. Ví dụ v1 hiện có: [`extract-esg.synthetic.json`](examples/extract-esg.synthetic.json); không sao chép dữ liệu synthetic vào BSR.

Mỗi ESG record cần tối thiểu:

| Nhóm | Trường cần giao | Quy tắc |
| --- | --- | --- |
| Định danh | `record_id`, `evidence_id`, `claim_type`, E/S/G và topic | ID ổn định, duy nhất; v2 nhận `claim`, `measurement`, `target`, `policy`, `governance_statement`. |
| Nội dung nguồn | `original_text`, `source_pages`, tên PDF và source hash; nếu là bảng, thêm ID bảng, hàng/cột, header năm/đơn vị, caption và footnote | Quote đúng nguyên văn; trang **vật lý PDF đánh số từ 1**. Trang in tách riêng và có thể null. Đoạn OCR lệch phải ghi issue. |
| Số liệu | `original_value`, `value`, `value_status`, `original_unit`, `unit`, `original_scale`, ghi chú quy đổi | Giữ số/đơn vị gốc và số chuẩn hóa. V1 chấp nhận metadata bổ sung nhưng adapter chưa giữ hết; v2 giữ rõ hơn. Không điền `0` cho missing. |
| Kỳ và ngữ cảnh | observation year/date, `period_type`, năm baseline, năm deadline của target, `metric_id`, `metric_definition`, `scope`, `reporting_boundary`, reporting entity, population/counting method khi liên quan | **Năm báo cáo không tự thành năm đo**. Số cột 2023 trong báo cáo 2024 có observation year 2023 nhưng report year 2024. Không so khác boundary/definition như cùng chỉ tiêu. |
| Trạng thái | `review_status`, `extraction_status`, `uncertainty`, method/model nếu có | V2 dùng `pending_human_review` cho record chưa được Mạnh duyệt. Confidence của LLM không nâng trạng thái review. Trường không rõ là null/unknown và có lý do. |

**Cách hiểu số trong ESG v2:** `original_value`, `original_unit`, `original_scale` chép từ nguồn; `value`/`unit` là số và đơn vị đã chuẩn hóa, `normalization_note` ghi phép đổi. `observation_year` là năm của số liệu; `year_basis` cho biết năm đến từ quote, header bảng hay ngữ cảnh đã review. `document.report_year` chỉ là năm của báo cáo. `evidence[]` phải chứa quote/span chính xác; khi số lấy từ ô bảng, thêm evidence cho header năm và đơn vị, liên kết bằng `header_evidence_ids`. Các trường bắt buộc khác xem đúng schema v2; không dùng ví dụ trong tài liệu này thay schema.

Một file v2 đã qua validator để xem **hình dạng JSON** là [`handoff_01.json`](../data/review/bsr_esg_extract_pilot_review_v10/audit_v2/handoff_01.json). Các record trong đó là heuristic candidate `pending_human_review`, **không phải dữ liệu gold hoặc giá trị đã được Mạnh duyệt**.

Với phép so qua báo cáo, phải giữ **số công bố lần đầu**, **số so sánh được in lại**, chú thích restatement/thay phương pháp và bằng chứng cho từng giá trị. Nếu báo cáo không giải thích việc đổi số, ghi `restatement_status=unknown`, không tự kết luận là không restatement. Hiện Graph chưa đưa đầy đủ trường này qua adapter v1/v2; đây là việc tích hợp cần làm sau khi nhận dữ liệu.

## Format BCTC mà Graph hiện đọc

Dùng [`extract-financial-handoff-v1.json`](../schemas/extract-financial-handoff-v1.json), ví dụ [`extract-financial-consolidated.synthetic.json`](examples/extract-financial-consolidated.synthetic.json). `document.financial_statement_scope` bắt buộc là `Separate` hoặc `Consolidated`; hai scope phải có `document_key` và JSON riêng. `structured_key_metrics[]` có `record_id`, `metric_code`, tên/định nghĩa chỉ tiêu, `source_page`, `claim_text` là dòng nguồn, `review_status`, và `measurements[]`. Mỗi measurement có `measurement_id` duy nhất, `period`, `period_type`, `value`, `value_status`, `unit`, `unit_multiplier`.

Để đối chiếu an toàn, bạn Extract còn cần giao trong JSON nguồn: `document.source_id`, SHA-256 PDF, đường dẫn PDF và page system; với mỗi metric/measurement là bảng/section và số thứ tự dòng; header gắn với từng cột năm; đơn vị ở đầu bảng; dấu âm; ghi chú/footnote; ngày tại thời điểm hay khoảng thời gian; giá trị gốc trước nhân hệ số; tên pháp nhân/boundary; số điều chỉnh và lý do nếu có. Các trường bổ sung này nằm trong JSON nguồn và có thể kiểm tra theo checklist; schema BCTC v1 cho phép chúng nhưng **adapter hiện chưa dùng hết** và cần nâng cấp trước khi đánh giá mâu thuẫn BCTC mạnh. Không biến OCR số rời hoặc bảng chưa căn cột thành `measurements[]` đã xác nhận; để chúng trong `numeric_occurrences`/`monetary_groups` hoặc `issue_log`.

**Tên field bổ sung thống nhất cho BCTC v1:** đặt `source_id`, `source_sha256`, `source_pdf_path`, `page_system="physical_pdf_page_1_based"` trong `document`. Trong từng `measurements[]`, đặt `original_value` (chuỗi đúng cách in), `original_unit`, `original_scale`, `restatement_status` (`unknown`, `not_restatement`, `restated`, `ambiguous`) và `restatement_note`. Đặt `source_evidence` object với `source_page`, `section`, `table_id`, `row`, `column`, `cell_text`, `year_header_text`, `year_header_row`, `unit_header_text`, `unit_header_row`, `caption`, `footnote_text`, `bbox` khi có. Nếu một header/footnote ở trang khác, thêm `header_source_page`/`footnote_source_page`; null nếu chưa xác định. `claim_text` giữ nguyên dòng/bảng đủ để nhìn thấy metric. Đây là **phần mở rộng của file bàn giao**, được schema v1 chấp nhận dưới `additionalProperties`; Graph adapter hiện cần bổ sung để kiểm chứng/chuyển các field này.

**Cách hiểu số trong BCTC v1:** `measurements[].value` là số **như in trong bảng** sau khi bỏ dấu phân tách chữ số, còn `unit_multiplier` là hệ số để đưa về `unit` cơ sở; ví dụ một dòng in `123` trong bảng “triệu đồng” có `value=123`, `unit="VND"`, `unit_multiplier=1000000`, `original_value="123"`, `original_unit="triệu đồng"`. Không nhân sẵn `value` rồi lại để multiplier khác 1. Dấu âm/ngoặc âm phải được giữ trong `original_value` và chuyển đúng sang dấu của `value`.

Ví dụ JSON BCTC đúng cấu trúc schema hiện có: [`extract-financial-separate.synthetic.json`](examples/extract-financial-separate.synthetic.json) và [`extract-financial-consolidated.synthetic.json`](examples/extract-financial-consolidated.synthetic.json). Một `record_id` có thể chứa hai `measurements` nếu bảng của báo cáo 2025 in cả cột 2025 và 2024; mỗi measurement phải có `measurement_id`, `period`, `period_type` và bằng chứng cột năm riêng trong metadata bổ sung.

## Điều kiện nhận và điều kiện kết luận

**Nhận file vào Graph:** JSON đúng schema; manifest khớp hash/path và định danh; PDF đúng hash; ID không trùng xung đột; trang nằm trong PDF; quote/value có thể truy ngược; cột năm và đơn vị có căn cứ; lỗi và coverage được ghi. Record thiếu ngữ cảnh có thể vào Graph ở trạng thái review, không bị biến thành mâu thuẫn.

**Đánh dấu `Contradicted` cho một cặp:** hai giá trị nói về cùng metric/định nghĩa, kỳ đo và loại kỳ, pháp nhân/boundary, scope/population, unit/scale, phương pháp; cả hai có evidence nguồn và review hợp lệ; độ chính xác/làm tròn và restatement đã được xét. Nếu một điều kiện chưa biết, ghi `NeedsReview` kèm lý do. Chênh lệch giữa BCTC riêng và hợp nhất tự nó không phải mâu thuẫn. Target khác actual, hoặc tăng/giảm giữa hai năm đo khác nhau, tự nó cũng không phải mâu thuẫn.

**Việc còn thuộc Graph:** xác minh alias metric và applicability; mở rule so cùng observation period giữa hai báo cáo; đưa restatement và metadata bảng qua adapter; định nghĩa riêng rule ESG–BCTC sau khi có cặp thực sự cùng boundary/định nghĩa; kiểm thử bằng ca đã được người duyệt. Ba rule ready hiện tại chủ yếu kiểm tra quan hệ số học **trong từng báo cáo**. File Extract đầy đủ là điều kiện cần, chưa tự hoàn tất những rule này.

## Thứ tự giao để có demo sớm

1. Giao source registry/PDF 2023 và sáu BCTC kiểm toán năm; kiểm tra cover, năm tài chính và `Separate`/`Consolidated` bên trong PDF. Không dùng BCTC quý hoặc báo cáo thường niên thay BCTC kiểm toán năm mà không khai báo.
2. Giao trước các record có khả năng so sánh: Scope 1/2/tổng phát thải, lao động (tổng/nhóm), HĐQT, các số ESG có cột so sánh năm trước, và chỉ tiêu BCTC thực sự liên quan trong thuyết minh. Giữ các mục ngoài phạm vi là `not_searched`, không gắn absence. Sau đó mở rộng nếu cần.
3. Chạy schema/provenance checks và trả issue ledger. Mạnh adjudicate từng record và từng cặp so sánh; chỉ sau đó Graph chạy rule, lưu cả `NeedsReview` và lý do.

## Kiểm tra kỹ thuật trước khi bàn giao

Chạy JSON Schema cho từng file theo đúng version, kiểm tra SHA-256 PDF và JSON, rà ID trùng, kiểm tra trang/quote/header/năm/đơn vị trên các record so sánh, rồi chạy `kg.pipeline` bằng config thử mới. Bàn giao cả danh sách record bị loại/chưa rõ và trang chưa tìm. Không sửa dữ liệu nguồn chỉ để test pass. Các ví dụ trong `docs/examples/` và test `tests/test_extract_graph_contract.py` kiểm tra contract đang có; v2 ESG dùng `kg.extract_v2_validation.check_batch` để kiểm tra provenance cơ học. Code parser/extractor đã được gỡ khỏi cây làm việc; Graph giữ validator nhận dữ liệu.
