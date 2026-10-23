"""Render a concise AI review handoff with the exact official PDF pages."""
from __future__ import annotations

import html
from pathlib import Path

import fitz


PAGES = {
    "BSR-2025-E-GHG": [56, 128, 129],
    "BSR-2025-S-WORKFORCE": [76, 78, 130],
    "BSR-2025-G-BOARD": [98, 99],
}
QUESTIONS = {
    "BSR-2025-E-GHG": [
        "Bản ghi 1.780.388 và 1.790.388 Scope 1 là hai phương pháp, hai boundary hay một số đã sửa? Có công bố restatement/erratum không?",
        "Dòng 1.792.598 ‘Lượng phát thải KNK’ có được doanh nghiệp định nghĩa rõ là tổng Scope 1 + Scope 2 cùng boundary và kỳ đo không?",
        "Các số dùng gross/net, phương pháp Scope 2 nào và quy tắc làm tròn/precision nào?",
    ],
    "BSR-2025-S-WORKFORCE": [
        "1.594 tổng và 214 nữ là số tại ngày nào? Có phải headcount hay FTE/trung bình năm?",
        "Quần thể gồm những pháp nhân và loại lao động nào? Nữ và tổng có cùng quần thể không?",
        "Vì sao Nam 1.353 + Nữ 214 = 1.567, thấp hơn tổng 1.594 đúng 27 người?",
    ],
    "BSR-2025-G-BOARD": [
        "Xác nhận trên đúng bản PDF chính thức rằng câu trang 98 nêu 2 thành viên độc lập nằm trong tổng 7 thành viên cùng HĐQT BSR?",
        "Ngày snapshot và danh sách tại nhiệm sau các thay đổi năm 2025 là gì, nếu muốn dùng kết quả ngoài phạm vi phát biểu trang 98?",
        "Tiêu chí ‘độc lập’ được doanh nghiệp định nghĩa ở đâu nếu cần đánh giá quản trị riêng? KG-G-01 không kiểm tra tuân thủ pháp luật.",
    ],
}


def esc(value):
    return html.escape(str(value), quote=True)


def render_review_packet(output_dir, expected, evaluations, claims, provenance, annotations, pdf_path):
    output_dir = Path(output_dir)
    image_dir = output_dir / "review_pages"
    image_dir.mkdir(parents=True, exist_ok=True)
    page_numbers = sorted({page for pages in PAGES.values() for page in pages})
    pdf = fitz.open(pdf_path)
    try:
        for page in page_numbers:
            pdf[page - 1].get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False).save(
                image_dir / f"official_p{page}.png")
    finally:
        pdf.close()
    eval_index = {(row["report_year"], row["rule_id"]): row for row in evaluations}
    claim_index = {row["record_id"]: row for row in claims}
    official = {row["claim_id"]: row for row in provenance["attached_evidence"]}
    source_by_id = {row["source_id"]: row for row in provenance["sources"]}
    contexts = {row["record_id"]: row for row in annotations["context_reviews"]}
    markdown = [
        "# BSR 2025 — gói review evidence",
        "",
        "AI đã kiểm tra các đoạn và trang dưới đây. Đây là đề xuất có audit trail, không phải gold label hay adjudication của người.",
        "",
        "## Danh tính nguồn",
        "",
        "| Source ID | Trạng thái | SHA256 | Vai trò |",
        "|---|---|---|---|",
    ]
    for source in provenance["sources"]:
        markdown.append(f"| `{source['source_id']}` | {source['availability']} | `{source.get('sha256') or 'unknown'}` | {source['kind']} |")
    markdown += ["", "PDF 68 trang mà Extract khai báo chưa có binary. Artifact text 68 trang và PDF 134 trang có hash riêng; crosswalk chỉ xác minh nội dung chọn lọc. AI đã đối chiếu context G theo cùng phát biểu; ngày snapshot vẫn unknown và pilot chưa được người adjudicate.", "", "## Crosswalk trang", "", "| Trang text 68 | Trang PDF 134 | Chứng cứ | Giới hạn |", "|---:|---|---|---|"]
    for row in provenance["validated_page_crosswalk"]:
        original = next(x for x in provenance["page_crosswalk"] if x["archived_page"] == row["archived_page"])
        markdown.append(f"| {row['archived_page']} | {', '.join(map(str,row['official_page_pair']))} | {original['correspondence']} | {original['limit']} |")
    html_cases = []
    for case in expected["cases"]:
        case_id = case["case_id"]
        evaluation = eval_index[(2025, case["rule_id"])]
        markdown += ["", f"## {case_id} · {case['rule_id']} · {evaluation['outcome']}", "",
                    f"**Record IDs:** {', '.join('`'+x+'`' for x in case['claim_ids'])}.",
                    f"**Guard hiện còn:** {', '.join('`'+x+'`' for x in evaluation['reasons'])}.", "",
                    f"**Đã xác minh:** {case['verified']}", "",
                    f"**Chưa xác minh:** {case['missing']}", ""]
        if case["dimension"] == "E":
            arithmetic = "1.780.388 + 2.210 = 1.782.598; 1.790.388 + 2.210 = 1.792.598. Tổng 1.792.598 trên trang 129 có nhãn tổng quát, chưa đủ điều kiện KG-E-01."
        elif case["dimension"] == "S":
            arithmetic = "214 ≤ 1.594. Kiểm tra phụ: 1.353 + 214 = 1.567; chênh 27 so với tổng 1.594, chưa kết luận nguyên nhân."
            markdown += ["**Issue riêng:** `ISSUE-BSR-S-2025-GENDER-GAP-27` ở `data/review/bsr_2025_s_gender_gap.issue.json`; không phải guard KG-S-01.", ""]
        else:
            arithmetic = "2 ≤ 7. Cùng câu trang 98 nêu HĐQT BSR và ‘trong đó’ 2 độc lập; đây là cùng khung phát biểu dù ngày snapshot chính xác chưa biết. Trang 99 có thay đổi thành viên trong năm, không mở rộng kết quả sang mọi thời điểm."
        markdown += [f"**Phép kiểm tra:** {arithmetic}", "", "| Claim | Evidence Extract → PDF chính thức | Nguyên văn PDF đã chọn |", "|---|---|---|"]
        html_claims = []
        for claim_id in case["claim_ids"]:
            row = official[claim_id]
            claim = claim_index[claim_id]
            provenance_entry = next(x for x in provenance["official_evidence"] if x["evidence_id"] == row["evidence_id"])
            quote = provenance_entry["quote"]
            markdown.append(f"| `{claim_id}` ({claim['value']} {claim['unit']}) | `{row['corroborates_evidence_id']}` → `{row['evidence_id']}` · PDF p.{row['official_page']} | {quote} |")
            html_claims.append(f"<tr><td><code>{esc(claim_id)}</code><br>{esc(claim['value'])} {esc(claim['unit'])}</td><td><code>{esc(row['corroborates_evidence_id'])}</code> → <code>{esc(row['evidence_id'])}</code><br>p.{row['official_page']}</td><td>{esc(quote)}</td></tr>")
        markdown += ["", "**Review context theo từng trường của AI:**", "",
                    "| Claim | Trường | Mức hỗ trợ | Căn cứ và evidence |", "|---|---|---|---|"]
        html_field_rows = []
        for claim_id in case["claim_ids"]:
            context = contexts[claim_id]
            for field, review in context["field_reviews"].items():
                refs = ", ".join(review["source_evidence_ids"])
                markdown.append(f"| `{claim_id}` | `{field}` | `{review['status']}` | {review['basis']} ({refs}) |")
                html_field_rows.append(
                    f"<tr><td><code>{esc(claim_id)}</code></td><td><code>{esc(field)}</code></td>"
                    f"<td>{esc(review['status'])}</td><td>{esc(review['basis'])} "
                    f"<code>{esc(refs)}</code></td></tr>")
        markdown += ["", "**Câu hỏi cho reviewer:**", ""]
        markdown += [f"- {question}" for question in QUESTIONS[case_id]]
        markdown += ["", "**Ảnh trang nguồn:**"]
        markdown += [f"- [PDF trang vật lý {page}](review_pages/official_p{page}.png)" for page in PAGES[case_id]]
        context_statuses = {contexts[claim_id]["status"] for claim_id in case["claim_ids"]}
        markdown += ["", "**Context annotation:** " + ", ".join(sorted(context_statuses)) + ". Review bởi AI; human pilot adjudication vẫn pending. Trường `measurement_date` không được suy từ năm báo cáo."]
        pictures = "".join(f'<figure><a href="review_pages/official_p{page}.png"><img src="review_pages/official_p{page}.png" alt="BSR official PDF page {page}"></a><figcaption>PDF chính thức · trang vật lý {page}</figcaption></figure>' for page in PAGES[case_id])
        issue_link = '<p><a href="../../data/review/bsr_2025_s_gender_gap.issue.json">Issue riêng: chênh 27 người</a> — ngoài guard KG-S-01.</p>' if case["dimension"] == "S" else ""
        html_cases.append(f'<section><h2>{esc(case_id)} · {esc(case["rule_id"])} · {esc(evaluation["outcome"])}</h2><p><b>Guard:</b> {esc(", ".join(evaluation["reasons"]))}</p><p><b>Context annotation:</b> {esc(", ".join(sorted(context_statuses)))} (AI; human adjudication pending)</p><p><b>Đã kiểm tra:</b> {esc(case["verified"])}</p><p><b>Còn thiếu:</b> {esc(case["missing"])}</p><p><b>Phép kiểm tra:</b> {esc(arithmetic)}</p>{issue_link}<table><thead><tr><th>Claim</th><th>Evidence Extract → PDF</th><th>Nguyên văn chọn lọc</th></tr></thead><tbody>{"".join(html_claims)}</tbody></table><h3>Review từng trường của AI</h3><table><thead><tr><th>Claim</th><th>Trường</th><th>Mức hỗ trợ</th><th>Căn cứ và evidence</th></tr></thead><tbody>{"".join(html_field_rows)}</tbody></table><h3>Câu hỏi cho reviewer</h3><ol>{"".join("<li>"+esc(q)+"</li>" for q in QUESTIONS[case_id])}</ol><div class="pages">{pictures}</div></section>')
    markdown += ["", "## Quyết định và audit", "", "Reviewer con người cần ghi nhận chứng cứ, ngày/phiên bản báo cáo, quyết định cho từng trường còn pending. Không lấy output engine làm gold label. `tools/bsr_pilot_acceptance_gate.py` vẫn yêu cầu adjudication của reviewer có tên; gói này không thay đổi gate đó."]
    (output_dir / "review_packet.md").write_text("\n".join(markdown) + "\n", encoding="utf-8")
    source_rows = "".join(f"<tr><td><code>{esc(s['source_id'])}</code></td><td>{esc(s['availability'])}</td><td><code>{esc(s.get('sha256') or 'unknown')}</code></td><td>{esc(s['kind'])}</td></tr>" for s in provenance["sources"])
    crosswalk_rows = "".join(f"<tr><td>{m['archived_page']}</td><td>{', '.join(map(str,m['official_page_pair']))}</td><td>{esc(m['correspondence'])}</td><td>{esc(next(x['limit'] for x in provenance['page_crosswalk'] if x['archived_page']==m['archived_page']))}</td></tr>" for m in provenance["validated_page_crosswalk"])
    page = f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BSR 2025 · Evidence review packet</title><style>body{{font:15px/1.5 Segoe UI,Arial,sans-serif;max-width:1200px;margin:0 auto;padding:24px;color:#163244;background:#f5f8fa}}h1{{font-size:30px}}section{{background:white;border:1px solid #d8e5e9;border-radius:12px;padding:20px;margin:22px 0}}table{{border-collapse:collapse;width:100%;overflow:auto;display:block}}th,td{{padding:8px;border-bottom:1px solid #d8e5e9;text-align:left;vertical-align:top}}code{{word-break:break-all;font-size:12px}}.pages{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}}figure{{margin:0}}img{{width:100%;border:1px solid #d3e0e5}}figcaption{{font-size:12px;color:#607989}}.note{{border-left:4px solid #d89b31;padding:12px;background:#fff5e3}}</style></head><body><h1>BSR 2025 · Gói review evidence</h1><p class="note">AI kiểm tra đoạn/trang chọn lọc. PDF Extract 68 trang chưa có binary; không xác nhận hai bản PDF tương đương toàn bộ. Context G đã được AI review theo cùng phát biểu, nhưng ngày snapshot còn unknown; human pilot adjudication vẫn pending.</p><h2>Danh tính nguồn</h2><table><tr><th>Source ID</th><th>Trạng thái</th><th>SHA256</th><th>Loại</th></tr>{source_rows}</table><h2>Crosswalk trang chọn lọc</h2><table><tr><th>Text 68</th><th>PDF 134</th><th>Chứng cứ</th><th>Giới hạn</th></tr>{crosswalk_rows}</table>{''.join(html_cases)}<p class="note">Reviewer cần ghi quyết định có tên, nguồn, ngày và lý do. Gói này không phải gold label hay phê duyệt pilot.</p><p><a href="review_packet.md">Bản Markdown</a> · <a href="index.html">Quay về dashboard</a></p></body></html>'''
    (output_dir / "review_packet.html").write_text(page, encoding="utf-8")
    return {"page_images": [f"review_pages/official_p{n}.png" for n in page_numbers],
            "cases": len(expected["cases"]), "source_ids": sorted(source_by_id)}
