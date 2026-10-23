# Nối Extract → Knowledge Graph cho BSR 2023–2025

Chạy từ gốc `esg-greenwashing-risk-framework`. Lệnh điều phối nằm trong Graph;
`D:\ESG\esgtracker` chỉ được chạy và đọc. Mỗi lần chạy cần một thư mục output mới.

## 1. Tạo cấu hình ESG và BCTC hợp nhất cho ba năm

Phạm vi chính của bài toán chỉ gồm 6 PDF: một báo cáo ESG và một BCTC hợp nhất
cho mỗi năm 2023, 2024, 2025. BCTC hợp nhất được chọn vì cặp lao động
1.594 ↔ 1.946 đang đối chiếu với chính báo cáo này.

```powershell
.\.venv\Scripts\python.exe -B tools/extract_graph_bridge.py --prepare-esg-bctc-config output/bsr_esg_bctc_6pdf_config.json
.\.venv\Scripts\python.exe -B tools/extract_graph_bridge.py --extract-config output/bsr_esg_bctc_6pdf_config.json --run-dir output/bsr_esg_bctc_run_001 --engine docling --allow-native-fallback --page-timeout 150
```

Lệnh tạo cấu hình kiểm tra dấu vân tay SHA-256 của nguồn, chọn đúng bản ESG
2025 chính thức và không giới hạn số trang. Với các PDF hiện có, phạm vi này
gồm 355 trang vật lý. Số cặp ứng viên chỉ được biết sau khi cả lượt chạy hoàn tất.
Bản `BSR_2025_official.pdf` có 134 trang đơn; `BSR_2025.pdf` có 68 trang,
phần lớn là trang đôi của cùng báo cáo. Khi người duyệt dùng bản 68 trang,
trang 76 của bản 134 tương ứng trang 39, còn trang 106 tương ứng trang 54.
Không dùng số trang của bản này để dẫn chứng cho bản kia mà không ghi rõ tệp.

## Phạm vi mở rộng 12 PDF

```powershell
.\.venv\Scripts\python.exe -B tools/extract_graph_bridge.py --prepare-full-config output/bsr_full_extract_config.json
```

Cấu hình lấy 12 ô nguồn từ `data/handoff/bsr_cross_report_profit_v1/manifest_with_annual_v1.json`:
ESG, báo cáo thường niên, BCTC riêng và BCTC hợp nhất cho từng năm. Nó kiểm tra
SHA-256 của từng PDF và chọn bản ESG 2025 có tên `official`. Không có trường `pages`
nghĩa là Extract phải duyệt tất cả trang vật lý của từng PDF. Đây là phạm vi
**quét nguồn**, chưa phải chứng nhận đã trích đúng mọi chỉ tiêu.

## 2. Chạy phạm vi mở rộng 12 PDF khi cần nghiên cứu thêm

```powershell
.\.venv\Scripts\python.exe -B tools/extract_graph_bridge.py --extract-config output/bsr_full_extract_config.json --run-dir output/bsr_full_run_001 --engine docling --allow-native-fallback --page-timeout 150
```

Nếu lượt chạy bị ngắt, dùng **cùng cấu hình** và output mới; thêm
`--reuse-extract-from output/bsr_full_run_001/extract` để sao chép checkpoint
trang đã xử lý thành công. Trang chưa hoàn tất sẽ được đọc lại. Extract ghi
checkpoint từng trang ngay và ghi bản tổng hợp theo nhóm 10 trang để giảm
thời gian ghi đĩa. Hai cơ chế này đã được kiểm tra bằng bài test và lượt pilot;
chúng không thay thế việc duyệt căn cứ trên PDF.

Mặc định bước tìm cặp chỉ ghép báo cáo ESG với BCTC; cấu hình
`data/config/bsr_esg_bctc_only_v1.json` giới hạn đúng tuyến này cho cả E, S và G.
Nếu số ESG thiếu năm đo nhưng cùng báo cáo năm với số BCTC có năm đo rõ ràng,
cấu hình này đưa cặp vào hàng đợi kiểm tra với dấu `report_year_hint_unverified`.
Năm báo cáo không được ghi đè thành năm đo; người duyệt vẫn phải xác nhận.
Riêng dòng lợi nhuận trước thuế ESG 2025 có loại phát biểu chưa rõ, bộ dò vẫn
đưa vào hàng đợi với dấu `variant_unknown_unverified` khi nhãn BCTC khớp mã
dòng 50 của báo cáo kết quả kinh doanh. Dấu này không phải kết luận hai số bằng nhau.
Nếu cần khảo sát thêm báo cáo thường niên, truyền
`--profile data/config/bsr_cross_report_discovery_extract_v4.json`.

Quy trình chạy `esgtracker/scripts/run_extract_batch.py`, đọc
`extract/delivery/manifest.json` sau khi gói đạt kiểm tra cơ học, chạy
`kg.cross_report_scan`, rồi đưa `discovery/comparisons.json` vào
`kg.corporate_pipeline`. Kết quả nằm trong một thư mục chạy:

- `bridge_report.json`: trạng thái và đường dẫn kết quả.
- `extract/run_report.json` và `extract/delivery/notes/extraction_quality.json`: lỗi trang, chất lượng trích xuất và bản ghi bị loại.
- `discovery/review.html`, `discovery/coverage.json`: cặp ứng viên và bản ghi chưa tìm được cặp.
- `discovery/esg_bctc_pairs.csv`: từng cặp ESG–BCTC với năm báo cáo, năm đo,
  trang PDF, nhãn, số liệu, câu trích và ngữ cảnh của hai nguồn; mở được bằng Excel.
- `graph/graph.ttl`, `graph/report.html`, `graph/review_template.json`: Graph và hàng đợi xác nhận của người duyệt.

Mã thoát `2` là **partial**, thường do thiếu trang hoặc đang chờ duyệt. Mã thoát
`1` là lỗi chặn. Chỉ khi gói Extract qua kiểm tra cơ học, scanner và Graph mới chạy.
Các cặp không tự chuyển thành mâu thuẫn đã xác nhận; năm đo, đơn vị, định nghĩa,
phạm vi và nguồn vẫn cần kiểm tra.
Có thể đưa thêm `--comparisons <file>` cho các cặp do người duyệt đề xuất,
`--narrative-candidates <file>` cho cặp câu văn bản, và `--reviews <file>` cho
quyết định đã duyệt. Những tệp này phải tham chiếu đúng ID/digest của batch mới;
không tái dùng mù quáng ID từ lần Extract cũ.

Để kiểm tra phần Graph bằng một gói bàn giao đã có mà không chạy OCR:

```powershell
.\.venv\Scripts\python.exe -B tools/extract_graph_bridge.py --manifest data/handoff/bsr_cross_report_profit_v1/manifest_with_annual_v1.json --run-dir output/bsr_bridge_check_001
```

## Giới hạn hiện tại và việc nên cải thiện ở Extract

Quét hết trang chỉ là điều kiện cần. Extract vẫn phải đo độ bao phủ theo
**trang × loại chỉ tiêu × năm × loại báo cáo**, ghi rõ trang lỗi OCR và dòng bị
loại. Checkpoint theo PDF/trang/profile và chạy tiếp giữa các batch đã có.
Cần ưu tiên tiếp: (1) tách đọc trang song song có giới hạn RAM sau khi đo bộ nhớ
trên máy chạy thật; (2) đối chiếu bảng Docling với parser chữ
theo nội dung hàng/cột, không chỉ theo số ô; (3) giữ năm đo, cột, đơn vị, footnote
và phạm vi riêng/hợp nhất dưới dạng trường có bằng chứng; (4) tạo bộ trang mẫu
đã được người duyệt để đo độ chính xác và độ bao phủ. Đây là các việc tiếp theo,
chưa được lệnh điều phối này tự động thực hiện.

Scanner hiện ghép cặp số cùng năm dựa trên metric/nhãn/nhóm chỉ tiêu; các câu
văn bản ESG chưa có quy trình tìm cặp tự động đầy đủ. `NeedsReview` vẫn là trạng
thái đúng khi thiếu xác nhận của người duyệt.

Profile `bsr_cross_report_discovery_extract_v4.json` thêm một mẫu chữ OCR cho
dòng BCTC có mã `60=50-51-52` của lợi nhuận sau thuế. Extract chỉ gắn năm cho
cột “Năm nay” khi tiêu đề kỳ tài chính cùng trang khớp năm và cột; validator
kiểm tra lại căn cứ này. Những trường hợp khác giữ năm đo chưa xác định. Mẫu OCR
chỉ dùng để **tìm ứng viên**; Graph vẫn yêu cầu người duyệt xác nhận định nghĩa,
phạm vi, kỳ, đơn vị và làm tròn.

Lượt kiểm tra nhỏ bằng `config/bsr_extract_pilot.json` và `--engine native` đã
đi qua đủ ba bước, nhưng chỉ xuất được 4/6 tài liệu: BCTC 2023 và 2024 bị chặn
vì không đọc chắc được phạm vi riêng/hợp nhất. Graph có 46 bản ghi, 0 cặp và
SHACL đạt. Đây là kiểm tra nối luồng, không phải thước đo độ bao phủ BSR.
Ban đầu config pilot khai các PDF ESG là `annual_report`; bản hiện tại đã đổi
thành `ESG` dựa trên handoff để giữ đúng tuyến ESG–BCTC.

Sau khi sửa config pilot thành `ESG`, lượt Docling/OCR đã xuất 6/6 PDF (163
record) và không chặn BCTC hợp nhất. Lượt chạy tiếp từ checkpoint chỉ đọc lại
2 trang `partial` trong số 9 trang pilot; scanner profile v4 tìm được 2 cặp
lợi nhuận sau thuế ứng viên, cả hai `NeedsReview`, và Graph đạt SHACL. Một cặp
đối chiếu năm đo 2024 trong hai báo cáo 2024; cặp còn lại dùng số năm đo 2023
trong báo cáo ESG 2024 và BCTC 2023 nên cần xem phiên bản/restatement. Pilot
vẫn chỉ đọc 9 trang.

Thử nghiệm riêng lao động 2025 với ESG trang PDF 76 và BCTC hợp nhất trang
PDF 14 đã đi qua đủ Extract → discovery → Graph: `1.594` lao động trong ESG
và `1.946` nhân viên trong BCTC được đưa thành **một ứng viên** `NeedsReview`.
Quy tắc mới chỉ lấy số ngay sau ngày 31/12/2025 trong cùng câu BCTC; số
so sánh 2024 trong ngoặc không bị gắn nhầm. Tiêu đề BCTC hợp nhất trên trang
14 bị OCR thiếu chữ được nhận diện bằng mẫu hẹp, vẫn gắn cờ cần kiểm tra ảnh
PDF. Mẫu này xác nhận luồng hoạt động trên hai trang, không chứng minh hai
chỉ tiêu có cùng phạm vi nhân sự hay đủ bao phủ cả ba năm.
