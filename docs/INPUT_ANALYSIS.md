# Phân tích dữ liệu đầu vào ESG Tracker BSR

## Kết luận

Workspace có sáu bundle BSR cho giai đoạn 2023–2025: một báo cáo ESG và một BCTC cho mỗi năm. MVP dùng trực tiếp JSON theo trang, chunk, manifest, structured JSON và summary trong `output` dưới cờ `is_demo_data = false`. Dữ liệu minh họa 2022–2025 vẫn được tạo riêng dưới cờ `is_demo_data = true`; dashboard mặc định mở nguồn thực và không trộn hai nhóm.

## Inventory

| Nhóm | Định dạng | Số lượng/phạm vi | Cách dùng trong MVP |
|---|---|---:|---|
| Đặc tả triển khai | DOCX | 1 tệp, 153 đoạn, 33 bảng | Nguồn yêu cầu schema, metric, rule, scoring và dashboard |
| Tài liệu Phase 1 | DOCX | 2 tệp, 6 bảng tổng | Vocabulary, reading matrix và mẫu evidence |
| Page-level extracts | JSON | 6 tệp, 289 trang | Nhập toàn bộ text trang BSR vào `passages` |
| Chunk extracts | JSON + manifest | 74 chunk + 6 manifest | Lưu nguyên nội dung và hash trong `source_artifacts` |
| Structured extracts | JSON lồng nhau | 6 tệp ESG/BCTC | Adapter đệ quy lấy fact có metric rõ ràng và claim tường minh |
| Summary tổng hợp | Markdown | 6 tệp | Tạo claim dễ đọc, liên kết lại trang nguồn khi xác định được |
| Record Phase 1 | JSON | 22 record ESG + 12 record BCTC | Nguồn fallback tương thích, không dùng khi bundle `output` đầy đủ |
| JSON Schema | JSON Schema 2020-12 | 23 thuộc tính record | Đối chiếu kiểu và trường bắt buộc |
| Source manifest | JSON | 6 tệp có SHA-256 | Kiểm soát thay đổi nguồn |
| Source artifacts | SQLite | 98 artifact | Lưu loại artifact, đường dẫn, nội dung, SHA-256, khoảng trang và cờ nguồn |
| Standards | PDF | 9 tài liệu GRI; GRI 11 có 89 trang | Mapping GRI và điều kiện disclosure |
| CSV/Excel/SQLite đầu vào | Không có | 0 | SQLite do ứng dụng tạo mới |

Lưu ý: `output` có thể chứa dữ liệu của doanh nghiệp khác. Adapter dùng allow-list cố định cho `BSR_2023`, `BSR_2024`, `BSR_2025`, `BCTC_BSR_2023`, `BCTC_BSR_2024` và `BCTC_BSR_2025`; không nhập PLX/PVD.

## Ánh xạ dữ liệu nguồn sang schema hệ thống

| Trường/nguồn | Bảng/cột đích | Xử lý |
|---|---|---|
| Tên bundle | `documents.document_id`, `report_year`, `document_type` | Tách năm và ESG/BCTC theo allow-list |
| Page JSON: `pages[].page`, `text` | `passages.page_number`, `source_text` | Giữ text theo trang, không ghi đè file nguồn |
| Structured JSON: khóa/path | `claims`, `metrics.metric_code` | Duyệt đệ quy; chỉ ánh xạ metric khi từ khóa đủ rõ |
| Structured JSON: `value`, `unit`, `year` | `metrics.raw_value`, `raw_unit`, `metric_year` | Giữ gốc; chuẩn hóa qua `metrics.yml` nếu quy đổi được |
| Structured JSON: `scope`, `boundary`, `methodology` | các trường comparability của metric | Không tự điền khi nguồn thiếu |
| Summary bullet | `claims.source_text` | Chỉ lấy mục nội dung ESG/tài chính/assurance; bỏ checklist kỹ thuật |
| Trang dẫn trong summary/structured JSON | provenance của claim/metric | Liên kết tới `passages`; để NULL nếu không xác định chắc chắn |
| Mọi file trong bundle | `source_artifacts` | Lưu path, content, SHA-256, page range/count và loại artifact |

## Trường còn thiếu hoặc chưa đồng nhất

- Không có bundle BSR 2022 trong `output` hiện tại.
- Nhiều record thiếu `scope`, `boundary`, `methodology`, `denominator`, `baseline_year` hoặc `target_year`.
- Giá trị/đơn vị tài chính có biến thể như VND, triệu đồng, tỷ đồng; cần quy đổi có kiểm soát.
- JSON lồng nhau khác cấu trúc giữa năm và loại báo cáo; adapter đệ quy chỉ nhập fact ánh xạ an toàn, không coi mọi con số trong BCTC là metric ESG.
- Một số BCTC là scan/OCR; confidence và trạng thái ambiguity phải được giữ.
- Chưa có Gold Dataset đã khóa nhãn để đo precision, recall và F1.
- Không có file PDF nguồn BSR ở thư mục gốc; page-level JSON và provenance trỏ tới tên file nguồn đã xử lý trước đó.

## Kết quả nhập đã xác minh

| Hạng mục nguồn thực | Số lượng |
|---|---:|
| Tài liệu | 6 |
| Trang/passage | 289 |
| Artifact | 98 |
| Claim | 147 |
| Metric ánh xạ vào dictionary | 50 |
| Evidence link sau pipeline | 147 |
| Rule result sau pipeline | 161 |

50 metric là các fact đáp ứng metric dictionary hiện tại, không phải toàn bộ con số trong BCTC. BCTC 2024–2025 vẫn được nhập đầy đủ ở lớp trang, artifact và claim; adapter không ép các chỉ tiêu tài chính ngoài dictionary thành metric ESG.

## Guardrail

Mọi cảnh báo trong dashboard là tín hiệu rule-based để rà soát. `MISSING`, `AMBIGUOUS` và `NOT_COMPARABLE` không được đổi thành `CONTRADICTS`. Dữ liệu minh họa chỉ kiểm thử luồng và không phải phát hiện thực tế về BSR.
