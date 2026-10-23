# Tiếp nhận ESG_extract_V1 cho demo BSR

Kiểm tra ngày 2026-10-16 trên folder nhận nguyên trạng. Không sửa JSON/PDF nguồn và không cập nhật quyết định review.

## Kết luận

Gói hiện **nạp được vào Graph như dữ liệu partial**, nhưng **chưa đủ** cho demo đối chiếu ESG–BCTC của BSR 2023–2025 hoặc kết luận mâu thuẫn. Đây là một báo cáo tài chính **riêng** năm 2024; 8 slot còn lại chưa có trong manifest một phiên. Số so sánh 2023 nằm trong PDF 2024 không thay thế báo cáo năm 2023.

## Bằng chứng đã kiểm tra

| Kiểm tra | Kết quả |
| --- | --- |
| PDF vật lý | 42 trang, hash `84a73087f5f308f7eb9b678751b6e69411cf40bb104e029860920089c9b02728`. Bìa trang vật lý 1 đã được mở bằng ảnh: Công ty Cổ phần Lọc hóa dầu Bình Sơn, **Báo cáo tài chính riêng đã được kiểm toán**, năm tài chính kết thúc 31/12/2024, Deloitte. |
| Contract + manifest/PDF | Validator độc lập báo `PASS files=1 records=1061; mechanical checks only, semantic review pending`. `validation/report.json` bên Extract cũng ghi manifest/mechanical valid, `complete_handoff=false`, `human_review_pending=true`. Nguồn URL/claim đối chiếu website do bên Extract khai báo; lượt này không tự tải và so lại website. |
| Coverage | 42 trang được đánh dấu checked, 0 unreadable, nhưng `coverage.status=partial`, `search_status=partial_search`; search outcomes có 2 `found`, 2 `not_searched`. Không suy doanh nghiệp thiếu công bố. |
| Record | 1.061 `financial_measurement` thuộc dimension X; 610 available, 278 unknown, 117 ambiguous, 56 missing. Có 522 observation year 2024, 453 năm 2023, 4 năm 2022, 82 unknown. |
| So sánh được | **0/1.061** có `metric_id` hoặc `metric_definition`; **1/1.061** có `year_basis=table_header`, còn 1.060 unknown. Boundary verified 0; review status đều `pending_human_review`. `scope` null ở toàn bộ record. |
| Issue log | 4.537 issue, gồm 1.846 `NOTE_FIELD_UNKNOWN`, 1.061 `RECORD_REQUIRES_REVIEW`, 354 native records không map được, 333 unit unknown và 333 scale unknown. |
| Nạp thử Graph | Chạy `kg.corporate_pipeline` với config BSR mặc định vào `.tmp/esg_extract_v1_review_run01/`: `status=partial`, 1.061 records, **0 comparisons**, 8 expected reports còn thiếu, 1.061 records pending review, SHACL conforms. Không tạo finding. |

`notes/demo_review_queue.json` có 7 candidate đều gắn topic workforce và `year_basis=unknown`. Ví dụ nhãn “Phải trả người lao động” (trang 8) và “Tạm ứng cho nhân viên” (trang 25) là **khoản tiền trên BCTC**, không phải số lượng lao động; không nên map chúng sang ESG employee headcount. Queue này chưa phải cặp so sánh hoặc gold.

## Việc bên Extract cần bổ sung để demo

1. Giao các slot còn thiếu: ESG 2023–2025; BCTC riêng 2023 và 2025; BCTC hợp nhất 2023–2025. Mỗi slot có JSON đúng contract, PDF đúng hash và manifest; nếu chưa có thì ghi `unavailable` cùng lý do trong manifest batch đầy đủ. Đừng suy absence từ file chưa giao.
2. Ưu tiên **ít record có thể đối chiếu** hơn 1.061 candidate thô. Với từng record có khả năng so: metric ID/định nghĩa ổn định, quote và ô bảng đúng PDF, header năm và đơn vị, original/normalized value, observation period/date, entity/boundary, phương pháp, footnote/restatement và trạng thái review. Các mục khác có thể giữ pending/unknown.
3. Tách loại chỉ tiêu: headcount khác phải trả người lao động, tạm ứng nhân viên hoặc chi phí nhân viên. ESG–BCTC chỉ tạo cặp khi thực sự cùng định nghĩa/pháp nhân/kỳ; BCTC riêng–hợp nhất không tự so ngang.
4. Báo coverage theo vùng đã tìm và lỗi parse/extract. Giữ raw output/issue log để rà lại; không đổi 0 thành missing hoặc ngược lại để Graph tạo finding.

## Phần Graph có thể tiếp tục

Adapter/validator/RDF/SHACL đã chạy được với file này. Có thể chuẩn bị thêm report lựa chọn KPI và phương án review các cặp được Extract chỉ định; các rule về mâu thuẫn thực tế cần các record/cặp có đủ căn cứ và quyết định của người review. Gói hiện tại không cung cấp một cặp so sánh tự động nào, nên mở rộng rule lúc này không tạo ra kết luận đáng tin hơn.
