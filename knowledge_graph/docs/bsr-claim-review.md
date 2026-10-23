# Phạm vi đánh giá 30 claim BSR trong demo

`output/bsr_demo/claim_review.json` được tạo lại cùng pipeline BSR. Mỗi dòng nối theo `claim_id` tới kết quả rule, tham chiếu tiêu chuẩn, BCTC, ứng viên đối chiếu qua năm và tín hiệu điều tra sơ bộ. Đây là **30 claim đã chọn**, không phải toàn bộ công bố BSR 2023–2025.

RDF trong `output/bsr_demo/graph.ttl` cũng chứa 60 node `StandardCandidate` (một tham chiếu theo metric và một checkpoint IFRS S1 cho mỗi claim) và 6 node `FinancialComparisonCandidate`, với cạnh/guard tách khỏi 7 quan hệ tiêu chuẩn đã review. Các node ứng viên có `verificationStatus=unverified_candidate`; mọi liên kết BCTC hiện `comparable=false`. Chúng là đường truy vết, không phải finding.

## Cách đọc trạng thái

| Trạng thái | Nghĩa trong demo |
|---|---|
| `Supported` | Một phép kiểm tra cụ thể đủ guard và cho kết quả phù hợp. Không xác nhận toàn bộ claim hay tuân thủ tiêu chuẩn. |
| `NeedsReview` | Có cặp dữ liệu để kiểm tra nhưng context hoặc nguồn chưa đủ chắc để kết luận mạnh. |
| `Skipped` | Rule có nhận diện claim nhưng thiếu đầu vào hoặc điều kiện thiết yếu. |
| `NotEvaluated` | Chưa có rule đã review và cặp dữ liệu phù hợp. Không suy ra đúng, sai hoặc thiếu công bố. |

Kết quả hiện tại theo claim: 2 `Supported`, 4 `NeedsReview`, 5 `Skipped`, 19 `NotEvaluated`; không có `Contradicted`. Các tín hiệu từ `demo_findings.json` chỉ giúp chọn ca điều tra; chúng không đổi trạng thái claim và không đi vào assessment chính. Cặp 27 người ở S, hai biến thể Scope 1, và các chênh lệch chất thải đều còn cần đối chiếu ngữ nghĩa và nguồn.

## Tiêu chuẩn và BCTC

`data/config/standard_metric_candidates.json` gắn từng metric với một tham chiếu **ứng viên** hoặc bối cảnh. `standards_crosswalk_sample.json` có một số quan hệ đã xác minh; “quan hệ đã xác minh” chỉ nói phép liên hệ concept–reference là có cơ sở, không nói BSR đã đáp ứng toàn bộ disclosure. Các tài liệu gốc để kiểm tra là [GRI 2](https://www.globalreporting.org/publications/documents/english/gri-2-general-disclosures-2021/), [GRI 302](https://www.globalreporting.org/publications/documents/english/gri-302-energy-2016/), [GRI 303](https://www.globalreporting.org/publications/documents/english/gri-303-water-and-effluents-2018/), [GRI 305](https://www.globalreporting.org/publications/documents/english/gri-305-emissions-2016/), [GRI 306](https://www.globalreporting.org/publications/documents/english/gri-306-waste-2020/) và [GRI 405](https://www.globalreporting.org/publications/documents/english/gri-405-diversity-and-equal-opportunity-2016/). Cần review phiên bản, thời kỳ áp dụng và điều kiện cụ thể trước khi kết luận compliance.

PDF BSR 2025 trang vật lý 129 ghi rõ nhãn GRI 306-3 cho tổng chất thải/nguy hại/không nguy hại và GRI 306-4 cho tái chế. AI đã đối chiếu trực tiếp bốn giá trị thập phân cùng mã BSR tự ghi và lưu evidence riêng tại `data/review/bsr_2025_provenance.json`. Đây vẫn chỉ là xác nhận **Báo cáo BSR ghi mã đó**, chưa xác nhận thực hiện đầy đủ GRI 306. Chỉ tiêu chôn lấp/xử lý cuối nằm ở PDF chính thức trang 130, nhưng các trang 31/65 trong Extract không chứa giá trị; bản text lưu giá trị ở trang 66. Issue locator thuộc Extract được ghi tại `data/review/bsr_2025_waste_locator.issue.json` và chưa bị sửa âm thầm.

PDF BSR 2025 trang 130 gắn dòng “Tổng số lao động” với GRI 401-1. [GRI 401-1](https://www.globalreporting.org/publications/documents/english/gri-401-employment-2016/) nêu tuyển mới và thôi việc; GRI 2-7 nêu tổng lao động. `data/review/bsr_2025_workforce_gri_reference.issue.json` ghi câu hỏi reviewer về vai trò của mã GRI 401-1 ở dòng đó. Đây là ứng viên cần giải thích, không phải kết luận BSR dùng sai tiêu chuẩn.

[IFRS S1 §20–22](https://www.ifrs.org/content/dam/ifrs/publications/pdf-standards-issb/english/2023/issued/part-a/issb-2023-a-ifrs-s1-general-requirements-for-disclosure-of-sustainability-related-financial-information.pdf?bypass=on) là checkpoint về reporting entity và thông tin liên kết, không phải yêu cầu một số ESG phải bằng một dòng BCTC. Demo chưa xác minh reporting entity ESG tương ứng với BCTC, tác động tài chính hoặc việc BSR áp dụng IFRS S1, nên cả 30 dòng giữ `not_established`/`not_assessed` cho kênh này.

Adapter BCTC hiện có 76 record; graph sinh 6 liên kết ứng viên cho 2 claim tổng lao động. Không liên kết nào qua guard về ngày đo, định nghĩa và ranh giới. Các metric khác không có record BCTC cùng định nghĩa được nối; không suy ra doanh nghiệp không công bố hoặc có mâu thuẫn. JSON BCTC chỉ có locator Extract, chưa có đối chiếu PDF độc lập trong demo.

## Điều kiện còn thiếu để kết luận rộng hơn

- Review PDF, định nghĩa và phiên bản cho các claim 2023–2024 và những claim 2025 mới có locator Extract.
- Xác minh kỳ đo, quần thể, phương pháp và reporting boundary trước khi bật thêm phép so sánh.
- Đánh giá từng yêu cầu của GRI/IFRS S1 cùng tính áp dụng và thông tin hỗ trợ; mapping theo tên metric không đủ để xác nhận compliance.
- Xác minh PDF BCTC và comparability ESG–BCTC. Chênh lệch số giữa phạm vi khác nhau chỉ là tín hiệu cần tra cứu.

`technical_demo_pass=true` trong `demo_acceptance.json` kiểm tra tính tái lập và guard của demo. `claim_review_coverage.all_claims_conclusively_assessed=false`, `standards_compliance_assessed=false` và `evidence_acceptance=pending_human_adjudication` nêu giới hạn đánh giá thực tế.
