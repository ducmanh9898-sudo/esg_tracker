# ESG Greenwashing Risk Graph Demo

Prototype chuẩn hóa 30 disclosure record BSR 2023–2025, chạy 9 quy tắc consistency và hiển thị evidence graph trong trình duyệt.

## Chạy nhanh trên Windows

Giải nén gói vào thư mục gốc `esg-greenwashing-risk-framework`. Không xóa các thư mục `esg`, `json`, `chunks` hiện có.

```powershell
python .\tools\create_config.py
python .\build_demo.py
```

Hoặc chạy kiểm thử rồi tạo demo bằng một lệnh:

```powershell
.\run_demo.ps1
```

Không cần cài thêm thư viện. Trang `output\graph_demo.html` sẽ tự mở. Nếu trình duyệt không mở:

```powershell
start .\output\graph_demo.html
```

Chạy kiểm thử:

```powershell
python -m unittest discover -s .\tests -v
```

## Kết quả được tạo

- `output/normalized_claims.json`: 30 claim theo Common Input Schema.
- `output/normalized_claims.csv`: bảng claim mở bằng Excel.
- `output/validation_report.json`: kiểm tra ID, năm, số, đơn vị, scope và nguồn.
- `output/findings.json` và `findings.csv`: kết quả của rule engine.
- `output/graph.json`: node và edge dùng cho demo.
- `output/graph_demo.html`: trang demo graph độc lập.
- `output/pvd_deduplication_report.json`: đối chiếu hai bản trích chồng lặp PVD 2025.
- `output/pvd_canonical_2025.json`: 9 metric PVD đã chọn bản đầy đủ làm nguồn chuẩn.

Kết quả dự kiến trên snapshot hiện tại:

```text
Claims: 30
Validation: 0 structural errors; 30 claims awaiting manual review
Findings: 10 — Contradicted: 1, NeedsReview: 3, Supported: 6
Graph: 113 nodes, 127 edges
```

## Luồng xử lý

```text
data/extract/esg/*.json
  -> data/config/selection.json
  -> tools/normalizer.py
  -> output/normalized_claims.json
  -> tools/rule_engine.py
  -> output/findings.json
  -> tools/graph_builder.py
  -> output/graph_demo.html
```

## Cách demo

1. Khi HTML mở, graph đã lọc sẵn `Mâu thuẫn` để tập trung vào R01.
2. Đi theo chuỗi `Company → Report → Claim → Measurement → Evidence → Finding → Rule`.
3. Bấm hai node Measurement để xem `1.780.388` và `1.790.388 tCO2e`; bấm Evidence để xem file, trang và JSON Pointer.
4. Bấm Finding R01 để xem phép tính chênh lệch `10.000 tCO2e` và guard của rule.
5. Lọc `Cần đối soát`, bấm R02/R03/R05 để xem phép tính và trang nguồn.
6. Lọc `Đạt`, bấm R07 để cho thấy cường độ giảm tính được 4,26%, phù hợp mức 4% công bố trong sai số làm tròn.
7. Nhấn mạnh `NeedsReview` không phải kết luận greenwashing; cần kiểm tra scope, phương pháp và PDF gốc.

## Giới hạn

Demo dùng JSON đã trích xuất trong repository. Mỗi record có file, trang và JSON Pointer, nhưng chưa có câu trích nguyên văn. Vì vậy đây là prototype phát hiện bất nhất trong dữ liệu đã trích, chưa phải kết luận greenwashing. Trước khi dùng làm kết quả nghiên cứu chính thức, reviewer cần đối chiếu PDF và đổi `review_status` thành `reviewed`.
