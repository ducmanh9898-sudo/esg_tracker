# Demo đối chiếu BCTC–ESG BSR 2023–2025

Mục tiêu là tìm **số liệu cần giải thích** giữa công bố ESG/phát triển bền
vững và BCTC hợp nhất. `Contradicted` chỉ được phép sau khi người duyệt xác
nhận hai record cùng định nghĩa, kỳ, phạm vi, cách tính, tình trạng trình bày
lại và ngưỡng làm tròn. `Contradicted` chỉ mô tả mâu thuẫn trong phép đối chiếu;
không kết luận doanh nghiệp ghi sai hoặc greenwashing.

## Dữ liệu và mức hoàn thành

- Nguồn đầu vào: [handoff aligned v2](../data/handoff/bsr_corporate_aligned_v2/manifest.json)
  (9 PDF/JSON), cộng PDF BSR 2025 chính thức 134 trang.
- [Config candidate](../data/config/bsr_cross_report_profit_v1.json) chỉ định
  bốn ô/đoạn ESG và bốn record BCTC tương ứng. Mọi record mới là
  `chatgpt_assisted`, `pending_human_review`. Nguồn 2023 và 2024 dùng PDF
  ESG đã có trong handoff; 2025 dùng PDF 134 trang. PDF 68 trang 2025 được
  giữ nguyên như nguồn legacy, không ghép số trang với bản 134.
- [Handoff v1](../data/handoff/bsr_cross_report_profit_v1/manifest.json):
  10 document, 8.673 record. Builder kiểm tra SHA-256, số trang, quote
  trên trang, header năm của bảng ESG 2024 và phép đổi tỷ đồng sang VND;
  validator contract chạy trên toàn bộ 10 JSON/PDF. Mỗi lần tạo output mới,
  builder từ chối ghi đè thư mục có sẵn.
- [Graph run v1](../output/bsr_cross_report_profit_v1/run_manifest.json):
  4 cặp rõ ràng, 4 `NeedsReview`, 0 `Contradicted`; SHACL đạt,
  `evaluation_status=pending_adjudication`. Trạng thái run là `partial` vì
  tài liệu đầu vào/khảo sát ESG chỉ bao phủ một phần, không phải lỗi kỹ thuật.
  CLI trả exit code 2 cho `partial`.
- Validator độc lập đã chạy: `PASS files=10 records=8673; mechanical checks only,
  semantic review pending`.
- [Review pack](../data/review/bsr_cross_report_profit_v1/README.md) có ảnh
  sáu trang gốc và bảng bốn case. Không có nhãn gold hay accuracy.

Các chênh lệch số học là +21.027.989 VND (2023), −91.587.455 VND (2024),
−138.578.972.011 VND (số 2023 trong ESG 2024) và +47.703.663 VND
(2025). Anh đã xác nhận ba cặp 2023 hiện hành, 2024 hiện hành và 2025
khớp do làm tròn trong cuộc trao đổi. Xác nhận này chưa hoàn tất review event
cho từng record trong Graph.
Anh đã xác nhận cặp số 2023 trong ESG 2024 là mâu thuẫn khi đối chiếu. Đây là
xác nhận trong cuộc trao đổi, chưa phải review event đầy đủ cho Graph. Nguyên
nhân vẫn có thể liên quan định nghĩa, phạm vi hoặc trình bày lại; không suy ra
BSR ghi sai từ finding này.
Sau review tuần tự, một PDF BCTC hợp nhất quý IV/2023 chính thức được lưu
như [nguồn tham chiếu bổ sung](../data/review/bsr_cross_report_profit_v1/supporting_source_2023_q4.json):
mã số 60 ghi 8.454.879.352.711 VND. Điều này gợi ý bảng ESG 2024 có thể
dùng số liệu quý IV trước BCTC năm đã kiểm toán; đó vẫn là giả thuyết,
không phải kết luận nguồn gốc hoặc nguyên nhân sai khác.

## Tạo lại một phiên bản handoff và Graph mới

Chạy trong PowerShell tại thư mục gốc dự án. Môi trường hiện tại là `.venv`;
không dùng cloud/API trả phí. Thay hậu tố `_v2` cho mọi đường dẫn output khi
tái chạy; lệnh từ chối ghi đè.

```powershell
.\.venv\Scripts\python.exe -B -m tools.cross_report_pilot `
  --source-manifest data\handoff\bsr_corporate_aligned_v2\manifest.json `
  --config data\config\bsr_cross_report_profit_v1.json `
  --output data\handoff\bsr_cross_report_profit_v2

.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline `
  --manifest data\handoff\bsr_cross_report_profit_v2\manifest.json `
  --config data\config\bsr_cross_report_profit_graph_v1.json `
  --comparisons data\handoff\bsr_cross_report_profit_v2\notes\cross_report_comparisons.json `
  --output-dir output\bsr_cross_report_profit_v2
```

Config Graph đặt `auto_metric_candidates=false`, vì demo này chỉ xét bốn
cặp BCTC–ESG được chỉ định. Mã chung cũng chỉ tự tạo cặp khi cả hai record
có observation year xác định và bằng nhau. Gói nguồn, config và output có
hash/snapshot để biết run dùng phiên bản nào. Không sửa raw Extract cũ.

## Sau khi người duyệt quyết định

Mở [mẫu quyết định](../data/review/bsr_cross_report_profit_v1/decisions_template.json),
đọc [hướng dẫn và ảnh gốc](../data/review/bsr_cross_report_profit_v1/README.md),
rồi lưu bản đã điền thành `decisions_filled.json` cùng thư mục. `input_digest`
gắn quyết định với đúng nội dung record/cặp hiện tại. Không điền thời điểm
hoặc danh tính người duyệt hộ người thật.

```powershell
.\.venv\Scripts\python.exe -B -m handoff.bsr_extract_2023_2025_v1.validate `
  --manifest data\handoff\bsr_cross_report_profit_v1\manifest.json `
  --pdf-dir data\handoff\bsr_cross_report_profit_v1\pdf

.\.venv\Scripts\python.exe -B -m tools.cross_report_review check `
  --run output\bsr_cross_report_profit_v1 `
  --pack data\handoff\bsr_cross_report_profit_v1\notes\cross_report_review_pack.json `
  --reviews data\review\bsr_cross_report_profit_v1\decisions_filled.json

.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline `
  --manifest data\handoff\bsr_cross_report_profit_v1\manifest.json `
  --config data\config\bsr_cross_report_profit_graph_v1.json `
  --comparisons data\handoff\bsr_cross_report_profit_v1\notes\cross_report_comparisons.json `
  --reviews data\review\bsr_cross_report_profit_v1\decisions_filled.json `
  --output-dir output\bsr_cross_report_profit_reviewed_v1
```

Xem `run_manifest.json`, `record_validation.json`, `findings.json`,
`evaluation.json`, `shacl_report.txt` và `report.html` của run mới. Nếu
người duyệt sửa **nội dung record**, cần tạo handoff phiên bản mới; các
`input_digest` cũ không còn hợp lệ. Validator kiểm tra quyết định không
thay thế việc kiểm tra evidence. `--gold` chỉ nhận tập held-out do người
duyệt chốt; review bốn candidate không đo được recall của toàn tài liệu.

## Kiểm chứng đã chạy và giới hạn

- `python -B -m unittest tests.test_corporate_graph tests.test_corporate_extract_alignment`:
  25 test đạt; chạy chung với `tests.test_cross_report_pilot` là 30 test đạt.
  `tests.test_cross_report_pilot` kiểm tra PDF thật, hash sai,
  quote sai, header năm sai, phép đổi đơn vị sai, tránh ghi đè và digest của
  mẫu quyết định.
- Graph thật đã đọc đủ 10 PDF/JSON và tạo 4 finding; SHACL đạt. Không có
  live cloud extraction và không có human adjudication. Chưa công bố
  precision/recall.
- BCTC hiện có `year_basis=unknown` trong Extract; nhiều field boundary,
  calculation method, restatement cũng `unknown/null`. Một số header năm
  có thể nhìn thấy trên ảnh trang, nhưng chưa có annotation đủ để sửa field
  nguồn và xác nhận ngữ nghĩa. Graph cố ý giữ `NeedsReview`.
- ESG 2023 p22 không có header năm riêng cho ô được chọn; record để
  `observation_year=null` dù tiêu đề tài liệu là 2023.
- BCTC và ESG có thể dùng nhãn dòng khác nhau. Một `metric_id` chung trong
  package là **đề xuất ánh xạ**, không phải sự tương đương đã xác nhận.
- Các trang ESG được chọn chỉ phục vụ pilot lợi nhuận. Tình trạng `partial`
  không phải doanh nghiệp thiếu công bố và không đại diện cho toàn bộ E/S/G.

Sau khi anh xác nhận bốn case và cung cấp căn cứ cho kỳ/phạm vi/điều chỉnh
số liệu, bước tiếp theo là tạo handoff mới với field đã sửa có provenance,
chạy lại Graph và xem finding. Không chỉnh ngưỡng để ép kết quả.
