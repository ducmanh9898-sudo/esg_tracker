# Sử dụng nền tảng extract v2

Đã triển khai bước P0/P1: schema JSON cho gói nguồn, ID theo PDF hash và
profile, bản PDF nguồn trong thư mục kết quả, checkpoint từng trang,
retry/resume, coverage và issue log. Chưa triển khai parser semantic ESG/BCTC,
review UI, Graph adapter, OCR routing theo chất lượng hoặc timeout từng trang.
Luồng kéo thả hiện tại vẫn chạy phiên bản trước, không tự chuyển sang v2.

## Chạy bằng PowerShell hoặc CMD

Tại thư mục `C:\Users\THINKPAD\Documents\ChatGPT\ESG\esg-tracker`, dùng
lệnh một dòng. Ví dụ dưới đây dùng file BSR hiện có trên máy:

```powershell
.\.venv\Scripts\python.exe scripts\extract_source_v2.py "C:\Users\THINKPAD\Documents\20260326 - BSR - BCTC rieng da duoc kiem toan cho nam tai chinh ket thuc ngay 31.12.2025.pdf" --company BSR --report-type financial_statements --report-year 2025
```

Chạy thử đúng trang PDF 9: thêm `--start-page 9 --max-pages 1`. Những trang khác
vẫn hiện pending; không coi đây là đọc full 44 trang. Tham số `--retries 1`
mặc định cho phép tối đa hai lần thử mỗi trang trong một lượt chạy.

ESG dùng `--report-type ESG`, thường niên dùng `--report-type annual_report`.
Company/year/type là metadata người dùng cung cấp, chưa tự xác minh từ nội dung.
Separate/consolidated và publication date còn null, không suy luận từ tên file.

Chạy lại đúng lệnh để resume: trang processed được dùng lại; trang partial hoặc
failed trong phạm vi chọn được thử lại; pending được xử lý. Bỏ giới hạn trang
để tiếp tục cả tài liệu. Khi file hoặc extraction profile đổi, kết quả nằm ở
workspace khác. Profile gồm phiên bản package và cấu hình OCR/table; không phải
fingerprint từng byte model weights. Cùng PDF byte có cùng report version ID.

Không sửa metadata trong một workspace checkpoint bằng cách truyền metadata
mâu thuẫn; công cụ báo lỗi. Hiện chưa có giao diện hiệu chỉnh inventory.

## Đầu ra

```text
data/processed/source_v2/report_<pdf-sha256>/profile_<hash>/
  source.pdf
  inventory.json
  profile.json
  pages/0001.json ...
  canonical.json
  validation.json
```

`canonical.json` chứa source blocks, nguyên văn/cells, source refs tới JSON
pointer trong checkpoint và PDF page 1-based. Printed page chưa parse thì null.
Tables/cells giữ payload gốc của Docling, không ghép thành câu rồi coi là trích dẫn.
Trang có lỗi giữ issue và lịch sử attempts trong checkpoint. Mọi trang PDF có
coverage kể cả khi chỉ chạy một trang. JSON được ghi bằng temporary file rồi
atomic replace để hạn chế file hỏng khi ngắt giữa chừng.

`capture_status: completed` chỉ nghĩa converter đã có nội dung thành công
cho mọi trang. Nó không khẳng định OCR đọc đúng hoặc không bỏ sót. Trang rỗng
hoặc conversion partial được đánh dấu partial, không tự coi là trang trắng.

`semantic_status: not_started`, `graph_ready: false`, `records: []` là chủ ý
ở bước này. Nguồn được giữ để parser bước sau tạo records đúng yêu cầu. Không
đưa gói này vào Graph như dữ liệu đã hoàn tất. Schema `esg-source/2.0.0` chỉ
kiểm tra gói nguồn, không thay thế contract semantic `esg-extract` đã thiết kế.

Validation kiểm tra schema, coverage counts, ID uniqueness, source hashes,
native pointer resolution, page alignment và record/block/issue counts.
Schema valid không phải xác minh giá trị hoặc reporting boundary.

CLI exit code: 0 khi capture completed; 2 khi partial (bao gồm chạy giới hạn
trang); 1 khi lỗi chương trình/input/schema. Tất cả đều có thể cần review nguồn.

## An toàn và giới hạn

Chỉ một writer mỗi workspace: khóa hệ điều hành `.capture.guard` và marker
`.writer.lock` có protocol `os_guard_v1`. Hệ điều hành nhả khóa khi process chết;
lượt chạy sau tự thu hồi marker đúng protocol khi đã lấy được khóa OS.
Marker legacy/không rõ protocol không tự xóa: phải xác minh chủ sở hữu đã dừng.
Lỗi init model được lưu ở page issue; lần sau có thể chạy tiếp. Ctrl+C có thể
cần resume; checkpoints đã ghi vẫn còn. GUI upload có process isolation; CLI
này vẫn trực tiếp chạy conversion trong process của CLI. Chưa có cancel API
hay timeout trang để dừng model bị treo; không coi đây là worker production hoàn chỉnh.

Từ 2026-10-10, backend PDF là PyPdfium thay vì docling_parse. Backend và phiên bản
package nằm trong profile hash, nên không dùng lẫn checkpoint của backend cũ.

Không sửa trực tiếp checkpoints hoặc source.pdf. Kiểm tra hash chỉ giúp phát
hiện thay đổi, không thay thế chữ ký hay hệ thống quản lý tài liệu bất biến.
Gói nguồn nằm cục bộ; quyền nhóm và bước đóng gói ZIP vẫn cần làm sau.

## Bước triển khai sau nền tảng

Kiểm tra thực tế ngày 2026-10-09: trang PDF 9 của BCTC riêng BSR 2025 đã tạo
11 source blocks, validation không có lỗi, coverage 1 processed/43 pending.
Chạy lại dùng checkpoint, không gọi lại OCR. Bộ kiểm thử tổng: 50 tests passed.
Đây không phải kiểm chứng độ chính xác OCR của mọi ô hoặc đọc toàn bộ báo cáo.

Xây table context builder và financial parser: header đa cấp/xuyên trang,
currency/scale, current/comparative period, metric/measurement riêng từng ô số.
Song song sau đó mới thêm nhánh ESG cho paragraphs/targets/policies/actions/
governance và candidate links. Giữ unknown/null khi chưa đủ chứng cứ.

Tiến độ cập nhật: đã có parser ứng viên bảng trong cùng trang; xem
`docs/FINANCIAL_V2_USAGE.md`. Context xuyên trang và semantic ESG vẫn chưa có.
