# BSR 2023–2025 — gói bàn giao để rà soát

## Kết quả đã kiểm tra

- Đủ chín đầu mục: ESG, BCTC riêng và BCTC hợp nhất cho 2023, 2024, 2025.
- Chín PDF nguyên bản, chín JSON corporate-extract-1.0, manifest đúng schema.
- SHA-256 của chín PDF khớp bản tải đối chứng từ HTTPS chính thức BSR. Không tắt TLS.
- 8.669 bản ghi ứng viên; không được hiểu thành 8.669 claim đã xác minh.
- Validator được cung cấp: PASS 9 file / 8.669 records.
- Kiểm tra bổ sung: tính lại 5.227 phép chuẩn hóa; đối chiếu 8.669 quote với
  checkpoint native và SHA-256 của 418 checkpoint. Không có lỗi cơ học.
- Toàn bộ bản ghi vẫn pending_human_review, không tự duyệt boundary hay kết luận greenwashing.

Nguồn ESG 2025 trên website BSR khác bytes với bản local đã ký/tải lên trước đây.
Gói này trích xuất bản chính thức như **nguồn mới**, không thay PDF dưới JSON cũ.
File local và lịch sử trước đó vẫn còn. Xem notes/source_provenance.json và
notes/source_selection.json để phân biệt phiên bản.

## Phương pháp và giới hạn còn lại

Gói giữ checkpoint Docling thành công. Với trang đồ họa Docling liên tục quá hạn,
chữ và ô bảng đọc trực tiếp PDF bằng PyMuPDF, ghi read_method và trạng thái partial.
Không tạo số/bbox/nhãn năm từ diễn giải. Định dạng số Việt Nam trên bảng lao động
2025 đã được xem trực quan trước khi chọn vi; các kỳ khác giữ auto nếu chưa rõ.

ESG 2025 bản chính thức có 67 trang native partial và một trang không đủ lớp chữ
(trang vật lý 68), giữ lỗi/chờ OCR hoặc kiểm tra nguồn. Không tự gọi đó là trang
trắng. Đọc được chữ không chứng minh đọc đủ biểu đồ, footnote hoặc toàn bộ KPI.

Những việc người rà soát vẫn phải làm:

1. So quote/ô/header/footnote với PDF thật, nhất là bảng gộp ô, biểu đồ và trang fallback.
2. Xác nhận định nghĩa metric trước khi gán metric_id chung giữa tài liệu.
3. Xác nhận kỳ đo, population, pháp nhân/boundary, phương pháp tính và restatement.
4. Chỉ sau khi người rà soát xác nhận đủ điều kiện so sánh mới chuyển sang Graph.

Unknown/null không phải 0 hay không công bố. Search found chỉ là tín hiệu có
trong vùng nguồn; không chứng minh đã tìm đủ. Các record không ánh xạ được giữ
trong notes/native và issue_log, không ép thành một loại giả để qua schema.

## Kiểm tra độc lập sau giải nén

Chạy từ thư mục chứa manifest.json:

```text
python -m pip install -r validation/requirements.txt
python validation/validate.py --manifest manifest.json --pdf-dir pdf
python validation/audit_corporate_handoff.py . --bsr-nine --pending-only
```

Lệnh bổ sung không phụ thuộc code ESG Tracker hoặc Knowledge Graph. Bỏ
`--pending-only` khi kiểm tra một bản đã được con người rà soát hợp lệ sau này.
Validator và audit không chứng minh OCR/năm/đơn vị đúng ngữ nghĩa so với PDF.

## Công cụ đã cập nhật

- Nút **Tải gói bàn giao chuẩn (ZIP)** ở phần Kết quả; JSON v2 cũ vẫn giữ nguyên.
- CLI export_corporate_handoff.py; lựa chọn bản mới nhất theo năm/kỳ và phạm vi
  có căn cứ trong PDF, không để năm nhập sai làm loại mất một đầu mục.
- Parser ESG 3: nhận diện STT/NHÓM/CHỈ SỐ TRỌNG YẾU/ĐVT, topic lao động.
- Parser BCTC 6: không lấy năm của một khoản cổ tức làm năm đo một cách máy móc;
  danh sách đính kèm riêng/hợp nhất không xác định scope của PDF.
- Worker từng trang có deadline và dừng đúng cây tiến trình sở hữu; lỗi không
  làm mất checkpoint hoặc làm giao diện ngừng phục vụ.
- Lịch sử có index nhỏ trên đĩa, không phải đọc lại toàn bộ JSON lớn mỗi lần mở app.

Khởi động lại app, rồi Ctrl+F5 để thấy nút mới. Xem hướng dẫn chi tiết trong
docs/CORPORATE_HANDOFF_USAGE.md của dự án.
