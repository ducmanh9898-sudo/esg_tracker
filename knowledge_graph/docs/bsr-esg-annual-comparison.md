# Demo BSR: ESG ↔ báo cáo thường niên và ESG ↔ BCTC

## Dữ liệu và phạm vi

PDF chính thức được tải từ [BSR](https://bsr.com.vn/), đăng ký tại `data/source/annual_reports_bsr_v3/registry.json` và giữ nguyên trong thư mục đó. Trang PDF vật lý đánh số từ 1; trang in không được suy đoán. Nguồn BSR 2023 có 82 trang, 2024 có 50 trang, 2025 có 45 trang. PDF 2023 có lớp text lỗi mã hóa; bản ghi lao động trang 29 là ứng viên đọc bằng hình và chờ người xác nhận. SHA-256, URL, thời điểm tải và tình trạng xác minh nằm trong registry. PDF ESG 2025 canonical 134 trang và artifact legacy 68 trang vẫn tách biệt.

`data/handoff/bsr_cross_report_profit_v1/manifest_with_annual_v1.json` thêm ba báo cáo thường niên vào manifest cũ, không sửa các JSON lịch sử. Bốn bản ghi thường niên mẫu gồm lao động 2023–2025 và hao hụt năng lượng 2025; đều là AI-assisted candidate, `pending_human_review`. `data/review/bsr_esg_annual_v1/review_pack.json` có quote, trang, ảnh và ô quyết định. `narrative_candidates_v2.json` có tám cặp chính sách/quản trị trùng văn bản để review, không là phán quyết về tính đúng của nội dung. Không tìm thấy cặp trên PDF 2023 bị lỗi lớp text không có nghĩa là báo cáo thiếu công bố.

Lượt chạy thực tế nằm ở `output/bsr_cross_report_discovery_v7_annual/` và `output/bsr_cross_report_annual_graph_v4/`. Validator handoff pass 13 file, 8.677 record. Discovery tạo 10 cặp số: sáu ESG ↔ BCTC, bốn ESG ↔ báo cáo thường niên. Bốn cặp thường niên bằng nhau ở mức số học (lao động 2023, 2024, 2025 và hao hụt năng lượng 2025) nhưng đều bị chặn ở kiểm tra ngữ cảnh. Graph có tám narrative candidates ở trạng thái `NeedsReview`, 10 numeric findings cũng `NeedsReview`, SHACL pass và không có lỗi chạy. `status=partial` phản ánh coverage/review chưa hoàn tất; không có kết luận mâu thuẫn đã xác nhận trong run này.

Nhánh đối chiếu được cấu hình bởi `comparison_routes` trong `data/config/bsr_cross_report_discovery_v3.json`: sustainability_report ↔ annual_report cho E/S/G và sustainability_report ↔ financial_statement cho số tài chính. Không có annual_report ↔ financial_statement. Matching số học chỉ đề xuất cặp cùng doanh nghiệp, năm quan sát có căn cứ, metric key phù hợp và không xung đột phạm vi hợp nhất đã biết. `equal_numeric_values` chỉ là chẩn đoán số; kết luận `Supported`/`Contradicted` đòi review định nghĩa, kỳ và boundary theo guard Graph. Narrative candidates được nối vào RDF và JSON projection ở trạng thái `NeedsReview`, không tạo Finding khẳng định.

## Chạy lại bằng PowerShell

Các lệnh dưới đây chạy tại root dự án, dùng môi trường `.venv` hiện có. Chọn thư mục output phiên bản mới nếu chạy lại; công cụ không ghi đè kết quả cũ.

```powershell
.venv\Scripts\python.exe -B -m tools.annual_report_sources --profile data/config/bsr_annual_sources_v1.json --output-dir data/source/annual_reports_bsr_v4
.venv\Scripts\python.exe -B -m tools.annual_report_pilot --base-manifest data/handoff/bsr_cross_report_profit_v1/manifest.json --registry data/source/annual_reports_bsr_v3/registry.json --specs data/config/bsr_annual_extract_pilot_v1.json --output-manifest data/handoff/bsr_cross_report_profit_v1/manifest_with_annual_v2.json --review-dir data/review/bsr_esg_annual_v2
.venv\Scripts\python.exe -B handoff/bsr_extract_2023_2025_v1/validate.py --manifest data/handoff/bsr_cross_report_profit_v1/manifest_with_annual_v1.json --pdf-dir data/handoff/bsr_cross_report_profit_v1/pdf
.venv\Scripts\python.exe -B -m kg.cross_report_scan --manifest data/handoff/bsr_cross_report_profit_v1/manifest_with_annual_v1.json --profile data/config/bsr_cross_report_discovery_v3.json --comparisons data/handoff/bsr_cross_report_profit_v1/notes/cross_report_comparisons.json --comparisons data/handoff/bsr_cross_report_profit_v1/notes/annual_explicit_candidates_v1.json --pilot-pack data/handoff/bsr_cross_report_profit_v1/notes/cross_report_review_pack.json --output-dir output/bsr_cross_report_discovery_next
.venv\Scripts\python.exe -B -m kg.annual_narrative_scan --claims output/bsr_cross_report_discovery_graph_v3/normalized_records.json --registry data/source/annual_reports_bsr_v3/registry.json --output data/review/bsr_esg_annual_v1/narrative_candidates_next.json
.venv\Scripts\python.exe -B -m kg.corporate_pipeline --manifest data/handoff/bsr_cross_report_profit_v1/manifest_with_annual_v1.json --config data/config/bsr_cross_report_discovery_v3.json --comparisons output/bsr_cross_report_discovery_v7_annual/comparisons.json --narrative-candidates data/review/bsr_esg_annual_v1/narrative_candidates_v2.json --output-dir output/bsr_cross_report_annual_graph_next
```

Lệnh Graph có thể trả exit code 2 khi `status=partial`; xem `run_manifest.json` và inventory để phân biệt dữ liệu chưa hoàn chỉnh với lỗi chạy. `evaluation_status=pending_adjudication` có nghĩa là chưa có precision/recall hợp lệ.

## Những chỗ cần Mạnh review

Mở `data/review/bsr_esg_annual_v1/review_pack.json` cùng ảnh trong `pages/`. Xem bốn record về quote, năm quan sát, đơn vị, định nghĩa và boundary; đặc biệt bản 2023 đọc bằng hình và cặp hao hụt năng lượng 2025 có kỳ quan sát chưa đủ rõ. Tám narrative candidates cần xác định hai nguồn có thực sự độc lập và phát biểu cùng ngữ nghĩa hay chỉ tái dùng nội dung. Giữ `decision=pending` tới khi quyết định; điền `accept`, `correct`, `reject` hoặc `uncertain` vào bản review đã sao chép kèm reviewer, thời điểm và ghi chú. Review pack không tự chuyển thành gold và chưa có công cụ nhập quyết định narrative vào kết luận Graph. Đối với numeric, dùng `review_template.json` trong output Graph làm mẫu cho các record/comparison event; cần reviewer, timestamp, basis và các check theo từng lớp. Xem thêm `docs/cross-report-discovery-demo.md`.

Đây là pilot bốn measurement và tám đoạn trùng văn bản, không phải extract đầy đủ báo cáo thường niên. Recall và công bố vắng mặt chưa thể đánh giá khi thiếu gold annotation theo vùng/trang. Không có API LLM trả phí được gọi.
