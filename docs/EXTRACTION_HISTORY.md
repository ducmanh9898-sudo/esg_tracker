# Lịch sử trích xuất

Kết quả được lưu tự động trên máy, không phụ thuộc tab hoặc bộ nhớ Python.
Trong phần Tải & trích xuất, chọn **Lịch sử trích xuất → Kết quả đã lưu →
Mở kết quả đã lưu**. Bảng records, nguồn PDF và nút tải JSON sử dụng lại kết quả
cũ, không chạy OCR. Có nút làm mới danh sách; không chuyển phiên khi đang xử lý.

Nguồn lịch sử:

- `data/processed/extraction_jobs/<job_id>/result.json` và `status.json`.
- Các lần cũ tại `data/processed/uploads_v2/<run_id>/run_manifest.json`, cùng
  file output được manifest tham chiếu, nếu vẫn còn trên máy.
- Dữ liệu nguồn và checkpoint tiếp tục nằm ở `data/processed/capture_v2/`.

Các bản ghi job và run tương ứng được gộp thành một mục. Lịch sử chỉ liệt kê
kết quả có tài liệu; số file lỗi được ghi trong nhãn. Lưu kết quả không đồng
nghĩa xác minh dữ liệu hay nhập vào dashboard SQLite. Không xóa các thư mục
trên nếu muốn mở lại kết quả. PDF/JSON không có sẵn trên ổ đĩa không thể được
khôi phục chỉ bằng lịch sử trình duyệt. Đây là lịch sử chung của bản cài local,
chưa có phân quyền theo tài khoản.

Kiểm tra: `tests/test_extraction_history.py` và `scripts/verify_history_ui.cjs`.
