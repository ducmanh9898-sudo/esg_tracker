# Knowledge Graph

Thư mục này chứa mã nguồn đối chiếu báo cáo ESG và BCTC. Khi chạy từ dashboard ở thư mục cha, ứng dụng tự chọn `knowledge_graph/` làm nơi chạy Graph. Không cần clone thêm repository khác hoặc đặt biến môi trường cho cấu trúc mặc định.

## Luồng dữ liệu

1. `dashboard/graph_upload.py` ở thư mục cha nhận kết quả Extract của sáu PDF BSR.
2. `src/extraction/corporate_handoff.py` tạo `knowledge_graph/output/bsr_upload_<job_id>/extract/delivery/`, gồm manifest, JSON, PDF nguồn và báo cáo kiểm tra cấu trúc.
3. `tools/extract_graph_bridge.py` gọi `kg.cross_report_scan` để tìm các cặp có khả năng so sánh, rồi gọi `kg.corporate_pipeline` để tạo Graph và đánh giá có điều kiện.
4. `tools/bsr_review_dashboard.py` tạo `review_cases.json`. Giao diện Dash đọc tệp này và mở trang PDF nguồn.

Hồ sơ đối chiếu mặc định là `data/config/bsr_esg_bctc_only_v1.json`. Kết quả Graph của một lần upload nằm trong `output/bsr_upload_<job_id>_analysis/`; dữ liệu bàn giao nằm trong `output/bsr_upload_<job_id>/extract/delivery/`.

Nếu dùng Graph với một gói bàn giao đã có, chạy từ **thư mục `knowledge_graph/`**:

```powershell
..\.venv\Scripts\python.exe -B tools/extract_graph_bridge.py --manifest C:\duong-dan\delivery\manifest.json --run-dir output\lan_chay_moi
```

`--run-dir` phải là thư mục kết quả **chưa tồn tại**. Tham số, schema và cách hiểu kết quả xem thêm trong `docs/` và `schemas/`.

Không có PDF hoặc kết quả BSR cũ trong repository. Cặp có nhãn `NeedsReview` chỉ là ứng viên; cần kiểm tra câu nguồn, năm đo, đơn vị, định nghĩa và phạm vi trước khi ra kết luận.
