# Kiểm chứng lần triển khai 2026-10-20

Đây là log lịch sử discovery v3/profile v1. Sau khi phát hiện các cặp ghép
nhầm khoản trích quỹ và lợi nhuận thuộc cổ đông công ty mẹ, profile v2 và
discovery v5 được tạo riêng; xem `docs/cross-report-discovery-demo.md` để dùng
output hiện hành. Các số 76/19/57 bên dưới chỉ mô tả lần chạy v3.

## Sửa lỗi matching và kiểm chứng 2026-10-21

- Gốc lỗi: regex `loi nhuan sau thue` của profile v1 match cả cụm nằm trong
  “trích quỹ từ lợi nhuận sau thuế”; dòng “lợi nhuận của cổ đông công ty mẹ”
  cũng bị đưa vào nhóm lợi nhuận sau thuế hợp nhất. Scanner cũ còn cho phép
  tự ghép năm quan sát chưa biết theo năm báo cáo, và giữ cặp phạm vi riêng/hợp
  nhất dù đã biết khác nhau.
- `data/config/bsr_cross_report_discovery_v2.json` dùng mẫu ở đầu nhãn và
  `exclude_patterns`. `kg/cross_report_scan.py` tôn trọng exclusion, chỉ tự
  ghép khi cả hai năm quan sát rõ và bằng nhau, bỏ cặp có consolidation đã
  biết khác; cặp explicit vẫn tồn tại để review.
- Discovery v5 quét cùng manifest 8.673 record: **6 cặp**, gồm 4 pilot và 2
  cặp cùng chỉ tiêu từ năm báo cáo BCTC khác. Cả 14 ID do người dùng chỉ ra
  hiện diện trong v3 và **0 ID** còn trong v5. Tổng cộng 70 ứng viên v3 không
  còn ở v5. Bản v3/v4 vẫn được giữ nguyên để truy vết.
- `output/bsr_cross_report_discovery_graph_v3`: 6 comparison, 6 `NeedsReview`,
  `errors=[]`, SHACL đạt. Run `partial` do coverage dữ liệu, evaluation
  `pending_adjudication`; không tự kết luận doanh nghiệp ghi sai hoặc greenwashing.
- Regression: 41 test thuộc discovery, pilot, Graph và alignment đạt. Review
  template v5 pass preflight hình thức với 9 record event và 6 comparison event;
  các event còn pending, chưa phải human review.

## Baseline và thay đổi

Baseline: branch `main`, commit `4addbfb5060f8d099650736d24236afe25480d73`,
340 entry trong git status trước lượt này. Không commit/push, không gọi API trả phí.
Không sửa PDF, manifest hoặc raw Extract đã có; không tạo quyết định human/gold.

File bổ sung:

- `kg/cross_report_scan.py`: discovery/diagnostic/coverage/review pack.
- `tools/cross_report_triage.py`: nhập screening có kiểm tra digest và lịch sử.
- `data/config/bsr_cross_report_discovery_v1.json`: profile pilot.
- `tests/test_cross_report_scan.py`: kiểm thử discovery/triage.
- `docs/cross-report-discovery-demo.md`: cách chạy và review.
- Báo cáo kiểm chứng này.

Điều chỉnh cục bộ trên file hiện có:

- `kg/corporate_assessment.py`: guard source version/audit basis tùy config; chặn tolerance NaN/Infinity.
- `kg/corporate_pipeline.py`: truyền guard; template có trường source basis khi bật.
- `tools/cross_report_review.py`: chặn tolerance NaN/Infinity.
- `tests/test_corporate_graph.py`: test guard mới, giữ hành vi legacy khi không bật.

## Đã chạy

- 38 tests: `test_cross_report_scan`, `test_cross_report_pilot`,
  `test_corporate_graph`, `test_corporate_extract_alignment`: **OK**, lần cuối 46,761 giây.
- Discovery v3: 10 tài liệu, 8.673 records, 0 lỗi input cơ học, không thiếu report slot.
- 76 cặp / 67 records: 19 pending_context_review, 57 blocked_context_mismatch.
  Mismatch bao gồm cả kỳ/interval không đồng bộ; không được hiểu là doanh nghiệp mâu thuẫn.
- Diagnostic: 3 trong dung sai đề xuất, 1 ngoài dung sai, 72 chênh lệch chưa có dung sai.
  Chưa cặp nào được kết luận là mâu thuẫn đã xác nhận.
- Review template thật: valid, 67 record events, 76 comparison events, không lỗi ID/digest.
- Graph thật: `output/bsr_cross_report_discovery_graph_v1`, 8.673 records, 76 findings
  NeedsReview, SHACL conforms=true, errors=[], source-basis guard hiện diện ở đủ 76 findings.
- Graph dùng comparisons từ discovery v1; đã kiểm tra nội dung **bằng nhau hoàn toàn**
  với comparisons discovery v3. Các bản discovery trước được giữ để không ghi đè.
- Graph bắt đầu 08:00:09 UTC, kết thúc 08:11:23 UTC. 18 artifacts, 596.044.881 bytes.
  Trong lúc chạy có quan sát process khoảng 1,6 GB RAM; đây không phải phép đo peak chính thức.
- `git diff --check` trên bốn file có chỉnh sửa hiện hữu: không lỗi whitespace.

## Giới hạn đã xác nhận

Run status **partial** do coverage nguồn; không phải failed, cũng không phải corpus hoàn tất.
Evaluation **pending_adjudication**; không công bố precision/recall.
Chỉ 59 record ESG có normalized numeric value; ứng viên hiện tìm thấy thuộc nhóm lợi nhuận.
Không tuyên bố đã tìm hết mâu thuẫn trong PDF hoặc toàn bộ E/S/G.
Tên chỉ tiêu gần giống không chứng minh cùng định nghĩa; không áp dung sai cho nhóm từ khóa chung.
Một số record còn year_basis unknown dù có observation_year; Graph tiếp tục chặn.
Cặp 2023 có giả thuyết khác phiên bản Q4/audited, chưa xác minh quan hệ sao chép giữa báo cáo.
Ba xác nhận hội thoại cũ được giữ dưới dạng context, không tự điền identity/time hoặc nhận là gold.

File mở đầu tiên: `output/bsr_cross_report_discovery_v3/review.html`.
File screening: `output/bsr_cross_report_discovery_v3/triage_template.csv`.
