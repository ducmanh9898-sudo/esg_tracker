"""Render the six-PDF BSR review queue from Extract, discovery and Graph output."""
from __future__ import annotations

import argparse
from decimal import Decimal
from html import escape
import json
import os
from pathlib import Path


def read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def display_number(value):
    if value is None:
        return "Chưa rõ"
    number = Decimal(str(value))
    return f"{number:,.0f}".replace(",", ".") if number == number.to_integral() else str(number)


def source_links(manifest: Path, run_dir: Path):
    result = {}
    for row in read(manifest)["files"]:
        pdf = (manifest.parent / row["pdf_path"]).resolve()
        if pdf.is_file():
            result[pdf.name] = Path(os.path.relpath(pdf, run_dir)).as_posix()
    return result


def source(record, links):
    evidence = (record.get("evidence") or [{}])[0]
    filename = evidence.get("source_file", "")
    page = evidence.get("physical_page")
    alternate_page = {76: 39, 106: 54}.get(page) if filename == "BSR_2025_official.pdf" else None
    return {
        "report_type": "BCTC" if record.get("report_type") == "Financial" else record.get("report_type"),
        "report_year": record.get("report_year"),
        "observation_year": record.get("observation_year"),
        "file": filename,
        "page": page,
        "alternate_page": alternate_page,
        "pdf": (links[filename] + (f"#page={page}" if page else "")) if filename in links else None,
        "value": record.get("value"),
        "unit": record.get("unit"),
        "label": record.get("label"),
        "quote": evidence.get("exact_quote") or evidence.get("context_text") or "",
        "context": evidence.get("context_text") or "",
    }


def source_from_audit(record, value, links):
    filename = record["source_file"]
    page = record["pdf_page"]
    return {
        "report_type": record["report_type"], "report_year": record["report_year"],
        "observation_year": record["observation_year"], "file": filename, "page": page,
        "alternate_page": record.get("alternate_68page_pdf_page"),
        "pdf": links.get(filename, "") + f"#page={page}" if filename in links else None,
        "value": value, "unit": record.get("unit"), "label": record.get("label"),
        "quote": record.get("quote", ""), "context": record.get("context", ""),
    }


def build_cases(run_dir: Path, manifest: Path):
    links = source_links(manifest, run_dir)
    discovery = read(run_dir / "discovery/findings.json")
    graph = {row["comparison_id"]: row for row in read(run_dir / "graph/findings.json")}
    cases = []
    for row in discovery:
        finding = graph.get(row["comparison_id"])
        if finding is None:
            raise ValueError("Graph finding missing: " + row["comparison_id"])
        if finding["status"] != "NeedsReview":
            continue
        sources = [source(item, links) for item in row["evidence"]]
        types = {item["report_type"] for item in sources}
        if types != {"ESG", "BCTC"}:
            continue
        labor = row.get("match_basis") == ["family:employees"]
        category = "S" if labor else "X"
        esg_label = next(item["label"] or "" for item in sources if item["report_type"] == "ESG")
        title = "Số lao động" if labor else ("Lợi nhuận trước thuế" if "trước thuế" in esg_label.lower()
                                            else "Lợi nhuận sau thuế")
        observation_years = {item["observation_year"] for item in sources if item["observation_year"]}
        year = next(iter(observation_years)) if len(observation_years) == 1 else None
        priority = "Cao" if labor and year == 2025 else "Cao" if row["comparison_id"] == "CMP-abdd45c67dd9e0394243" else "Trung bình"
        cases.append({
            "id": row["comparison_id"], "kind": "ESG ↔ BCTC", "category": category,
            "title": title,
            "year": year, "priority": priority, "status": finding["status"],
            "sources": sources,
            "delta": str(abs(Decimal(str(row["numeric_diagnostic"]["delta"]))))
            if row.get("numeric_diagnostic", {}).get("delta") is not None else None,
            "unit": row.get("numeric_diagnostic", {}).get("unit"),
            "reasons": finding.get("reasons", []),
            "question": ("Hai báo cáo có cùng phạm vi nhân sự, ngày đo và cách tính không?"
                         if labor else "Có cùng định nghĩa, phạm vi hợp nhất, năm đo và quy tắc làm tròn không?"),
            "graph_finding_id": finding.get("finding_id"),
        })

    for series in read(run_dir / "temporal/series.json"):
        for audit in series.get("comparative_note_audit", []):
            if audit.get("screening_result") != "different_source_text_values":
                continue
            sources = [source_from_audit(audit["earlier_report"], audit["earlier_report_current_value"], links),
                       source_from_audit(audit["later_report"], audit["later_report_comparative_value"], links)]
            cases.append({
                "id": f"BCTC-COMPARATIVE-{audit['observation_year']}", "kind": "BCTC ↔ BCTC",
                "category": "S", "title": "Số lao động năm trước được ghi lại khác nhau",
                "year": audit["observation_year"], "priority": "Cao", "status": audit["status"],
                "sources": sources, "delta": audit["delta"], "unit": audit["earlier_report"].get("unit"),
                "reasons": ["comparative_source_text_difference", "restatement_not_reviewed"],
                "question": "Số so sánh năm trước đã được điều chỉnh lại hay hai câu dùng phạm vi nhân sự khác nhau?",
                "graph_finding_id": None,
                "note": "Số ở báo cáo sau được đọc từ câu thuyết minh; chưa là bản ghi số độc lập trong Graph.",
            })

    records = read(run_dir / "graph/normalized_records.json")
    budget = [record for record in records if record.get("report_type") == "ESG"
              and record.get("value") in (17419900000000, 17389000000000)
              and "ngân sách" in (record.get("label") or "").lower()]
    if len(budget) == 2 and {row["report_year"] for row in budget} == {2023, 2024}:
        budget.sort(key=lambda row: row["report_year"])
        cases.append({
            "id": "ESG-BUDGET-2023-VS-2024", "kind": "ESG ↔ ESG", "category": "X",
            "title": "Nộp ngân sách nhà nước cho năm 2023?", "year": 2023,
            "priority": "Trung bình", "status": "NeedsReview",
            "sources": [source(item, links) for item in budget],
            "delta": str(abs(Decimal(str(budget[0]["value"])) - Decimal(str(budget[1]["value"])))),
            "unit": "VND", "reasons": ["earlier_report_observation_year_unknown", "restatement_not_reviewed"],
            "question": "Số trong ESG 2023 có thật sự là số đo năm 2023 và có cùng định nghĩa với ESG 2024 không?",
            "graph_finding_id": None,
            "note": "Đối chiếu bổ sung từ bản ghi Extract; chưa phải cặp đã được Graph tạo finding.",
        })
    cases.sort(key=lambda case: (case["priority"] != "Cao", case["kind"] != "ESG ↔ BCTC", case["id"]))
    return cases


REASON_LABELS = {
    "measurement_date_mismatch": "Ngày đo có thể khác nhau",
    "metric_definition_not_equivalent": "Định nghĩa chỉ tiêu chưa tương đương",
    "metric_id_not_equivalent": "Mã chỉ tiêu chưa tương đương",
    "reporting_boundary_unknown": "Phạm vi báo cáo chưa rõ",
    "scope_unknown": "Phạm vi chưa rõ",
    "population_unknown": "Nhóm đối tượng chưa rõ",
    "restatement_not_reviewed": "Chưa kiểm tra số liệu điều chỉnh lại",
    "observation_interval_unknown": "Khoảng thời gian đo chưa rõ",
    "source_version_audit_basis_unreviewed": "Chưa duyệt phiên bản nguồn và cơ sở kiểm toán",
    "earlier_report_observation_year_unknown": "Chưa xác nhận năm đo trong báo cáo trước",
    "comparative_source_text_difference": "Cùng năm đo nhưng câu nguồn ghi hai giá trị khác nhau",
    "rounding_tolerance_unreviewed": "Chưa duyệt ngưỡng làm tròn",
    "counting_method_unknown": "Cách đếm chưa rõ",
    "consolidation_unknown": "Phạm vi hợp nhất chưa rõ",
}


def e(value):
    return escape(str(value if value is not None else ""), quote=True)


def render_case(case):
    sources = case["sources"]
    source_cards = []
    for item in sources:
        link = (f'<a href="{e(item["pdf"])}" target="_blank" rel="noopener">Mở PDF trang {e(item["page"])} ↗</a>'
                if item["pdf"] else "Không có đường dẫn PDF")
        year = f"báo cáo {item['report_year']}, số đo {item['observation_year'] or 'chưa rõ'}"
        page_label = f" · bản 68 trang: trang {item['alternate_page']}" if item.get("alternate_page") else ""
        source_cards.append(f'<div class="source"><div class="source-top"><strong>{e(item["report_type"])} · {e(year)}</strong><span>{e(item["file"])} · trang PDF {e(item["page"])}{e(page_label)}</span></div>'
                            f'<div class="value">{e(display_number(item["value"]))} <small>{e(item["unit"] or "")}</small></div>'
                            f'<div class="label">{e(item["label"] or "")}</div><blockquote>{e(item["quote"])}</blockquote>{link}</div>')
    reasons = [REASON_LABELS[reason] for reason in case["reasons"] if reason in REASON_LABELS]
    if not reasons:
        reasons = ["Cần xác nhận ngữ cảnh và nguồn trước khi kết luận"]
    pills = "".join(f"<li>{e(reason)}</li>" for reason in dict.fromkeys(reasons))
    detail = (f'<section class="detail" id="{e(case["id"])}"><div class="detail-head"><span class="eyebrow">{e(case["kind"])} · năm đo {e(case["year"] or "chưa rõ")}</span>'
              f'<h2>{e(case["title"])}</h2><span class="status">{e(case["status"])}</span></div>'
              f'<div class="flow"><div>NGUỒN 1</div><b>→</b><div>ĐỐI CHIẾU</div><b>→</b><div>NGUỒN 2</div><b>→</b><div>{e(case["status"])}</div></div>'
              f'<div class="source-grid">{"".join(source_cards)}</div>'
              f'<div class="decision"><div><b>Chênh lệch quan sát</b><strong>{e(display_number(case["delta"]))} {e(case["unit"] or "")}</strong></div>'
              f'<div><b>Câu hỏi cần duyệt</b><p>{e(case["question"])}</p></div></div>'
              f'<h3>Vì sao cần review?</h3><ul class="reasons">{pills}</ul>'
              f'<p class="note">{e(case.get("note") or "Trạng thái lấy từ Graph; chênh lệch số chưa chứng minh mâu thuẫn.")}</p>'
              f'<p class="id">Mã: {e(case["id"])}{(" · Graph: " + e(case["graph_finding_id"])) if case["graph_finding_id"] else ""}</p></section>')
    search_text = " ".join([case["title"], *(item["file"] for item in sources)])
    line = (f'<button class="case-row" data-kind="{e(case["kind"])}" data-category="{e(case["category"])}" data-search="{e(search_text)}" data-target="{e(case["id"])}">'
            f'<span class="priority {"high" if case["priority"] == "Cao" else "medium"}">{e(case["priority"])}</span>'
            f'<span><strong>{e(case["title"])}</strong><small>{e(case["kind"])} · năm đo {e(case["year"] or "chưa rõ")}</small></span>'
            f'<span class="gap">{e(display_number(case["delta"]))} {e(case["unit"] or "")}</span><span class="row-status">{e(case["status"])}</span></button>')
    return line, detail


HTML = """<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BSR 2023–2025 · Hàng chờ review</title>
<style>
:root{font-family:Inter,system-ui,Segoe UI,Arial,sans-serif;color:#e8eef6;background:#0b1220;font-synthesis:none}*{box-sizing:border-box}body{margin:0}a{color:#7dd3fc}header{padding:34px max(24px,calc((100vw - 1440px)/2));background:linear-gradient(115deg,#152d42,#0b1220 70%);border-bottom:1px solid #27384d}h1{font-size:clamp(26px,3vw,42px);margin:8px 0}.eyebrow{text-transform:uppercase;letter-spacing:.14em;font-size:11px;color:#7dd3fc;font-weight:700}.intro{color:#bdcbd9;max-width:850px;line-height:1.6}.metrics{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px}.metric{border:1px solid #395064;background:#172638;border-radius:12px;padding:11px 16px;min-width:140px}.metric b{display:block;font-size:24px}.metric span{color:#aec0cf;font-size:12px}main{max-width:1440px;margin:0 auto;padding:24px;display:grid;grid-template-columns:minmax(310px,440px) minmax(0,1fr);gap:24px}.queue,.detail{background:#121e2d;border:1px solid #2d4053;border-radius:16px}.queue{align-self:start;position:sticky;top:16px;max-height:calc(100vh - 32px);display:flex;flex-direction:column}.queue-head{padding:20px;border-bottom:1px solid #2d4053}h2{margin:8px 0 12px}input,select{color:#e8eef6;background:#0b1624;border:1px solid #3a5166;padding:10px;border-radius:8px;width:100%;font:inherit}.filters{display:flex;gap:8px;margin-top:8px}.case-list{overflow:auto}.case-row{width:100%;display:grid;grid-template-columns:74px 1fr;gap:7px 10px;text-align:left;padding:15px 19px;color:inherit;background:transparent;border:0;border-bottom:1px solid #26394c;cursor:pointer;font:inherit}.case-row:hover,.case-row.active{background:#1b3448}.case-row small{display:block;color:#a5b8c7;margin-top:4px}.priority{font-size:11px;font-weight:700;border-radius:20px;padding:4px 8px;align-self:start;text-align:center}.high{background:#6b2d32;color:#ffe2db}.medium{background:#4d4226;color:#fff0ba}.gap{grid-column:2;color:#e7eff8;font-weight:700}.row-status{grid-column:2;color:#fbbf24;font-size:12px}.details{min-width:0}.detail{display:none;padding:24px}.detail.active{display:block}.detail-head{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.detail-head .eyebrow{width:100%}.detail-head h2{margin:0;flex:1}.status{background:#5c4219;color:#ffe3a5;padding:6px 10px;border-radius:20px;font-size:12px}.flow{display:flex;align-items:center;gap:7px;flex-wrap:wrap;margin:22px 0;color:#88abc1;font-size:11px}.flow div{border:1px solid #3c566c;border-radius:8px;padding:8px;background:#182c3f}.flow b{color:#64c3eb}.source-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.source{background:#0e1926;border:1px solid #30485d;border-radius:12px;padding:16px;min-width:0}.source-top{display:flex;flex-direction:column;gap:5px}.source-top span{font-size:12px;color:#aebdca;overflow-wrap:anywhere}.value{font-size:26px;font-weight:750;margin-top:13px;color:#f8fbff;overflow-wrap:anywhere}.value small{font-size:14px;color:#a8c5d7}.label{color:#b1c8d7;font-size:13px;margin:4px 0}.source blockquote{margin:15px 0;padding:11px;border-left:3px solid #55b6d8;background:#152638;line-height:1.5;color:#d8e6f0;font-size:13px;white-space:pre-wrap;overflow-wrap:anywhere}.source a{font-size:13px}.decision{display:grid;grid-template-columns:220px 1fr;gap:12px;margin:16px 0}.decision>div{padding:15px;background:#1d3042;border-radius:10px}.decision b{display:block;color:#b4c6d4;font-size:12px}.decision strong{display:block;margin-top:7px;font-size:20px}.decision p{margin:7px 0 0;line-height:1.5}h3{font-size:16px;margin-top:22px}.reasons{display:flex;gap:8px;flex-wrap:wrap;list-style:none;margin:0;padding:0}.reasons li{border:1px solid #4c5e67;border-radius:20px;padding:7px 10px;font-size:12px;color:#d0dce5}.note,.id{color:#aebecd;font-size:12px;line-height:1.5}.id{overflow-wrap:anywhere}.more{padding:18px 20px;border-top:1px solid #2d4053;color:#aebecd;font-size:12px;line-height:1.6}.more a{display:inline-block;margin-right:12px}@media(max-width:900px){main{display:block}.queue{position:static;max-height:400px;margin-bottom:16px}.source-grid,.decision{grid-template-columns:1fr}header{padding:24px}}
</style></head><body><header><div class="eyebrow">BSR · Extract → Knowledge Graph</div><h1>Thông số cần người review</h1><p class="intro">Các số dưới đây là ứng viên cần kiểm tra nguồn và ngữ cảnh. <b>NeedsReview</b> nghĩa là “cần người duyệt”; chênh lệch số chưa phải kết luận hai báo cáo mâu thuẫn. Trang này được tạo từ kết quả chạy 6 PDF ESG và BCTC hợp nhất của năm 2023–2025.</p><div class="metrics">__METRICS__</div></header><main><aside class="queue"><div class="queue-head"><h2>Hàng chờ review</h2><input id="search" type="search" placeholder="Tìm chỉ tiêu hoặc nguồn PDF"><div class="filters"><select id="kind"><option value="">Mọi loại so sánh</option><option>ESG ↔ BCTC</option><option>ESG ↔ ESG</option><option>BCTC ↔ BCTC</option></select><select id="category"><option value="">Mọi khía cạnh</option><option value="E">Môi trường (E)</option><option value="S">Xã hội (S)</option><option value="G">Quản trị (G)</option></select></div></div><div class="case-list">__ROWS__</div><div class="more">Xem dữ liệu đầy đủ: <a href="discovery/review.html">Cặp ESG–BCTC</a><a href="temporal/report.html">So sánh theo năm</a><a href="graph/report.html">Graph</a><br>Chưa có ứng viên trực tiếp thuộc E giữa ESG và BCTC trong lượt quét này; không đồng nghĩa BSR không công bố chỉ tiêu E.</div></aside><div class="details">__DETAILS__</div></main><script>
const rows=[...document.querySelectorAll('.case-row')],details=[...document.querySelectorAll('.detail')];function choose(row){rows.forEach(r=>r.classList.toggle('active',r===row));details.forEach(d=>d.classList.toggle('active',d.id===row.dataset.target));if(innerWidth<901)document.querySelector('.details').scrollIntoView({behavior:'smooth'});}rows.forEach(r=>r.addEventListener('click',()=>choose(r)));function filter(){const q=document.querySelector('#search').value.toLocaleLowerCase('vi'),k=document.querySelector('#kind').value,c=document.querySelector('#category').value;rows.forEach(r=>r.hidden=!!((q&&!r.dataset.search.toLocaleLowerCase('vi').includes(q))||(k&&r.dataset.kind!==k)||(c&&r.dataset.category!==c)));const active=rows.find(r=>r.classList.contains('active'));if(active?.hidden){const first=rows.find(r=>!r.hidden);if(first)choose(first);else details.forEach(d=>d.classList.remove('active'));}}document.querySelectorAll('#search,#kind,#category').forEach(el=>el.addEventListener('input',filter));if(rows.length)choose(rows[0]);
</script></body></html>"""


def render(run_dir: Path, manifest: Path):
    run_dir = run_dir.resolve()
    manifest = manifest.resolve()
    cases = build_cases(run_dir, manifest)
    rows, details = zip(*(render_case(case) for case in cases)) if cases else ([], [])
    graph_count = sum(case["graph_finding_id"] is not None for case in cases)
    temporal = read(run_dir / "temporal/summary.json")
    metrics = [(len(cases), "trường hợp hiển thị"), (graph_count, "cặp ESG ↔ BCTC trong Graph"),
               (len(cases)-graph_count, "đối chiếu bổ sung"), (temporal["comparisons"], "phép so sánh qua năm")]
    metric_html = "".join(f'<div class="metric"><b>{n}</b><span>{e(label)}</span></div>' for n, label in metrics)
    html = (HTML.replace("</style>", "[hidden]{display:none!important}</style>")
            .replace('<option value="G">Quản trị (G)</option>', '<option value="X">Tài chính trong ESG</option>')
            .replace("__METRICS__", metric_html).replace("__ROWS__", "".join(rows))
            .replace("__DETAILS__", "".join(details)))
    (run_dir / "index.html").write_text(html, encoding="utf-8")
    (run_dir / "review_cases.json").write_text(json.dumps({"schema_version": "bsr-review-dashboard-1.0", "cases": cases}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"cases": len(cases), "graph_cases": graph_count, "extra_cases": len(cases)-graph_count,
            "entry_page": str(run_dir / "index.html")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(render(args.run_dir, args.manifest), ensure_ascii=False))


if __name__ == "__main__":
    main()
