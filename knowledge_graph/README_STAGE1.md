# Giai đoạn cấu hình dữ liệu cho ESG Graph Demo

Các file trong gói này là phần đã hoàn thành trước khi viết normalizer và graph engine.

## Cấu trúc

- `tools/create_config.py`: khai báo 30 claim BSR, 9 quy tắc demo và alias để nhận diện dữ liệu PVD 2025 bị trùng.
- `data/config/selection.json`: 30 claim được sinh từ script.
- `data/config/rules.json`: 9 quy tắc được sinh từ script.
- `data/config/pvd_aliases.json`: mapping giữa hai bản trích xuất chồng lặp của cùng báo cáo PVD 2025.

## Cách dùng

Đặt hai thư mục `tools` và `data` vào thư mục gốc của repository rồi chạy:

```powershell
python .\tools\create_config.py
```

Kiểm tra:

```powershell
(Get-Content .\data\config\selection.json -Raw | ConvertFrom-Json).Count
(Get-Content .\data\config\rules.json -Raw | ConvertFrom-Json).Count
(Get-Content .\data\config\pvd_aliases.json -Raw | ConvertFrom-Json).Count
```

Kết quả lần lượt phải là 30, 9 và 9.
