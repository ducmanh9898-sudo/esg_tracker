# ESG Rule Catalogue v1 — KG-E-01, KG-S-01 và KG-G-01 đã kích hoạt

**Trạng thái:** KG-E-01, KG-S-01 và KG-G-01 đã được kích hoạt trong Graph v2 phiên bản 1.0; các rule draft vẫn chưa chạy. `ready` chỉ nói đặc tả đã được duyệt, không nói dữ liệu thật đã đủ điều kiện. Các ví dụ dưới đây đều **synthetic**.

### Quyết định triển khai đợt 1

- `review_status=reviewed` trên claim là nguồn đã được người có trách nhiệm review; `unreviewed`, `unknown` hoặc thiếu trạng thái không được nâng thành reviewed. Alias chỉ đủ điều kiện khi `verification_status=verified` **và** có `review_basis`; alias `candidate` dù trùng tên vẫn cần review. Hai trạng thái thuộc hai đối tượng khác nhau và đều phải đạt để kết luận mạnh.
- Thứ tự: nhận diện applicability và vai trò theo canonical mapping → kiểm tra đủ record/không trùng vai trò → so context/metric definition, unit, period, scope, boundary, board/population identity → source review/provenance → giá trị null/uncertain → precision đã xác minh → số học. `NeedsReview` ưu tiên trước `InsufficientEvidence` khi đồng thời có context/mapping/source chưa rõ và value thiếu. **Mọi** lý do, kể cả missing, vẫn ghi vào evaluation log.
- `NotApplicable` chỉ khi report có record định tính thuộc đúng topic mà rule số không áp dụng (ví dụ policy không số), hoặc có căn cứ không áp dụng khác. Không thấy ứng viên trong coverage chưa xác minh, hoặc có ứng viên nhưng thiếu hẳn một vai trò, là `Skipped`/chưa đánh giá, không phải DisclosureGap hay finding. Hai record biết rõ thuộc HĐQT khác nhau cũng `Skipped`; chưa rõ board identity là `NeedsReview`. Không chọn record đầu tiên nếu một vai trò có nhiều ứng viên/variant; nhóm đó `NeedsReview` và log toàn bộ ID.
- Nhóm ứng viên dùng cùng company, **report ID** và observation year. Cùng report year nhưng khác report ID không ghép. Một report có nhiều kỳ so sánh được log riêng; thiếu năm đo không được suy từ report year. `Supported` và `Contradicted` đều cần cùng guard về mapping, review, context và precision. Precision chỉ lấy từ review annotation có căn cứ nguồn: exact hoặc `rounded_half_up` với `step` xác minh; không kế thừa tolerance demo.
- Các trường kiểm chứng như `metric_definition_verified`, `organizational_scope`, `emission_basis`, `scope2_method`, `population_id`, `board_id`, `measurement_date`, `counting_method` và `precision` là annotation ngữ cảnh của Graph trên normalized claim trong engine/test; chúng **chưa** là field bắt buộc của contract Extract hiện tại. Đường nhập annotation review đã được triển khai riêng tại [hướng dẫn review](graph-review-annotations.md); mẫu corpus thật vẫn ở trạng thái pending và chưa tạo xác nhận verified. Không được tự suy review từ alias.
- `rule_evaluations.json` là log cả outcome không sinh finding; `ready_findings.json` và `findings.json` chỉ chứa ba rule mới. `demo_findings.json` giữ nguyên toàn bộ 10 finding demo (kể cả R06 và các Supported cũ) để audit. Demo không vào RDF, SPARQL evidence chain hoặc claim/company assessments chính; giao diện hiển thị ở bảng “Đối soát demo” riêng. Không có risk score.

**Nguồn nội bộ đã đối chiếu:** [roadmap](../Greenwashing_ESG_System_Roadmap_Extract_Graph.docx), [topic](../topic.txt), [Core](../kg/core.ttl), [Oil & Gas Profile](../profiles/oil_gas.json), [contract](extract-graph-contract.md), [config rule demo](../data/config/rules.json), [catalogue demo dạng máy](../data/config/rule_catalogue.json), [engine](../tools/rule_engine.py), [Graph v2 pipeline](../kg/pipeline.py), [assessment rules](../kg/assessment_rules.py), [temporal legacy](../tools/temporal_assessment.py), [SHACL chất lượng](../kg/shapes.ttl), [SHACL audit](../kg/business_shapes.ttl) và test. Roadmap giai đoạn 12 yêu cầu rule có input, applicability, expected relation, violation, finding, rationale, trường hợp ambiguous; giai đoạn 13 tách thay đổi năm với inconsistency. Không có điều khoản GRI/IFRS/SASB nào được dùng làm ngưỡng hoặc kết luận tuân thủ trong ba rule ready dưới đây.

## 1. Rule nào hiện được gọi

`kg.pipeline.build` đọc `data/config/corpus_config.json`. Nhánh `ready_rule_aliases` bật KG-E-01, KG-S-01 và KG-G-01 cho mọi company có ứng viên metric; alias thực vẫn ở trạng thái `candidate`, nên không mặc định có kết luận mạnh. Nhánh demo `rule_sets.BSR` vẫn trỏ đến `data/config/rules.json`; engine `tools.rule_engine.evaluate` duyệt chín cấu hình R01–R09 trên claim BSR đủ điều kiện, nhưng **toàn bộ kết quả demo chỉ vào file audit và bảng demo riêng**. **Không có** demo `rule_sets` cho PLX/PVD. `data/config/rule_catalogue.json` mô tả chín rule demo cho coverage/acceptance gate, **không** điều khiển ba rule mới.

| ID đang cấu hình | Loại kiểm tra | Điều kiện/giới hạn đang mã hóa |
| --- | --- | --- |
| R01 | E, hai trị Scope 1 cùng báo cáo; nhất quán số | `ghg_scope1`, tolerance **1 tCO2e**; khác trị có thể thành `Contradicted` sau guard. Không tự áp cho mọi metric. |
| R02 | S, tổng lao động = nam + nữ; tổng/thành phần | `employees_*`, riêng report year **2025**; failure `NeedsReview` vì chưa chứng minh phân loại đầy đủ. |
| R03–R04 | E, đối soát tổng chất thải với hai cách chia | Report year **2025**, tolerance **0,02 tấn**; chưa xác minh tập thành phần đầy đủ. |
| R05 | E, cùng observation year qua hai report | `ghg_total_unspecified`, tolerance **1 tCO2e**; failure `NeedsReview`, chưa phải `TemporalInconsistency`. |
| R06 (audit only) | G, thành viên độc lập ≤ tổng HĐQT | `board_total`/`board_independent`, đơn vị người; cùng mọi rule demo khác chỉ nằm trong audit. |
| R07 | E, mức giảm cường độ công bố so với hai trị | Report year **2025**, năm 2024→2025, tolerance **0,5 điểm %**; failure `NeedsReview`. |
| R08 | E, EII actual so với target | Report year **2023**, hướng `lower_is_better` từ config; target không phải actual; failure `NeedsReview`. |
| R09 | S, tỷ lệ nam+nữ = 100% | Report year **2023**, tolerance **0,1 điểm %**; chỉ kiểm tra hai tỷ lệ đã chọn. |

Đây là các phép **nhất quán số học hoặc claim–performance/target trong dự án**, không chứng minh tuân thủ tiêu chuẩn hay greenwashing. Các tolerance demo nêu trên **không được kế thừa** sang rule ready. `tools.rule_engine.make_finding` còn có fallback `company_id="BSR"` khi danh sách claim rỗng; selection/temporal config và test demo chứa ID BSR. Tổng quát hóa cần chọn theo canonical metric/topic, kỳ đo, variant, đơn vị, scope và boundary đã xác minh; không chọn bằng tên công ty hay năm cố định. Alias metric của PLX/PVD hiện khác BSR; chưa có crosswalk được review cho mọi metric, nên không coi chuỗi tên giống nhau là đã map.

**Hạn chế engine cần giữ trong review:** R01 tên là “cùng báo cáo” nhưng khóa nhóm hiện dùng `report_year`, **không** dùng `report_id`; các rule tổng/thành phần chọn record đầu tiên khi có nhiều variant; `Supported` chưa được guard review/context chặt như `Contradicted`; `make_finding` gắn severity theo status. Các điểm này là lý do không sao chép config demo thành catalogue chung hoặc dùng finding demo làm expected của ca synthetic mới.

Các kiểm tra **khác** đang tồn tại:

| Thành phần | Đang chạy hay không | Phân loại đúng |
| --- | --- | --- |
| JSON Schema normalized, `input_review.json`, `kg/shapes.ttl` | Graph v2 chạy trên input/RDF | Validation/chất lượng: ID, report/evidence, locator, giá trị `available`; cảnh báo/vi phạm cấu trúc không là `Contradicted` ESG. |
| `kg/business_shapes.ttl` | Graph v2 chạy sau finding | Audit: finding `Contradicted` phải có boundary verified; không tự tạo finding. |
| `kg.rdf_store.link_cross_year` | Graph v2 chạy | Tạo cặp năm `Comparable`/`NeedsReview`, **không** tạo finding. |
| `kg.assessment_rules.disclosure_gap_findings` | Được gọi nhưng `required_disclosures=[]` trong profile | Chưa có rule disclosure gap hoạt động cho corpus hiện tại. |
| `kg.assessment_rules.temporal_revision_findings` | Được gọi nhưng `temporal_revision_rules=[]` | Chưa có rule `TemporalInconsistency` hoạt động cho corpus hiện tại. |
| `kg.pipeline.financial_comparability` | Tạo candidate cho cặp `employees_total`/`workforce.total` và guard context | Chưa có đánh giá tác động ESG–tài chính; `financial_reconciliation.json` là danh sách cần review, không phải finding. |
| `tools.temporal_assessment` | Đường demo cũ với series/claim ID BSR, không được Graph v2 gọi | Phân tích temporal candidate, không phải rule finding production. |

## 2. Quy ước chung cho rule trong catalogue

- **Khóa áp dụng:** canonical concept/metric đã được Graph xác nhận; `dimension`/`topic` và `claim_type` từ normalized claim; company ID chỉ để nhóm theo thực thể, không nằm trong điều kiện riêng cho BSR. Một rule có thể `NotApplicable` với một hoặc nhiều report của BSR, PLX hay PVD.
- **Khóa so sánh:** cùng company, **observation period/period type**, metric definition, unit hoặc conversion đã xác minh, scope, reporting boundary/entity, variant và phương pháp/baseline nếu phép kiểm tra phụ thuộc chúng. `report_year` chỉ là năm của báo cáo chứa số; số so sánh 2024 trong báo cáo 2025 vẫn có `observation_year=2024`. Không so Separate với Consolidated. Không lấy boundary của report làm boundary claim đã verified.
- **Chất lượng nguồn:** `review_status=reviewed`, nguyên văn và locator trang/JSON Pointer truy được; `evidence_id`, `record_id`, `report_id`, `source_file` giữ nguyên. `original_text=null`, thiếu trang, unknown period, metric mapping mơ hồ hoặc OCR chưa review → `NeedsReview`/không vào phép so mạnh. `confidence` của Extract không thay manual review.
- **Số học:** ba rule ready chỉ dùng đẳng thức/tập con khi các số có cùng định nghĩa và precision đã kiểm tra. Số đếm nguyên không cần tolerance; số phát thải làm tròn cần khoảng giá trị suy từ **độ chính xác hiển thị được nguồn xác nhận**. Nếu precision không xác định, không suy tolerance; trả `NeedsReview` khi khác số.
- **Kết quả:** `Supported` chỉ nói phép kiểm tra cụ thể đạt; `Contradicted` là mâu thuẫn giữa các dữ kiện đủ điều kiện so, không phải gian lận. `InsufficientEvidence` chỉ khi nhóm claim đã xác định, context đã đủ và **một record hiện hữu** cần cho phép so có `value=null/missing`. Thiếu hẳn record hoặc coverage chưa xác minh → `Skipped` trong log, **không tạo finding**. Policy chỉ có nội dung định tính thuộc topic → `NotApplicable` trong log, không tạo finding. Unit/boundary/period mismatch hoặc chưa review → `NeedsReview`, không phải contradiction. Policy không có số không là evidence gap.
- **Evidence chain khi có finding:** finding/rule ID → toàn bộ input `record_id` → từng `evidence_id`, `original_text`, `source_file`, `source_pages`, `json_pointer` → `report_id`/report year và observation period; lưu phép tính/điều kiện context và các uncertainty. Không phát minh evidence cho record vắng. `NotApplicable` và `Skipped` luôn có evaluation log và không tạo finding.
- **Tiêu chuẩn:** cơ sở ba rule ready là quan hệ số học/tập con **do dự án định nghĩa**; standard reference/version = **không áp dụng**. Crosswalk tiêu chuẩn là ngữ cảnh riêng, không biến phép cộng thành chứng nhận GRI, IFRS hay SASB. Không đặt severity hay risk score cho catalogue này.

## 3. Ba rule ready đã bật trong Graph v2

### KG-E-01 — Tổng Scope 1 + Scope 2 đã công bố

- **Mục đích/dimension/topic:** đối soát total được nguồn gọi rõ là **Scope 1 + Scope 2** với hai thành phần; E / climate_and_ghg. Đây là phép cộng của cùng loại phát thải, **không** là kiểm tra đầy đủ disclosure GHG.
- **Input bắt buộc:** ba claim measurement đã map và review: `scope1_emissions`, `scope2_emissions`, `scope1_plus_scope2_total` (tên canonical **đề xuất**, không ép đổi ID Extract), với `metric_definition`, `value/value_status`, `unit`, `observation_year`, `period_type`, `scope`, `reporting_boundary[_verified]`, `review_status`, `evidence[]`. `source_file`, trang, pointer và original text phải truy được. Tùy chọn: original value/precision, measurement method, assurance note; baseline chỉ cần nếu một nguồn định nghĩa tổng theo baseline khác.
- **Applicability:** total phải nói rõ chỉ gồm Scope 1 và Scope 2, cùng cách gross/net và cách hợp nhất, cùng kỳ/phạm vi; không dùng `ghg_total_unspecified`. Chỉ chạy ở BSR/PLX/PVD nếu ba vai trò được map và đủ context; tên như `scope_1` hay `ghg_emissions_scope_1_tco2e` chỉ là **candidate alias** trước review.
- **Logic/so sánh:** total phải được định nghĩa đúng bằng hợp của hai thành phần; phương pháp đo, unit tCO2e hoặc conversion xác minh, observation period/period type/scope/boundary phải tương thích. Tính `total − (scope1 + scope2)`. Nếu số hiển thị là exact, delta phải bằng 0; nếu có làm tròn đã chứng minh, khoảng của total phải giao khoảng tổng hai thành phần. Không dùng tolerance demo R01/R03, không suy total khi thiếu record total.
- **Status:** `Supported` khi ba giá trị nhất quán trong precision nguồn; `Contradicted` khi ba giá trị exact hoặc các khoảng đã xác minh không thể giao nhau, không có restatement/khác định nghĩa; `InsufficientEvidence` khi nhóm ba record hiện hữu, context đủ và một value null; `NeedsReview` khi unit, gross/net, kỳ, scope, boundary, precision, OCR, mapping hoặc review chưa rõ; `Skipped` khi thiếu record total hoặc coverage chưa xác minh. Không dùng E/S/G dimension X của BCTC.
- **Chain/cơ sở/trạng thái:** chain chung với **ba** claim và ba evidence; rationale là đẳng thức số học có điều kiện từ nhãn/định nghĩa trong chính báo cáo; standard ID/version: không áp dụng. **Ready (spec)** vì có điều kiện đủ/không đủ và không cần ngưỡng tự đặt; mapping và review dữ liệu thật còn pending.

### KG-S-01 — Số lao động nữ không vượt tổng lao động

- **Mục đích/dimension/topic:** kiểm tra một **tập con** người lao động so với tổng cùng quần thể; S / workforce. Không giả định nam+nữ là phân loại đầy đủ, không kiểm tra tỷ lệ đại diện.
- **Input bắt buộc:** hai measurement canonical `employees_female_count`, `employees_total_count` (tên đề xuất), số đếm nguyên không âm, `metric_definition`, `value/value_status`, unit `person`, kỳ đo/loại kỳ, định nghĩa nhân sự (nhân viên/cộng tác viên/contractors), scope, boundary verified, reviewed evidence. Tùy chọn: headcount/FTE, ngày chốt, thành phần quần thể; nếu các trường này cần để xác định cùng quần thể thì chúng trở thành **điều kiện so**.
- **Applicability/logic:** chỉ khi female là tập con được nguồn định nghĩa trong đúng total; `female_count ≤ total_count` và cả hai ≥ 0. Không dùng `female_share` như count, không lấy dữ liệu khác ngày/boundary. Baseline không liên quan vì đây là so cùng kỳ.
- **Status:** `Supported` khi quan hệ tập con đúng; `Contradicted` khi count đã review và female > total; `InsufficientEvidence` khi cặp record hiện hữu, context đủ nhưng value null; `NeedsReview` khi có số âm, headcount/FTE, kỳ, unit, phạm vi nhân sự, boundary, nguồn hoặc mapping không so được; `NotApplicable` cho policy/narrative thuần túy, `Skipped` khi thiếu count hoặc coverage chưa rõ. Thiếu hẳn female record **không** tự thành gap.
- **Chain/cơ sở/trạng thái:** chain chung với **hai** claim; rationale là quan hệ tập con của quần thể người, không dựa vào phân loại giới tính đầy đủ; standard ID/version: không áp dụng. **Ready (spec)**, áp dụng theo dữ liệu phù hợp của bất kỳ công ty nào; cần review alias và định nghĩa lao động thật.

### KG-G-01 — Thành viên HĐQT độc lập không vượt tổng HĐQT

- **Mục đích/dimension/topic:** kiểm tra số thành viên độc lập là tập con của tổng thành viên cùng HĐQT; G / board. Không kiểm tra tỷ lệ tối thiểu theo luật hay chuẩn quản trị.
- **Input bắt buộc:** hai measurement canonical `board_independent_count`, `board_total_count` (tên đề xuất), số đếm nguyên không âm, định nghĩa thành viên đang tại nhiệm, đơn vị `person`, cùng ngày/kỳ, cùng HĐQT, reporting entity/boundary verified, reviewed evidence. Tùy chọn: ngày hiệu lực thay đổi thành viên, loại ghế, nhiệm kỳ; nếu nguồn là hai thời điểm khác nhau, không so.
- **Applicability/logic:** chỉ khi nguồn nêu independent là tập con của total của **cùng** board; `independent ≤ total`. Không dùng một policy/governance statement không có số làm `board_total=0`. Baseline không liên quan cho so cùng thời điểm.
- **Status:** `Supported` khi quan hệ tập con đúng; `Contradicted` khi số đếm exact đã review và independent > total; `InsufficientEvidence` khi cặp record hiện hữu, context đủ nhưng value null; `NeedsReview` khi có số âm, ngày chốt, định nghĩa, unit, board identity chưa rõ, trang/nguồn hoặc review chưa đủ; `NotApplicable` nếu chỉ có policy; `Skipped` nếu thiếu cặp count, coverage chưa rõ hoặc biết chắc là hai HĐQT khác nhau.
- **Chain/cơ sở/trạng thái:** chain chung với **hai** claim; rationale tập con toán học; standard ID/version: không áp dụng. **Ready, đã bật**; kế thừa ý tưởng từ R06 nhưng bỏ giả định tên công ty, còn dữ liệu thật cần review.

## 4. Bộ trường hợp kiểm chứng độc lập với engine (synthetic)

Mọi ca `Supported`/`Contradicted` dưới đây giả định: record ID, report ID, evidence ID, original text, trang, pointer, source file đầy đủ; `review_status=reviewed`; mapping/định nghĩa/unit/kỳ/scope/boundary đã xác minh; số nêu là exact và cùng đối tượng. Thay đổi một điều kiện chỉ khi ô ca nêu rõ. **Expected status là đặc tả**, không phải output hiện tại của `tools.rule_engine.evaluate`. `NotApplicable` nghĩa không phát sinh finding.

| Case | Rule | Input synthetic khác biệt | Expected | Lý do |
| --- | --- | --- | --- | --- |
| E-PASS | KG-E-01 | Scope1=40, Scope2=60, total1+2=100 tCO2e | Supported | 40+60=100 với ba định nghĩa khớp. |
| E-FAIL | KG-E-01 | 40, 60, total1+2=105 tCO2e; nguồn xác nhận exact | Contradicted | 105≠100, không có rounding/restatement khác. |
| E-NULL | KG-E-01 | Scope1=40, Scope2=null, total=100; ba record có mặt | InsufficientEvidence | Phép cộng cần Scope2; null không bằng 0. |
| E-CONTEXT | KG-E-01 | Scope1 thuộc Separate, Scope2/total thuộc Consolidated | NeedsReview | Boundary khác; không tính chênh số thành contradiction. |
| E-ABSENT | KG-E-01 | Chỉ có Scope1 và Scope2, không có record total | Skipped | Đã nhận diện ứng viên nhưng thiếu record total; không tự tạo total hay disclosure gap. |
| S-PASS | KG-S-01 | Female=45, total=100 người cùng population | Supported | 45≤100; không suy nam=55. |
| S-FAIL | KG-S-01 | Female=105, total=100 người cùng population | Contradicted | Tập con lớn hơn tổng exact. |
| S-NULL | KG-S-01 | Female=null, total=100; cả hai record có mặt | InsufficientEvidence | Thiếu giá trị cần so, không gán 0. |
| S-CONTEXT | KG-S-01 | Female là FTE, total là headcount, hoặc khác ngày chốt | NeedsReview | Khác định nghĩa/kỳ; không phép so mạnh. |
| S-ABSENT | KG-S-01 | Chỉ có `female_share` hoặc policy nhân sự | NotApplicable | Không phải hai số đếm cùng quần thể. |
| G-PASS | KG-G-01 | Independent=3, board total=9 cùng ngày | Supported | 3≤9, không đánh giá mức độc lập đủ hay thiếu. |
| G-FAIL | KG-G-01 | Independent=10, total=9 cùng HĐQT | Contradicted | Tập con lớn hơn tổng exact. |
| G-NULL | KG-G-01 | Independent=null, total=9; cả hai record có mặt | InsufficientEvidence | Thiếu số cần so. |
| G-CONTEXT | KG-G-01 | Independent cuối năm, total giữa năm; hoặc trang OCR chưa review | NeedsReview | Không cùng thời điểm/nguồn chưa đủ tin cậy. |
| G-POLICY | KG-G-01 | Chỉ có policy HĐQT, không có count | NotApplicable | Policy không cần số, không là evidence gap. |

**Các invariant của test:** đổi unit/period/scope/boundary → không `Contradicted`; thay target/metric qua năm → không tự `TemporalInconsistency`; cùng record ID nhưng hai provenance khác → giữ để review, không đếm trùng vô điều kiện; mọi finding phải truy được chain; PLX/PVD/BSR cùng context cho cùng expected result; dữ liệu thật không được dùng làm expected synthetic.

## 5. Rule draft / research pending (không kích hoạt)

### KG-S-02 — Tổng lao động theo các nhóm

- **Mục đích/dimension/topic:** S/workforce, đối soát total với một partition nguồn công bố. **Input:** total và mọi nhóm thành phần, `metric_definition`, unit, kỳ, scope, boundary, evidence; tùy chọn danh mục nhóm và cách xử lý giới tính không công bố/khác. **Applicability/logic:** chỉ khi nguồn xác nhận partition **đầy đủ và không chồng lắp**; tính tổng thành phần theo precision nguồn. **Expected:** nếu xác minh đầy đủ và bằng nhau → Supported; lệch exact → Contradicted; record hiện hữu null → InsufficientEvidence; chưa rõ tính đầy đủ/unit/boundary → NeedsReview; không có partition xác minh → NotApplicable. **Chain:** total + từng part + nguồn nêu partition. **Basis:** số học có điều kiện, standard/version không áp dụng. **Draft:** contract chưa có xác nhận machine-readable về tập thành phần đầy đủ; R02/R09 demo không đủ cơ sở kết luận mạnh chung.

### KG-NAR-01 — Claim định tính về kết quả/target so với evidence

- **Mục đích/dimension/topic:** E/S/G; so một phát biểu cụ thể như “đã đạt mục tiêu” với measurement/target cùng metric. **Input:** claim text, assertion polarity, metric/target relation, kỳ, baseline, hướng tốt/xấu, value, scope/boundary, original text/evidence; tùy chọn phương pháp tính. **Applicability/logic:** phải biết câu nói khẳng định **đạt/không đạt** cái gì, target và actual cùng kỳ; policy thuần túy không áp dụng. **Expected:** phát biểu khớp phép tính reviewed → Supported; phát biểu trái phép tính có đủ context → Contradicted; record hiện hữu thiếu actual/target → InsufficientEvidence; câu mơ hồ/mismatch/review chưa đủ → NeedsReview; không có assertion kiểm tra được → NotApplicable. **Chain:** narrative claim + actual + target + nguồn. **Basis:** project claim–evidence consistency, không phải điều khoản chuẩn; standard/version pending. **Research pending:** contract giữ text nhưng chưa có assertion polarity/link được review; không dùng LLM guess làm verified.

### KG-TEMP-01 — Khác giá trị cho cùng kỳ đo giữa hai báo cáo

- **Mục đích/dimension/topic:** E/S/G, cùng metric và **cùng observation period** nhưng khác report year. **Input:** hai claim và evidence, variant, metric definition, unit, period, scope/boundary, baseline/method, restatement status và giải thích; tùy chọn precision. **Applicability/logic:** so cùng fact sau khi loại trừ restatement hợp lệ, thay đổi phương pháp/boundary và rounding; target đổi qua năm không thuộc rule này. **Expected:** cùng trị reviewed → Supported; khác trị exact, context giống và xác minh **không restatement** → `TemporalInconsistency`; có record null → InsufficientEvidence; thiếu restatement/method/precision hoặc context khác → NeedsReview; khác observation period/metric → NotApplicable. **Chain:** cả hai claim, hai report và evidence gốc. **Basis:** project temporal consistency, standard/version không áp dụng. **Draft:** `restatement_status` và method chưa được adapter mới chuyển thành normalized field xác minh; profile đang để `temporal_revision_rules=[]`. Không đổi số qua năm thành inconsistency.

### KG-DISC-01 — Thiếu disclosure bắt buộc theo applicability

- **Mục đích/dimension/topic:** E/S/G tùy topic; kiểm tra absence sau search. **Input:** yêu cầu disclosure có standard reference/version và applicability verified cho company/industry/period, coverage `verified_complete` trên bộ tài liệu đúng boundary, issue log/search trace; tùy chọn claim hiện hữu nhưng value missing. **Applicability/logic:** chỉ khi cả nghĩa vụ và độ bao phủ tìm kiếm đã review. **Expected:** disclosure đúng yêu cầu tìm thấy → Supported (chỉ trong phạm vi kiểm tra); tìm không thấy sau coverage đủ → DisclosureGap; record hiện hữu null nhưng search chưa đủ và rule thực sự cần value → InsufficientEvidence ở cấp claim, không phải DisclosureGap; applicability/coverage mơ hồ → NeedsReview; không áp dụng → NotApplicable. **Chain:** requirement/version + searched report/page range + claim/evidence nếu có; absence phải có search trace, không tạo evidence giả. **Basis:** cần nguồn GRI/IFRS/SASB chính thức và quyết định applicability cụ thể, chưa gắn điều khoản. **Research pending:** profile `required_disclosures=[]`; coverage thực chưa được xác nhận đầy đủ, do đó không bật.

### KG-FIN-01 — Kết nối ESG với số liệu tài chính

- **Mục đích/dimension/topic:** liên kết E/S/G với financial context, **không** tạo dimension ESG thứ tư. **Input:** claim ESG, financial measurement, định nghĩa tác động/line item, period/date, unit/hệ số, reporting entity/boundary, source text và evidence hai phía; tùy chọn assurance. **Applicability/logic:** chỉ tạo relation/candidate khi nội dung nguồn **nói rõ** kết nối và metric/period/entity tương ứng; Separate và Consolidated không so trực tiếp. **Expected:** link có căn cứ reviewed → Supported **cho link**, không phải chứng minh hiệu quả tài chính; nguồn khẳng định con số tài chính đối nghịch với con số cùng định nghĩa/kỳ/boundary → Contradicted chỉ sau review riêng; cần giá trị hiện hữu null → InsufficientEvidence; thiếu linkage/mapping/boundary → NeedsReview candidate; không có claim kết nối → NotApplicable. **Chain:** ESG claim/evidence/report và financial measurement/evidence/report. **Basis:** project evidence linkage; standard/version chưa xác minh. **Draft:** current pipeline chỉ tạo candidate workforce và reconciliation review; không suy tác động ESG từ doanh thu/lợi nhuận tăng giảm.

## 6. Input sẵn có và quyết định cần duyệt

- Contract hiện giữ `record_id`, `metric_id` có thể null, `metric_definition`, `claim_type`, value/value status, observation year/period type, scope, boundary/verification, review status, target variant, original text, source pages, pointer, report/source và financial Separate/Consolidated. Đủ để **biểu diễn** ba rule ready và các ca synthetic; không khẳng định corpus thật đã review.
- Extract cần cung cấp **nguyên văn/locator**, định nghĩa count/tổng, unit và độ chính xác trình bày, ngày/kỳ đo, scope/boundary, trạng thái review và issue log khi có. Với rule draft, cần thêm bằng chứng về partition đầy đủ, assertion “đạt mục tiêu”, restatement/method, coverage tìm kiếm hoặc ESG–financial linkage; chưa yêu cầu đổi contract trong bước này. Graph chịu trách nhiệm kiểm tra/mapping, không ép Extract tự tạo finding.
- Còn cần nhóm Graph review: (1) alias nào của BSR/PLX/PVD đủ `review_basis` để chuyển từ `candidate` sang `verified`; (2) bằng chứng nguồn cho precision/method, population/board identity và boundary; (3) cùng source statement có đủ chứng minh partition cho rule draft hay không; (4) phương pháp adjudication temporal restatement và disclosure applicability trước khi nâng draft. `NotApplicable`/`Skipped` đã được ghi riêng vào evaluation log.
- **Ngoài phạm vi đợt triển khai này:** ngưỡng ngành/tolerance/severity/risk score, kết luận tuân thủ tiêu chuẩn, kết luận greenwashing, luật quản trị doanh nghiệp, suy ESG→lợi nhuận và mọi rule draft. `data/config/rules.json`, `data/config/rule_catalogue.json` và `profiles/oil_gas.json` giữ nguyên; pipeline chỉ nối ba rule đã duyệt.
