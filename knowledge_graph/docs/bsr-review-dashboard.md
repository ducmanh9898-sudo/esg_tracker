# BSR 2023–2025: màn hình các thông số cần duyệt

ESG Tracker hiện đọc `review_cases.json` trực tiếp: chạy ứng dụng tại
`D:\ESG\esgtracker` và mở `http://127.0.0.1:8050/#graph-review` để xem mục
**Đối chiếu BSR** ngay trong dashboard. Mặc định bảng chỉ hiển thị kết quả của
phiên upload hiện tại; muốn xem batch BSR đã chạy trước thì chọn **Lượt BSR đã
chạy trước**. Trang HTML riêng bên dưới vẫn dùng được khi chỉ muốn xem kết quả
Graph mà không chạy ứng dụng ESG Tracker.

Lệnh Extract → Graph trong `tools/extract_graph_bridge.py` tạo `index.html` và
`review_cases.json` sau bước so sánh qua năm. Trang tổng hợp lấy trạng thái từ
`graph/findings.json`, câu trích và trang nguồn từ kết quả Extract, cùng các
đối chiếu bổ sung qua năm. Mỗi trường hợp có liên kết mở đúng trang PDF.

Lượt chạy hiện tại dùng 6 PDF: ESG và BCTC hợp nhất của từng năm 2023, 2024,
2025. Trang hiển thị 10 trường hợp `NeedsReview` (cần người duyệt): 8 cặp
ESG ↔ BCTC do Graph tạo, 1 số lao động BCTC năm 2024 khác nhau giữa báo cáo
2024 và cột số so sánh của báo cáo 2025, và 1 chỉ tiêu nộp ngân sách trong ESG
2023/2024 có năm đo ở báo cáo trước chưa rõ. Hai đối chiếu bổ sung chưa phải
`finding` (kết luận có mã) trong Graph. Các thay đổi đơn thuần từ năm này sang
năm khác trong 81 phép so sánh theo thời gian không được mặc nhiên xem là mâu
thuẫn; xem trang `temporal/report.html` để khảo sát chúng.

Mở trên localhost:

```powershell
.\run_bsr_review_dashboard.ps1
```

Sau đó vào địa chỉ do lệnh in ra. Có thể chọn cổng khác bằng `-Port 8766`.
Nếu chạy lại pipeline với thư mục output khác, dùng `-RunDir <thư_mục_output>`.
Muốn tạo lại riêng màn hình từ một kết quả đã chạy, không cần chạy lại OCR:

```powershell
.\.venv\Scripts\python.exe -B -m tools.bsr_review_dashboard `
  --run-dir output/bsr_esg_bctc_temporal_final_20261023 `
  --manifest output/bsr_esg_bctc_full_run_20261023/extract/delivery/manifest.json
```

Trang PDF 2025 là trang **vật lý của bản chính thức 134 trang**. Ví dụ, trang
76 của bản đó tương ứng trang 39 trong bản PDF 68 trang; trang 106 tương ứng
trang 54. Chữ OCR trong câu trích có thể thiếu dấu, vì vậy người duyệt cần mở
PDF gốc. `NeedsReview` không có nghĩa đã xác nhận mâu thuẫn; cần kiểm tra năm
đo, phạm vi hợp nhất, định nghĩa, đơn vị, cách làm tròn và điều chỉnh số liệu.
Màn hình hiện chỉ đọc kết quả, chưa ghi quyết định duyệt trở lại Graph.
