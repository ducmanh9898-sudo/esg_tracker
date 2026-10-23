# Hiệu chỉnh Extract BSR để đưa vào Knowledge Graph

Đầu vào là **gói `corporate-extract-1.0` gồm PDF, JSON và manifest**. Công cụ
`tools.corporate_extract_alignment` chạy sau Extract, trước Graph. Nó giữ gói
gốc và tạo gói mới; không tải lại PDF, không gọi LLM/API. Logic chung không
hard-code BSR. `corporate-extract-1.0` và ID nguồn/record/evidence vẫn giữ
nguyên để Graph tiếp tục đọc qua `kg.corporate_pipeline`.

## Việc công cụ tự kiểm tra

1. Kiểm tra manifest, SHA-256 PDF/JSON, số trang PDF, schema và locator bằng
   validator bàn giao thật.
2. Tìm ô số 2–3 chữ số, không có năm quan sát, ở cột đầu bảng BCTC. Nếu cùng
   hàng có ô số tiền ở cột năm sau nó, gói mới tạm chuyển ô nghi vấn sang
   `value.status=ambiguous`, `normalized_value=null`, bỏ đơn vị VND gán nhầm
   và thêm issue `POSSIBLE_TABLE_CODE_COLUMN`. Đây là **quarantine kỹ thuật**;
   record vẫn chờ người đối chiếu PDF. Các tín hiệu yếu hơn chỉ vào watchlist.
3. Không tự tạo `metric_id`, metric definition, kỳ quan sát, scope/boundary,
   restatement hay kết luận mâu thuẫn. Graph cần các mục này và quyết định
   người duyệt cho từng record/cặp trước khi cho kết luận mạnh.

## Chạy trên gói đã nhận

Từ thư mục gốc dự án, trong PowerShell:

```powershell
.\.venv\Scripts\python.exe -B -m tools.corporate_extract_alignment audit --manifest BSR_2023_2025_handoff\manifest.json --output data\review\bsr_corporate_alignment_audit_v2.json
.\.venv\Scripts\python.exe -B -m tools.corporate_extract_alignment review-pack --manifest BSR_2023_2025_handoff\manifest.json --output data\review\bsr_corporate_alignment_review_v3.json --limit 50
.\.venv\Scripts\python.exe -B -m tools.corporate_extract_alignment align --manifest BSR_2023_2025_handoff\manifest.json --output data\handoff\bsr_corporate_aligned_v2
.\.venv\Scripts\python.exe BSR_2023_2025_handoff\validation\validate.py --manifest data\handoff\bsr_corporate_aligned_v2\manifest.json --pdf-dir data\handoff\bsr_corporate_aligned_v2\pdf
.\.venv\Scripts\python.exe data\handoff\bsr_corporate_aligned_v2\validation\audit_corporate_handoff.py data\handoff\bsr_corporate_aligned_v2 --bsr-nine --pending-only
.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline --manifest data\handoff\bsr_corporate_aligned_v2\manifest.json --output-dir output\bsr_corporate_aligned_v2
.\.venv\Scripts\python.exe -B -m tools.corporate_extract_alignment pair-pack --manifest data\handoff\bsr_corporate_aligned_v2\manifest.json --output data\review\bsr_corporate_pair_candidates_v2.json --limit 30 --pairing same-type
```

Mỗi `--output` phải là đường dẫn mới. `align` chép PDF/JSON/native artifact
để gói mới tự chứa, vì validator Graph yêu cầu PDF nằm trong chính gói và
element pointer cần native artifact. Bản gốc không bị ghi đè. `notes/alignment_audit.json`
và `validation/upstream_report.json` lưu lineage của bản trước.

Lượt BSR hiện tại: 88 record bị quarantine kỹ thuật, 1 record chỉ ở watchlist;
validator pass 9 PDF/JSON và 8.669 record. Audit native kiểm 5.139 giá trị
còn `available`, 8.669 quote và 418 checkpoint hash. Các số này là kiểm tra
cơ học, không phải precision/recall của Extract.

## Người duyệt sửa gì

Mở `data/review/bsr_corporate_alignment_review_v3.json`. Mỗi record có ID,
hash PDF, trang vật lý, quote, context, header và các field Extract đề xuất.
`technical_flag` và `technical_effect` cho biết trường hợp mã số đã bị chặn
tự động ở gói aligned hay chỉ được đưa vào watchlist.
Mở PDF theo `pdf_path` tương đối từ folder gói nguồn, rồi điền:

- `decision`: `accept`, `correct`, `reject` hoặc `uncertain`.
- Với `accept/correct/reject`: `reviewer`, `reviewed_at_utc` có múi giờ,
  `basis` nêu trang/ô/header và cả bốn `checks` = `true` **sau khi thực sự
  kiểm tra** source quote, value, association năm/đơn vị và semantic context.
- Với `correct`: `corrections` chứa field cấp record cần thay bằng **giá trị
  đầy đủ theo schema**, ví dụ `period` hoặc `value`. Không sửa trực tiếp
  `record_id`, PDF hash, document ID hay evidence ID. Nếu sửa `evidence`, phải
  giữ đúng locator/quote PDF; validator sẽ chạy lại.
- Với `uncertain`: để `corrections={}` và ghi `notes`; trạng thái vẫn chờ.

Ví dụ một quyết định sửa ô mã số `100` ở trang PDF 7: giữ nguyên record và
quote gốc, đặt `decision=correct`; trong `corrections.value`, sao chép toàn
bộ object `value` và đổi `status` thành `not_applicable`,
`normalized_value/normalized_unit/normalization_factor` thành `null`, thêm
`normalization_note` giải thích đó là cột `Mã số`. Dữ liệu ban đầu vẫn ở gói
gốc; gói mới giữ `original_value="100 "` và nhật ký quyết định.

**Không điền reviewer/thời điểm thay người duyệt.** Gói review hiện là mẫu,
không phải gold. 50 candidate là tập được chọn để duyệt, không phải annotation
đầy đủ của một vùng PDF, nên không thể tính recall từ nó.

50 record là mẫu kiểm chất lượng Extract. Record trong 30 cặp gợi ý có thể
nằm ngoài mẫu này. Để demo một phép đối chiếu, duyệt **cả hai record của cùng
một cặp** và quyết định so sánh riêng trong `review_template.json` của Graph;
chỉ duyệt 50 record mẫu không bảo đảm xuất hiện finding đã xác nhận.

`bsr_corporate_pair_candidates_v2.json` chỉ gợi ý cặp có cùng nhãn chuẩn hóa,
năm quan sát 2023–2025 và đơn vị ở hai báo cáo khác nhau. Mở cả hai PDF và xác minh
định nghĩa metric, kỳ, phạm vi, restatement trước khi xác nhận cặp. Có thể
truyền file này bằng `--comparisons` cho Graph để xem các finding
`NeedsReview`; nó không tự tạo kết luận mâu thuẫn.

```powershell
.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline --manifest data\handoff\bsr_corporate_aligned_v2\manifest.json --comparisons data\review\bsr_corporate_pair_candidates_v2.json --output-dir output\bsr_corporate_pair_review_v2
```

**Cập nhật sau khi đối chiếu PDF:** file cặp `v2` là bản lịch sử, không dùng làm
đầu vào Graph mới. Nó từng ghép 5.540.498 tấn ở dòng 2.1 “Nguyên liệu chế biến”
(PDF 2023 trang vật lý 25) với 5.601.406 tấn ở dòng 1.1 “Nguyên liệu nhập”
(PDF 2024 trang vật lý 24). Đây là hai nhóm khác nhau trong bảng, nên cặp đó
không hợp lệ. Chạy bản `v3` để dùng guard số dòng bảng và xem cặp đúng dòng 2.1:
5.540.498 tấn ở cả hai báo cáo. Cặp 70,3% cũng là dòng 2.4 ở cả hai báo cáo.
Các giá trị bằng nhau không tạo mâu thuẫn. Số dòng giống nhau chỉ giúp lọc lỗi
ghép rõ ràng; parent heading và định nghĩa metric vẫn cần người duyệt trước khi
Graph có thể kết luận mạnh. Graph cũng chặn cặp `equal` có số dòng bảng khác nhau
với lý do `table_row_context_mismatch` nếu vô tình nạp lại cặp cũ.

**Phạm vi demo ESG ↔ BCTC:** file cặp `v3` ở trên chỉ là kiểm tra phụ giữa
các báo cáo cùng loại (ESG ↔ ESG, BCTC ↔ BCTC), không phải phép đối chiếu chính
của demo. `pair-pack` nay mặc định `--pairing cross-type`. Với gói BSR hiện tại,
file `data/review/bsr_corporate_esg_financial_pair_candidates_v1.json` có
`comparisons=[]`: chưa có record ESG và BCTC nào trùng nhãn chuẩn hóa, năm quan
sát và đơn vị. Không suy ra thiếu công bố hoặc không có mâu thuẫn từ kết quả 0 này.
Các record hiện chưa có `metric_id` chung; muốn đối chiếu phải bổ sung ánh xạ
chỉ tiêu/quan hệ có nguồn và xác nhận kỳ, đơn vị, ranh giới kế toán. Không dùng
cặp BCTC ↔ BCTC để thay cho phép đối chiếu ESG ↔ BCTC.

```powershell
.\.venv\Scripts\python.exe -B -m tools.corporate_extract_alignment pair-pack --manifest data\handoff\bsr_corporate_aligned_v2\manifest.json --output data\review\bsr_corporate_esg_financial_pair_candidates_v1.json --pairing cross-type --limit 30
```

```powershell
.\.venv\Scripts\python.exe -B -m tools.corporate_extract_alignment pair-pack --manifest data\handoff\bsr_corporate_aligned_v2\manifest.json --output data\review\bsr_corporate_pair_candidates_v3.json --limit 30 --pairing same-type
.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline --manifest data\handoff\bsr_corporate_aligned_v2\manifest.json --comparisons data\review\bsr_corporate_pair_candidates_v3.json --output-dir output\bsr_corporate_pair_review_v3
```

Sau khi người duyệt đã điền file riêng, ví dụ
`data/review/bsr_corporate_alignment_review_filled.json`, chạy:

```powershell
.\.venv\Scripts\python.exe -B -m tools.corporate_extract_alignment align --manifest BSR_2023_2025_handoff\manifest.json --review data\review\bsr_corporate_alignment_review_filled.json --output data\handoff\bsr_corporate_aligned_reviewed_v1
.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline --manifest data\handoff\bsr_corporate_aligned_reviewed_v1\manifest.json --output-dir output\bsr_corporate_reviewed_draft_v1
.\.venv\Scripts\python.exe -B -m tools.corporate_extract_alignment graph-review --manifest data\handoff\bsr_corporate_aligned_reviewed_v1\manifest.json --graph-run output\bsr_corporate_reviewed_draft_v1 --review data\review\bsr_corporate_alignment_review_filled.json --output data\review\bsr_graph_record_reviews_v1.json
.\.venv\Scripts\python.exe -B -m kg.corporate_pipeline --manifest data\handoff\bsr_corporate_aligned_reviewed_v1\manifest.json --reviews data\review\bsr_graph_record_reviews_v1.json --output-dir output\bsr_corporate_reviewed_v1
```

`graph-review` chuyển **chỉ** quyết định record đã có trong gói aligned
sang format review của Graph, gắn đúng `input_digest` sau adapter. Quyết định
so sánh giữa hai record vẫn pending; người duyệt phải kiểm tra sự tương đương
định nghĩa, kỳ, đơn vị, boundary, restatement và tolerance trong
`review_template.json` của Graph. Không được dùng metric ID giống nhau làm
bằng chứng đủ cho mâu thuẫn.

## Giới hạn hiện tại

- Watchlist rộng hơn quarantine vì thiếu liên kết hàng/cột năm đáng tin cậy;
  cần đối chiếu PDF, đặc biệt BCTC hợp nhất 2025.
- Nhiều record ESG là claim/policy/target không có số; Graph lưu evidence nhưng
  không áp phép so số học lên chúng.
- Validation cơ học pass chỉ nói rằng nguồn, hash, locator và schema nhất quán.
  Nó không chứng minh Extract đúng nội dung hay nguồn chính thức đầy đủ.
- Khi chưa có quyết định người duyệt và metric definition được xác nhận,
  Graph trả `NeedsReview` hoặc không có cặp so sánh; không suy doanh nghiệp
  greenwashing hay thiếu công bố từ việc chưa tìm thấy record.
