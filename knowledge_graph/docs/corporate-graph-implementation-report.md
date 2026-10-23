# Bàn giao tích hợp Graph cho corporate-extract-1.0

Ngày kiểm chứng: 2026-10-16. Branch `main`, HEAD `4addbfb5060f8d099650736d24236afe25480d73`. Repository đã có nhiều staged/unstaged/untracked trước lượt làm việc. Baseline git status và diff tracked trước thay đổi lưu tại `.tmp/corporate_graph_baseline/`. Không reset/clean/stash, commit/push hoặc sửa dữ liệu corpus/review lịch sử.

## Đã triển khai

- Adapter nhận format độc lập đã giao bên Extract, giữ dữ liệu original/normalized, nguồn, kỳ đo, header/cell/footnote, uncertainty và toàn bộ payload gốc.
- Kiểm tra manifest JSON/PDF hash, số trang PDF thật, source/evidence identity, locator, quote trong supplied context, liên kết năm/unit và quy đổi số không mơ hồ. Cấm ID record trùng toàn batch và evidence/source ID xung đột.
- Entry point mới dùng RDF core, claim/evidence mapping, source nodes và SHACL hiện có; BCTC có cả FinancialDisclosure type. Không tự nối batch mới vào corpus cũ.
- Candidate cùng kỳ giữa các report, gồm ESG–BCTC; rule sum_equals/subset trong cùng report và equal giữa hai observations. Rule template/aliases nằm trong config; alias chỉ đề xuất, cần review quan hệ.
- Chặn kết luận mạnh khi thiếu human record review hoặc comparison review; khác period, unit, entity/consolidation, scope/method/definition hoặc restatement chưa rõ. Tolerance phải do reviewer cung cấp với căn cứ.
- Review gắn content digest, snapshot theo run, phát hiện quyết định stale. Bốn lớp quote/value/association/context độc lập. Không tin trạng thái reviewed trong output Extract như quyết định của người dùng Graph.
- Run manifest, partial/errors/coverage, per-record audit, comparison findings, report HTML kèm PDF links, RDF và JSON, pending gold evaluation. Output atomic trong thư mục mới, ID deterministic và không ghi đè run cũ.

## Kiểm chứng đã chạy

1. `python -B -W ignore::DeprecationWarning -m kg.test_runner`: **165 tests, OK, process exit 0**; chạy trên bản sao tạm, hoàn tất lúc 2026-10-16 08:13:25 UTC. Bao gồm 14 test corporate ở thời điểm chạy.
2. Sau bổ sung test ambiguity và chỉnh thông báo quyết định not_comparable, `python -B -W ignore::DeprecationWarning -m unittest tests.test_corporate_graph -q`: **15 tests, OK**. Đây là tập con bổ sung, không cộng 15 vào 165 như số test độc lập.
3. Standalone handoff `test_validate.py`: **4 tests, OK**.
4. Chạy CLI thật với 9 PDF + 9 JSON development giả lập: **21 record, 57 candidate, 57 NeedsReview, 0 lỗi, SHACL conforms, evaluation pending_adjudication**. Output `.tmp/corporate_development_run03/`; input `.tmp/corporate_development_delivery/`. Các PDF có bytes/hash/text thật nhưng nội dung synthetic, không phải BSR và không phải output extraction được adjudicate.
5. `git diff --check`: exit 0; chỉ có thông báo LF/CRLF ở một số file đã có.

Test corporate bao gồm: JSON/PDF→RDF và provenance; rerun ổn định; cùng kỳ khác số/khớp số; year unknown; scope/unit/target khác; restatement; separate/consolidated; stale hoặc AI review; sai source hash/trang/quote/header năm/unit; duplicate cùng file và xuyên file; PDF hash thay đổi; parse/extraction error không tạo disclosure absence; output không ghi đè; sum arithmetic và mapping ambiguous; file review đầy đủ; gold gate; normalization sai scale; các lớp review độc lập.

Test strong findings dùng **SYNTHETIC TEST REVIEWER** trong fixture tạm, không điền tên hoặc thời điểm Mạnh duyệt dữ liệu thật. Test evaluation với nhãn synthetic chỉ kiểm tra phép tính và guard, không đo chất lượng BSR.

## File thay đổi của lượt này

File mới: `kg/corporate_adapter.py`, `kg/corporate_assessment.py`, `kg/corporate_pipeline.py`, `kg/corporate_fixture.py`, `tests/test_corporate_graph.py`, `data/config/corporate_bsr_demo.json`, `docs/corporate-graph-runbook.md`, báo cáo này.

File đã có được cập nhật: `README.md`, `docs/bsr-extract-handoff-2023-2025.md`, `requirements.txt`, `requirements.lock` (thêm pypdf 6.20.1, đã có trong .venv). Không đổi schema/ZIP gửi bên Extract.

## Còn chờ dữ liệu thật và người review

- Chưa có delivery mới của bên Extract; chưa chứng minh toàn bộ BSR 2023–2025 đi qua luồng mới.
- Người review xác nhận quote với PDF, header/năm/unit, định nghĩa, boundary/method, restatement, tolerance và cặp so sánh. Nguồn URL chính thức không được xác nhận chỉ bằng hash của file được giao.
- Narrative claim/policy/governance/target được lưu và truy vết; chưa tự suy luận ngữ nghĩa hoặc xác minh việc thực hiện chính sách. Phép kết luận mạnh hiện giới hạn vào quan hệ số học đã được review.
- Restatement thật giữ NeedsReview; chưa tự tính cầu nối điều chỉnh. Metric khác mã/tên/định nghĩa cần kiểm tra trước khi chuẩn hóa, không dùng fuzzy match tự động để tạo contradiction.
- Không có gold BSR adjudicated, không công bố precision/recall/accuracy thực tế. Tập candidate không dùng làm ground truth đầy đủ cho recall.
- Workflow local theo batch; rerun an toàn vào thư mục mới, không có checkpoint granular/distributed ingestion. Review file có lịch sử và content digest, không phải chữ ký xác thực danh tính.

Các giới hạn này không chặn tiếp nhận delivery hợp contract. Cách vận hành nằm trong `docs/corporate-graph-runbook.md`.
