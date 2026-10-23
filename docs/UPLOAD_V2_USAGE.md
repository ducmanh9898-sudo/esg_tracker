# Trích xuất bằng kéo thả — pipeline v2

## Khởi động

Trong PowerShell hoặc CMD, dùng lệnh một dòng:

```powershell
cd "C:\Users\THINKPAD\Documents\ChatGPT\ESG\esg-tracker"
.\.venv\Scripts\python.exe app.py
```

Mở `http://127.0.0.1:8050`, tìm khu vực **ESG TRACKER / EXTRACT**.
Nếu ứng dụng đang chạy phiên bản cũ, dừng bằng Ctrl+C rồi chạy lại.

## Quy trình

1. Kéo thả PDF hoặc bấm chọn file. Giới hạn 20 file/lần, 100 MB/file và
   250 MB/lần tải. File được xử lý toàn bộ trang, không giới hạn smoke-test.
2. Nhập mã doanh nghiệp, năm và loại báo cáo nếu tên file không rõ. Các
   trường nhập áp dụng cho cả batch; khi tải nhiều doanh nghiệp/năm/loại,
   để trống metadata tương ứng và kiểm tra tên file. Nhận diện từ tên file
   là metadata ứng viên, không phải nội dung đã xác minh. Không tự lấy năm
   báo cáo để điền năm cho từng số liệu.
3. Để quy ước số `auto` nếu chưa kiểm tra tài liệu. `1.594` giữ ambiguous
   trong auto; chọn Việt Nam chỉ khi đã xác nhận dấu chấm phân cách hàng
   nghìn. Không chọn locale chỉ để làm hết mục cần rà soát.
4. Bấm **Trích xuất và phân tích**. Tiến độ hiển thị tài liệu và trang đọc
   thành công/đã xử lý. Trang failed/partial không được tính là đọc thành công.
   Docling thực hiện OCR, bố cục và bảng; sau đó BCTC đi vào financial v2,
   ESG/BCTN đi vào ESG v2. Các file lỗi có danh sách riêng; không chặn file khác.
5. Lọc/sắp xếp bảng records, chọn nút tròn ở một hàng. Phần **Đối chiếu nguồn**
   hiển thị nguyên văn, field_sources (trang PDF, hash, JSON pointer, bbox nếu
   có), ô bảng, boundary và missing_fields. PDF gốc tự chọn theo record;
   bấm **Mở PDF gốc ở tab mới** để mở tại trang nguồn. Trình xem PDF của trình
   duyệt có thể không hỗ trợ page anchor. Có thể chọn PDF khác hoặc tải về.
6. Bấm **Tải kết quả JSON v2** để lấy `ESG_upload_analysis_v2.json`.

## Cách đọc JSON

- `documents[].output.records`: claim/policy/action/target/governance,
  metric/measurement hoặc financial_context tùy nhánh.
- `documents[].output.evidence` và `links`: ứng viên ESG, hoặc liên kết
  metric–measurement của tài chính. Không đồng nhất hai loại quan hệ.
- `documents[].coverage`: tổng trang và trạng thái từng trang.
- `documents[].output.issues`: toàn bộ mục cần rà soát; giao diện chỉ hiển thị
  tối đa 100 mục để tránh quá tải.
- `documents[].native_artifacts[artifact_id]`: checkpoint Docling nguyên bản.
  `native_json_pointer` được resolve từ đối tượng này, không phải từ root JSON
  tải xuống. PDF gốc tải riêng; JSON không nhúng toàn bộ bytes PDF.
- `failures`: tài liệu không tạo được output; không coi là tài liệu thiếu công bố.

Kết thúc worker không đồng nghĩa đã đọc đủ trang hoặc hiểu đủ dữ liệu.
`capture_status: partial`, `semantic_status: partial`, `needs_review` và
`graph_ready: false` được giữ rõ ràng. Việc xem record không tự chuyển thành
verified. Chưa có thao tác sửa/duyệt field rồi lưu vào JSON trên giao diện này.
Chưa tự tính so sánh đạt mục tiêu hoặc đưa ra kết luận greenwashing.

## Lưu trữ và giới hạn

### Quy cách tên file tải về

JSON một báo cáo: `<MA_DN>_<LOAI>_<NAM>_[PHAMVI_]extract_v2_<YYYYMMDD_HHMMSS>_<ID8>.json`.
Ví dụ: `BSR_BCTC_2024_HOPNHAT_extract_v2_20261010_101530_A1B2C3D4.json`.
Loại gồm BCTC, BCTN hoặc ESG. BCTC có RIENG/HOPNHAT khi có bằng chứng PDF;
chưa rõ thì PHAMVI_UNKNOWN, không suy từ tên file. Metadata PDF khả dụng được
ưu tiên; nếu chưa có thì dùng metadata đầu vào để đặt tên, không coi là xác minh.
Mã doanh nghiệp/năm chưa có là UNKNOWN. Timestamp theo giờ Việt Nam (UTC+7),
ID ngẫu nhiên phân biệt các lần tải. Tên chỉ dùng chữ ASCII/số/gạch dưới an toàn
trên Windows. `v2` chỉ nhánh xuất JSON, không có nghĩa dữ liệu đã xác minh.

Batch thêm BATCH02/BATCH03… theo số file đầu vào; nhiều doanh nghiệp/năm là MULTI,
nhiều loại là MIXED. Ví dụ `MULTI_MIXED_MULTI_BATCH02_extract_v2_20261010_101530_A1B2C3D4.json`.
Batch chỉ thành công một phần vẫn giữ nhãn batch, không đổi thành một báo cáo.
JSON vẫn chứa toàn bộ documents/failures như trước. PDF gốc tải xuống giữ nguyên
tên nguồn để truy vết; quy cách mới chỉ áp dụng nút tải kết quả JSON trên giao diện.

File upload: `data/uploads/<run_id>/<index>/`.
Outputs/manifest: `data/processed/uploads_v2/<run_id>/`.
Checkpoint dùng lại giữa các lần upload: `data/processed/capture_v2/` (phân biệt
metadata đầu vào, PDF hash và extraction profile).
Các báo cáo riêng/hợp nhất cùng doanh nghiệp/năm được lưu độc lập, không
ghi đè nhau. Luồng upload không tự nhập records vào SQLite hoặc chạy bộ
scoring của dashboard dữ liệu có sẵn. Các màn dashboard cũ vẫn độc lập.

OCR/Docling chạy trong tiến trình con; lỗi native của worker không làm tắt Dash.
Job/progress/result/log được lưu tại `data/processed/extraction_jobs/<job_id>/`.
Job ID lưu trong session của tab; F5 cùng tab có thể đọc lại trạng thái từ đĩa.
Đóng tab hoặc xóa session có thể mất liên kết; chưa có màn lịch sử job.
Nếu worker dừng, tải lại cùng PDF và giữ nguyên metadata để dùng lại trang
processed cùng profile. Đổi backend/package/OCR sẽ tạo profile khác và đọc lại.
Chưa có hủy job, timeout trang hoặc dọn file tự động. Xem [khôi phục lỗi OCR](OCR_CRASH_RECOVERY.md).
Không triển khai
server phát triển này ra Internet: URL PDF dùng UUID job làm capability,
chưa phải cơ chế đăng nhập/phân quyền nhiều người dùng.

Các kiểm thử tích hợp dùng nguồn giả lập có kiểm soát; chưa chứng minh độ
đầy đủ/accuracy trên toàn bộ báo cáo BSR/PLX thực tế. Xem thêm
[nhánh ESG](ESG_V2_USAGE.md) và [nhánh tài chính](FINANCIAL_V2_USAGE.md).
