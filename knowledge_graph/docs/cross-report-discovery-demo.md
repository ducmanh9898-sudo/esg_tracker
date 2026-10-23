# Demo đối chiếu BCTC–ESG, độc lập công ty

## Mở gì để demo

Mở `output/bsr_cross_report_discovery_v5/review.html` bằng trình duyệt.
Danh sách gọn sáu cặp ở
`data/review/bsr_cross_report_profit_v1/discovery_pairs_v5.md`; Graph run tương ứng
ở `output/bsr_cross_report_discovery_graph_v3/report.html`.
Đây là báo cáo offline; liên kết PDF mở đúng file nguồn và trang vật lý, đánh số từ 1.
Mỗi cặp có ID, digest đầu vào, nhãn, kỳ quan sát (có thể null), năm báo cáo,
quote/context, hash PDF, locator, chênh lệch và các điều kiện chưa đủ.

Các số liệu của lần chạy nằm trong `summary.json`; `inventory.json` ghi lỗi/coverage
từng tài liệu; `coverage.json` ghi cả record không tìm được cặp.
`source_documents` trong Graph giữ nguyên dữ liệu bàn giao; scanner không sửa Extract.

**6 ứng viên hiện hành không phải 6 mâu thuẫn.** Truy hồi theo mã chỉ tiêu, tên được chuẩn hóa,
hoặc nhóm từ khóa cấu hình. Một nhóm có thể chứa doanh thu thuần/tổng doanh thu,
lợi nhuận hợp nhất/riêng lẻ, hoặc chỉ tiêu mẹ/con. Người review phải xác định tương đương.
Các scope/period/unit đã biết khác nhau được xếp `blocked_context_mismatch`.
Không lấy năm báo cáo lấp vào năm quan sát thiếu.

Discovery v3 có 76 ứng viên do profile v1 dùng regex `loi nhuan sau thue` ở
bất kỳ vị trí nào trong nhãn. Điều này kéo cả khoản trích quỹ *từ lợi nhuận sau thuế*
và lợi nhuận thuộc cổ đông công ty mẹ vào nhóm tổng lợi nhuận sau thuế. Profile v2
đặt ranh giới đầu nhãn và `exclude_patterns`. Scanner cũng chặn cặp tự sinh
nếu thiếu năm quan sát hoặc đã biết khác phạm vi hợp nhất/riêng. Discovery v5
giữ nguyên bốn cặp pilot, thêm hai cặp cùng chỉ tiêu từ phiên bản BCTC khác.
Output v3/v4 được giữ để truy vết.

## Kiến trúc

1. JSON + PDF + manifest → validator hiện có (schema/hash/page/quote).
2. Adapter giữ original, normalized, raw document/record, provenance và input digest.
3. `kg.cross_report_scan` truy hồi **chỉ ESG–Financial, cùng công ty**; giữ coverage.
4. Diagnostic số học riêng: bằng nhau, khác nhưng chưa biết độ chính xác hiển thị,
   trong/ngoài dung sai đề xuất. Dung sai chưa phải phê duyệt của người dùng.
5. `kg.corporate_pipeline` tạo RDF/SHACL và finding có guard; chưa duyệt là NeedsReview.
6. Screening của người dùng → lịch sử riêng; review đầy đủ từng lớp → Graph;
   gold/evaluation là bước độc lập.

Discovery tự động chỉ tạo cặp khi cả hai record có năm quan sát xác định và
bằng nhau, đồng thời không có phạm vi hợp nhất/riêng đã biết là khác nhau.
Cặp explicit vẫn được giữ để reviewer xử lý phần kỳ/ngữ cảnh còn thiếu.

Universal logic nằm trong `kg/`; profile nằm trong `data/config/`.
Đổi công ty bằng manifest và profile khác: `company_id`, `expected_reports`,
`metric_families`, comparisons tùy chọn. Regex chạy trên nhãn bỏ dấu, chữ thường;
mỗi family có thể khai báo `exclude_patterns` để chặn nhãn chứa cùng từ nhưng
khác chỉ tiêu.
Không có tên BSR hoặc đường dẫn BSR trong logic scanner/triage.
Profile từ khóa tiếng Việt này chưa chứng minh phù hợp mọi ngành/ngôn ngữ.
Các case và dung sai pilot BSR là dữ liệu riêng, không nhúng trong thuật toán.

## Chạy lại (PowerShell, từ thư mục dự án)

Chọn thư mục output **mới** cho mỗi lần chạy; công cụ từ chối ghi đè.

```powershell
.venv\Scripts\python.exe -B -m kg.cross_report_scan `
  --manifest data/handoff/bsr_cross_report_profit_v1/manifest.json `
  --profile data/config/bsr_cross_report_discovery_v2.json `
  --comparisons data/handoff/bsr_cross_report_profit_v1/notes/cross_report_comparisons.json `
  --pilot-pack data/handoff/bsr_cross_report_profit_v1/notes/cross_report_review_pack.json `
  --session-context data/review/bsr_cross_report_profit_v1/session_confirmations.json `
  --output-dir output/bsr_cross_report_discovery_next
```

`--comparisons`, `--pilot-pack`, `--session-context` không bắt buộc cho công ty khác.
Exit code 2/status partial là coverage đầu vào chưa đầy đủ, không phải thành công toàn corpus.
Lỗi tài liệu nằm trong inventory; không biến lỗi tìm kiếm/extract thành không công bố.

```powershell
.venv\Scripts\python.exe -B -m kg.corporate_pipeline `
  --manifest data/handoff/bsr_cross_report_profit_v1/manifest.json `
  --config data/config/bsr_cross_report_discovery_v2.json `
  --comparisons output/bsr_cross_report_discovery_v5/comparisons.json `
  --output-dir output/bsr_cross_report_graph_next
```

Graph xuất `graph.ttl`, `graph.json`, `findings.json`, `report.html`,
`record_validation.json`, `review_template.json`, `evaluation.json`, `run_manifest.json`.
Profile tắt so sánh tự sinh BCTC–BCTC và thêm guard `require_source_basis_review`.

## Anh review thế nào

### Bước 1: screening đơn giản

Sao chép `triage_template.csv` từ discovery v5 sang file riêng, mở bằng Excel/LibreOffice.
Giữ nguyên comparison_id và input_digest. Điền:

- `decision`: `rounding_match`, `potential_contradiction`, `not_comparable`,
  `extraction_error`, `uncertain`; chưa xem để `pending`.
- `reviewer`: tên người thực sự review.
- `reviewed_at_utc`: thời gian thực, ISO 8601 có timezone; không dùng thời gian mẫu.
- `notes`: căn cứ trang, header, năm, đơn vị, phạm vi, phiên bản.

Không cần duyệt mọi cặp để nhập các quyết định đã làm.

```powershell
.venv\Scripts\python.exe -B -m tools.cross_report_triage `
  --run output/bsr_cross_report_discovery_v5 `
  --decisions data/review/my_screening.csv `
  --output data/review/my_screening_history_001.json
```

Lần sửa sau dùng lịch sử `_002.json`. Công cụ kiểm tra ID/digest/trùng và identity/time,
ghi atomically, không ghi đè lịch sử. Timestamp import là thời gian máy, tách thời gian review.
Screening không tự nâng record thành accepted, không tự tạo gold.
Xác nhận hội thoại cũ được giữ riêng trong `session_context_not_adjudication.json`.

### Bước 2: review đủ điều kiện để Graph kết luận

Sao chép `review_template.json` của discovery v5 ra file riêng.
Mỗi record cần xác nhận riêng `source_quote`, `value`, `association`, `semantic_context`.
Mỗi comparison cần quyết định comparable/not_comparable, dung sai có căn cứ,
restatement_checked, source_basis_checked và source_basis_note, identity/time/basis thật.
Nếu field trích xuất sai hoặc thiếu, cần sửa **bản Extract mới có provenance** và chạy lại
validator/scanner; digest thay đổi làm review cũ stale. Check box không sửa giá trị/năm nguồn.

```powershell
.venv\Scripts\python.exe -B -m tools.cross_report_review check `
  --run output/bsr_cross_report_discovery_v5 `
  --pack output/bsr_cross_report_discovery_v5/review_pack.json `
  --reviews data/review/my_graph_review.json

.venv\Scripts\python.exe -B -m kg.corporate_pipeline `
  --manifest data/handoff/bsr_cross_report_profit_v1/manifest.json `
  --config data/config/bsr_cross_report_discovery_v2.json `
  --comparisons output/bsr_cross_report_discovery_v5/comparisons.json `
  --reviews data/review/my_graph_review.json `
  --output-dir output/bsr_cross_report_graph_reviewed_001
```

Preflight review kiểm tra hình thức; Graph vẫn thực thi guard ngữ nghĩa/source basis.
Chưa có gold hợp lệ thì evaluation là pending_adjudication, precision/recall null.
Muốn đo recall cần annotation đầy đủ trên các vùng PDF định trước; danh sách ứng viên
không phải toàn bộ ground truth.

## Cặp cần chú ý

- Ba cặp pilot có độ lệch nằm trong dung sai làm tròn đề xuất. Riêng ESG2023 vẫn
  thiếu căn cứ trực tiếp cho năm của ô; chưa tự điền observation_year.
- Cặp ESG2024 cột2023: 8.454 tỷ so với BCTC 8.592.578.972.011 đồng lệch
  138.578.972.011 đồng, vượt dung sai 0,5 tỷ đề xuất.
- Chứng cứ phụ Q4/2023 tại
  `data/review/bsr_cross_report_profit_v1/supporting_source_2023_q4.json`:
  8.454.879.352.711 đồng. Đây là giả thuyết khác phiên bản/cơ sở trước kiểm toán,
  chưa chứng minh ESG lấy số từ Q4. 8.454 không phải làm tròn gần nhất của 8.454,879 tỷ.
  Không kết luận doanh nghiệp sai hoặc greenwashing.
- Giữ PDF2025 canonical134 trang và legacy68 trang riêng; mapping đã xác minh của
  một trang không được mở rộng thành mapping toàn tài liệu.

## Giới hạn

Quét tất cả **record được validator nhận**, không khẳng định tìm hết sai lệch trong PDF.
ESG có ít record numeric đã chuẩn hóa, thiếu nhiều metric/year/context. Không có
cloud LLM/API trả phí trong luồng này. Không thay parser hoặc tái extract toàn bộ tài liệu.
Discovery chưa đánh giá claim định tính, quan hệ nhân quả hoặc độ đầy đủ công bố.
Graph nghiêm ngặt có thể giữ cả cặp số học rõ ràng ở NeedsReview khi lớp khác chưa đủ.
Không có thay đổi tự động vào PDF/raw Extract hoặc quyết định của người review.

## Kiểm thử

```powershell
.venv\Scripts\python.exe -B -W ignore::DeprecationWarning -m unittest `
  tests.test_cross_report_scan tests.test_cross_report_pilot `
  tests.test_corporate_graph tests.test_corporate_extract_alignment
```

Test fixture chứng minh guard và workflow; dữ liệu thật chứng minh chạy được input hiện có,
không chứng minh chất lượng extraction. Không có accuracy khi chưa adjudicate.
