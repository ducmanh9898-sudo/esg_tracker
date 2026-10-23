# Báo cáo triển khai MVP ESG Tracker

## Đã hoàn thành

- Schema SQLite gồm tám bảng bắt buộc và bảng `claim_scores` bổ sung.
- Adapter cho sáu bundle `output` của BSR 2023–2025, đọc JSON trang, chunk/manifest, structured JSON và summary; giữ provenance, nội dung artifact và SHA-256.
- Dataset minh họa riêng 2022–2025, 48 claim và trên 30 metric, gắn `is_demo_data = true`.
- Metric dictionary 16 metric, có Việt–Anh, variants, đơn vị chuẩn, GRI, chiều hướng, comparability và tolerance.
- Tách câu spaCy blank Vietnamese có fallback regex; trích thuộc tính claim bằng regex/keyword.
- RapidFuzz candidate score và comparability gate trước khi xác định relationship.
- Sáu trạng thái matching: SUPPORTS, PARTIAL_SUPPORT, CONTRADICTS, MISSING, AMBIGUOUS, NOT_COMPARABLE.
- 15 luật GW01–GW15 cấu hình YAML và engine rule-based.
- Scoring claim theo công thức mặc định, tổng hợp topic/pillar/year, hiển thị evidence coverage và confidence.
- Dashboard Dash tiếng Việt có 5 tab, bộ lọc chung, reset, loading, tooltip, DataTable và drill-down claim.
- Unit tests cho normalization, matching, rule engine, scoring và database schema.

## Kết quả xác minh ngày 13 tháng 9 năm 2026

- `pytest -q`: 30 test passed.
- Import module Dash: thành công, 5 callback được đăng ký.
- HTTP smoke test: `/` và `/_dash-layout` đều trả về 200; layout chứa đủ tab Contradiction Explorer.
- Nguồn thực: 6 document, 289 passage, 98 artifact, 147 claim và 50 metric; pipeline tạo 147 evidence link, 161 rule result và 47 topic score.
- Kiểm tra `PRAGMA foreign_key_check`: không có lỗi; không có page number vượt `documents.page_count`.
- Dashboard mặc định chọn nguồn BSR thực tế; demo chỉ hiển thị khi người dùng chủ động chọn.
- Dataset demo có đủ các trạng thái SUPPORTS, PARTIAL_SUPPORT, CONTRADICTS, MISSING, AMBIGUOUS và NOT_COMPARABLE.
- Source compilation bằng `compileall`: thành công.

## Chưa hoàn thành hoặc giới hạn MVP

- Chưa có dữ liệu BSR 2022 thực tế trong nguồn đã trích; năm 2022 trên dashboard mặc định là demo.
- Adapter đã nhập toàn bộ text trang và artifact, nhưng chỉ chuyển các fact trong structured JSON thành metric khi ánh xạ an toàn vào 16 metric cấu hình. Không phải mọi con số BCTC đều là metric ESG.
- Chưa có Gold Dataset được hai annotator khóa nhãn; do đó chưa báo cáo precision, recall, F1 hoặc Cohen kappa.
- Drill-down mở provenance dạng text; chưa nhúng PDF viewer/highlight trực tiếp vì PDF nguồn BSR không nằm trong gói đầu vào gốc của MVP.
- GRI omission chỉ là rule scaffold; cần materiality assessment được rà soát thủ công trước khi áp dụng dữ liệu thực.
- Không dùng mô hình machine learning hay API trả phí; toàn bộ phân loại/matching/rule là rule-based.
