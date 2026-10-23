# Kịch bản demo ESG Knowledge Graph — 2 đến 3 phút

## 1. Mở đầu

“Đây là prototype phát hiện tín hiệu bất nhất trong dữ liệu ESG đã trích xuất từ báo cáo BSR 2023–2025. Hệ thống không tự kết luận doanh nghiệp greenwashing; nó tạo finding có thể truy vết để chuyên gia kiểm tra.”

## 2. Giải thích pipeline

“Dữ liệu JSON ban đầu có cấu trúc khác nhau. Pipeline chọn 30 disclosure record E/S/G, chuẩn hóa về Common Input Schema, kiểm tra dữ liệu bắt buộc, chạy 9 rule và dựng knowledge graph.”

Chuỗi truy vết trên graph:

`Company → Report → Claim → Measurement → Evidence → Finding → Rule`

## 3. Trình diễn mâu thuẫn R01

Graph mở sẵn bộ lọc **Mâu thuẫn**.

1. Bấm Measurement thứ nhất: `1.780.388 tCO2e`.
2. Bấm Measurement thứ hai: `1.790.388 tCO2e`.
3. Bấm hai Evidence để chỉ ra cùng file BSR 2025 nhưng khác vị trí/JSON Pointer; trang liên quan là 29 và 65.
4. Bấm Finding R01: chênh lệch `10.000 tCO2e`.
5. Bấm Rule R01: rule chỉ chạy khi cùng công ty, báo cáo, kỳ, metric, unit và scope.

Câu kết luận nên nói:

“Đây là `Contradicted` ở cấp disclosure vì hai giá trị đủ điều kiện so sánh không khớp. Nó chưa phải kết luận gian lận; bước tiếp theo là đối chiếu PDF gốc để xác định restatement, khác boundary hay lỗi trích xuất.”

## 4. Trình diễn cross-year

Chọn **Cần đối soát**, bấm R05.

“Cùng số liệu phát thải của năm quan sát 2023 được trình bày khác nhau trong báo cáo 2023 và báo cáo 2024, chênh 118.404 tCO2e. Vì có thể là restatement hoặc thay đổi phương pháp, hệ thống gán `NeedsReview`, không gán `Contradicted`.”

## 5. Trình diễn rule đạt

Chọn **Đạt**, bấm R07.

“Từ 235 xuống 225 kgCO2e trên tấn sản phẩm tương ứng giảm 4,26%. Báo cáo công bố giảm 4%, nằm trong tolerance 0,5 điểm phần trăm nên rule trả `Supported`.”

## 6. Số liệu tổng kết

- 30 disclosure record E/S/G.
- 9 rule, sinh 10 finding.
- 1 Contradicted, 3 NeedsReview, 6 Supported.
- 113 node và 127 edge.
- 9 cặp metric PVD 2025 chồng lặp được nhận diện; giữ bản đầy đủ làm canonical và giữ bản partial làm provenance.

## 7. Giới hạn cần nói rõ

Các JSON hiện chưa lưu câu trích nguyên văn cho từng record và chưa kèm PDF gốc. Toàn bộ 30 record đang ở trạng thái `unreviewed`. Vì vậy demo chứng minh kiến trúc chuẩn hóa, graph, rule và explainability; chưa phải kết quả nghiên cứu cuối cùng.
