# So sánh chỉ tiêu BSR qua các năm

Luồng sáu PDF hiện có hai phần chạy nối tiếp sau Extract:

1. Tìm ứng viên đối chiếu **ESG với BCTC** theo cùng năm đo.
2. Tìm chuỗi **trong ESG** hoặc **trong BCTC hợp nhất** theo năm đo 2023, 2024, 2025.

Phần thứ hai được tạo bởi `kg.longitudinal_scan` sau khi Graph chuẩn hóa bản ghi.
Mỗi chuỗi giữ loại báo cáo, đơn vị, năm đo, năm xuất bản, tên PDF, trang và câu trích.
Nếu một năm xuất hiện ở nhiều báo cáo, ưu tiên giá trị trong báo cáo của chính năm đó;
các bản khác vẫn nằm trong `alternative_source_versions` để duyệt.
Chuỗi ba năm có hai phép tính năm liền kề và một phép tính 2023 → 2025.

Các số tăng/giảm và phần trăm là **phép tính số học**. Chúng không chứng minh rằng
định nghĩa chỉ tiêu, phạm vi công ty, ngày đo và cách đếm giữ nguyên. Tất cả
các cặp đang có trạng thái `NeedsReview` (cần người kiểm tra), chưa phải kết luận
`Supported` (đồng bộ) hay `Contradicted` (mâu thuẫn).

## Chạy lại từ gói Extract đã có

```powershell
.\.venv\Scripts\python.exe -B -m tools.extract_graph_bridge --manifest output/bsr_esg_bctc_full_run_20261023/extract/delivery/manifest.json --profile data/config/bsr_esg_bctc_only_v1.json --run-dir output/bsr_esg_bctc_new_run
```

Mỗi lần chạy cần thư mục đầu ra mới. Muốn chạy cả Extract từ sáu PDF, thay
`--manifest ...` bằng `--extract-config output/bsr_esg_bctc_6pdf_config_20261023.json`.

Mở `index.html` trong thư mục kết quả để đi tới ba trang: cặp ESG ↔ BCTC,
so sánh theo năm và báo cáo Graph. Phần theo năm có:

- `temporal/series.json`: danh sách chuỗi và nguồn cho từng năm;
- `temporal/comparisons.json`: chênh lệch, phần trăm, trạng thái và lý do cần duyệt;
- `temporal/graph.json`: các nút/quan hệ thời gian nối vào `graph/graph.json` qua mã bản ghi;
- `temporal/report.html`: bảng đọc được bằng trình duyệt;
- `temporal/summary.json`: mức bao phủ và nhóm chưa thể ghép chắc chắn.

Trang của ESG 2025 trong PDF chính thức 134 trang khác PDF 68 trang người dùng đang xem.
Riêng trang 76 của bản 134 tương ứng trang 39 của bản 68; trang 106 tương ứng trang 54.
Chỉ hai cặp trang này đã được kiểm tra; các trang khác giữ số trang của đúng tệp nguồn.

Số so sánh trong ngoặc của ghi chú lao động BCTC năm sau được kiểm tra **riêng**.
Ví dụ BCTC 2025 trang 14 trích số năm 2024 là 1.891 người, trong khi BCTC 2024
trang 12 ghi 1.840 người. Giá trị 1.891 mới được đọc từ câu trích, chưa phải bản ghi
số đã chuẩn hóa. Người duyệt cần xác nhận PDF và xem có điều chỉnh lại số liệu không.

Nhãn “Dầu thô trong nước” ở ESG 2024 trang 24 xuất hiện ở hai bảng. Luồng dùng
mã dòng 1.1/1.4 và 2.1/2.4 trong ngữ cảnh trích xuất để tạo bốn chuỗi riêng.
Nếu mã dòng thiếu, giá trị không được tự ghép. Những nhóm vẫn còn hai giá trị
không phân biệt được sẽ nằm trong `blocked_groups`.
Nhãn “Nộp Ngân sách nhà nước” đang bị Extract gắn chiều E; cần duyệt lại phân loại
trước khi nói có chuỗi chỉ tiêu môi trường nhiều năm.
