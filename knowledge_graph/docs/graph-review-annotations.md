# Annotation review cho KG-E-01, KG-S-01, KG-G-01

Graph lưu review tại `data/review/ready_rule_annotations.json`, độc lập với JSON Extract. `data/config/corpus_config.json` chọn file bằng `graph_review_annotations`; `data/config/ready_rule_aliases.json` vẫn là nơi duy nhất liệt kê alias/role. Annotation mapping tham chiếu `alias_id = rule_id|metric_id|role`, không khai báo thêm alias mới. Schema: `schemas/graph-review-annotations-v1.json`.

## Trường nào được rule dùng

| Field trong annotation / normalized claim | Rule dùng | Căn cứ người review cần ghi trong `review_basis` và `source_refs` |
| --- | --- | --- |
| `source_reviews.status`, `source_refs.evidence_id`, `source_file`, `source_pages` hoặc `json_pointer`, `original_text` | E/S/G | Đối chiếu claim với nguyên văn và vị trí trong báo cáo; ghi quote thật nếu Extract chưa có. `reviewed` chỉ xác nhận nguồn của **claim này**. |
| `mapping_reviews.alias_id`, `status` | E/S/G | Giải thích vì sao metric trong claim đúng vai trò canonical đã khai báo ở `ready_rule_aliases.json`; tên giống nhau chưa đủ. |
| `observation_year`, `period_type`, `reporting_boundary`, `unit`, `variant`, `metric_definition`, `scope` | E/S/G | Kỳ đo, loại kỳ, đơn vị, phiên bản số, định nghĩa và phạm vi của **từng claim** trong báo cáo. Context `verified` mới đặt các cờ `period_type_verified`, `reporting_boundary_verified`, `metric_definition_verified`. |
| `organizational_scope`, `emission_basis`, `scope2_method`, `calculation_method` | KG-E-01 | Cùng tổ chức/phạm vi, gross hay net, phương pháp Scope 2 và cách tính. Ghi vị trí nguồn của từng xác nhận. |
| `total_definition` (claim total) | KG-E-01 | Nguồn nói rõ total gồm Scope 1 + Scope 2; không suy từ hai thành phần. |
| `precision.mode`, `precision.step`, `precision.source_basis` | KG-E-01 | Nguồn xác nhận số exact hoặc quy tắc làm tròn half-up và bước làm tròn. Không suy precision từ số chữ số hiển thị. |
| `baseline_id` (nếu claim dùng baseline) | KG-E-01 | Baseline của các số được so; cần giống nhau. |
| `population_id`, `counting_method`, `measurement_date` | KG-S-01 | Cùng quần thể lao động, headcount và ngày chốt; không đổi share/FTE thành count. |
| `board_id`, `counting_method`, `measurement_date` | KG-G-01 | Cùng HĐQT, headcount và ngày chốt; hai board khác nhau không được ghép. |

`value`, `value_status`, `metric_id`, `claim_type`, `topic`, `dimension`, `report_id` và nguồn gốc Extract là input gốc, **không** phải trường để người review sửa trong annotation. Mỗi annotation có `annotation_id`, `company_id`, `report_id`, `record_id`, `extract_path`, SHA-256 `extract_sha256`, `status`, `reviewer`, `reviewed_at`, `review_basis` và `source_refs`. Các trường này xác định đối tượng, căn cứ và phát hiện review cũ; chúng không thay số liệu. `missing_fields` trong mẫu chỉ là checklist, không tạo finding.

## Cách điền và chạy

1. Mẫu hiện tại có **48 source review, 48 mapping review, 48 context review** từ 48 claim ID trong findings chính. Tất cả là `pending`; các giá trị đã có chỉ được sao chép từ normalized input. Người review phải mở JSON Extract và trang nguồn. Điền `source_refs.original_text` nếu đang null; giữ đúng `source_file`, trang/JSON Pointer, ID và đường dẫn. Nếu không có nguồn đủ tin cậy, giữ `pending`.
2. Với từng loại review, ghi tên người review, thời điểm ISO 8601 có múi giờ và `review_basis` nêu quote/trang/phương pháp. Chỉ sau khi kiểm tra, đổi source sang `reviewed`, mapping/context sang `verified`. Context là xác nhận **theo claim và rule**, không kế thừa từ mapping hoặc metadata báo cáo. `precision` và `total_definition` chỉ xác nhận khi nguồn nói rõ. Không điền `unknown` bằng suy đoán. Giữ `pending` khi `missing_fields` chưa được giải quyết; có thể chỉnh checklist sau khi xác minh.
3. Chạy `.venv\Scripts\python.exe -m kg.pipeline --output-dir output/kg_v2`. Pipeline kiểm schema, ID claim/report, alias hiện có, provenance và SHA-256 của **file JSON Extract hiện tại**. Annotation sai, thiếu căn cứ hoặc stale vào `annotation_audit.json` với lý do; batch vẫn tiếp tục. Nếu file Extract thay đổi, review lại nguồn và cập nhật fingerprint theo bản đã kiểm tra, không chỉ thay hash.
4. Kiểm `rule_evaluations.json` để thấy guard nào còn thiếu; `findings.json`, assessments và RDF chỉ phản ánh ba rule chính. `demo_findings.json` vẫn là đối soát demo riêng. `normalized_claims.json` giữ trạng thái Extract gốc; review đã áp dụng chỉ xuất hiện trong RDF và `annotation_audit.json`, không sửa JSON Extract.

Ví dụ tạo **mẫu mới** từ output hiện tại (không ghi đè file đã được người review điền):

```powershell
.venv\Scripts\python.exe -m kg.review_annotations --claims output/kg_v2/normalized_claims.json --findings output/kg_v2/findings.json --aliases data/config/ready_rule_aliases.json --output data/review/new_pending_template.json
```

Mẫu pending của corpus thật không chứng nhận claim BSR/PLX/PVD. Test `tests/test_graph_review_annotations.py` dùng nguồn **synthetic** để kiểm trường hợp verified, thiếu review, sai tham chiếu và fingerprint cũ.
