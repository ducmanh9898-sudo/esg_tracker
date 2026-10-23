# Bộ công cụ trích xuất ESG dùng chung

## Phạm vi

Bộ công cụ tạo dữ liệu ứng viên ở cấp claim và company từ:

- Báo cáo phát triển bền vững/ESG.
- Báo cáo thường niên.
- Báo cáo tài chính.

Pipeline giữ nguyên tài liệu, trang nguồn, SHA-256, phương pháp trích xuất và trạng thái cần rà soát. Đầu ra không phải ý kiến kiểm toán, kết luận sai phạm hoặc kết luận greenwashing.

## Thành phần

- `config/extraction_toolkit.yml`: registry doanh nghiệp, phân ngành, quy tắc tên file và ngưỡng trích xuất.
- `config/metrics.yml`: taxonomy chỉ tiêu ESG và đơn vị chuẩn.
- `src/extraction/toolkit.py`: nhận diện tài liệu, đọc PDF, loại header/footer lặp, nhận OCR sidecar, tạo claim candidates và review queue.
- `scripts/extract_corpus.py`: CLI cho một PDF hoặc cả thư mục.

Registry mẫu đã có BSR, GAS, PLX và PVD. Có thể bổ sung doanh nghiệp bằng YAML mà không sửa mã Python.

## Quy ước tên file

Các dạng mặc định:

```text
<COMPANY>_<YEAR>.pdf
BCTC_<COMPANY>_<YEAR>.pdf
BCTN_<COMPANY>_<YEAR>.pdf
ESG_<COMPANY>_<YEAR>.pdf
```

Loại báo cáo cũng được suy ra từ thư mục `BCESG`, `BCTC`, `BCTN`, `ESG`, `SUSTAINABILITY` hoặc `ANNUAL_REPORT`. Token `BCTC` có thể nằm sau ngày hoặc mã công bố trong tên file, không bắt buộc ở đầu tên.

Với tên file không theo quy ước, chạy một file cùng các tham số `--company`, `--year` và `--document-type`.

## Chạy kiểm kê trước khi trích xuất

Từ thư mục `esg-tracker`:

```powershell
.\.venv\Scripts\python.exe scripts\extract_corpus.py "C:\duong-dan\raw_pdf" --dry-run
```

Kiểm tra `company_id`, năm, loại báo cáo và subsector trước khi chạy thật.

Nếu thư mục chứa nhiều ngành nhưng chỉ muốn chạy các doanh nghiệp đã đăng ký cho demo Oil & Gas:

```powershell
.\.venv\Scripts\python.exe scripts\extract_corpus.py "C:\duong-dan\raw_pdf" --registered-only --dry-run
```

Doanh nghiệp chưa có trong registry được gắn `industry = Unknown`, không tự động coi là Oil & Gas.

## Chạy trích xuất

```powershell
.\.venv\Scripts\python.exe scripts\extract_corpus.py "C:\duong-dan\raw_pdf" --run-id oil_gas_2023_2025_v1
```

Đầu ra mặc định:

```text
data/processed/extract/<run-id>/
├── run_manifest.json
├── claims.json
├── claims.csv
├── review_queue.json
├── review_queue.csv
├── company_summary.json
├── company_summary.csv
└── documents/<document-key>/
    ├── manifest.json
    ├── pages.json
    ├── claims.json
    └── review_queue.json
```

Run id là bất biến: công cụ từ chối ghi đè thư mục đã tồn tại. Dùng run id mới khi chạy lại để giữ audit trail.

## PDF scan và OCR

Công cụ mặc định tự phát hiện trang scan hoặc trang chỉ có watermark/text rất ngắn và chạy RapidOCR cục bộ. Trang thành công được gắn `extraction_method = rapidocr_onnxruntime`. Nếu OCR không khả dụng hoặc không tạo đủ text, công cụ tạo `OCR_REQUIRED`; dữ liệu thiếu không được thay bằng số 0.

Có thể cung cấp OCR sidecar để tái sử dụng kết quả OCR hoặc kiểm soát engine bên ngoài. Sidecar được ưu tiên hơn OCR tự động:

OCR sidecar có cấu trúc:

```text
ocr-root/
└── <PDF-STEM>/
    ├── page-1.txt
    ├── page-2.txt
    └── ...
```

Chạy lại:

```powershell
.\.venv\Scripts\python.exe scripts\extract_corpus.py "C:\duong-dan\raw_pdf" `
  --ocr-dir "C:\duong-dan\ocr-root" `
  --run-id oil_gas_2023_2025_ocr_v1
```

Trang dùng OCR được gắn `extraction_method = ocr_sidecar` và confidence thấp hơn text layer gốc.

## Bảng báo cáo tài chính

Với BCTC, công cụ:

- nhận diện `Separate` hoặc `Consolidated` từ tiêu đề báo cáo; nếu không xác định được thì giữ `null` và tạo `FINANCIAL_SCOPE_UNRESOLVED`;
- kế thừa đơn vị `VND` từ tiêu đề bảng khi từng ô số không lặp lại đơn vị;
- ghép giá trị `Năm nay/Số cuối năm` với `Năm trước/Số đầu năm`;
- tạo claim cho doanh thu, lợi nhuận sau thuế, tổng tài sản và lưu chuyển tiền thuần từ hoạt động kinh doanh;
- giữ `review_status = unreviewed` cho tới khi người dùng đối chiếu trang PDF.

## Quy trình QA

1. Rà `run_manifest.json` để xác nhận đủ tài liệu và không có lỗi đọc file.
2. Xử lý `OCR_REQUIRED` trước.
3. Xử lý `NO_CLAIMS_EXTRACTED`: kiểm tra chất lượng OCR và cấu trúc bảng; không diễn giải là doanh nghiệp không công bố.
4. Rà các claim có `extraction_status = ambiguous`.
5. Xác nhận metric, đơn vị, năm, Scope, boundary và mẫu số intensity.
6. Chỉ chuyển `review_status` sang trạng thái đã duyệt sau khi kiểm tra trang PDF.
7. So sánh doanh nghiệp chỉ khi metric và điều kiện so sánh tương thích.

## Lệnh hữu ích

Chạy thử vài trang:

```powershell
.\.venv\Scripts\python.exe scripts\extract_corpus.py "C:\duong-dan\PLX_2025.pdf" --max-pages 5 --run-id smoke_plx
```

Ép metadata cho một file:

```powershell
.\.venv\Scripts\python.exe scripts\extract_corpus.py "C:\duong-dan\report.pdf" `
  --company PLX --year 2025 --document-type ESG --run-id plx_2025_v1
```

Chạy test:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Giới hạn hiện tại

- Đây là rule-based candidate extraction, không phải hiểu ngữ nghĩa hoàn chỉnh.
- Bảng phức tạp, biểu đồ và PDF scan cần OCR hoặc rà thủ công.
- Nếu nhãn và số liệu của bảng tài chính nằm ở các dòng/cột tách rời, phiên bản này đưa tài liệu vào `NO_CLAIMS_EXTRACTED` để QA thay vì tự ghép số liệu.
- Một câu chứa nhiều metric được đưa vào review queue thay vì tự động tách và kết luận.
- Company summary chỉ tổng hợp độ phủ và trạng thái dữ liệu; không tạo điểm greenwashing.
