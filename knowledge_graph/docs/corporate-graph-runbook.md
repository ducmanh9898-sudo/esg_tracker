# Nhận JSON + PDF từ bên Extract vào Graph

Luồng mới nhận đúng `corporate-extract-1.0` trong ZIP đã bàn giao. Bên Extract không cần đổi format hay biết code Graph. Chạy bằng `kg.corporate_pipeline`; lệnh `kg.pipeline` và corpus lịch sử vẫn phục vụ luồng cũ. Hai entry point cùng dùng RDF core, ánh xạ claim/evidence và SHACL của dự án. Không tự trộn batch mới với dữ liệu lịch sử.

Gói BSR đã nhận có bước hiệu chỉnh Extract giữ nguyên nguồn và xuất bản mới;
xem [hướng dẫn hiệu chỉnh và review](corporate-extract-alignment.md).

## Khi nhận dữ liệu

Giữ nguyên folder giao hàng, ví dụ `data/incoming/bsr_2023_2025_v1/` chứa `manifest.json`, `json/`, `pdf/`. Path trong manifest tính từ thư mục chứa manifest. PDF được mở và kiểm tra bytes/hash/số trang, không dùng page mapping của artifact legacy. Chạy từ thư mục gốc dự án:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline --manifest data/incoming/bsr_2023_2025_v1/manifest.json --output-dir output/corporate_bsr_run01
```

Config mặc định `data/config/corporate_bsr_demo.json` kiểm tra đủ 9 báo cáo BSR 2023–2025: ESG, BCTC riêng, BCTC hợp nhất. Công ty/năm nằm trong config; code chung không hard-code BSR. Số liệu so sánh của kỳ trước vẫn thuộc document chứa nó. Năm báo cáo không điền vào năm quan sát còn thiếu.

Exit code: **0** hoàn thành xử lý kỹ thuật trong phạm vi khai báo, **2** partial (thiếu báo cáo, file bị chặn, coverage partial/lỗi hoặc issue chưa giải quyết), **1** lỗi batch. `completed` không có nghĩa record đã được người duyệt hoặc đã tìm thấy mâu thuẫn. Record trong file bị chặn không vào Graph; lỗi hash manifest hoặc ID xung đột toàn batch làm run fail. Coverage complete do Extract khai báo vẫn cần người kiểm tra.

Mỗi lần dùng output directory mới. Dữ liệu nguồn không bị sửa. RDF/record/finding ID ổn định cho cùng input; chạy lại vào thư mục mới không sinh thêm node trùng. Ghi output vào staging rồi chuyển nguyên thư mục khi hoàn thành; output cũ không bị ghi đè. Nếu tiến trình bị dừng, folder `.corporate-run-*` còn lại là run chưa hoàn thành; chạy lại từ đầu vào output mới. Đây là batch local nhỏ, không có queue/checkpoint từng record hay tự retry vô hạn.

## File cần mở

| Output | Dùng để làm gì |
| --- | --- |
| `run_manifest.json` | Kết quả kỹ thuật, lỗi, số record/candidate, hash manifest và thời điểm chạy. |
| `report.html` | Xem kết quả từng cặp, mở PDF tại trang vật lý và xem record gốc. Trình duyệt có thể yêu cầu mở PDF thủ công do chính sách file cục bộ. |
| `inventory.json` | Coverage, lỗi từng file, issue log và báo cáo còn thiếu. |
| `record_validation.json` | Source/locator cơ học và bốn lớp review riêng: quote, value, association, semantic context. |
| `review_template.json` | Mẫu quyết định record và cặp, ban đầu pending. |
| `comparisons.json` | Danh sách phép so và thứ tự operands. |
| `findings.json` | Supported/Contradicted/NeedsReview, lý do và phép tính. |
| `assessment_coverage.json` | Record nào có phép so, record nào chưa được đánh giá. |
| `arithmetic_coverage.json` | Rule số học thiếu hoặc có nhiều ứng viên cho một thành phần. |
| `normalized_records.json`, `source_documents.json` | Dữ liệu chuẩn hóa cùng toàn bộ JSON nguồn, giữ original/normalized, uncertainty, header và footnote. |
| `graph.ttl`, `graph.json` | RDF authoritative và bản chiếu JSON. Header/footnote có node locator; JSON gốc còn được lưu trên RDF để không mất field. |
| `shacl_report.txt` | Kiểm tra cấu trúc RDF. |
| `evaluation.json` | Chờ adjudication nếu chưa có gold độc lập đủ điều kiện. |

## Review và lịch sử

Sao chép `review_template.json` sang một file mới, ví dụ `data/review/corporate_bsr/decisions_v1.json`. Chỉ Mạnh/người review thực sự điền danh tính và thời điểm. AI không tạo các quyết định này cho dữ liệu thật.

Với `record_events`: giữ `record_id` và `input_digest`, điền `decision` thành `accept`, `reject` hoặc để `pending`; điền `reviewer`, `reviewed_at_utc` theo ISO 8601 có timezone, `basis`. Chỉ đặt từng cờ trong `checks` thành true sau khi đã kiểm tra lớp tương ứng. Quote tồn tại trong context JSON chỉ là kiểm tra nội bộ; nó chưa chứng minh quote đúng với PDF.

Với `comparison_events`: giữ ID/digest; chọn `comparable`, `not_comparable` hoặc `pending`; ghi người review, thời điểm, căn cứ, `absolute_tolerance` theo đơn vị chuẩn hóa và độ làm tròn nguồn. Đặt `restatement_checked=true` chỉ sau khi kiểm tra chú thích trình bày lại. `not_applicable_fields` chỉ cho `population`/`counting_method` khi cả hai không áp dụng và đã có giải thích trong basis. `scope_relation_confirmed` dùng cho phép tổng/subset có các scope khác nhau nhưng quan hệ đã được xác nhận. Các mismatch kỳ, pháp nhân, consolidation, đơn vị hoặc định nghĩa không bị bỏ qua vì đã chọn comparable.

Ví dụ sửa record: nếu giá trị 100 thực tế phải là 110, yêu cầu/tạo **bản JSON nguồn mới**, cập nhật manifest JSON hash và ghi lý do trong issue log; PDF hash giữ nguyên nếu bytes không đổi. Chạy lại vào run mới để nhận `input_digest` mới, rồi review giá trị đã sửa. Quyết định cũ bị đánh dấu stale khi digest không khớp; không sửa file review/output cũ để khớp dữ liệu mới. Mỗi run lưu snapshot config, manifest và review đã dùng.

```powershell
.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline --manifest data/incoming/bsr_2023_2025_v1/manifest.json --reviews data/review/corporate_bsr/decisions_v1.json --output-dir output/corporate_bsr_run02
```

Review file là khai báo có lịch sử do người dùng quản lý, không phải chữ ký điện tử xác thực danh tính. Không nhập output ChatGPT có tự nhận `reviewer_kind=human` như quyết định của Mạnh.

## Phép so hiện hỗ trợ

Trong demo BSR, phép so chính là **ESG ↔ BCTC**. Graph hỗ trợ cặp xuyên loại
báo cáo khi có metric/quan hệ đã ánh xạ, nhưng gói BSR hiện tại chưa cung cấp
`metric_id` chung hoặc cặp ESG ↔ BCTC đủ căn cứ để tạo candidate tự động. Bộ
30 cặp từ `bsr_corporate_pair_candidates_v3.json` là kiểm tra phụ cùng loại báo
cáo, không đại diện cho mục tiêu demo. File
`data/review/bsr_corporate_esg_financial_pair_candidates_v1.json` ghi rõ 0 cặp
xuyên loại theo tiêu chí nhãn/năm/đơn vị; đây là khoảng trống mapping/coverage,
không phải kết luận không có mâu thuẫn.

Tự tạo candidate giữa các document có cùng company/metric và cùng observation year (hoặc năm chưa biết để review). Bao gồm ESG–ESG, BCTC–BCTC và ESG–BCTC. Khác năm đo không tự thành mâu thuẫn. Cùng tên nhưng khác metric ID không tự ép mapping; khi nhận bộ dữ liệu thật, kiểm tra định nghĩa trước khi thống nhất ID trong revision.

Ba mẫu số học trong config: Scope 1 + Scope 2 = tổng đã xác định; số lao động nữ <= tổng lao động; số thành viên độc lập <= tổng HĐQT. Alias chỉ tạo candidate, không chứng minh tương đương. Nếu thiếu hoặc có nhiều ứng viên cho một vai trò, ghi coverage chưa đủ. Không tạo disclosure absence.

Có thể thêm `comparisons.json` riêng cho quan hệ có evidence, kể cả số học BCTC:

```json
{"comparisons": [
  {"relation": "sum_equals", "record_ids": ["COMPONENT-A", "COMPONENT-B", "TOTAL"]},
  {"relation": "subset", "record_ids": ["SUBSET", "TOTAL"]},
  {"relation": "equal", "record_ids": ["REPORT-A-OBSERVATION", "REPORT-B-OBSERVATION"]}
]}
```

Truyền `--comparisons đường/dẫn/comparisons.json` vào cả lần tạo template và lần áp dụng review. Với `sum_equals`, operand cuối là tổng; `subset` là operand đầu <= operand sau. Tổng/subset yêu cầu cùng report. Mọi phép so mạnh cần review record, review quan hệ, context tương đương, giá trị số và tolerance có căn cứ. Restatement unknown/restated còn ở NeedsReview; chưa tự tính ngược số trình bày lại. Policy, claim, governance evidence và target được lưu/truy vết; hiện không có suy luận ngữ nghĩa tự động cho những phát biểu đó.

## Evaluation và giới hạn

`--gold path.json` nhận `schema_version="corporate-assessment-gold-1.0"`, `items[]` có `comparison_id`, `input_digest`, `expected_status`, `split="held_out"`, `adjudication_status="adjudicated"`, `reviewer_kind="human"`, `reviewer`, `reviewed_at_utc`, `basis`. Chỉ tính **assessment_accuracy** trên các cặp được adjudicate độc lập; không biến candidate thành gold. Ngưỡng nghiệm thu kiểm thử kỹ thuật: mọi case đã định nghĩa phải đúng; không có false contradiction trong ca thiếu grounding hoặc lỗi kỹ thuật. Ngưỡng chất lượng thực tế phải được chốt trên tập held-out trước khi xem kết quả; hiện không có gold thật nên không công bố accuracy thực tế.

Extraction precision/recall luôn null trong harness Graph này. Muốn đo recall cần annotation đầy đủ các vùng nguồn xác định trước bằng harness Extract. Không dùng danh sách candidate so sánh làm corpus gold đầy đủ.

Hash và số trang chỉ xác minh đúng binary được giao; không xác minh tính chính thức của URL, nội dung OCR hay ngữ nghĩa header. Dấu phân tách số mơ hồ cần human value review. Char offsets/bbox được giữ nguyên theo bên Extract khai báo; không tự suy chúng là tọa độ canonical PDF. Không gọi LLM, dịch vụ ngoài hoặc database.

## Tái hiện test

```powershell
.\.venv\Scripts\python.exe -B -W ignore::DeprecationWarning -m unittest tests.test_corporate_graph -q
.\.venv\Scripts\python.exe -B -W ignore::DeprecationWarning -m kg.test_runner
.\.venv\Scripts\python.exe -B -m kg.corporate_fixture .tmp/my_synthetic_delivery
.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline --manifest .tmp/my_synthetic_delivery/manifest.json --config .tmp/my_synthetic_delivery/config.json --output-dir .tmp/my_synthetic_run
```

Fixture là PDF thật về mặt định dạng, có text và hash thật, nhưng **số liệu giả lập** thuộc company SYNTHETIC. Nó kiểm chứng vận hành JSON/PDF → RDF → SHACL → assessment, không chứng minh extraction BSR chính xác. Không đưa fixture vào corpus thật hoặc gold của Mạnh.
