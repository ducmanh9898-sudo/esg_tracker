# Parser bảng tài chính v2

Đã triển khai parser ứng viên metric/measurement từ bảng và financial_context
từ thuyết minh định tính trong source capture v2. Luồng kéo thả cũ chưa chuyển sang parser này. Đây chưa phải bộ trích
hoàn chỉnh toàn bộ yêu cầu ESG/BCTC hoặc gói đã xác minh để đưa vào Graph.

## Chạy

Bước 1: chạy `scripts/extract_source_v2.py` theo `docs/SOURCE_V2_USAGE.md`.
Bỏ `--max-pages` để đọc cả PDF. Company/type/year ở bước này là metadata do
người dùng cung cấp; parser không lấy report year điền vào năm của số liệu.

Bước 2: chạy parser trên thư mục có `canonical.json`. Với bản BSR đã chạy thử,
dùng lệnh một dòng sau tại thư mục dự án:

```powershell
.\.venv\Scripts\python.exe scripts\extract_financial_v2.py "data\processed\source_v2\report_db1029e26ab7aa9ed99026c3c3c2a0e6625059fe897431c2d5d32243ad15006d\profile_2d45a0f1d4b1548d36b02d249be427e62cdf6f92cc4702ab74b4e8ebe1e61648"
```

Không OCR lại ở bước này. Sau khi capture thêm các trang, chạy lại parser để
xuất lại candidates; ID của các record trên cùng source anchor không đổi.
Output được tạo trong `financial_v2/parser_<hash>/financial_records.json`,
không ghi đè source capture `canonical.json` hoặc các output legacy. Parser
output là dữ liệu sinh lại, chưa hỗ trợ lưu review edits; không sửa tay nó.

`--number-format auto` là mặc định. `1.234` chưa chắc là 1234 hay 1.234 nên
giữ parsed value null. Chỉ dùng `--number-format vi` hoặc `en` sau khi kiểm tra
định dạng thực tế; lựa chọn được lưu trong output, không suy ra từ mã tiền tệ.

## Cách đọc output

- `records` gồm metric theo hàng và measurement theo ô số/ô trống được phát
  hiện; không giới hạn bốn KPI. Mã số và thuyết minh có header nhận diện được
  được giữ trong nguồn, không coi là số tiền.
- `original_text` của metric là nhãn hàng nguồn; của measurement là chuỗi ô
  nguồn. `original_cells` giữ nhãn/header/value, không dựng câu diễn giải.
- `payload.raw_value` giữ dấu phân cách/ngoặc; `parsed_value` là chuỗi Decimal.
  `normalized_value` chỉ có khi xác định được unit và scale; tránh mất chính
  xác với số lớn. Dấu gạch và ô trống không phải số 0.
- `content_period` lấy từ year/date rõ ở header. Đầu/cuối năm chỉ có period
  role, không tự gán năm hoặc ngày từ report year. Header nhiều kỳ không rõ
  hoặc quý chưa parse được giữ null. Header OCR sai không được sửa âm thầm.
- Unit/currency/scale kế thừa từ nhãn đơn vị đứng trước bảng trong thứ tự
  đọc native hoặc header cột, có `field_sources`; chỉ kế thừa xuyên trang khi
  đạt điều kiện continuation bên dưới.
- `statement_scope` nhận separate/consolidated khi có nhãn nguồn rõ; thiếu
  hoặc xung đột thì null. Boundary pháp nhân không được điền theo scope này.
  Không suy ra scope từ tên file. Inventory gốc không bị sửa khi parser tìm scope.
- `field_sources` có artifact hash, JSON pointer đến cell/text, PDF page,
  row/column và bbox nếu nguồn cung cấp. Printed page còn null.
- `missing_fields` và `boundary.missing_fields` được đồng bộ. Records đều
  needs_review; pillar unknown cho dữ liệu tài chính, không ép vào E/S/G.
- `links` nối metric với measurement dạng candidate. `issues` giữ lỗi nguồn,
  thiếu kỳ/unit/scope, ô gộp và những ô chưa xác định.

## Đã kiểm tra và phần còn thiếu

Trên trang 9 BCTC riêng BSR 2025 đã lưu: 1 bảng, 37 metric candidates và 72
measurement candidates. Hàng mã 270 giữ hai số `85.004.418.533.771` và
`88.352.140.328.065`; currency VND lấy từ nhãn đơn vị của trang. Period giữ
null vì header OCR không đủ rõ. Đây là thử một trang, không xác nhận mọi ô
đúng hoặc toàn bộ báo cáo đã được trích.

Kết quả mẫu ở parser version 2 có 146 issues (kỳ/period role chưa rõ và hai ô
không được phát hiện). Nhãn “báo cáo tài chính riêng này” ở đoạn chữ trang 9
cung cấp statement_scope separate, nhưng không xác minh boundary pháp nhân.
Không coi validation passed là mọi issue đã giải quyết.

Validation kiểm tra schema, ID/FK, đồng bộ missing fields và field source
pointers/raw values. Đây không phải kiểm tra độ chính xác OCR hay kiểm toán.
`semantic_status: partial`, `graph_ready: false` luôn được giữ ở phiên bản này.

Chưa triển khai: continuation không có nhãn tiếp theo rõ, context qua trang lỗi,
parser kỳ quý/range duration, diễn giải field trong thuyết minh, đối chiếu tổng số học,
semantic ESG, Graph adapter và review UI. Các bảng header sai/mất có thể tạo
ứng viên chưa đúng loại cột; chúng cần review, không dùng trực tiếp vào báo cáo.
Ô không được Docling phát hiện không được bịa thành ô nguồn; issue ghi phần
bị thiếu khi xác định được cột kỳ vọng. Không phát hiện được mọi ô bị bỏ sót.

## Bảng xuyên trang và phạm vi ở parser version 2

JSON schema `esg-financial-candidates/2.1.0`, parser_version 2 xuất thư mục
parser hash mới, giữ nguyên output version 1. ID các records trên source anchor
cũ không đổi. Chạy lại cùng lệnh ở trên, không cần chạy lại OCR.

Chỉ nối hai bảng cuối/đầu của hai trang liền nhau khi cả hai trang processed,
tiêu đề giống nhau có “tiếp theo/continued”, số cột phù hợp, header không mâu
thuẫn và không xung đột unit/scale/scope. Thiếu căn cứ hoặc khác header/năm/
đơn vị/phạm vi thì không kế thừa, có issue TABLE_CONTINUATION_UNCONFIRMED.
Không nối tự động qua trang trắng/pending/failed/partial hoặc chỉ vì giống số cột.

`table_continuations` chứa quyết định rule_matched/rejected, lý do và nguồn
tiêu đề. Rule_matched không phải verified. `payload.logical_table_id` nhóm các
record thuộc chuỗi bảng nhưng không gộp/xóa record hay chỉnh sửa cells nguồn.
Header thiếu ở trang sau có thể kế thừa từ trang trước, và field_sources vẫn
trỏ về ô header nguyên thủy. Chuỗi nhiều trang giữ nguồn header ở trang đầu.

Statement scope ưu tiên nhãn rõ trên chính trang bảng; nếu không có thì xem
tiêu đề báo cáo rõ trong source ledger. Nhãn mâu thuẫn giữ ambiguous/null,
không fallback sang tên file. Một bảng continuation đủ điều kiện có thể kế
thừa scope của chuỗi với nguồn/basis tương ứng. Không có nghĩa included_entities,
excluded_entities hay consolidation_method đã được xác minh.

Kiểm thử gồm continuation 3 trang, các trường hợp từ chối vì khác unit/year/
scope, trang lỗi ở giữa, scope mâu thuẫn và bỏ qua tên file/tham chiếu chung.
Bộ kiểm thử tổng: 87 tests passed. Đã kiểm tra ID của 109 records trang BSR
mẫu không đổi so với parser version 1; output cũ vẫn được giữ.
Trên BSR thực tế mới kiểm tra scope ở trang 9; kiểm tra nối nhiều trang hiện
dùng fixtures, chưa khẳng định đã đọc toàn bộ BSR hoặc mọi dạng bảng xuyên trang.

## Thuyết minh định tính ở parser version 3

Chạy cùng lệnh CLI. Schema `esg-financial-candidates/2.2.0`, parser_version 3
xuất thư mục hash mới, không ghi đè output của versions 1/2. Các table records
cũ giữ ID. `counts.financial_contexts` cho biết số đoạn ứng viên được trích.

Mỗi đoạn chữ tạo một `financial_context` với nguyên văn và source pointer.
Không nối các đoạn thành một câu trích dẫn giả. Nội dung không có số vẫn được
giữ khi thuộc section thuyết minh hoặc có dấu hiệu tài chính cần rà soát.
Tiêu đề thuyết minh và mục con đi theo native reading order, có nguồn riêng;
có thể kế thừa qua các trang liền nhau processed. Trang thiếu/lỗi/partial ở
giữa chặn kế thừa. Không tự nối hai đoạn ở hai trang thành một đoạn hoàn chỉnh.

`payload.context_type_candidates` là nhãn theo từ khóa ở đoạn hoặc tiêu đề
mục: accounting_policy, risk_disclosure, commitment, contingency, related_party,
estimate_judgment, financial_esg_context. Các nhãn là tín hiệu chủ đề ứng viên,
không xác nhận một sự kiện/claim; câu phủ định vẫn cần review. Chính sách kế
toán không tự trở thành ESG policy; cam kết tài chính không tự thành ESG target.
Pillar vẫn unknown, không tự kết luận ESG/greenwashing.

`payload.statement`, `notes_title_raw`, `section_heading_raw` giữ đúng text
nguồn. `field_sources` trỏ tới các đoạn/header tương ứng. Ngày hiệu lực, kỳ
nội dung, target/baseline chưa parse được giữ null và field status/issue;
không lấy năm báo cáo hoặc một năm xuất hiện trong đoạn để tự điền.

`notes_coverage` ghi disposition của mọi text block: heading, paragraph
candidate, layout/footer/unit label, ngoài notes hoặc chưa rõ thứ tự đọc.
Các block chưa thành record vẫn nằm trong source ledger. Không gọi coverage
này là độ chính xác hoặc chứng minh mọi thuyết minh đã được nhận diện.

Validation kiểm tra original/payload text với nguồn, source pointer, coverage
text blocks và liên kết record. Trang 9 BSR vẫn có 37 metrics, 72 measurements,
0 financial_contexts: trang bảng không bị biến thành thuyết minh chỉ vì có
câu footer “Các thuyết minh kèm theo...”. Test định tính sử dụng fixtures;
chưa kiểm tra toàn bộ phần thuyết minh BSR thực tế.

Kiểm thử tổng: 96 tests passed. Bước sau là nhánh ESG với policy/action/target/
governance typed records, sau đó candidate evidence links và tích hợp UI.

Cập nhật tiếp: nhánh ESG text candidates đã có CLI/schema riêng, hướng dẫn
ở `docs/ESG_V2_USAGE.md`; chưa tích hợp UI hoặc evidence links.

## Cập nhật BCTC parser version 4 (2026-10-09)

Schema hiện tại là `esg-financial-candidates/2.3.0`. Những ghi chú về versions
1/2/3 phía trên là lịch sử, không mô tả toàn bộ khả năng hiện tại.

- Source-v2 ưu tiên Tesseract vie+eng cục bộ nếu có đủ model. OCR tạo lớp chữ
  tạm thời, sau đó Docling nhận dạng bố cục/bảng. PDF nguồn không bị thay đổi.
  Không dùng OSD tự xoay nội dung scan; scan xoay sai bên trong PDF cần review.
- Chạy `scripts/setup_vietnamese_ocr.py` để chuẩn bị model; cần cài Tesseract.
  Profile lưu hash model; OCR/profile mới có thể thay đổi segmentation và IDs.
- Bảng chính bị Docling bỏ sót có thể phục hồi từ các header rõ ràng và tọa độ
  từ OCR. Không có quy tắc riêng điền số BSR; bảng phục hồi vẫn needs_review.
- Loại mục lục có cột Trang khỏi measurement. Không dùng tên lớp tài sản làm
  label column; loại cột mã/thuyết minh dù header mã có nhiễu OCR nhẹ.
- Metadata có dẫn nguồn PDF, tách biệt input. Kỳ tương đối dựa vào kỳ được
  công bố và chính sách năm tài chính, không lấy năm input. Ngày ký không phải
  ngày công bố; statement scope không phải boundary pháp nhân của mọi KPI.
- Giữ nguyên chuỗi OCR/cells. Ô gạch/trống là null, không phải 0. Mã/note number
  đọc không rõ không được đoán. Major note heading thiếu số chặn việc kế thừa
  số thuyết minh trước đó. Các trường null và missing_fields được đồng bộ.
- Có semantic_coverage, metadata nguồn, kỳ được trình bày, hierarchy ứng viên
  theo công thức và arithmetic_checks. Chỉ so cùng đơn vị/scale/scope/kỳ tương
  thích; sai lệch tạo issue, không sửa nguồn. Kết quả vẫn partial/graph_ready=false.

### Bàn giao nhiều báo cáo

Chạy từ thư mục dự án, mỗi lệnh một dòng:

```powershell
.\.venv\Scripts\python.exe scripts\export_financial_handoff.py "<workspace chứa canonical.json>" --output-dir outputs/batch_moi --number-format vi
```

Có thể truyền nhiều workspace. Export tạo một JSON BCTC mỗi báo cáo, manifest,
schema, README, PDF gốc và page checkpoints; từ chối ghi đè thư mục bàn giao.
`vi` là lựa chọn format đã đối chiếu cho BSR này, không được suy từ VND cho mọi
tài liệu; mặc định `auto` giữ số mơ hồ. Thay placeholder bằng đường dẫn thật.

`scripts/verify_bsr2024_handoff.py` chỉ là bộ đối chiếu mẫu theo đúng SHA PDF
BSR đã kiểm tra; không phải quy tắc trích xuất và không tự bổ sung số vào output.

## Ghép cột ở parser version 5 (2026-10-10)

GUI và CLI cùng dùng parser 5; vẫn schema 2.3.0 (contract chấp nhận cả parser
4 và 5). Thư mục parser hash mới giữ lại output version 4. Không cần OCR lại
source-v2 đã có đủ trang cùng profile; upload lại cùng file/metadata sau khi
khởi động lại app sẽ dùng checkpoint và chạy parser mới.

- Header mã số bị lệch grid/gộp thuyết minh: đối chiếu bbox với các cột body,
  chỉ nhận khi ít nhất ba ô mã 2–3 chữ số và tỷ lệ phù hợp ít nhất 70%.
  Header gộp không có tọa độ/không đủ căn cứ: item_code_raw null.
- Mã/thuyết minh giữa cột nhãn và cột kỳ rõ ràng không trở thành số tiền.
  Chuỗi mã OCR giữ nguyên, không sửa theo danh mục chỉ tiêu hay công thức.
- Hai số tiền phân nhóm đầy đủ bị gộp vào một ô: chỉ tách khi ô nằm ngang
  cả hai header kỳ rõ ràng, không trùng ô số riêng và không span nhiều hàng.
  Gán theo thứ tự vị trí header, không mặc định năm nay ở bên trái.
- field_sources có native pointer/hash/full raw_text, text_span [start,end)
  trỏ đoạn nguyên văn cho mỗi giá trị. Bbox vẫn của cả ô gốc, không bịa bbox token.
  Validator kiểm tra substring và giữ original_cells gốc; mappings vẫn needs_review.
- Nhiều số trong cùng một cột hoặc số nguyên có khoảng trắng chưa đủ căn cứ
  để tách; giữ null/ambiguous. Không dùng số kỳ vọng để chọn token.

BSR 2024: 45/45 trang, 37/38 mẫu mã/cột/giá trị đạt (trước sửa 16/38),
12 kiểm tra số học pass và 2 chưa kiểm tra được. Còn mẫu mã 20, cột năm trước,
trang PDF 10 bị lẫn số hàng liền trước; parsed_value null. Kiểm tra mẫu không
chứng minh mọi ô đúng. Semantic vẫn partial/graph_ready=false.
166 kiểm thử phần mềm đạt. Gói mới: `outputs/BSR_2024_mapping_v5_20261010/`.
