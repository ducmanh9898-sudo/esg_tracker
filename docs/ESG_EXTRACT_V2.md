# ESG_extract_V2 — bản bổ sung để rà soát

Đây là gói nguồn và candidate, không phải gold, kiểm toán hoặc kết luận greenwashing.
Mọi record giữ `pending_human_review`; boundary.verified=false. Candidate pair giữ
`NeedsReview`, verdict=null, eligible_for_numeric_comparison=false.

## Tệp cần đọc

- manifest.json: 9 slot BSR × 2023/2024/2025 × ESG/BCTC riêng/BCTC hợp nhất;
  có đường dẫn và SHA-256 PDF/JSON. Slot không có nguồn giữ unavailable có lý do.
- pdf/: PDF nguyên bản, giữ nguyên bytes kể cả chữ ký số.
- json/: corporate-extract-1.0, giữ record/evidence IDs cũ, nguyên văn, giá trị gốc,
  năm quan sát và JSON pointer. Có thể bổ sung record từ thuyết minh/cell nguồn.
- notes/record_enrichment.json: các bổ sung và nguồn gốc phiên bản trước.
- notes/demo_review_queue.json: priority_records, candidate_pairs với ID/evidence
  hai phía, excluded_from_headcount_pairing cho khoản tiền không phải số người.
- notes/native/: JSON parser và checkpoint nguyên bản để phân giải JSON pointer.
- validation/report.json: tổng hợp kiểm định bản V2, không dùng báo cáo cũ thay thế.
- validation/extra_checks.json: kiểm tra quote, checkpoint hash, normalization.
- validation/review_checks.json: kiểm tra cặp, loại tiền/số người, trạng thái review.
- validation/graph_load_report.json: kết quả nạp **property graph tham chiếu local**.

## Đọc cặp candidate

`candidate_pairs` là giả thuyết cùng chỉ tiêu/năm/đơn vị để người dùng kiểm tra,
không phải cặp đã đủ điều kiện so sánh số. `blockers` ghi các phần chưa rõ như ngày
đo, pháp nhân, population, cách đếm, restatement và làm tròn. Không tạo cặp nếu biết
chắc khác metric, khác năm hoặc xung đột riêng/hợp nhất. Không ghép tổng doanh thu
ESG với doanh thu thuần BCTC, nộp ngân sách với chi phí thuế TNDN, hoặc phải trả
người lao động với số nhân viên. Chênh lệch giá trị không tự sinh Contradicted.

`local:*:v1` là mã từ điển cục bộ có định nghĩa trong record, không phải mã GRI/IFRS
đã được đơn vị báo cáo xác nhận. Gán mã không xác nhận các phạm vi là tương đương.
`year_basis=reviewed_context` là tên enum của schema cho suy giải header tương đối
từ caption; không có nghĩa người dùng đã duyệt. Mọi record vẫn pending_human_review.

Các issue cũ được giữ làm lịch sử quan sát của extractor; structured fields và issue
bổ sung phản ánh trạng thái mới. Phương pháp đếm/population/chi tiết hợp nhất không
có chứng cứ vẫn null; không suy boundary của KPI ESG từ BCTC hoặc bìa báo cáo.

## Kiểm định lại (PowerShell, trong thư mục gói đã giải nén)

```powershell
python validation/validate.py --manifest manifest.json --pdf-dir pdf
python validation/audit_corporate_handoff.py . --bsr-nine --pending-only
python validation/validate_corporate_review.py .
```

Cần Python và các gói trong validation/requirements.txt. Validator gốc kiểm tra
cơ học. Audit bổ sung và adapter Graph không thay cho đối chiếu PDF.

## Graph

notes/graph_review.json gồm Report, Record, Evidence, CandidatePair và quan hệ
HAS_RECORD, SUPPORTED_BY, ESG_SIDE, FINANCIAL_SIDE. Script validate_corporate_review.py
thực sự materialize nodes/edges vào graph tham chiếu local, kiểm tra ID/FK và 9 slot.
`missing_expected_reports=0` chỉ cho adapter này. Chưa có endpoint/schema của Graph
đích nên không khẳng định đã nạp Neo4j hay hệ thống bên ngoài; cần ánh xạ vào API
Graph đích khi nhận được hợp đồng tích hợp. Không chạm database dashboard đang chạy.

## Tạo lại bản bổ sung từ gói cũ (trong repo)

```powershell
.\.venv\Scripts\python.exe scripts/build_review_delivery_v2.py outputs/BSR_2023_2025_HANDOFF_REVIEW_READY_20261016_v2 outputs/ESG_extract_V2
```

Đích phải là thư mục mới. Quy tắc nhận dạng và enrichment cũng được tích hợp vào
bộ xuất corporate của UI/CLI để bản xuất sau không quay về hàng đợi keyword cũ.
