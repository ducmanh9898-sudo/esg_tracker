# Nhánh trích xuất ESG v2

Đã có parser văn bản riêng cho claim, policy, action, target và governance.
Đây là typed candidates theo từ khóa/context, chưa phải semantic extraction
đầy đủ hoặc dữ liệu verified. Không kết luận greenwashing. Đã nối vào giao
diện kéo thả; xem [hướng dẫn upload v2](UPLOAD_V2_USAGE.md). Chưa có Graph adapter. Phiên bản 2 bổ sung bảng ESG và liên kết
claim–evidence dạng ứng viên, không phải xác nhận bằng chứng hỗ trợ claim.

## Chạy từ PDF

Trong PowerShell hoặc CMD tại thư mục dự án, dùng lệnh một dòng. File BSR 2023
dưới đây là đường dẫn đã được người dùng cung cấp; đổi thành PDF ESG thực tế
nếu đã chuyển vị trí:

```powershell
.\.venv\Scripts\python.exe scripts\extract_source_v2.py "C:\Users\THINKPAD\Documents\Báo cáo ESG\BSR_2023.pdf" --company BSR --report-type ESG --report-year 2023
```

Chạy thử vài trang: thêm `--max-pages 3`. Bỏ giới hạn trang để đọc cả tài liệu.
Capture in ra thư mục `output`; sao chép đường dẫn thư mục đó vào lệnh sau:

```powershell
.\.venv\Scripts\python.exe scripts\extract_esg_v2.py "<THU_MUC_OUTPUT_CO_CANONICAL_JSON>"
```

Thay phần trong dấu `<...>` bằng thư mục thật, không nhập nguyên placeholder.
Parser không OCR lại. Chạy lại capture để tiếp tục trang lỗi/chưa đọc, rồi chạy
lại parser để tạo output tương ứng. BCTN có thể dùng `--report-type annual_report`;
BCTC phải dùng nhánh `extract_financial_v2.py`, không đổi nhãn để ép sang ESG.

Output: `esg_v2/parser_<hash>/esg_records.json`. Source capture và output
tài chính không bị ghi đè. Chạy lại cùng source anchor/config giữ ID record.
Output parser là file sinh lại, chưa dùng để lưu review edits bằng tay.

## Records và giới hạn từng field

Mỗi đoạn nguồn có thể tạo claim và các records typed liên quan. Tất cả giữ
nguyên toàn bộ đoạn ở `original_text`/`payload.statement`; không dựng câu tóm
tắt vào nguyên văn. Nhiều records cùng đoạn không phải nhiều bằng chứng độc
lập. Chưa tách từng mệnh đề trong đoạn hoặc resolve actor/action/object.

| Type | Field đã hỗ trợ | Field còn null khi chưa xác định |
| --- | --- | --- |
| Claim | Statement và nguồn, classification candidates | Actor/action/object/qualifier |
| Policy | Policy text; ngày hiệu lực với cụm có hiệu lực từ/effective from rõ | Scope, effective date thiếu hoặc mâu thuẫn |
| Action | Activity nguyên văn | Beneficiaries/time/disclosed results |
| Target | Target year với đến năm/by; baseline year chỉ khi ghi năm cơ sở/năm gốc/baseline; % ngay sau “mục tiêu giảm/tăng/đạt” | Value/unit không thuộc mẫu rõ, deadline date/baseline value |
| Governance | Tên cơ quan xuất hiện trực tiếp, hoặc candidates nếu nhiều tên; tần suất ngay sau “báo cáo/reports” | Person/role/oversight mechanism, tần suất chưa rõ |

Không lấy năm đầu/cuối bất kỳ trong đoạn làm baseline/target year. “So với
năm 2020” chưa đủ để gán baseline. Target year khác content period; reporting
year cũng không tự điền vào content period. Deadline date không tự tạo thành
31/12 chỉ vì đã có target year.

`boundary`/reported entity chưa parse thì null, cả hai missing_fields đồng bộ.
Danh sách đơn vị chung của báo cáo không được dùng để điền cho mọi KPI. Các
field đã tìm được vẫn needs_review, không có nghĩa boundary đã xác minh.

`classification` dùng bảng mã ứng viên trong `config/esg_v2.yml`, có version và
hash. Đây là taxonomy provisional, chưa chốt với Graph. Một pillar chỉ được
đề xuất nếu các topic candidates cùng E/S/G; nhiều pillar hoặc chưa rõ giữ
unknown. Không ép số liệu tài chính trong BCTN thành E/S/G.

Negation cue tạo issue ESG_NEGATION_REVIEW; parser chưa hiểu đầy đủ phủ định.
Câu “không công bố mục tiêu” có thể tạo target candidate theo chủ đề, không
phải xác nhận tồn tại một mục tiêu. `assertion_status: unverified` áp dụng
mọi record; không chuyển candidate type thành kết luận sự kiện.

## Coverage nguồn và bàn giao

`coverage.source_pages` giữ tổng trang/trang processed, partial, failed và
pending từ capture. `coverage.blocks` có disposition của mọi source block.
Đoạn chưa khớp quy tắc giữ unknown record; headings/layout vẫn trong ledger.
Thứ tự đọc không rõ có issue, không kế thừa section. Section context chỉ kế
thừa qua trang liền nhau processed, không qua trang lỗi/chưa xử lý.

Bảng có header cột được Docling đánh dấu có thể sinh `metric` theo hàng và
`measurement` theo ô số liệu. Nhãn không có trong taxonomy vẫn được giữ.
`original_text` của measurement là đúng chữ trong ô, không phải câu diễn giải;
`payload.header_raw`, `value_raw`, `unit`, `content_period` và `field_sources`
giữ nhãn kỳ, đơn vị và JSON pointer/trang nguồn. Đơn vị chỉ lấy từ cột đơn vị,
header đơn vị hoặc dòng đơn vị độc lập trước bảng trên cùng trang. Không lấy
`standard_unit` của taxonomy để điền đơn vị bị thiếu.

Header nhiều tầng được ghép để đọc kỳ; nhiều năm mâu thuẫn giữ null. Không
đoán “năm nay” từ năm báo cáo. Ô gộp/chồng lấn, số OCR không rõ, dấu gạch hoặc
ô trống không bị chuyển thành 0. Mặc định `auto` giữ `1.594` là ambiguous;
nếu đã xác nhận quy ước số của tài liệu, thêm `--number-format vi` hoặc `en`.
Với `vi`, `1.594` là 1594. Không đổi locale chỉ để làm hết lỗi.

Chưa ghép bảng ESG xuyên trang, chưa suy luận header thiếu, chưa đọc số từ
biểu đồ. Hàng thiếu nhãn, ô không được parser nhận dạng vẫn ở source ledger;
mọi bảng giữ issue rà soát độ đầy đủ. Không gọi JSON này là trích xuất đầy đủ
báo cáo chỉ vì capture đã đọc đủ trang.

`evidence` trỏ đến measurement và đúng ô nguồn. `links` chỉ được tạo khi claim
hoặc target và nhãn hàng khớp duy nhất một mã metric ứng viên trong
`config/metrics.yml`; hash cấu hình được lưu trong output. Cùng topic không
đủ tạo liên kết. Quan hệ luôn `candidate_context`, `needs_review`,
`comparability.eligible: false`. Kỳ/unit/definition/boundary chưa đối chiếu
được ghi unknown; không tính đạt mục tiêu, support/contradiction hoặc điểm
greenwashing. `graph_ready: false`, `semantic_status: partial`.

Validation kiểm tra schema, uniqueness/counts, source/hash/pointer, nguyên văn,
đồng bộ missing_fields và block coverage. Không đo accuracy OCR hoặc xác nhận
phân loại đúng. Kiểm thử bước này dùng fixtures nguồn v2, chưa chạy và đánh
giá toàn bộ ESG BSR/PLX/PVD thực tế.

Nhánh ESG có 22 ca kiểm thử, bao gồm bảng nhiều kỳ, đơn vị, locale, ô gộp,
metric chưa biết, liên kết khác metric và phát hiện sửa nguồn/evidence/link.
Các ca có phân loại nhiều type, giữ nguyên văn, năm mục tiêu/baseline rõ hoặc
mâu thuẫn, hiệu lực policy, governance, phủ định, unknown, bảng pending,
heading xuyên trang/trang lỗi, ID ổn định và phát hiện dữ liệu nguồn bị sửa.

## Bước tiếp theo

Chạy đánh giá trên báo cáo thật để kiểm tra header, bảng xuyên trang và độ đầy
đủ từng ô; bổ sung lưu quyết định rà soát field và lịch sử job trên giao diện.
