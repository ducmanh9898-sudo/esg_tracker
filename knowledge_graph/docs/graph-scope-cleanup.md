# Dọn repository về phạm vi Knowledge Graph — 2026-10-16

Đã rà entry points, import nội bộ, cấu hình dữ liệu, tham chiếu provenance và regression tests để xác định phần nào thuộc Graph, phần nào là thử nghiệm Extract. Đây là review phục vụ loại bỏ phụ thuộc/file dư; không phải chứng nhận mọi thuật toán đã hoàn thiện.

## Đã gỡ khỏi cây làm việc

**692 file**, tổng bytes trước nén **88.116.286**, được sao lưu và đối chiếu SHA-256 trước khi xóa. Bản ZIP lưu tại `.archive/graph_scope_cleanup_20261016/removed_files.zip` (78.781.655 bytes). Mục tiêu là giảm số file hoạt động; archive vẫn chiếm dung lượng để bảo toàn công việc chưa commit.

| Nhóm | Quyết định và lý do |
| --- | --- |
| `esg_extract/` — 14 file | Gỡ parser Docling, worker, fallback bảng, cloud/assisted extraction, tạo candidate/review pack và Extract CLI. Không thuộc nhiệm vụ Graph của người dùng. |
| `requirements-extract.*`, `README_EXTRACT_ESG.md`, hai config Extract | Gỡ dependency và hướng dẫn chạy pipeline Extract. `.venv` hiện có không bị gỡ package hàng loạt; cài mới phần Graph chỉ dùng requirements chính. |
| 444 file trong các review pack cũ | Gỡ v1–v9 và các pack thử `bsr_esg_extract_v2*`; giữ nguyên v10 và ghi chú Mạnh. Các phiên bản cũ có trong ZIP để đối chiếu/khôi phục. |
| 180 file trong `data/extract/jobs/` | Gỡ requests, fallback, parse thử và graph smoke/review outputs không còn được v10/runtime Graph tham chiếu. |
| `tests/test_esg_extract_v2.py` | Archive 12 test cho hệ thống Extract đã gỡ. Các kiểm tra đầu vào Graph cần thiết được giữ qua validator và test riêng. |
| `build_dataset.ps1`, `tools/rebuild_page_chunks.py` | Script dựng page/chunk không được Graph sử dụng; script đầu còn thiếu `pages_*.ps1`. |
| Ba tài liệu draft/tiến độ Extract | Gỡ hướng dẫn Extract không còn chạy được và bản draft bàn giao đã bị thay thế. |
| `__pycache__`, `.pyc` trong thư mục code/test | Gỡ cache Python sinh tự động; không cần lưu trong source tree. Một số cache vốn đã staged: chỉ xóa working copy, không thay index bằng git reset/clean. |

Danh sách chính xác từng path/hash và action nằm trong `.archive/graph_scope_cleanup_20261016/manifest.json`. Các mục `snapshot_before_edit` là bản sao file tích hợp vẫn còn trong repository, không tính vào 692 file bị xóa.

## Những phần giữ lại có lý do

- `kg/`: RDF, schema/provenance validation, adapter, constraint/assessment, review và pipeline. Chuyển `esg_extract.validation` thành `kg.extract_v2_validation`; `kg.source_identity` chỉ đọc PDF/hash, không download/parse/extract.
- `data/extract/esg/`, `data/extract/financial/`, manifest: **input JSON của Graph**, không phải chương trình Extract. Xóa chúng sẽ làm mất corpus đang demo.
- `data/source/`: PDF gốc, hash registry và page-text legacy dùng truy vết. Không coi text 68 trang là PDF canonical 134 trang.
- `data/review/bsr_esg_extract_pilot_review_v10/`, `review_pack_Manh_notes.md` và các Graph review annotations: công việc review của người dùng, không phải file tạm.
- Năm thư mục artifact parser được v10 tham chiếu: BSR 2024 `parse_native`, `parse_standard_p30_v1`; BSR 2025 `parse_native`, `parse_standard_extra_v1`, `parse_standard_tables_v2`. Giữ artifact để validator còn kiểm tra span/hash; không giữ code parser để chạy lại Extract.
- `handoff/`: contract độc lập, JSON mẫu và validator cho người làm Extract; Graph corporate adapter đang dùng contract này.
- `tools/`, `build_demo.py` và dashboard/script demo còn có consumer thực tế. Ví dụ `tools.bsr_pilot_dry_run`, `tools.bsr_handoff_impact` và regression tests còn gọi `build_demo`. Chưa xóa chỉ vì tên cũ hoặc số lượng file nhiều.
- `schemas/`, `profiles/`, `data/config/`, tài liệu Graph và test Graph: cần cho validation, boundary, rules và khả năng tái hiện demo.

## Kiểm chứng sau khi xóa

- Audit AST của **65 file Python còn hoạt động**: không có import nội bộ trỏ tới module đã mất. Audit lưu cùng archive; kiểm tra tĩnh này không thay thế runtime tests hoặc kiểm tra import động.
- `python -B -W ignore::DeprecationWarning -m kg.test_runner`: **157 tests, OK, exit 0**, hoàn tất 08:27:41 UTC ngày 2026-10-16. Test runner chạy trên bản sao và loại `.archive` khỏi bản sao.
- Trong số đó có **3 test nhận legacy v2** mới: xác minh toàn bộ **40 candidate v10**, chặn source hash sai và chặn partial khi chưa bật tùy chọn. 40 candidate vẫn pending/NeedsReview; test không đổi human review.
- Số test từ 166 xuống 157 là do gỡ 12 test Extract và thêm 3 test Graph, không phải bỏ test Graph đang lỗi để làm suite pass.
- `git diff --check`: exit 0, chỉ thông báo LF/CRLF ở các file đã có.

## Cách dùng sau dọn

1. Nhận JSON/PDF của bạn Extract: xem `docs/corporate-graph-runbook.md`, chạy `python -m kg.corporate_pipeline`.
2. Chạy corpus Graph hiện có: `python -m kg.pipeline`.
3. Mở demo BSR hiện có: `run_bsr_demo.ps1`.
4. Chạy regression bảo toàn output: `python -B -m kg.test_runner`.

Code `esg_extract` và lệnh Extract cũ không còn hoạt động. Nếu cần tra lại thử nghiệm, giải nén ZIP vào một thư mục mới theo `.archive/README.md`; không giải nén đè hàng loạt lên Graph hiện tại. Archive được `.gitignore` loại khỏi Git, nên cần tự giữ bản sao nếu chuyển máy. Chưa commit hoặc push.
