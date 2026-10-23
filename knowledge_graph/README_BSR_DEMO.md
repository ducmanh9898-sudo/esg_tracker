# Demo ESG một doanh nghiệp: BSR

Demo này chạy pipeline Graph v2 riêng cho BSR. Năm chính là 2025; 2023–2024 chỉ dùng để xem liên kết giữa các năm. Kết quả chính gồm claim-level findings, company-level assessments, RDF và giao diện local. Review nguồn của AI là review bởi AI, không thay thế adjudication của người.

Giao diện đọc kết quả cho nhà đầu tư và chuyên gia bền vững nằm ở `output/bsr_demo/index.html` (hoặc `graph_demo.html`). Chọn E/S/G để xem sơ đồ chỉ tiêu → phép kiểm tra → kết quả, nguyên văn và chỉ dẫn tên báo cáo, trang PDF vật lý, mục/bảng. Ô tìm kiếm nhận chỉ tiêu, trang hoặc tên tệp. Giao diện không cung cấp hay mở PDF nguồn; gói review có ảnh trang là artifact nội bộ dành cho reviewer. [Quy tắc thiết kế và giới hạn](docs/bsr-kg-user-interface.md).

Ngay trên trang chính có mục **Đồ thị bằng chứng tương tác**: chọn E, S, G hoặc ESG ↔ BCTC; bấm vào nút doanh nghiệp, chỉ tiêu, phép kiểm tra, trạng thái hay nguồn để xem giải thích và locator. Đây là lát cắt từ dữ liệu Graph v2 của các ca demo, có quan hệ bằng nét liền và đường về nguồn bằng nét đứt. Có thể dùng Tab rồi Enter/Space bằng bàn phím.

Mục **30 claim ESG** liệt kê toàn bộ claim đã chọn: 8 từ báo cáo 2023, 6 từ 2024, 16 từ 2025. Có bộ lọc năm, E/S/G và tìm kiếm. Mỗi dòng nối đến `claim_review.json`: kết quả và lý do của rule chính, tín hiệu điều tra sơ bộ tách biệt, tham chiếu GRI, kiểm tra ngữ cảnh IFRS S1 §20–22, liên kết BCTC có guard, ứng viên qua năm, nguồn và trang. Mười một claim 2025 có giá trị/nhãn đã được AI đối chiếu PDF chính thức trong phạm vi ghi trên dòng; bốn claim chất thải trong số đó có thêm mã GRI do chính BSR ghi ở trang vật lý 129. Claim xử lý cuối có số ở PDF chính thức trang 130 nhưng locator Extract 31/65 lệch với bản text 68 trang (giá trị ở trang 66), nên chưa nối evidence tương đương; xem `data/review/bsr_2025_waste_locator.issue.json`. Các claim còn lại chỉ có locator do Extract khai báo. Danh sách này không phải toàn bộ claim của báo cáo BSR.

`claim_review.json` bao phủ 30/30 claim nhưng **không xác nhận 30/30 claim đúng hoặc sai**. Kết quả rule chính hiện là 2 claim `Supported` trong phạm vi một phép kiểm tra, 4 `NeedsReview`, 5 `Skipped`, 19 `NotEvaluated`; các trạng thái đếm theo claim, không phải số finding. Bộ tham chiếu trong `data/config/standard_metric_candidates.json` tạo quan hệ hoặc ứng viên theo metric, không đánh giá tuân thủ GRI. IFRS S1 §20–22 kiểm tra khả năng nối thông tin và reporting entity, không phải rule so bằng số giữa ESG và BCTC. BCTC chỉ có 6 liên kết ứng viên cho 2 claim lao động; mọi liên kết còn bị chặn vì thiếu context so sánh. 28 claim khác không có BCTC tương đương được nối, không phải bằng chứng BSR không công bố. Các tín hiệu từ rule demo vẫn tách khỏi finding chính và chỉ dùng để chọn ca điều tra.

Trong `graph.ttl` và `graph.json` của output BSR, mỗi claim có node ứng viên tham chiếu GRI và checkpoint IFRS S1 riêng (60 quan hệ ứng viên), cùng 6 node liên kết BCTC có `comparable=false` và blocker. Chúng tách khỏi 7 quan hệ tiêu chuẩn đã review trong graph; người xem mở **Chi tiết** của claim để thấy nhánh liên kết và provenance. Không có cạnh ứng viên nào tự trở thành finding hoặc kết luận compliance.

Mục **Báo cáo tài chính** trên cùng trang cho thấy liên kết ứng viên giữa tổng lao động ESG 2025 (1.594) và tổng lao động trong BCTC hợp nhất 2025 (1.946), kèm tên nguồn, locator và lý do chưa thể so trực tiếp. BCTC trong demo là 76 record từ adapter cũ; sáu upload BCTC format 2.3 mới chưa ingest. PDF BCTC không có trong workspace để AI đối chiếu độc lập, nên locator BCTC vẫn được ghi là locator JSON Extract, không phải trang đã xác minh trong lượt này.

## Chạy trên Windows / PowerShell

Từ root repository:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_bsr_demo.ps1 -Open
```

Nếu đã có `.venv`, chỉ cần lệnh cuối. Bỏ `-Open` nếu chỉ muốn tạo output. Mở thủ công `output/bsr_demo/index.html` cũng được. Script kiểm tra hash PDF nguồn, build pipeline và so sánh ba ca với expected results đã viết trước khi chạy. `technical_demo_pass=true` không có nghĩa toàn bộ dữ liệu đã được xác thực.

Output nằm riêng trong `output/bsr_demo/`; script không ghi đè `output/kg_v2/` hoặc các output corpus khác. File quan trọng: `index.html`, `graph_demo.html`, `graph.ttl`, `rule_evaluations.json`, `ready_findings.json`, `findings.json`, `demo_findings.json`, `claim_assessments.json`, `company_assessments.json`, `evidence_chains.json`, `annotation_audit.json`, `demo_acceptance.json`.

Đợt review evidence 2025 còn tạo `source_provenance_audit.json`, `evidence_chain_sources.json`, `review_packet.md`, `review_packet.html` và ảnh trang tại `review_pages/`. Registry nguồn nằm ở `data/review/bsr_2025_provenance.json`. PDF 134 trang chính thức và artifact text Extract 68 trang có hash riêng; binary PDF 68 trang chưa có. Crosswalk sáu trang chỉ đối chiếu các đoạn đã chọn, không xác nhận hai bản báo cáo tương đương toàn bộ. Bảy evidence trực tiếp từ PDF chính thức được nối vào các claim E/S/G. Context G được AI xác minh cho quan hệ 2≤7 trong đúng phát biểu trang 98, không suy ngày snapshot; S/E và human pilot adjudication vẫn pending. Mở `review_packet.html` để xem guard, nguyên văn, ảnh trang và câu hỏi cho reviewer.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_bsr_demo -q
.\.venv\Scripts\python.exe -B -m kg.test_runner
```

Test runner dùng bản sao tạm của repository. Tài liệu ca review, kịch bản trình diễn 5–7 phút, nguồn và các issue còn mở nằm ở [docs/bsr-demo.md](docs/bsr-demo.md).
