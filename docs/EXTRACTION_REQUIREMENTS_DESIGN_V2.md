# Thiết kế trích xuất toàn bộ báo cáo ESG và tài chính

Trạng thái mới nhất: đã nối source/financial/ESG v2 vào UI kéo thả, tiến độ,
đối chiếu nguồn và export JSON/native checkpoints. Chưa có sửa/duyệt field,
lịch sử job, Graph adapter hoặc đánh giá toàn bộ corpus thật. Xem
`docs/UPLOAD_V2_USAGE.md`. Các ghi chú tiến độ dưới đây là lịch sử từng bước.

Ngày thiết kế: 2026-10-09. Trạng thái: thiết kế đề xuất, chưa triển khai pipeline v2.
Tiến độ cùng ngày: đã có nền tảng source capture P0/P1 riêng (schema nguồn,
identity, per-page checkpoint/retry/resume, coverage, issues và validation).
Xem `docs/SOURCE_V2_USAGE.md`. Chưa có semantic parsers hoặc Graph adapter v2;
những module trong lộ trình dưới đây chỉ được coi là đã làm trong phạm vi này.
Tiến độ tiếp theo: đã có financial table candidates trong cùng trang, schema
và CLI riêng; xem `docs/FINANCIAL_V2_USAGE.md`. P2 còn thiếu context xuyên trang,
scope xác định theo nguồn và thuyết minh định tính. Chưa nối vào UI kéo thả.
Cập nhật tiếp: parser version 2 có continuation với tiêu đề rõ, kiểm tra xung
đột header/unit/scope và statement scope có nguồn. Các continuation chưa rõ
vẫn bị từ chối. Parser version 3 bổ sung financial_context theo đoạn thuyết minh,
section context, tag ứng viên và text-block coverage. Diễn giải field của
thuyết minh và nhánh ESG còn pending; chưa có review UI hoặc Graph adapter.
Tiến độ mới: đã có ESG text candidates (claim/policy/action/target/governance),
CLI/schema/config riêng và block coverage. Xem `docs/ESG_V2_USAGE.md`. ESG
metrics/measurements từ bảng, semantic interpretation đầy đủ, evidence links,
review UI và Graph adapter vẫn pending.
Nguồn yêu cầu hiện hành: `C:\Users\THINKPAD\Documents\requirementsESG (1).docx`.
Revision thiết kế: 2.1. Bản này thay thế cách hiểu dùng một parser chung cho ESG
và BCTC; dùng chung lớp nguồn nhưng tách hai nhánh semantic extraction.

Mục tiêu là xử lý tất cả các trang của báo cáo ESG, thường niên và BCTC; giữ nội
dung nguồn; tạo records có truy vết và bàn giao theo một hợp đồng dữ liệu rõ ràng.
Oil & Gas là ngành demo, không phải điều kiện giới hạn bộ đọc. Kết quả hỗ trợ
phân tích ở cấp record/claim và company, không phải kiểm toán hay kết luận greenwashing.

Phạm vi corpus demo theo tài liệu mới: báo cáo ESG của BSR, PLX, PVD qua các
năm và BCTC tương ứng. Danh sách năm lấy từ inventory tài liệu thực tế; không
tự coi đã có đủ 2023–2025 cho cả ba doanh nghiệp. Báo cáo thường niên được đọc
như tài liệu hỗn hợp: route từng section sang nhánh ESG hoặc tài chính.

## 1 Phạm vi và giới hạn của cam kết toàn bộ

Phân biệt ba mức, không gộp thành một cờ `full`:

- Coverage xử lý: mọi trang đã có kết quả hoặc lỗi được ghi nhận, kể cả phụ lục,
  thuyết minh, trang trắng, ảnh và trang chưa đọc được.
- Coverage nội dung: mọi block nguồn được đưa vào hàng đợi phân loại; block không
  sinh record phải có disposition và lý do. Không chỉ đọc các hàng chứa số.
- Completeness ngữ nghĩa: mỗi yêu cầu có giá trị có nguồn, hoặc null kèm trạng
  thái/lý do. Việc xử lý đủ trang không chứng minh đọc đúng mọi chữ, ô hay trường.

Không thể cam kết mọi trường đúng 100% chỉ bằng Docling. Cần bộ chuẩn đối chiếu
và review để đo lỗi bỏ sót/OCR/mapping. Không coi “không trích được” là “không công bố”.

## 2 Khoảng cách với hệ thống hiện tại

Đối chiếu mã nguồn tại thời điểm thiết kế:

| Thành phần | Hiện tại | Thiết kế v2 |
| --- | --- | --- |
| Docling | JSON native và bảng theo trang | Giữ lại làm lớp nguồn, bổ sung page checkpoint và trạng thái lỗi |
| Tạo record | `all_table_claims` chỉ lấy hàng chứa số | Phân loại cả đoạn chữ, bảng, caption, footnote và nội dung ảnh đọc được |
| Nội dung nguyên văn | Ghép các ô bằng dấu `|` vào `original_text` | Nguyên văn nằm ở span/cell; chuỗi ghép chỉ là `display_text` |
| Giá trị | `value`, `unit`, `period_mapping` còn null | Một measurement cho từng giá trị và kỳ xác định được |
| Phạm vi | Một boundary suy ra ở cấp tài liệu | Tách report scope và boundary riêng từng record có bằng chứng |
| ID | Phụ thuộc document key và thứ tự bảng | ID theo phiên bản PDF, source anchor và slot ngữ nghĩa |
| Lỗi | Một lỗi chuyển đổi có thể làm mất kết quả cả tài liệu | Lưu kết quả từng trang, retry riêng trang lỗi, bàn giao partial |
| Inventory | Upload chặn cùng company/year/type | Cho phép riêng, hợp nhất và các phiên bản khác nhau |
| Review | Một cảnh báo chung về bảng | Issue đến từng record/field/anchor; xác minh theo từng field |
| Graph | Chưa có hợp đồng v2 đã xác nhận | Schema canonical và adapter có version; chốt interface trước import |

Các file hiện có cần mở rộng là `src/extraction/docling_backend.py`,
`src/extraction/toolkit.py`, `dashboard/upload_analysis.py` và lớp import dữ liệu.
Không migrate trực tiếp database hiện tại trước khi kiểm tra tương thích. Các
cột NOT NULL hiện có không được ép dữ liệu chưa biết thành giá trị giả.

## 3 Luồng xử lý đề xuất

```text
Upload PDF
  → Inventory và hash phiên bản
  → Phân tích từng trang và checkpoint
  → Docling layout/table + OCR khi cần
  → Source blocks/cells/spans bất biến
  → Section và table context xuyên trang
  → Tạo ứng viên định tính và định lượng
  → Parse giá trị/kỳ/đơn vị với source anchors
  → Phân loại ứng viên ESG và liên kết evidence/target
  → Validation và coverage reconciliation
  → Review theo field
  → JSON canonical + adapter Graph + gói nguồn
```

### Tiếp nhận và inventory

Mỗi file có hash SHA256, tên gốc, kích thước, vị trí truy cập được, số trang và
version. Nhận diện company/type/period từ tên và nội dung; khi mâu thuẫn giữ
candidate values và yêu cầu review. Ngày ở đầu tên file không tự động là ngày
công bố hoặc kỳ báo cáo. Metadata do người dùng nhập giữ nguồn `user_supplied`.

Cho phép nhiều báo cáo cùng công ty, năm và loại; không gộp riêng với hợp nhất.
PDF giống byte nhận cùng report version; batch ID vẫn khác. Phiên bản công bố
lại là report version mới, có liên kết với bản trước nếu xác định được.

### Đọc toàn trang và phục hồi lỗi

Lập manifest đủ mọi trang trước khi đọc. Đánh giá text native, ảnh và chất lượng
đọc theo từng trang/vùng. Docling làm lớp layout/table; OCR dùng cho scan hoặc
vùng native text có vấn đề, tránh mặc định coi mọi text native là đáng tin.
Giữ từng phương án đọc và phương án được chọn; không âm thầm sửa chữ nguồn.

Checkpoint sau mỗi trang bằng ghi nguyên tử. Timeout/retry có giới hạn; lỗi
một trang không xóa trang thành công. Resume theo PDF hash, engine/model/config
version; không dùng cache khác cấu hình như kết quả mới. Lưu lỗi ngay cả khi
không có record. Đánh dấu trang trắng chỉ sau khi kiểm tra, không dựa duy nhất
vào việc OCR trả rỗng. Biểu đồ chưa đọc được phải tạo issue/region pending.

PDF là dữ liệu không tin cậy: giới hạn file/trang/tài nguyên, xử lý worker riêng;
chỉ dẫn nằm trong PDF không được điều khiển chương trình hoặc semantic model.

### Source ledger và context

Lưu block paragraphs/headings/tables/pictures/captions/footnotes với PDF page
1-based, bbox và coordinate system. Printed page giữ raw text và parsed label
riêng; không suy ra bằng một offset nếu không có chứng cứ. Native JSON pointer
phải kèm artifact ID và hash vì pointer chỉ có nghĩa trong đúng artifact.

Giữ ô trống, ô gộp, header nhiều tầng, hàng phân nhóm, note reference và dấu
ngoặc của số âm. Ghép bảng xuyên trang bằng tiêu đề, cấu trúc cột và continuation
evidence; không chắc thì giữ bảng riêng và issue. Unit/scale ở đầu bảng chỉ
được kế thừa xuống ô trong context đã xác định, kèm anchor tới header gốc.

### Semantic extraction

Mọi block được phân loại. Một đoạn có thể sinh nhiều records; một measurement
có thể có nhiều source spans. Block chưa phân loại giữ disposition `pending`
hoặc `unknown`, không bị bỏ khỏi ledger. Loại bỏ header/footer lặp chỉ khỏi
candidate extraction, không xóa khỏi nguồn; lưu lý do `repeated_header`.

Parser định lượng ưu tiên deterministic theo cell/header và Decimal. Bộ trích
định tính có thể dùng model theo JSON schema, nhưng output chỉ được chấp nhận
khi trỏ được tới span có thực. Không dùng kiến thức ngoài báo cáo để điền thiếu.
Model/backend định tính là lựa chọn triển khai, chưa bắt buộc dịch vụ cloud;
phải được cấu hình rõ trước khi gửi tài liệu ra ngoài máy.

## 4 Hợp đồng dữ liệu canonical đề xuất

Schema đề xuất `esg-extract/2.0.0-draft`; chưa coi là interface đã được Graph
chấp thuận. JSON UTF-8, version hóa schema, parser, model và adapter độc lập.

Các collections cấp batch:

| Collection | Nội dung |
| --- | --- |
| `batch` | ID, thời điểm UTC, method/config versions, actual counts, validation result |
| `companies` | Company ID, tên gốc/chuẩn hóa, các entities đã xác định |
| `reports` | Report/version ID, file/hash, loại, kỳ, ngày công bố, scope, source access |
| `source_artifacts` | PDF/native JSON/text artifacts, hash và vị trí truy cập |
| `source_blocks` | Block/cell/span, nguyên văn và vị trí nguồn |
| `records` | Common envelope và payload theo loại |
| `evidence` | Evidence ID, content/source refs và loại bằng chứng |
| `links` | Candidate/confirmed links giữa records và evidence/targets/metrics |
| `coverage` | Từng trang/section/block và phần pending/failed |
| `issues` | Record/field/source refs, code, severity, status, lý do và hành động |

### Common envelope và 16 nhóm trường bắt buộc

| STT tài liệu | Trường canonical | Quy tắc |
| --- | --- | --- |
| 1 Công ty | `company_id`, `reported_entity` | Tên/mã/entity giữ nguồn; không đồng nhất công ty mẹ và cơ sở |
| 2 Báo cáo | `report_id`, `report_version_id` | FK tới inventory có filename/type/source access |
| 3 Kỳ báo cáo | `reports.reporting_period` | Year, raw text, start/end nếu có |
| 4 Ngày công bố | `reports.publication_date` | Date và source refs hoặc null + status |
| 5 Phạm vi báo cáo | `reports.report_scope` | Entity level và separate/consolidated/unknown |
| 6 Record ID | `record_id` | Duy nhất, ổn định theo identity policy |
| 7 Nguyên văn | `source_refs`, `original_text`, `original_cells` | Table giữ label/header/value riêng; diễn giải ở `interpretation_notes` |
| 8 Vị trí | Source anchor | PDF page, printed page, section/table/row/column/bbox/native pointer |
| 9 Loại nội dung | `record_type`, `type_candidates` | Claim/metric/measurement/target/policy/action/governance/financial_context/unknown |
| 10 ESG | `classification.pillar`, `topic_candidates`, `codebook_version` | E/S/G hoặc unknown; financial context không ép vào E/S/G |
| 11 Thời gian nội dung | `content_period` | Tách reporting period, có raw header/source refs |
| 12 Phạm vi nội dung | `boundary` | Entities/activities/sites/inclusions/exclusions/consolidation method riêng |
| 13 Bằng chứng | `evidence`, `links` | Candidate link không tự động là support hoặc contradiction |
| 14 Dữ liệu | `data_status`, `field_status` | Sáu trạng thái theo yêu cầu; trạng thái ở cấp field khi cần |
| 15 Review | `review.status`, `verified_fields` | Unreviewed/needs_review/verified, reviewer/time/method |
| 16 Cần kiểm tra | `missing_fields`, `issues` | JSON pointer đến field, source và lý do cụ thể |

`data_status` dùng `available`, `missing`, `ambiguous`, `not_applicable`,
`unknown`, `extraction_failure`. `missing` chỉ khi đã kiểm tra phạm vi nguồn
liên quan mà không tìm thấy; `unknown` khi chưa xác định; `ambiguous` khi có
nhiều cách đọc; `extraction_failure` khi kỹ thuật thất bại. Available không
đồng nghĩa verified. Mọi field phải tồn tại theo schema loại record, có thể null.

`field_status` ánh xạ JSON pointer tới status, reason, source refs, candidate
values nếu có. Các trường bắt buộc nhưng null không tự động là lỗi schema.
`missing_fields` được sinh từ các field áp dụng còn null, không sửa tay ở hai
nơi; `boundary.missing_fields` là projection của cùng dữ liệu field_status.
Trường not_applicable có null và lý do, không tính là missing.

Review toàn record chỉ `verified` khi tất cả field áp dụng đã được kiểm tra.
Review một số field phải liệt kê `verified_fields`; boundary chưa rõ vẫn giữ
needs_review. Nếu giữ `extraction_status: resolved` vì tương thích, chỉ có
nghĩa tìm được nội dung/giá trị và source, không phải boundary đã xác minh.

### Payload theo loại dữ liệu

| Loại | Payload cần giữ |
| --- | --- |
| Claim | Statement raw, actor/action/object/qualifier nếu xác định, candidate classification |
| Metric | Original name, candidate code, definition, methodology, source refs |
| Measurement | Metric ref, raw value, parsed decimal string, raw/parsed unit và scale, content period, boundary |
| Cường độ/tỷ lệ | Measurement + numerator/denominator/unit/formula được công bố, không tự dựng |
| Target | Statement, target value/unit/year/deadline, baseline year/value, boundary |
| Target progress | Measurement kỳ thực hiện + candidate/confirmed target link, không chỉ gộp vào target text |
| Policy | Text, scope, effective period/date nếu có |
| Action | Activity, beneficiaries/scope, time, disclosed results và measurement refs |
| Governance | Responsible body/person, role, oversight mechanism, reporting frequency |
| Nhiều năm | Measurement riêng mỗi kỳ; links về thay đổi định nghĩa/unit/method/baseline/boundary |
| Restatement | Original/revised measurements, content period, report versions và reason source |
| BCTC | Statement type, item code/name, current/comparative columns, currency/scale, scope và cell anchors |
| ESG–tài chính | Chỉ nội dung doanh nghiệp công bố liên quan chi phí/đầu tư/doanh thu/rủi ro/tác động; source và links |

Decimal xuất chuỗi để không mất chính xác số VND lớn. `raw_value` luôn là
chuỗi gốc; `parsed_value` không nhân scale, `normalized_value` chỉ tạo nếu đơn
vị và scale đã xác định. Null, ô trống và dấu gạch không chuyển thành 0.
Financial context không tự thành đánh giá hiệu quả ESG hay cáo buộc.

## 5 Trích xuất BCTC và phân biệt kỳ

Đọc cả bảng cân đối, kết quả kinh doanh, lưu chuyển tiền tệ, thay đổi vốn nếu
có, chính sách kế toán và toàn bộ thuyết minh; không dùng whitelist bốn KPI.
Chỉ tiêu chưa có mã chuẩn vẫn có metric name gốc và measurement. Các bảng
thuyết minh có breakdown theo công ty con, loại tiền, aging, kỳ hạn hoặc giao
dịch phải giữ dimensions gốc, không ép thành cặp năm nay/năm trước.

Một hàng hai năm tạo metric và hai measurements. Current/comparative được
xác định từ header/ngày; không dựa đơn thuần vào trái/phải. Với BCTC quý, kỳ
từ đầu năm và kỳ quý không được nhập làm một. Balance sheet as-of date khác
duration của income/cash flow. Tên cột gốc luôn đi cùng parsed period.

Unit/currency/scale và tên bảng có thể nằm ở trang trước; chỉ kế thừa nếu đã
xác nhận logical table context. Nếu không thì null + issue. Phạm vi riêng/hợp
nhất lấy từ title/opinion/report context có anchor; từng số liệu vẫn có thể
thuộc entity khác được nêu ở thuyết minh. Không dùng danh sách cơ sở hay phạm
vi đánh giá trọng yếu chung để xác nhận boundary mọi KPI.

Tổng cộng/đối chiếu tài sản–nguồn vốn/cash flow là validation có điều kiện:
chỉ chạy khi đúng kỳ, đơn vị, scope và đủ thành phần. Sai lệch tạo issue; không
tự sửa số nguồn để cân bảng. Số trình bày lại không ghi đè số ở báo cáo cũ.

## 6 Identity và Graph adapter

Report version ID lấy từ PDF SHA256. Logical report ID có company/type/period/
scope với identity metadata; nếu thiếu metadata dùng provisional identity,
không đoán rồi âm thầm đổi ID.

Record ID được cấp từ report version + immutable source anchor + semantic
slot/type. Source anchors được lưu registry trước semantic extraction; không
dùng global table counter, text OCR đã sửa hoặc thứ tự model output làm ID.
Chạy lại cùng extraction snapshot dùng lại IDs. Khi re-OCR thay đổi segmentation,
reconcile anchors theo page/bbox/source registry; không chắc thì cấp revision
mới và lưu `supersedes`, không tuyên bố ID ổn định xuyên mọi phiên bản engine.
Sửa label/value/boundary sau review không đổi record/evidence ID.

Graph adapter ánh xạ collections canonical vào interface thực tế và kiểm tra
mọi FK. Cần chốt naming/enums/cardinality với bên Graph; chưa có interface
Graph v2 trong các file mã nguồn đã đọc. Link unresolved giữ trạng thái và
issue; không tạo phantom evidence. Candidate match chỉ đề xuất, có điều kiện
so sánh metric/period/unit/definition/boundary, không là kết luận tự động.

## 7 Coverage validation và bàn giao

Coverage có status từng page: pending, processed, partial, failed hoặc
confirmed_blank; kèm issue IDs, stage completed, attempt count và timestamps.
Processed phải đạt các stage bắt buộc, không chỉ converter trả về một object.
Section coverage có page ranges và trạng thái detected/unknown, không khẳng
định biết mọi section nếu chưa lập được mục lục. Mọi source block có disposition.

Batch phải báo số trang total/processed/partial/failed/pending/blank, số blocks,
số records theo loại, fields missing/ambiguous và reviewed counts. Tỷ lệ xử lý
trang công khai công thức và mẫu số; không dùng tỷ lệ này làm accuracy.
Tổng các nhóm trang loại trừ nhau phải bằng số trang PDF.

Validation gồm schema/type/enums, ID uniqueness, FK integrity, source pointer
resolution, page/bbox range, raw-to-source alignment, required field status,
null vs zero, year vs content period, unit/scale inheritance evidence, boundary
provenance, missing_fields sync, review evidence và count reconciliation.
Validation passed không có nghĩa mọi dữ kiện đúng; chưa đạt schema thì bàn
giao quarantined batch và validation issues, không coi đã sẵn sàng import Graph.

Gói bàn giao:

```text
batch/<batch-id>/
  manifest.json             batch metadata và validation summary
  inventory.json            reports/companies/versions/source access
  canonical.json            records/evidence/links/source references
  coverage.json             pages/sections/blocks và phần chưa hoàn tất
  issues.json               field-level issue log
  validation.json           check results và lỗi import-blocking
  sources/<report-version>/ source PDF hoặc access mapping + hash
  sources/<report-version>/ native/pages/tables và provenance
  graph/                    adapter output + adapter/schema versions
```

Đường dẫn tuyệt đối trên máy người tạo không được coi là nhóm đã truy cập
được. Chế độ bàn giao có thể đóng gói PDF tương đối trong ZIP nếu quyền chia sẻ
cho phép, hoặc map tới URL/kho nhóm đã kiểm tra quyền. Không tự upload ra ngoài.

## 8 Module và lộ trình triển khai

Các module sau là đề xuất mới, chưa tồn tại dưới dạng pipeline v2:

1. P0 `contracts/`, `inventory.py`, `identity.py`, `source_ledger.py`:
   chốt schema/Graph mapping, ID registry và versioning; fixture hợp lệ/lỗi.
2. P1 mở rộng `docling_backend.py`, thêm `page_worker.py`, `coverage.py`:
   per-page checkpoints, OCR routing, timeout/retry/resume, giữ partial outputs.
3. P2 `table_context.py`, `financial_parser.py`:
   tất cả bảng BCTC/thuyết minh, headers/units/periods, mỗi ô số một measurement,
   preserve unknown dimensions và chạy đối chiếu số học có điều kiện.
4. P3 `semantic_extractor.py`, `classify.py`, `candidate_links.py`:
   paragraphs/policies/actions/governance/targets, multilingual, unknown queue,
   links candidate và thay đổi nhiều năm/restatement.
5. P4 `validation.py`, `review_store.py`, `graph_adapter.py`, `export_bundle.py`:
   review theo field, đồng bộ missing_fields, package nguồn, adapter contract tests.
6. P5 cập nhật `dashboard/upload_analysis.py`:
   inventory theo file, counts theo page/stage, partial/failure không hiện completed
   thành công chung; lọc record type, xem nguồn và export đúng trạng thái.

Không thay parser legacy rồi migrate toàn bộ một lần. Pipeline v2 chạy song
song bằng feature flag, xuất thư mục khác, không ghi đè JSON/handoff cũ. Adapter
legacy chỉ xuất phần biểu diễn được; các trường không tương thích phải có loss
report thay vì bỏ âm thầm.

## 9 Điều kiện nghiệm thu

Các điều kiện không thỏa hiệp: 100% trang có trạng thái; 100% source blocks
được quản lý disposition; mọi record có source hoặc issue thiếu nguồn; IDs
không trùng ngoài chủ ý; FK resolved hoặc flagged; không tự điền null thành 0;
không mixed separate/consolidated; không verified nếu chưa có review.

Bộ chuẩn phải gồm BSR 2023–2025 ESG/BCTC và thêm doanh nghiệp khác; có PDF scan,
native/mixed, bảng nhiều trang, nhiều cấp header, unit ở đầu bảng, quý/năm,
restatement, ô trống/gạch, ghi chú, biểu đồ và qualitative-only paragraphs.
Đối chiếu độc lập với PDF gốc, không dùng JSON cũ làm ground truth mặc định.

Đo riêng detection recall cho bảng/block/record, OCR accuracy, row-column
alignment, numeric exact match, period/unit/scope accuracy và qualitative-type
precision/recall. Báo cáo denominators và failure cases. Chốt ngưỡng bằng pilot
và người dùng trước production; không công bố “đủ mọi trường” từ một trang smoke test.

Các test trọng điểm: lỗi trang giữa vẫn giữ trang khác; resume không nhân đôi;
upload riêng/hợp nhất cùng năm; số VND lớn không mất chữ số; raw label không bị
thay bởi diễn giải; hai kỳ thành hai measurements; policy không có số vẫn sinh
record; boundary null còn missing_fields; reviewer sửa field không đổi ID;
Graph pointer không resolve bị chặn/flag; source access của gói bàn giao kiểm tra được.

Thiết kế này chưa triển khai các module v2, chưa chạy extraction toàn bộ corpus
và chưa xác nhận accuracy/Graph compatibility. Bước triển khai đầu tiên là P0
và P1, sau đó ưu tiên P2 để đáp ứng nhu cầu BCTC trước.

## 10 Hai nhánh trích xuất theo bản yêu cầu mới

```text
                Lớp nguồn chung và source ledger
                    /                     \
       ESG semantic extractor      Financial statement extractor
       claim/target/policy/...      statement/note/metric/measurement
                    \                     /
              Canonical records có source anchors
                            ↓
             Candidate ESG–financial reconciliation
                            ↓
                Validation → review → Graph adapter
```

### Nhánh ESG

Đọc paragraphs lẫn bảng, chart labels và footnotes để tìm claim, metric,
measurement, target, policy, action và governance. Không bắt buộc phải có con
số mới tạo record. Phân loại E/S/G và topic chỉ là candidate theo codebook
version; nội dung chưa rõ giữ unknown. Một đoạn chứa mục tiêu và kết quả thực
hiện sinh records riêng và target-progress link, không gộp mất hai ý nghĩa.

Ví dụ cấu trúc, không phải số liệu doanh nghiệp: bảng có một chỉ tiêu và ba
cột năm tạo một metric và ba measurements có period/source riêng; target ở
đoạn khác tạo target record. Nếu baseline không được nêu, baseline null và có
issue; không lấy số năm đầu tiên trong bảng làm baseline mặc định.

### Nhánh tài chính

Đọc toàn bộ nội dung, nhưng phân biệt source capture với semantic classification.
Mỗi chỉ tiêu tài chính được nhận diện tạo metric và measurements theo từng
cột/dimension; phần thuyết minh định tính giữ financial_context hoặc loại nội
dung liên quan. Bảng không xác định được header vẫn bàn giao candidate record
và toàn bộ cells với issue, không bỏ hàng khỏi batch.

Chỉ tạo claim/target/policy/action/governance mang phân loại ESG khi có đoạn
công bố liên quan. Các số thuần tài chính có pillar unknown và domain financial;
ký hiệu X của hệ thống cũ chỉ nằm trong adapter legacy, không coi là pillar ESG.
`statement_scope` separate/consolidated không thay thế boundary của từng số
liệu thuyết minh. Current/comparative không dùng như year nếu chưa parse được
header; currency và scale phải có source refs trước khi chuẩn hóa giá trị.

### Nhánh liên kết ESG và tài chính

Chạy sau khi cả hai nhánh đã tạo records. Ưu tiên liên kết theo nội dung công
bố: note references, investment/project names, chi phí/đầu tư môi trường,
doanh thu hoặc rủi ro liên quan. Matching theo company và report year chỉ
thu hẹp candidates; cần thêm content period, boundary, definition và unit.

Link chứa from/to record IDs, relation type, status candidate/confirmed/
unresolved, source refs, matching criteria và incompatibilities. Số tổng chi
phí trong BCTC không tự chứng minh một claim chi môi trường; khoản mục có tên
gần nhau không tự coi là cùng metric. Một measurement có thể liên quan nhiều
claims; một claim có thể có nhiều evidence. Chưa có BCTC tương ứng vẫn giữ
claim ESG và issue missing_counterpart_report, không loại công ty khỏi batch.

## 11 Hợp đồng giữa các module

| Module đề xuất | Input | Output | Điều kiện chuyển bước |
| --- | --- | --- | --- |
| Inventory | Uploaded PDFs + user metadata | Report versions và company candidates | Hash, source access, số trang; metadata chưa rõ được flagged |
| Page worker | Report version + extraction profile | Page artifacts và page events | Mỗi trang có checkpoint hoặc failure |
| Source ledger | Native Docling/page artifacts | Blocks/cells/spans và stable anchors | Không mất ô trống/merged cells, giữ provenance |
| Context builder | Ledger theo thứ tự trang | Sections/logical tables/header context | Kế thừa phải có evidence; không chắc vẫn giữ raw |
| ESG extractor | Ledger + ESG contexts + codebook | Typed candidates và field statuses | Không yêu cầu số; raw/source alignment |
| Financial extractor | Ledger + financial contexts | Metrics/measurements/financial contexts | Decimal, period, currency, scale và cell anchors |
| Linker | Hai tập records + evidence | Candidate links và unresolved issues | Không cross-scope hoặc gán support tự động |
| Validator/exporter | Canonical batch + source access map | Validation và handoff bundle | Counts/FK/source checks và loss report |

Danh mục field đề xuất nằm ở `config/extraction_v2_contract_draft.yml`.
Đây là data dictionary và chính sách thiết kế, không phải cấu hình đã được
runtime hiện tại đọc, cũng không phải JSON Schema đã chốt với Graph.

### Hành vi người dùng và API nội bộ

Luồng sử dụng: kéo thả nhiều PDF → xác nhận metadata từng file → chọn cả báo
cáo hoặc phạm vi thử → chạy → xem coverage/issues → review → tải gói bàn giao.
Metadata phải theo từng file, không dùng một dropdown chung để gán nhầm toàn
bộ batch trộn ESG/BCTC, nhiều năm hoặc riêng/hợp nhất.

Job state: queued, running, partial, failed, completed, cancelled. completed
chỉ khi các stage bắt buộc xong; validation/review state hiển thị riêng. Resume
tạo attempt mới, không ghi đè audit history. Giao diện hiển thị trang đã xử lý,
trang lỗi, record counts theo loại và field issues; không dùng số claim làm
thước đo duy nhất cho tiến độ hay độ đầy đủ.

Các thao tác nội bộ đề xuất: create_batch(files, metadata_by_file),
start_batch(profile), resume_batch(failed_or_pending_pages),
get_batch_status(), review_field(record_id, field_pointer, decision),
export_batch(format, include_sources). Đây là interface thiết kế, chưa phải
endpoint/CLI có thể chạy. Review edit phải lưu old/new value và source/reviewer.

## 12 Ma trận nghiệm thu riêng ESG và BCTC

| Fixture | Kết quả bắt buộc |
| --- | --- |
| ESG policy không có số | Policy record có text/source; không bị lọc bởi regex số |
| ESG bảng ba năm | Một metric, ba measurements với header/kỳ riêng |
| Target có deadline nhưng thiếu baseline | Giữ target, baseline null và field issue |
| ESG governance có cơ quan giám sát | Governance record; chỉ điền vai trò/tần suất khi nêu |
| BCTC riêng và hợp nhất cùng công ty/năm | Hai report versions và phạm vi riêng, upload không chặn |
| BCTC tiền tệ ở đầu bảng | Unit được kế thừa với header anchor, không dựa vào từng hàng |
| BCTC cột so sánh có số trình bày lại | Measurement có restatement link; không ghi đè bản cũ |
| BCTC bảng thuyết minh nhiều dimensions | Giữ các dimensions/cells; không ép thành hai cột năm |
| BCTC số thuần tài chính | Không tự gán E/S/G hoặc tạo cáo buộc |
| Cả hai báo cáo có khoản đầu tư được nêu liên quan | Candidate link có nguồn hai bên và comparison conditions |
| Thiếu BCTC một năm của PLX/PVD/BSR | Giữ ESG records, báo thiếu counterpart trong inventory/issues |
| Scan không đọc được một trang | Batch partial, giữ trang khác, source page và failure rõ ràng |

Không có field nào được điền chỉ để đủ bảng yêu cầu. “Đáp ứng yêu cầu” nghĩa
là có contract, giá trị có nguồn hoặc trạng thái thiếu/chưa rõ rõ ràng, không
phải mọi field đều khác null. Các test này là tiêu chí triển khai, chưa phải
những khả năng đã được kiểm chứng trong runtime hiện tại.
# Cập nhật nhánh ESG: bảng và evidence candidates

ESG parser v2 (`esg-candidates/2.1.0`) đã bổ sung metric theo hàng,
measurement theo ô/header kỳ, đơn vị nguồn và evidence ô nguồn. Liên kết
claim/target–evidence chỉ là `candidate_context` bằng alias metric duy nhất;
chưa xác nhận comparability, boundary, support/contradiction hoặc đạt mục tiêu.
Mọi bảng vẫn yêu cầu rà soát độ đầy đủ; chưa xử lý header ESG xuyên trang và
biểu đồ. Chưa nối parser v2 vào giao diện kéo thả. Xem `ESG_V2_USAGE.md`.

