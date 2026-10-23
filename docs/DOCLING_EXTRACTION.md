# Trích xuất bằng Docling

Giao diện kéo thả sử dụng Docling với OCR toàn trang và nhận diện bảng ở chế độ ACCURATE.
Các mô hình được tải về máy lần đầu; tài liệu được xử lý cục bộ.

JSON tải xuống có `structured_documents`: toàn bộ JSON gốc theo trang, các bảng,
các hàng và ô với chỉ số hàng/cột, span và provenance của Docling.
File `documents/<document-key>/docling_full.json` lưu cùng nội dung trong mỗi run.

Các hàng chứa số được đưa vào bảng claim để rà soát. `value`, `unit` và
`period_mapping` giữ null cho đến khi xác định chắc ý nghĩa ô. Không còn dùng
parser bốn metric cũ để suy luận từ Markdown do Docling tạo.

CLI:

```powershell
.\.venv\Scripts\python.exe scripts\extract_corpus.py "C:\duong-dan\BCTC_BSR_2025.pdf" --engine docling --run-id bsr_docling_v1
```

`--max-pages 3` chỉ dùng để kiểm tra cài đặt. Bỏ tham số này để đọc cả tài liệu.
Docling có thể bỏ sót bảng hoặc đọc sai OCR; xuất đủ các ô được phát hiện không
đồng nghĩa mọi trường đã được xác minh. Cần so sánh nguồn và kiểm tra các tổng.

## Kiểm tra thực tế

Đã kiểm tra một trang của BCTC riêng BSR 2025 (trang PDF 9): phát hiện 1 bảng,
38 hàng và 198 ô. Hàng mã số 270 có hai ô `85.004.418.533.771` và
`88.352.140.328.065`, kèm chỉ số cột và tọa độ. Tên chỉ tiêu vẫn có lỗi OCR
tiếng Việt; đây là kiểm tra khả năng trích xuất, không phải xác nhận toàn bộ
44 trang hay tính đúng đắn của mọi trường. Phiên bản thử nghiệm: Docling 2.135.0.
