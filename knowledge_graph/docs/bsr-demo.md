# BSR 2025: ca review, kết quả và kịch bản demo

## Phạm vi và ranh giới

Đây là demo **một công ty BSR**, chưa phải MVP 3–5 công ty. Config `data/config/bsr_demo_config.json` chỉ chọn BSR, nhưng rule trong `kg/ready_rules.py` vẫn dùng Universal Core và `profiles/oil_gas.json`, không rẽ nhánh logic theo mã BSR. Extract cung cấp fact, locator và uncertainty. Graph chuẩn hóa, mapping, nối RDF, đánh giá rule và assessment. Thiếu evidence không phải contradiction; contradiction của rule cũng không tự động chứng minh tẩy xanh.

Bộ ca kỳ vọng có thể đọc bằng máy ở `data/config/bsr_demo_expected_cases.json`, được lập trước lần chạy BSR đầu tiên. Các kết quả ở `output/bsr_demo/demo_acceptance.json` là so sánh với bộ này; chúng không dùng output engine làm gold label. `evidence_acceptance=pending_human_adjudication`.

## Nguồn và phương pháp kiểm tra

- PDF chính thức: [trang báo cáo của BSR](https://bsr.com.vn/bao-cao), [bản PDF 2025](https://bsr.com.vn/c/document_library/get_file?download=true&groupId=37629&uuid=f9f89a31-e74d-7033-9a29-7429ff516c82). Bản lưu ở `data/source/pdf/BSR_2025_official.pdf`, 134 trang vật lý, SHA256 `bb2e79c06b0781fe0da4cc3842ae7caeec73e4441d2da412ab3a466cb162c433`.
- AI dùng PyMuPDF để trích text, render và **nhìn** trang vật lý 76, 98, 129; đối chiếu thêm trang 56, 99, 128, 130. Text của `data/source/page_text/BSR_2025.json` là bản 68 trang ghép; các số tương ứng hiện diện tại locator trang 29, 39, 50, 65. Chưa có hash PDF gốc của bản 68 trang để chứng minh hai file trùng byte hoặc toàn bộ nội dung.
- `data/review/bsr_demo_annotations.json` ghi reviewer `AI reviewer (AI-assisted review; no human adjudication)`, thời gian UTC, PDF hash, trang và cách kiểm tra. Bảy source review và bảy mapping review của ba ca E/S/G 2025 được áp dụng. Mapping E xác nhận nhãn Scope 1/2 cho từng biến thể, **không** chọn biến thể chuẩn hoặc tự tạo tổng. Hai context G được AI xác minh cho đúng phát biểu trang 98; ngày snapshot vẫn `null`. Context S/E vẫn pending.
- Lần chạy hiện tại: annotation audit có 20 applied, 11 pending, 0 rejected/file error. Bốn source review mới chỉ xác nhận giá trị/nhãn/mã GRI do BSR tự ghi cho chất thải; không duyệt context hoặc compliance. Gói review trình bày `field_reviews` và `frame_source` của AI; human pilot adjudication vẫn pending.
- BSR 2023–2024 hiện chỉ đọc JSON Extract và page text có sẵn; **chưa đối chiếu PDF** cho các ca đó. Sáu BCTC upload 2.3 mới chỉ được đọc JSON, **chưa ingest hoặc đối chiếu PDF**.

## Bảng ca 2025

Registry `data/review/bsr_2025_provenance.json` tách bốn định danh: PDF 68 trang do Extract khai báo nhưng thiếu binary/hash; artifact text 68 trang SHA256 `af1c9ade097922b78d000ed8e3ac233d4c01532859cfb76f0579ffb447a32d8a`; PDF chính thức 134 trang SHA256 `bb2e79c06b0781fe0da4cc3842ae7caeec73e4441d2da412ab3a466cb162c433`; và JSON Extract SHA256 `8bb394d56340604f09e3ca5b61de4616f83cc61cae913d97bd556b1a15dc0055`. Artifact text có hình học trang đôi. Crosswalk chọn lọc đã kiểm tra bằng hình học và cụm từ/số trên cả hai nguồn: 29→56–57, 39→76–77, 50→98–99, 51→100–101, 65→128–129, 66→130–131. Không có căn cứ xác nhận PDF 68 trang tương đương toàn bộ PDF 134 trang. `output/bsr_demo/source_provenance_audit.json` lưu kết quả xác minh; 11 evidence PDF mới ghi trang vật lý, hash, nguồn và Extract evidence gốc mà chúng hỗ trợ. Locator của một claim xử lý cuối bị lệch và được giữ thành issue riêng.

### Guard còn chặn theo evaluation hiện tại

| Case / record ID | Guard còn chặn | Bằng chứng đã đối chiếu và việc cần xác nhận |
|---|---|---|
| E: `CLM-0D01A0724720`, `CLM-E5998E76E480`, `CLM-F4910997AD2B` | `missing_role_record`, `missing_scope1_plus_scope2_total`, `period_unknown_or_unverified`, `reporting_boundary_unknown_or_unverified` | PDF vật lý 56/128/129 xác nhận hai số Scope 1 là 1.780.388 và 1.790.388, Scope 2 là 2.210 tCO2e. Dòng 1.792.598 trên trang 129 chỉ có nhãn “Lượng phát thải KNK”; cần nguồn định nghĩa rõ tổng Scope 1+2, kỳ/boundary, nguyên nhân hai biến thể, phương pháp và precision. Không chọn biến thể chỉ vì phép cộng khớp. |
| S: `CLM-08082F5B81CD`, `CLM-B7EB563E51B8` | `counting_method_unknown`, `graph_context_review_missing`, `metric_definition_unverified`, `period_type_unverified`, `reporting_boundary_unknown`, `reporting_boundary_unverified` | PDF vật lý 76 xác nhận hai hàng cùng nhóm bảng, cột 2025, đơn vị Người. AI đã kiểm tra và áp dụng riêng `comparison_frame_id` cùng `population_id` ở mức nhóm bảng; context tổng thể vẫn pending vì snapshot/annual method, phương pháp đếm và boundary chưa rõ. Chênh 27 người được ghi riêng ở `data/review/bsr_2025_s_gender_gap.issue.json`, không là guard KG-S-01. |
| G: `CLM-936FE665DA79`, `CLM-ECD3B116A03A` | Không còn guard chặn; evaluation ghi `subset_within_total`. | PDF vật lý 98 nêu cùng câu HĐQT BSR gồm 7 thành viên, **trong đó** 2 độc lập. Context AI gắn cùng `comparison_frame_id` đã kiểm tra PDF hash/trang/nguyên văn, cùng board và boundary. Ngày snapshot chính xác và danh sách sau thay đổi trang 99 vẫn unknown; không dùng kết quả ngoài phát biểu trang 98. |

`graph_context_review_missing` vẫn đúng cho S: workflow chỉ áp dụng hai trường được PDF chứng minh và giữ hàng context tổng thể `pending`. Audit ghi hai `partial_applied` để phân biệt với context G `verified`. `not_headcount` đã bỏ khỏi Universal Core: cùng phương pháp FTE cũng có thể so tập con, trong khi G không phải số lao động. Ngày cụ thể được thay bằng điều kiện **cùng ngày đã kiểm chứng hoặc cùng khung nguồn đã kiểm chứng**; ngày chưa biết vẫn là unknown. Gói bàn giao cho người adjudicate là `output/bsr_demo/review_packet.html` hoặc `.md`, kèm ảnh tám trang tại `review_pages/`.

### Phân loại guard S/G

Catalogue `data/config/rule_catalogue.json` có R06 (board subset) và R02 (male+female sum) thuộc bộ demo cũ; chúng không chạy trong assessment chính. `KG-G-01` và `KG-S-01` thực thi ở `kg/ready_rules.py`. R06 không nêu yêu cầu headcount/FTE; R02 là phép hòa giải khác, không được đưa thành guard của KG-S-01.

| Rule | Bắt buộc cho phép so | Hữu ích nhưng không bắt buộc | Guard áp sai đã sửa |
|---|---|---|---|
| KG-G-01 | Hai role đúng, số nguyên không âm, cùng HĐQT/quần thể, cùng khung thời gian, unit `person`, source/mapping/context review có căn cứ. `board_id`, boundary, định nghĩa role và cùng `comparison_frame_id` đã được câu trang 98 hỗ trợ. | Ngày snapshot cụ thể, danh sách sau các thay đổi, tiêu chí pháp lý thành viên độc lập; cần cho kết luận rộng hơn, không cần cho 2≤7 trong chính câu này. | `counting_method_unknown` và `not_headcount` tái dùng từ lao động; `measurement_date_unknown` coi ngày chính xác là bắt buộc dù cùng phát biểu đã được xác minh. |
| KG-S-01 | Hai role đúng, nữ là tập con của tổng trong cùng quần thể/boundary, cùng kỳ hoặc khung so sánh, cùng phương pháp đếm, unit `person`, review nguồn/mapping/context. | Ngày chốt chính xác nếu đã có khung so sánh được xác minh; giải thích chênh Nam+Nữ so với tổng thuộc issue riêng. | `not_headcount` buộc đúng headcount; phương pháp FTE đồng nhất cũng có thể so. `measurement_date_unknown` được thay bằng `comparison_frame_unknown` khi cả ngày và khung nguồn đều chưa xác minh. |

| Guard trước khi sửa | Phân loại | Rationale / xử lý |
|---|---|---|
| G `board_id_unknown` | Bắt buộc | Hai số phải thuộc cùng HĐQT; câu trang 98 định danh HĐQT BSR cho cả hai. |
| G `measurement_date_unknown` | Áp sai khi yêu cầu ngày chính xác | Cần cùng thời điểm/khung so sánh, được chứng minh bằng một phát biểu có “trong đó”; giữ ngày cụ thể unknown. Khác ngày đã biết vẫn chặn. |
| G `counting_method_unknown`, `not_headcount` | Áp sai từ guard nhân sự | Catalogue R06 chỉ so số thành viên; không có rationale đòi phương pháp headcount/FTE của lao động. |
| G `metric_definition_unverified`, `period_type_unverified`, `reporting_boundary_unknown`, `reporting_boundary_unverified` | Bắt buộc ở mức ngữ nghĩa cần cho cặp số | Câu trang 98 xác định vai trò tổng/tập con, năm 2025, board BSR và cùng boundary của phát biểu; không xác minh danh sách tại nhiệm sau thay đổi. |
| G `graph_context_review_missing` | Bắt buộc theo workflow | Hai context G được AI review với PDF hash, trang và nguyên văn; human pilot gate vẫn riêng. |
| S `population_id_unknown`, `reporting_boundary_unknown`, `reporting_boundary_unverified` | Bắt buộc | Đã xác nhận cùng nhóm bảng nhưng ranh giới pháp nhân/loại lao động chưa đủ, nên boundary vẫn chặn. |
| S `measurement_date_unknown` | Ngày chính xác là metadata hữu ích; cùng khung là bắt buộc | Hai hàng cùng bảng/cột 2025 đã được kiểm tra; `comparison_frame_id` được áp riêng. Không suy 31/12/2025. |
| S `counting_method_unknown`, `metric_definition_unverified`, `period_type_unverified` | Bắt buộc | Cần biết hai số cùng phương pháp và là cùng loại kỳ/snapshot; bảng chưa nói rõ. |
| S `not_headcount` | Áp sai | FTE đồng nhất cũng thỏa phép so tập con; chỉ còn yêu cầu cùng phương pháp được review. |
| S `graph_context_review_missing` | Bắt buộc theo workflow | Chỉ hai trường khung nguồn/quần thể nội bộ bảng được áp dụng một phần; context đầy đủ vẫn pending. |

Unit `person`, mapping từng role, provenance và giá trị số nguyên không âm là điều kiện bắt buộc chung. `Nam+Nữ=Tổng` thuộc R02/demo audit, không thuộc KG-S-01.

| Case / rule | Claim và evidence ID | Giá trị, kỳ, unit | Nguồn và trang | Đã xác minh / còn thiếu | Expected = actual |
|---|---|---|---|---|---|
| `BSR-2025-E-GHG` / `KG-E-01` | `CLM-0D01A0724720` / `EVD-88EB1729C78C`; `CLM-E5998E76E480` / `EVD-8ED19444DA56`; `CLM-F4910997AD2B` / `EVD-25131859C4E9` | Scope 1: 1.780.388 hoặc 1.790.388; Scope 2: 2.210 tCO2e; 2025, annual; boundary chưa rõ | `BSR_2025.pdf` trang Extract 29/65; PDF chính thức trang vật lý 56/128/129 | Giá trị hai biến thể có trên PDF. Nhãn 1.792.598 trên trang 129 là “Lượng phát thải KNK”, chưa định nghĩa rõ tổng Scope 1+2; chưa adjudicate biến thể, boundary, precision. | `Skipped` |
| `BSR-2025-S-WORKFORCE` / `KG-S-01` | `CLM-08082F5B81CD` / `EVD-E113234E5811`; `CLM-B7EB563E51B8` / `EVD-E3ECF6AD54E1` | Tổng 1.594, nữ 214 người; 2025; phương pháp/boundary chưa rõ | `BSR_2025.pdf` trang Extract 39/66; PDF chính thức trang vật lý 76/130 | Giá trị, đơn vị, cùng bảng và nhóm quần thể nội bộ bảng đã đối chiếu. Chưa rõ headcount/FTE hay trung bình/snapshot và boundary đầy đủ. | `NeedsReview` |
| `BSR-2025-G-BOARD` / `KG-G-01` | `CLM-936FE665DA79` / `EVD-D66F09A80222`; `CLM-ECD3B116A03A` / `EVD-1D7056BC28CC` | HĐQT 7, độc lập 2 người; 2025; ngày snapshot cụ thể chưa rõ | `BSR_2025.pdf` trang Extract 50/51/66; PDF chính thức trang vật lý 98/99 | Cùng câu trang 98 xác nhận cùng board, quan hệ tập con và cùng khung phát biểu. Trang 99 ghi thay đổi thành viên; không suy kết quả cho thời điểm khác. | `Supported` |

Mỗi claim trong bảng dùng cùng report ID `BSR:2025:ESG:unknown:BSR_2025_esg.json`. JSON pointer, nguồn Extract, nguyên văn đã review và trang PDF mở được từ `output/bsr_demo/index.html`. `KG-E-01` không có finding vì evaluation `Skipped` vẫn được log; không lấy tổng do Extract tự tính làm nguồn công bố.

## Kết quả chạy và giới hạn assessment

Lần build 11/10/2026: 30 claim BSR (2023: 8, 2024: 6, 2025: 16); 76 financial record từ adapter cũ, không tự coi là ESG claim; 9 evaluation ready rule gồm 6 `Skipped`, 2 `NeedsReview`, 1 `Supported` (G 2025). Ba finding chính: 2 `NeedsReview` (S 2025, G 2024) và 1 `Supported` (G 2025). Có 8 cross-year candidate `NeedsReview`, chưa có temporal finding. `Contradicted=0`, `InsufficientEvidence=0`; không gán risk score. Company assessment đếm 2 finding cho 2025 và 3 finding duy nhất cho 2023–2025. Không có finding thiếu evidence chain. Hai bộ SHACL `conforms=true` chỉ xác nhận các shape đã định nghĩa, không xác thực toàn bộ dữ kiện nguồn.

`demo_findings.json` chứa finding của bộ rule thử nghiệm cũ và chỉ dùng audit. Chúng không đi vào `findings.json`, RDF finding chính hay company assessment. Không có dữ liệu synthetic trong kết quả chính BSR.

## Kịch bản trình diễn 5–7 phút

1. **0:00–1:00** Chạy `run_bsr_demo.ps1 -Open`; mở dashboard, chỉ ra BSR là doanh nghiệp duy nhất, 30 claim và hai cấp kết quả. Mở `demo_acceptance.json` để thấy kỹ thuật pass và evidence còn pending.
2. **1:00–2:15** Mở ca E. Xem hai biến thể Scope 1, Scope 2, ba trang PDF và lý do `Skipped`; giải thích vì sao không tự chọn record đầu tiên hoặc coi số tổng quát là tổng được định nghĩa.
3. **2:15–3:30** Mở ca S, PDF trang 76 và finding `KG-S-01`. Xem 1.594/214, nguyên văn, evidence ID, JSON pointer, report ID; giải thích guard về khung kỳ, phương pháp đếm và quần thể. Mở issue chênh 27 riêng.
4. **3:30–4:45** Mở ca G, PDF trang 98/99. Chỉ ra “trong đó” chứng minh 2 thuộc 7 trong cùng phát biểu. `Supported` chỉ cho phép tập con này; ngày snapshot chưa biết và pilot vẫn chờ người adjudicate.
5. **4:45–5:45** Xem company summary và cross-year: 3 finding duy nhất, 8 liên kết có comparability pending, risk score rỗng. Mở `graph_demo.html` để xem RDF graph và evidence chain.
6. **5:45–6:30** Xem phần nguồn/giới hạn, annotation audit và `demo_findings.json` tách riêng. Kết luận demo kỹ thuật hoàn thành; chấp nhận evidence cần review của người.

## Issue còn lại theo owner

| Issue | Owner / hành động |
|---|---|
| Binary PDF 68 trang do Extract khai báo chưa tìm thấy; chỉ đối chiếu được sáu trang của artifact text 68 với PDF chính thức 134. | Extract/chủ nguồn cung cấp đúng binary, hash và version nếu cần xác nhận quan hệ giữa hai bản; Graph giữ hai source ID tách biệt. |
| Ca E: Scope 1 trên trang 56/128 là 1.780.388, trang 129 là 1.790.388; tổng 1.792.598 không ghi rõ định nghĩa Scope 1+2. | BSR/Extract làm rõ báo cáo, restatement và định nghĩa; Graph reviewer adjudicate role/variant/precision sau khi có bằng chứng. |
| Ca S: kỳ/snapshot, phương pháp đếm, quần thể và organizational boundary chưa đầy đủ. | BSR hoặc reviewer nguồn bổ sung; Graph reviewer chỉ duyệt context có căn cứ. |
| `ISSUE-BSR-S-2025-GENDER-GAP-27`: Nam+Nữ = 1.567, thấp hơn tổng 1.594 đúng 27 người; không là guard KG-S-01. | BSR/Extract source reviewer giải thích nhóm chưa phân loại, khác kỳ/cách đếm hoặc lỗi nguồn. Xem `data/review/bsr_2025_s_gender_gap.issue.json`. |
| Ca G: ngày snapshot và danh sách sau thay đổi chưa biết; không cần cho 2≤7 trong đúng phát biểu trang 98. | Người adjudicate xác nhận evidence/phiên bản PDF cho pilot; BSR cung cấp ngày/danh sách nếu muốn dùng kết quả ngoài khung phát biểu. |
| BSR 2024 G và các ca 2023–2024 chưa đối chiếu PDF. | Reviewer nguồn tìm đúng phiên bản PDF và tạo annotation. |
| Upload BCTC mới: 2024 riêng có `reports[0].reporting_year=2025` trong khi metadata kết thúc 2024; 2025 hợp nhất/riêng có lần lượt 689/820 `STATEMENT_SCOPE_CONFLICT`. | Extract sửa lỗi phân loại/metadata ở nguồn, giữ audit; Graph không suy scope từ tên file. |
| Sáu upload BCTC mới có `graph_ready=false`, `semantic_status=partial`, measurement `needs_review`; kỳ/unit/scale/value còn unknown. Ví dụ BCTC hợp nhất 2025 tạo tên “Ông Bùi Ngọc Dương” thành metric (`record_4600888700bf5ea0c8bd848b259990f917d065a24982f8a3539aa57817d4e923`); BCTC riêng 2025 gán “TÀI SẢN NGẮN HẠN” vào `note_table` (`record_cd7052df2b2e9621601ffda17c311baa855f61e1f4289b48bc7fcbb55fbfe90c`). | Extract cải thiện và reviewer kiểm tra nguồn; Graph chỉ viết adapter/preflight cho phần thực sự cần sau khi xác định overlap với 76 record cũ. |
| BCTC hợp nhất 2024 nêu 1.840 nhân viên tại 31/12/2024 (`record_6530ddcc4b4fb8299522597b652f1c9e81e447bbaaac67a22986cfae6cdf4a28`); BCTC hợp nhất 2025 nêu số so sánh cùng ngày là 1.891 (`record_d9092129af18c75c09f82c19b3b11c2ba0ca8c99207d83043c2d7f9ca98339b9`). | Extract/reviewer đối chiếu hai PDF, kiểm tra restatement và boundary. Graph chưa tạo inconsistency finding. |

Sáu upload mới có tổng 3.232 metric, 6.930 measurement candidate và 1.239 financial context theo `documents[].output.counts`. Chúng không được cộng vào 30 claim hoặc 76 financial record của demo. `kg/adapters.py` hiện không có adapter `esg-financial-candidates/2.3.0`; đường ingest hiện tại chỉ dùng các BCTC adapter cũ đã chọn trong config. Đây là quyết định phạm vi demo, không phải tuyên bố upload mới đã được kiểm chứng.
