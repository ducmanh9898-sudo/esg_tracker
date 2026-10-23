# Bàn giao corporate-extract-1.0

## Bản bổ sung V2 ngày 17/10/2026

Xem `docs/ESG_EXTRACT_V2.md`. Bộ xuất corporate hiện thêm local metric definitions
cho các dòng có căn cứ, phục hồi số nhân viên có ngày đo trực tiếp trong thuyết minh,
và xuất hàng đợi dạng object gồm priority_records/candidate_pairs/exclusions.
Không dùng lại cách đọc queue là array của bản cũ. Cặp chỉ là giả thuyết NeedsReview;
chưa đủ phạm vi/kỳ/phương pháp thì eligible_for_numeric_comparison=false.
Gói `outputs/ESG_extract_V2` có kiểm định và property graph tham chiếu local riêng;
không đồng nghĩa đã kết nối Graph bên ngoài.

## Giao diện

Khởi động lại app. Tải báo cáo hoặc mở kết quả trong Lịch sử trích xuất. Ở phần
Kết quả, chọn **Tải gói bàn giao chuẩn (ZIP)**. Nút JSON v2 vẫn giữ nguyên định
dạng nội bộ để tương thích. ZIP mới chứa PDF gốc, JSON theo hợp đồng được cung
cấp, manifest, nguồn native và validator. Gói mặc định là partial, cần rà soát.

## Dòng lệnh — PowerShell, mỗi lệnh một dòng

```powershell
cd "C:\Users\THINKPAD\Documents\ChatGPT\ESG\esg-tracker"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/export_corporate_handoff.py --saved-id JOB_ID --destination outputs/delivery_moi --zip
.\.venv\Scripts\python.exe scripts/export_corporate_handoff.py --bsr-history --destination outputs/BSR_delivery_moi --zip
.\.venv\Scripts\python.exe outputs/BSR_delivery_moi/validation/validate.py --manifest outputs/BSR_delivery_moi/manifest.json --pdf-dir outputs/BSR_delivery_moi/pdf
```

Thay JOB_ID bằng ID lịch sử; run cũ dùng `run:<id>`. `--destination` phải là thư
mục mới, không ghi đè bản đã bàn giao. Có thể truyền `--result` là result.json
của worker. JSON portable không chứa workspace/PDF nên không đủ để đóng ZIP.

`--bsr-history` tìm kết quả BSR 2023–2025 trong lịch sử local, không chạy OCR,
giữ phiên bản mới nhất cho mỗi năm/loại/phạm vi và thêm đầu mục thiếu trong ma trận 3 năm × 3 loại.
Nó không tự tìm các PDF/JSON cũ nằm ngoài lịch sử, cũng không tải nguồn chính thức.

`--source-info provenance.json` nhận một object keyed bởi SHA256 của PDF:

```json
{
  "<PDF_SHA256>": {
    "url": "https://official.example/report.pdf",
    "downloaded_at_utc": null
  }
}
```

URL được cung cấp không tự chứng minh bytes khớp bản công bố chính thức. Không
điền URL ví dụ này vào dữ liệu thật. Không suy ngày công bố từ ngày ký.

## Các giới hạn phải ghi khi bàn giao

- Đây là adapter xuất chuẩn, không biến OCR thành bản chép tay đã xác nhận.
- Metric định nghĩa chưa được xác định vẫn null; không gộp theo tên/alias.
- Các record không xác định E/S/G hoặc không ánh xạ được loại giữ trong notes/native
  với issue, không biến mất khỏi nguồn và không ép thành claim.
- Search coverage chưa được kiểm chứng vẫn not_searched; không tạo disclosure absence.
- Compound units, footnote chưa liên kết, scope/population/method chưa xác định
  giữ unknown/null. Restatement không có nhãn giữ unknown, không khẳng định không có.
- BCTC chưa xác định phạm vi tài liệu bị chặn xuất chuẩn; không đoán từ tên file.
- Danh sách tài liệu đính kèm riêng/hợp nhất không được dùng làm title của PDF.
- `mechanical_valid` không đồng nghĩa `complete_handoff`; xem counts partial,
  unavailable, blocked và reviewer status. Chưa có workflow review để tự động
  chuyển gói thành hoàn chỉnh/ngữ nghĩa đã kiểm chứng.

## Kiểm thử

`tests/test_corporate_handoff.py`: schema/validator gốc, hash, duplicate sources,
cột so sánh, normalization một lần, precision, nguồn thiếu, scope conflict,
attachment list, không ghi đè và đóng ZIP. `scripts/verify_corporate_ui.cjs`
kiểm tra nút tải ZIP từ lịch sử trên server QA cổng 8051.

## Chạy lại ba PDF ESG BSR và cập nhật parser mà không làm mất bản cũ

```powershell
.\.venv\Scripts\python.exe scripts/capture_bsr_esg_handoff.py "C:\Users\THINKPAD\Documents\Báo cáo ESG"
.\.venv\Scripts\python.exe scripts/refresh_esg_handoff.py JOB_ID --vi-years 2025
```

Lệnh đầu dùng Docling, chọn native text khi có lớp chữ đủ dài, còn lại OCR theo
cấu hình. Đây là heuristic có khai báo trong profile, không bảo đảm đọc nội dung
biểu đồ. Thời hạn chuyển đổi Docling mặc định 120 giây/trang, thực thi bằng
worker riêng có thể dừng đúng cây tiến trình sở hữu khi quá hạn; có thể đổi bằng
`--page-timeout`. Runtime settings lưu riêng trong job, không làm mất checkpoint.
Không dùng JSON diễn giải cũ làm nguồn. Lệnh thứ hai tạo job lịch sử mới,
parser 3 nhận dạng STT/NHÓM/CHỈ SỐ TRỌNG YẾU/ĐVT và topic workforce. Chỉ dùng
`--vi-years 2025` sau khi kiểm tra định dạng số Việt Nam trên PDF tương ứng.
Không biến kết quả thành reviewed. Gói có `notes/demo_review_queue.json` để
người rà soát bắt đầu từ các chủ đề demo, không phải danh sách mâu thuẫn.

Khi các trang đồ họa khiến Docling liên tục quá hạn, dùng:

```powershell
.\.venv\Scripts\python.exe scripts/finish_bsr_esg_with_native_fallback.py "C:\Users\THINKPAD\Documents\Báo cáo ESG"
```

Lệnh này tạo **profile hybrid mới**: tái sử dụng quan sát Docling đã thành công
với hash/lineage, đọc trực tiếp chữ và bảng PDF bằng PyMuPDF cho phần còn lại.
Không ghi đè checkpoint cũ; source/record anchors của profile mới có thể khác.
Mọi trang fallback vẫn `partial`, kể cả khi đọc được chữ/bảng, không được gọi là
Docling đã hoàn thành. File scan thiếu lớp chữ không được coi là đã đọc; vẫn cần
OCR. Ô gộp giữ bbox và span theo lưới parser, không tạo giá trị cho ô không có.
`notes/native` giữ checkpoint, full native page text và phương pháp từng trang.
Một số biểu đồ, footnote và định nghĩa/boundary vẫn cần người rà soát.

Luồng upload mặc định cũng dùng page worker riêng, deadline 180 giây/trang.
Profile mới tách khỏi cache cũ; lịch sử và file kết quả cũ vẫn giữ nguyên.

Nguồn BSR đã tải qua HTTPS Windows và đối chiếu bytes được cấu hình tại
`config/bsr_verified_sources_20261016.json`. Khi xuất, có thể truyền file đó bằng
`--source-info`. Bộ xuất tính lại SHA-256 của bản tải đối chứng, không tin một
cờ verified đơn thuần. Các phiên bản nguồn bị loại khỏi ma trận chín đầu mục
được liệt kê trong `notes/source_selection.json`; không xóa file/lịch sử cũ.
