# ESG Tracker — giao diện workspace ngày 11/10/2026

## Đã triển khai

- Shell sidebar/header mới; điều hướng theo section, tự đánh dấu vị trí đang xem.
- Nền trắng/xanh rất nhạt; primary #15803D, dark #14532D. Inter hỗ trợ tiếng Việt,
  fallback Segoe UI. Không có ảnh lá trang trí, không thêm thư viện frontend.
- Tổng quan chỉ lấy dữ liệu phiên tải lên. Chưa có kết quả hiển thị dấu gạch,
  không tự tạo số. Claim, metric và measurement không cộng chung vào tổng claim.
- Status ứng viên/needs_review hiển thị NOT_REVIEWED — Chưa rà soát. Giá trị gốc
  trong record/JSON vẫn nguyên. Số claim đã rà soát chỉ dựa trên trạng thái rõ ràng.
- Upload hai cột desktop; một cột mobile, danh sách file, metadata, tiến độ hiện có,
  error state và nút thử lại dùng đúng file/tham số đã chọn.
- Danh sách có tìm kiếm và lọc doanh nghiệp, năm báo cáo, E/S/G, trạng thái, loại
  record; giữ phân trang/sort/filter native và chọn dòng theo ID ổn định.
- Chi tiết nội dung/nguồn đặt cạnh nhau trên desktop, xếp dọc mobile. Bbox/hash/
  JSON pointers/cells/boundary/missing_fields còn nguyên trong disclosure kỹ thuật.
- Đối chiếu tài chính và nhất quán nội bộ ESG là hai vùng riêng; không suy ra
  số claim đã đối chiếu tài chính từ link nội bộ hoặc metric–measurement.
- Dashboard dữ liệu đã lưu vẫn có đầy đủ tabs/callbacks, nằm riêng trong vùng
  lưu trữ. Không lấy điểm rủi ro cũ làm điểm ESG của phiên tải lên.

## Khả năng truy cập & responsive

Desktop sidebar; dưới 900px điều hướng ngang cuộn được. Ở 320/390/1024px không
tràn ngang toàn trang; bảng cuộn ngang riêng. Focus rõ, skip link, nhãn accessible
cho combobox và chọn dòng, live status, reduced motion. Chuyển trạng thái 180ms.
Các cặp màu chữ chính/phụ/nút/cảnh báo/lỗi được đo AA >=4.5:1; placeholder
dropdown cũng kiểm tra computed CSS để tránh màu nhạt từ stylesheet cũ.
Đây là kiểm tra có phạm vi, không phải chứng nhận toàn bộ WCAG/screen-reader.

## Kiểm tra lại

Khởi động app tại thư mục dự án:

```powershell
.\.venv\Scripts\python.exe app.py
```

Kiểm thử Python: `python -m pytest -q -p no:cacheprovider` bằng Python của .venv.
Kiểm thử trình duyệt: `node scripts/verify_workspace_ui.cjs --extract`.
Script dùng Playwright/Edge có sẵn trong môi trường QA; không thêm dependency
vào runtime app. Có thể đặt ESG_UI_BROWSER=chrome nếu môi trường QA dùng Chrome.

Test trình duyệt gồm empty/error/retry, điều hướng, focus, responsive, upload
BCTC BSR 2024, chọn record, đọc PDF nguồn HTTP 200, tải JSON và search không khớp.
Ảnh và báo cáo kiểm tra: `outputs/ui_qa_20261011/`.

Kết quả kiểm chứng: 171 tests passed. Browser QA với Edge đạt ở 1440px,
1024px, 390px và 320px; không có JavaScript page errors. Bộ lọc năm, doanh
nghiệp, trạng thái và tìm kiếm đã thao tác thực tế, cùng luồng upload/export.
Tỷ lệ tương phản đo được: chữ chính 14.95, chữ phụ 4.94, chữ phụ trên xanh
nhạt 4.72, nút chính 5.02, warning 6.84 và error 7.60.

Logic parser/OCR, worker, DB schema, API PDF và cấu trúc JSON export không đổi.
Các adapter mới chỉ tạo dữ liệu hiển thị; không ghi trạng thái review vào output.
Chưa bổ sung thao tác duyệt/sửa field hay engine so sánh tài chính mới.
# Dashboard lưu trữ — đồng bộ theme

Áp dụng cùng token Superdesign xanh–trắng cho `.legacy-dashboard`: header, bộ lọc,
tab, KPI, bảng, biểu đồ và chi tiết bằng chứng. CSS được giới hạn trong dashboard
lưu trữ; không thay đổi callback, dữ liệu, API hay cách tính. Màu cảnh báo vẫn
giữ amber/red; bằng chứng ứng viên có nền trung tính để tránh ngụ ý đã xác minh.
Bảng có độ rộng tối thiểu cho cột văn bản và vùng cuộn tối đa 620px.

Kiểm tra bằng `node scripts/verify_archive_ui.cjs`: 5 tab × 4 kích thước màn hình
(1440, 1024, 390, 320), không tràn ngang toàn trang, màu tab đang chọn, đặt lại
bộ lọc, chi tiết bằng chứng và focus bàn phím. Ảnh và kết quả nằm tại
`outputs/ui_qa_20261011/archive/`.

