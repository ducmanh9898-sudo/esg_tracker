# Khôi phục lỗi OCR native trên Windows

## Thay đổi ngày 2026-10-10

Windows ghi nhận Python dừng ngày 10/10 lúc 00:38:56 tại
`docling_parse/pdf_parsers.cp312-win_amd64.pyd`, mã `0xc0000005`.
Đây là lỗi truy cập bộ nhớ trong thư viện native; try/except Python không đủ
để bảo vệ process giao diện. Chưa có bằng chứng xác định nguyên nhân nội bộ
của thư viện hoặc bảo đảm mọi PDF không còn lỗi.

- Converter chọn rõ `PyPdfiumDocumentBackend`, không dùng backend docling_parse.
- GUI chạy OCR/Docling trong subprocess, tối đa một worker đồng thời trong
  mỗi process Dash. Native crash của child được ghi thành job failed với mã lỗi.
- Trạng thái, kết quả và log nằm trên đĩa; F5 cùng tab giữ job ID bằng session.
- Checkpoint trang dùng chung giữa các lượt upload cùng PDF, metadata và profile.
- Khóa OS tự nhả khi worker chết. Marker legacy không tự xóa.
- JSON ghi atomic replace, có retry ngắn khi Windows tạm giữ file.

Không cần nâng cấp package để áp dụng bản sửa này.

## Kiểm chứng trên máy

- 154 tests passed; gồm child exit `0xc0000005`, Dash layout vẫn trả HTTP 200,
  checkpoint còn nguyên sau hard exit và writer khác không lấy được khóa đang dùng.
- BCTC BSR 2024: 45/45 trang processed, schema và references hợp lệ.
- Upload lại cùng file/metadata: dùng cùng workspace, SHA của cả 45 checkpoint
  không đổi; không gọi lại OCR các trang processed.
- Chất lượng semantic vẫn partial: 570 metrics, 1.330 measurements. Kiểm tra
  mẫu chỉ 16/38 ghép đủ mã chỉ tiêu/cột và đúng giá trị; 22 mẫu chưa resolve được.
  Ví dụ số tổng tài sản có trong raw/parsed value nhưng item_code_raw còn null
  khi backend gộp header mã số với thuyết minh. Không tự điền mã hoặc số liệu.
  Vì vậy đây là bản sửa độ ổn định, chưa phải chứng nhận chất lượng dữ liệu.

Gói chạy mới tại `outputs/BSR_2024_PyPdfium_20261010/` có manifest và
`verification.json` ghi rõ kiểm tra chưa đạt. Gói giao trước đó không bị ghi đè.

Cập nhật sau sửa ghép cột (parser 5, cùng ngày): 37/38 mẫu đạt; còn một ô
lẫn hàng trước giữ null. Gói mới `outputs/BSR_2024_mapping_v5_20261010/`;
xem [hướng dẫn parser 5](FINANCIAL_V2_USAGE.md). Số 16/38 phía trên là baseline
trước sửa ghép cột, không phải kết quả mới nhất.

## Sử dụng

1. Dừng ứng dụng cũ bằng Ctrl+C trong terminal của ứng dụng (không dừng tất cả Python).
2. Chạy PowerShell:

```powershell
cd "C:\Users\THINKPAD\Documents\ChatGPT\ESG\esg-tracker"
.\.venv\Scripts\python.exe app.py
```

3. Mở `http://127.0.0.1:8050`. Kéo thả báo cáo, kiểm tra mã DN/năm/loại/
   quy ước số rồi bấm trích xuất.
4. Nếu báo worker dừng: giữ PDF nguyên bytes, tải lại và nhập cùng metadata.
   Trang processed cùng profile được dùng lại; trang chưa hoàn tất được đọc tiếp.
   Không sửa checkpoint để ép thành processed.
5. Log chẩn đoán: `data/processed/extraction_jobs/<job_id>/worker.log`;
   trạng thái: `status.json`; kết quả: `result.json`.

20 trang đã lưu bằng backend cũ được giữ nguyên, nhưng lần chuyển PyPdfium
phải đọc lại trong profile mới. Đây không phải lỗi resume. Các lượt sau cùng
profile mới mới có thể dùng lại các trang đó.

## Giới hạn

Chưa có timeout từng trang, nút hủy hoặc màn lịch sử job. Nếu worker còn sống
nhưng không tiến triển, hệ thống chưa tự xác nhận là treo. Không mở nhiều
instance Dash để chạy song song mô hình nặng. Dữ liệu upload và request lưu
cục bộ, chưa có chính sách tự dọn hoặc phân quyền server nhiều người dùng.

Đọc đủ trang và schema hợp lệ không đồng nghĩa OCR đúng mọi ô hoặc semantic
đã đầy đủ. Công cụ hỗ trợ phân tích, không phải kiểm toán hay kết luận greenwashing.
