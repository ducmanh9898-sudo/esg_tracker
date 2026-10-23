# Extract batch PDF: sử dụng và giới hạn

Pipeline này chạy tuần tự từng trang PDF bằng Docling/OCR trong worker riêng, sau đó tạo native ESG/BCTC và bản bàn giao `corporate_extract_v1`. Không gọi LLM hoặc API trả phí. Bản bàn giao là **candidate chờ review**, không phải dữ liệu gold và không tự khẳng định mâu thuẫn.

## Môi trường

Tại gốc repo `esgtracker`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip show docling docling-core rapidocr onnxruntime pymupdf
```

Phiên bản đã kiểm tra trên Windows/CPU: Docling 2.135.0, docling-core 2.103.0, RapidOCR 3.9.2, onnxruntime 1.31.0, PyMuPDF 1.28.2. Model TableFormer thuộc `docling-project/docling-models` revision `v2.3.0`; tải model qua luồng chính thức của Docling/Hugging Face. Lần đầu cần mạng, các lần sau có thể đặt `HF_HUB_OFFLINE=1` để kiểm tra không phụ thuộc mạng. Máy quét PDF có thể cần nhiều RAM/thời gian; mặc định một page worker/lần và timeout 120 giây. OCR vẫn có lỗi ký tự, cần xem ảnh PDF gốc.

## Chạy pilot hoặc công ty khác

Sao chép `config/extract_batch.example.json`, đổi `company_id`, PDF, SHA-256 thật (`Get-FileHash -Algorithm SHA256`), `report_type`, năm do người cung cấp và số **trang vật lý PDF**. `report_year` là metadata đầu vào, không tự chứng minh observation year. Bỏ `pages` nếu muốn quét toàn bộ PDF. `annual_report` và `ESG` đi qua ESG parser; `financial_statements` đi qua BCTC parser. Dùng thư mục output mới cho mỗi lần chạy; bản cũ giữ nguyên. Nếu đã tự xác minh PDF tải từ trang công bố chính thức, khai báo `url`, `official_domains` (mảng hostname chính xác), và `verification` gồm `method: windows_https_download_and_sha256_match` cùng `downloaded_pdf`; chỉ khi bytes và hostname khớp mới ghi xác minh nguồn. Không khai báo nếu chưa kiểm tra độc lập.

```powershell
.\.venv\Scripts\python.exe scripts/run_extract_batch.py --config config/extract_batch.example.json --output outputs/extract_run_001 --engine docling --allow-native-fallback --page-timeout 150
```

`--allow-native-fallback` chỉ cho phép PyMuPDF khi Docling lỗi hoặc bỏ mất bảng/ô, hay ghép giá trị KPI card mà parser literal tách được. `page_events.json` nêu `read_method`, `fallback_reason`, lỗi, số bảng/ô và số giá trị card đứng riêng của hai parser. Các record fallback có cờ `native_fallback_layout_needs_review`; record OCR có `ocr_transcription_needs_review`. `--engine native` là chế độ fallback để so sánh, không tương đương parse bảng Docling. Nếu Docling phát hiện bảng nhưng sai ô mà số ô vẫn bằng nhau, kiểm tra thủ công bảng và ảnh gốc; bộ đếm không bảo đảm đúng nội dung.

Batch hiện gọi source capture **một lần cho mỗi PDF**, kể cả khi `pages` chọn các trang rời như `[1, 9]`. Mỗi trang vẫn có checkpoint JSON riêng được ghi ngay; canonical JSON tổng hợp được ghi mặc định sau mỗi 10 trang và lần cuối, thay vì ghi lại toàn bộ sau từng trang. Dùng `--checkpoint-interval 1` nếu cần canonical cập nhật sau từng trang; giá trị lớn hơn giảm thời gian ghi đĩa trên PDF dài. Nếu tiến trình dừng giữa hai lần ghi canonical, checkpoint của trang đã xử lý vẫn còn.

Để tiếp tục một batch bị ngắt mà vẫn giữ output cũ bất biến, chạy lại với cùng config, một output **mới** và `--reuse-checkpoints-from <output_cũ>`. Batch sao chép `source.pdf` và checkpoint trang sang output mới, bỏ lock/log/aggregate cũ, kiểm tra lại SHA-256, profile và locator rồi chỉ đọc lại trang chưa `processed` (kể cả trang `partial`/`failed`). Config phải giống hệt bản cũ; thay đổi PDF, parser/Docling hoặc cấu hình OCR sẽ không dùng lại checkpoint của profile khác. Việc sao chép tốn dung lượng đĩa nhưng tiết kiệm lượt OCR đã hoàn thành.

Artifact chính: `run_report.json` (trạng thái partial/failure), `result.json` (đường dẫn từng workspace), `page_events.json`, `capture/.../source.pdf`, `capture/.../pages/NNNN.json` (checkpoint parser), `capture/.../canonical.json`, native ESG/BCTC JSON, và `delivery/`. `delivery/manifest.json` và `delivery/validation/` ghi kết quả validator; `delivery/notes/extraction_quality.json` ghi coverage, record bị loại và lý do. `mechanical_valid=true` chỉ có nghĩa qua kiểm tra contract/locator cơ học. `complete_handoff=false` và `human_review_pending=true` là bình thường khi mới xét trang pilot. Kỳ OCR suy từ ngày kết thúc và cột “Năm nay” nằm trong native artifact; handoff để `observation_year=null` khi không có header năm cùng cột hoặc quote trực tiếp.

`extraction_quality.json` hiện có bảng đếm theo `report_year`, `source_document_type` và `dimensions` E/S/G/X cho từng PDF: số record, số record định lượng, số dòng không còn blocker cơ học và các metric ID đã xuất. Đây là bảng **theo dõi vùng đã trích**, không phải bằng chứng rằng mọi chỉ tiêu đã được tìm, so sánh đúng hoặc được người duyệt xác nhận. Luôn xem `coverage.pages_checked`, `pages_unreadable` và `search_outcomes` trước khi nói về độ bao phủ.

Với BCTC scan, `period.year_basis: same_page_title_and_column` chỉ được ghi cho cột **“Năm nay”** khi cùng trang có tiêu đề “Cho năm tài chính kết thúc ngày 31 tháng 12 năm YYYY”, cột giá trị trùng cột header và năm/ngày cuối kỳ trong native artifact khớp. Validator kiểm tra lại hai locator trên cùng trang. Trường hợp mất tiêu đề, lệch cột, lệch năm, hoặc cột “Năm trước” vẫn để năm đo chưa xác định; OCR và phép ghép cặp vẫn chờ người duyệt.

CLI trả exit code `2` cho batch partial/chờ review, `1` khi có lỗi tài liệu/delivery; đọc `run_report.json` để biết lý do cụ thể. Chạy lại vào thư mục output mới để giữ artifact cũ. Tầng source capture vẫn có checkpoint theo trang khi chạy lại trong cùng workspace qua lệnh capture hiện có; batch này ưu tiên output bất biến và chưa có lệnh resume giữa nhiều batch.

Để đưa bản bàn giao đã review vào Graph, dùng quy trình import hiện có trong `docs/CORPORATE_HANDOFF_USAGE.md` sau khi kiểm tra source hash, quote, hàng/cột, năm, đơn vị, boundary và cách làm tròn trên PDF. Không dùng `not_searched` hoặc lỗi parse làm bằng chứng không công bố. Không đổi `pending_human_review` thành đã duyệt khi chưa có quyết định của người review.

## Các trang BSR thử nghiệm hiện tại

`config/bsr_extract_pilot.json` trỏ đến 6 PDF đã có trong repo Graph ở máy pilot, chọn ESG 2023 p22, 2024 p23, 2025 p106; BCTC 2023 p1/p9, 2024 p1/p9, 2025 p1/p11. Ba PDF ESG được khai là `report_type: ESG`, dựa trên loại `sustainability_report` trong handoff hiện có, để Graph giữ đúng tuyến ESG–BCTC. Đây là sample page coverage, không phải toàn bộ 3 năm. SHA-256 trong config phải khớp file đang dùng. Các trang BCTC scan cần OCR; cột số và tiêu đề OCR phải review. Trang ESG 2024 p23 có trường hợp Docling bỏ mất bảng mà parser literal thấy; fallback được giữ với cờ review. Trang ESG 2025 p106 có card KPI; năm và consolidation của KPI card vẫn unknown cho tới khi người review xác nhận căn cứ.
