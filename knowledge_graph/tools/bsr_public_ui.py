"""Reader-facing BSR knowledge graph view; source files remain outside the UI."""
from __future__ import annotations

import html
from collections import Counter
from decimal import Decimal
from pathlib import Path

from tools.bsr_graph_ui import GRAPH_SCRIPT, GRAPH_STYLE, graph_fragment
from tools.bsr_claim_catalog import CATALOG_SCRIPT, CATALOG_STYLE, claim_catalog


STATUS = {
    "Contradicted": ("Có số liệu không khớp", "Một phép kiểm tra đủ điều kiện cho kết quả mâu thuẫn; cần đọc lại nguồn trước khi diễn giải."),
    "NeedsReview": ("Cần kiểm tra thêm", "Có dữ liệu liên quan, nhưng bối cảnh chưa đủ chắc để kết luận."),
    "Supported": ("Phù hợp với phép kiểm tra", "Các số phù hợp với đúng phép kiểm tra được nêu; không đánh giá toàn bộ doanh nghiệp."),
    "Skipped": ("Chưa thể kiểm tra", "Thiếu đầu vào hoặc định nghĩa cần thiết cho phép kiểm tra."),
}

CASES = {
    "E": {"title": "Khí thải nhà kính", "rule": "KG-E-01", "question": "Tổng Scope 1 + Scope 2 có khớp với hai thành phần?",
          "why": "Báo cáo nêu nhiều biến thể Scope 1 nhưng chưa định nghĩa rõ một tổng Scope 1 + Scope 2 để so sánh. Không thể coi đây là mâu thuẫn số học.",
          "section": "Phụ lục 5 · Bảng chi tiết các chỉ số bền vững (E-S-G)",
          "table": "Nhóm Phát thải · dòng Scope 1 và Scope 2", "pages": "128–129 (xem thêm trang 56)",
          "next": "Xác định chỉ tiêu nào được nguồn định nghĩa là tổng Scope 1 + Scope 2, sau đó làm rõ biến thể Scope 1 và ranh giới tính."},
    "S": {"title": "Lao động nữ và tổng lao động", "rule": "KG-S-01", "question": "Lao động nữ có nằm trong tổng lao động cùng quần thể?",
          "why": "Hai số nằm trong cùng bảng năm 2025; phương pháp đếm, kỳ đo và ranh giới tổ chức chưa được xác minh đầy đủ.",
          "section": "Phát triển nguồn nhân lực", "table": "Quy mô lao động và ổn định nhân sự · cột 2025", "pages": "76 (đối chiếu thêm phụ lục trang 130)",
          "next": "Xác nhận phương pháp đếm, kỳ báo cáo và ranh giới lao động. Chênh lệch 27 người giữa nam + nữ và tổng là issue riêng, không phải guard của phép kiểm tra này."},
    "G": {"title": "Thành viên HĐQT độc lập", "rule": "KG-G-01", "question": "Số thành viên độc lập có vượt tổng thành viên cùng HĐQT?",
          "why": "Cùng một câu cho biết HĐQT BSR có 7 thành viên, trong đó 2 độc lập. Phép kiểm tra 2 ≤ 7 được hỗ trợ cho chính phát biểu đó.",
          "section": "Cơ cấu quản trị doanh nghiệp · Hội đồng quản trị", "table": "Đoạn mô tả cơ cấu HĐQT", "pages": "98 (thay đổi thành viên: trang 99)",
          "next": "Ngày chốt chính xác và danh sách tại nhiệm chưa rõ; người review cần adjudicate nếu dùng cho pilot."},
}

GUARDS = {
    "missing_role_record": "thiếu chỉ tiêu cần so",
    "missing_scope1_plus_scope2_total": "chưa có tổng được định nghĩa rõ là Scope 1 + Scope 2",
    "period_unknown_or_unverified": "kỳ đo chưa xác minh",
    "reporting_boundary_unknown_or_unverified": "ranh giới báo cáo chưa xác minh",
    "counting_method_unknown": "phương pháp đếm chưa rõ",
    "graph_context_review_missing": "bối cảnh so sánh chưa được duyệt đầy đủ",
    "metric_definition_unverified": "định nghĩa chỉ tiêu chưa xác minh",
    "period_type_unverified": "loại kỳ đo chưa xác minh",
    "reporting_boundary_unknown": "ranh giới tổ chức chưa rõ",
    "reporting_boundary_unverified": "ranh giới tổ chức chưa xác minh",
    "subset_within_total": "giá trị tập con không vượt tổng",
}

FINANCIAL_GUARDS = {
    "boundary_unverified": "ranh giới lao động trong báo cáo ESG chưa được xác minh tương đồng với phạm vi BCTC hợp nhất",
    "measurement_date_unverified": "ngày chốt của chỉ tiêu ESG chưa được xác minh",
    "measurement_period_mismatch": "kỳ đo khác nhau",
    "metric_definition_unverified": "định nghĩa lao động giữa hai báo cáo chưa được xác minh là giống nhau",
}


def h(value):
    return html.escape(str(value if value is not None else "Chưa rõ"), quote=True)


def number(value):
    if isinstance(value, (Decimal, float, int)):
        return format(Decimal(str(value)), ",f").replace(",", "#").replace(".", ",").replace("#", ".")
    return str(value)


def render_public_ui(output_dir: Path, data: dict, acceptance: dict) -> None:
    """Render a static, accessible exploration view using only verified public locators."""
    output_dir = Path(output_dir)
    claims = {row["record_id"]: row for row in data["normalized_claims"]}
    nodes = {row.get("evidenceId"): row for row in data["graph"]["nodes"] if row.get("evidenceId")}
    official = {row["claim_id"]: row for row in data["source_provenance_audit"]["attached_evidence"]}
    evals = {(row["report_year"], row["rule_id"]): row for row in data["rule_evaluations"]}
    year = next(row for row in data["company_assessments"]["company_year_assessments"] if row["report_years"] == [2025])
    counts = Counter(row["outcome"] for row in data["rule_evaluations"] if row["report_year"] == 2025)
    case_cards = []
    case_details = []

    for dimension, meta in CASES.items():
        case = next(row for row in data["expected"]["cases"] if row["dimension"] == dimension)
        evaluation = evals[(2025, meta["rule"])]
        outcome = evaluation["outcome"]
        label, interpretation = STATUS[outcome]
        search_text = " ".join([dimension, meta["title"], meta["question"], meta["section"],
                                meta["table"], meta["pages"], "BSR_2025_official.pdf"]
                               + [str(claims[claim_id].get("label") or "") for claim_id in case["claim_ids"]])
        case_cards.append(f'''<a class="topic-card {h(outcome)}" href="#case-{dimension}" data-search="{h(search_text)}">
          <span class="topic-letter">{dimension}</span><span class="topic-body"><strong>{h(meta['title'])}</strong><small>{h(meta['question'])}</small></span>
          <span class="status {h(outcome)}">{h(label)}</span></a>''')

        value_nodes = []
        source_rows = []
        for claim_id in case["claim_ids"]:
            claim = claims[claim_id]
            supplement = official.get(claim_id)
            source_node = nodes.get(supplement["evidence_id"], {}) if supplement else {}
            value_nodes.append(f'''<div class="graph-node value-node"><span class="eyebrow">Chỉ tiêu</span>
                <strong>{h(claim.get('label') or claim.get('metric_id'))}</strong>
                <b>{h(number(claim['value']))} {h('người' if claim['unit'] == 'person' else claim['unit'])}</b></div>''')
            if supplement:
                source_rows.append(f'''<li><b>{h(claim.get('label') or claim.get('metric_id'))}: {h(number(claim['value']))}</b>
                  <span class="quote">“{h(source_node.get('originalText') or 'Chưa có nguyên văn')}”</span>
                  <small>Trang PDF vật lý {h(supplement['official_page'])} · Đối chiếu bởi AI trong phạm vi {h(supplement['review_scope'])}.</small></li>''')
        guards = ", ".join(GUARDS.get(reason, reason.replace("_", " ")) for reason in evaluation.get("reasons", []))
        calculation = evaluation.get("calculation") or {}
        if "subset_count" in calculation and "total_count" in calculation:
            comparison = f"{number(Decimal(calculation['subset_count']))} ≤ {number(Decimal(calculation['total_count']))}"
        elif all(key in calculation for key in ("scope1", "scope2", "reported_total")):
            scope1, scope2 = Decimal(calculation["scope1"]), Decimal(calculation["scope2"])
            total = Decimal(calculation["reported_total"])
            comparison = (f"{number(scope1)} + {number(scope2)} = {number(scope1 + scope2)}; "
                          f"tổng công bố {number(total)} tCO2e")
            if outcome == "Contradicted":
                comparison += f"; chênh lệch {number(abs(scope1 + scope2 - total))} tCO2e"
        else:
            comparison = ""
        finding = next((row for row in data["findings"] if row["rule_id"] == meta["rule"] and row["report_years"] == [2025]), None)
        finding_id = finding["finding_id"] if finding else "Không tạo finding vì rule chưa chạy được"
        related_financial = ('<p><a href="#financial">Xem số lao động liên quan trong báo cáo tài chính →</a></p>'
                             if dimension == "S" else "")
        case_details.append(f'''<article class="case-detail" id="case-{dimension}" data-search="{h(search_text)}">
          <div class="case-title"><div><span class="eyebrow">{dimension} · Năm 2025 · {h(meta['rule'])}</span><h3>{h(meta['title'])}</h3><p>{h(meta['question'])}</p></div>
            <span class="status {h(outcome)}">{h(label)}</span></div>
          <div class="case-grid"><section class="visual" aria-label="Sơ đồ bằng chứng {dimension}"><h4>Đường đi của kết quả</h4>
            <div class="graph-flow"><div class="graph-values">{''.join(value_nodes)}</div><span class="flow-arrow" aria-hidden="true">→</span>
              <div class="graph-node rule-node"><span class="eyebrow">Phép kiểm tra</span><strong>{h(meta['question'])}</strong><small>{h(guards)}</small></div>
              <span class="flow-arrow" aria-hidden="true">→</span><div class="graph-node result-node {h(outcome)}"><span class="eyebrow">Kết quả</span><strong>{h(label)}</strong>{f'<b>{h(comparison)}</b>' if comparison else ''}<small>{h(interpretation)}</small></div></div>
            <p class="plain-reason">{h(meta['why'])}</p>{related_financial}</section>
            <aside class="locator"><span class="eyebrow">Tìm trong tài liệu</span><h4>Báo cáo Phát triển Bền vững BSR 2025</h4>
              <dl><dt>Tên báo cáo</dt><dd>Báo cáo Phát triển Bền vững BSR 2025</dd><dt>Tên tệp trong demo</dt><dd><code>BSR_2025_official.pdf</code></dd><dt>Trang</dt><dd>PDF vật lý {h(meta['pages'])}</dd>
                <dt>Mục</dt><dd>{h(meta['section'])}</dd><dt>Bảng hoặc đoạn</dt><dd>{h(meta['table'])}</dd></dl>
              <p class="locator-note">Hệ thống chỉ chỉ dẫn vị trí; không cung cấp file báo cáo. Số trang là trang PDF vật lý tính từ trang đầu, không phải số trang của bản Extract 68 trang.</p></aside></div>
          <details><summary>Xem nguyên văn và giới hạn kiểm tra</summary><div class="detail-body"><ol class="source-list">{''.join(source_rows)}</ol>
            <p><b>Điều kiện còn vướng:</b> {h(guards)}</p><p><b>Cần xem tiếp:</b> {h(meta['next'])}</p>
            <p><b>Truy vết nội bộ:</b> {h(', '.join(case['claim_ids']))} · {h(finding_id)}</p>
            <p>Review nguồn do AI thực hiện. Human adjudication của pilot vẫn chờ.</p></div></details></article>''')

    temporal = len(data["temporal_comparisons"])
    s_case = next(row for row in data["expected"]["cases"] if row["dimension"] == "S")
    esg_total = claims[s_case["claim_ids"][0]]
    finance = next(row for row in data["financial_records"]
                   if row["report_year"] == 2025 and row["record_type"] == "financial_disclosure"
                   and row.get("item", {}).get("item_id") == "workforce.total")
    link = next(row for row in data["financial_candidates"]
                if row["claim_id"] == esg_total["record_id"]
                and row["financial_disclosure_id"] == finance["disclosure_id"])
    financial_guards = "; ".join(FINANCIAL_GUARDS.get(reason, reason.replace("_", " "))
                                 for reason in link["reasons"])
    financial_difference = abs(Decimal(str(finance["value"])) - Decimal(str(esg_total["value"])))
    financial_years = Counter(row["report_year"] for row in data["financial_records"])
    earlier = next((row for row in data["findings"] if row["report_years"] == [2024]), None)
    earlier_text = (f"Năm 2024 có một finding {STATUS[earlier['status']][0].lower()} về HĐQT. "
                    "Locator BSR_2024.pdf, trang 37 chỉ đến từ Extract và chưa được đối chiếu PDF; chưa dùng làm kết luận giữa các năm."
                    if earlier else "Chưa có finding năm 2024 trong tập chính.")
    graph_html = graph_fragment(data, CASES, STATUS, GUARDS, FINANCIAL_GUARDS, number)
    catalog_html = claim_catalog(data)
    document = f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>BSR 2025 · Khám phá bằng chứng ESG</title><style>
:root{{--ink:#142b37;--muted:#55717d;--paper:#f5f7f4;--card:#fff;--line:#dce5e3;--teal:#076965;--amber:#8b5609;--green:#17704b;--red:#a33d3e}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.55 'Segoe UI',Arial,sans-serif}}
a{{color:var(--teal)}}a:focus-visible,summary:focus-visible,input:focus-visible{{outline:3px solid #efb74a;outline-offset:3px}}
.shell{{max-width:1220px;margin:auto;padding:0 28px}}header{{background:#113d42;color:#fff;padding:18px 0 70px}}header .top{{display:flex;justify-content:space-between;align-items:center;gap:20px}}
.brand{{font-size:14px;font-weight:800;letter-spacing:.09em;text-transform:uppercase}}nav{{display:flex;gap:24px;flex-wrap:wrap}}nav a{{color:#effafa;text-decoration:none;font-size:14px}}
nav a:hover{{text-decoration:underline}}.hero{{padding-top:58px;max-width:830px}}.hero .eyebrow{{color:#a4ddd3}}h1{{font-size:clamp(32px,4.2vw,54px);line-height:1.12;letter-spacing:-.035em;margin:12px 0 20px}}
header p{{color:#d8e9e7;max-width:700px;margin:0}}.eyebrow{{display:block;color:var(--muted);font-size:12px;font-weight:800;letter-spacing:.085em;text-transform:uppercase}}
main{{margin-top:-39px}}.summary-card,.case-detail,.topic-card,.info-card{{background:var(--card);border:1px solid var(--line);border-radius:18px;box-shadow:0 12px 35px #163f3610}}
.summary-card{{padding:22px 28px;display:grid;grid-template-columns:1.4fr repeat(4,1fr);align-items:center;gap:18px}}
.summary-card strong{{font-size:24px;line-height:1.2;display:block}}.summary-card p{{margin:5px 0 0;color:var(--muted);font-size:14px}}
.metric{{border-left:1px solid var(--line);padding-left:18px}}.metric b{{font-size:28px;display:block;line-height:1.2}}.metric span{{font-size:13px;color:var(--muted)}}
h2{{font-size:clamp(23px,2.5vw,31px);margin:55px 0 8px;letter-spacing:-.025em}}.intro{{color:var(--muted);max-width:760px;margin:0 0 22px}}
.search{{display:flex;align-items:center;gap:12px;margin:22px 0}}.search label{{font-weight:700;white-space:nowrap}}.search input{{width:min(100%,540px);border:1px solid #b9c9c8;border-radius:9px;padding:12px 14px;font:inherit}}
.topic-list{{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}}.topic-card{{min-height:185px;padding:20px;text-decoration:none;color:var(--ink);display:flex;flex-direction:column;gap:8px;border-top:5px solid #a8b8ba}}
.topic-card.NeedsReview{{border-top-color:#d08a25}}.topic-card.Supported{{border-top-color:var(--green)}}.topic-card.Skipped{{border-top-color:#7f929b}}.topic-card:hover{{transform:translateY(-3px);box-shadow:0 15px 35px #163f3622}}
.topic-letter{{font-size:13px;font-weight:800;color:var(--teal)}}.topic-body strong{{display:block;font-size:19px}}.topic-body small{{display:block;font-size:14px;color:var(--muted);margin-top:4px}}.status{{display:inline-block;align-self:flex-start;border-radius:100px;padding:5px 11px;font-size:13px;font-weight:800;white-space:normal}}
.status.NeedsReview{{background:#fff0d4;color:#7c4c07}}.status.Supported{{background:#ddf5e8;color:#12633e}}.status.Skipped{{background:#edf1f2;color:#455f6a}}.status.Contradicted{{background:#ffe5e6;color:#9d2d35}}
.topic-card .status{{margin-top:auto}}.case-detail{{padding:29px;margin:22px 0;scroll-margin-top:18px}}.case-title{{display:flex;justify-content:space-between;align-items:start;gap:16px}}
h3{{font-size:25px;margin:4px 0}}.case-title p{{margin:0 0 22px;color:var(--muted)}}h4{{margin:0 0 14px;font-size:17px}}.case-grid{{display:grid;grid-template-columns:minmax(0,1.75fr) minmax(270px,1fr);gap:25px}}
.visual{{min-width:0}}.graph-flow{{display:flex;align-items:stretch;gap:9px}}.graph-values{{flex:1.1;display:grid;gap:9px;min-width:0}}.graph-node{{border:1px solid #cddfdc;border-radius:12px;padding:13px;background:#f5faf9;min-width:0}}
.graph-node strong{{display:block;font-size:14px;line-height:1.3;margin:4px 0}}.graph-node b{{display:block;font-size:20px}}.graph-node small{{display:block;color:var(--muted);font-size:12px}}
.rule-node{{flex:1.1;background:#e9f4f3}}.result-node{{flex:1}}.result-node.NeedsReview{{background:#fff8ea;border-color:#e7bd79}}.result-node.Supported{{background:#edfaf1;border-color:#95d2ae}}.result-node.Skipped{{background:#f4f6f7;border-color:#b9c7cc}}
.flow-arrow{{align-self:center;color:#6e9994;font-size:23px}}.plain-reason{{font-size:15px;margin:18px 0 0}}.locator{{background:#f0f6f4;border:1px solid #d6e6e1;border-radius:12px;padding:19px}}
.locator h4{{margin:5px 0 14px}}dl{{margin:0;display:grid;grid-template-columns:110px 1fr;gap:8px 10px;font-size:14px}}dt{{color:var(--muted)}}dd{{margin:0;font-weight:650;min-width:0;word-break:break-word}}
code{{font:13px Consolas,monospace;word-break:break-word}}.locator-note{{color:var(--muted);font-size:13px;margin:17px 0 0}}details{{margin-top:22px;border-top:1px solid var(--line);padding-top:14px}}summary{{cursor:pointer;color:var(--teal);font-weight:800}}
.detail-body{{max-width:880px;font-size:14px}}.source-list{{padding-left:22px}}.source-list li{{margin:13px 0}}.source-list small,.quote{{display:block}}.quote{{background:#f5f7f5;border-left:3px solid #a6c4ba;padding:9px;margin:6px 0}}
.info-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:18px}}.info-card{{padding:22px}}.info-card h3{{font-size:19px;margin:0 0 9px}}.info-card p{{color:var(--muted);margin:0 0 12px}}.info-card ul{{padding-left:20px;margin:8px 0}}
.finance-grid{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.finance-value{{padding:19px;border:1px solid var(--line);border-radius:12px;background:#f8fbfa}}.finance-value strong{{display:block;font-size:28px;margin:5px 0}}.finance-value small{{display:block;color:var(--muted)}}.finance-note{{border-left:4px solid #d08a25;background:#fff8ec;padding:14px 17px;border-radius:7px;margin:18px 0}}.finance-source{{font-size:14px;margin:0 0 9px}}.finance-source b{{display:block}}
.legend{{display:flex;gap:8px 18px;flex-wrap:wrap}}.legend span{{font-size:13px}}footer{{padding:45px 0;color:var(--muted);font-size:13px}}[hidden]{{display:none!important}}
{GRAPH_STYLE}
{CATALOG_STYLE}
@media(max-width:900px){{.summary-card{{grid-template-columns:repeat(2,1fr)}}.summary-card>div:first-child{{grid-column:1/-1}}.metric{{border-left:0;border-top:1px solid var(--line);padding:12px 0 0}}.case-grid,.info-grid{{grid-template-columns:1fr}}}}
@media(max-width:680px){{.shell{{padding:0 17px}}header{{padding-bottom:60px}}header .top{{align-items:start;flex-direction:column}}.hero{{padding-top:35px}}.topic-list,.finance-grid{{grid-template-columns:1fr}}.topic-card{{min-height:0}}.case-detail{{padding:19px}}.case-title{{display:block}}.case-title .status{{margin-bottom:18px}}.graph-flow{{display:block}}.graph-node{{margin:8px 0}}.flow-arrow{{display:block;transform:rotate(90deg);text-align:center}}dl{{grid-template-columns:95px 1fr}}}}
</style></head><body><header><div class="shell"><div class="top"><div class="brand">ESG · Bằng chứng doanh nghiệp</div><nav aria-label="Điều hướng"><a href="#overview">Tổng quan</a><a href="#graph">Đồ thị</a><a href="#claims">30 claim</a><a href="#explore">Khám phá E/S/G</a><a href="#financial">Báo cáo tài chính</a><a href="#limits">Giới hạn</a></nav></div>
<div class="hero"><span class="eyebrow">BSR · Báo cáo 2025 · Demo một doanh nghiệp</span><h1>Đi từ kết quả đến đúng trang báo cáo.</h1>
<p>Xem thông tin môi trường, xã hội và quản trị theo phép kiểm tra cụ thể. Mỗi kết quả chỉ ra số liệu, lý do và vị trí nguồn để bạn tự đối chiếu.</p></div></div></header>
<main class="shell"><section id="overview" class="summary-card" aria-label="Tổng quan BSR 2025"><div><span class="eyebrow">Tổng quan</span><strong>BSR trong năm 2025</strong><p>Ba phép kiểm tra đang được trình bày; không có điểm rủi ro tổng hợp. <a href="#claims">Xem đủ {len(data['normalized_claims'])} claim ESG đã chọn</a>.</p></div>
<div class="metric"><b>{counts['Contradicted']}</b><span>Có số liệu không khớp</span></div><div class="metric"><b>{counts['NeedsReview']}</b><span>Cần kiểm tra thêm</span></div>
<div class="metric"><b>{counts['Supported']}</b><span>Phù hợp phép kiểm tra</span></div><div class="metric"><b>{counts['Skipped']}</b><span>Chưa thể kiểm tra</span></div></section>
{graph_html}
{catalog_html}
<section id="explore"><h2>Khám phá theo chủ đề</h2><p class="intro">Chọn một chủ đề để thấy đường đi từ số liệu đến kết quả và trang nguồn. Màu sắc luôn đi kèm chữ; “phù hợp” chỉ nói về phép kiểm tra đang hiển thị.</p>
<div class="search"><label for="case-search">Tìm thông tin</label><input id="case-search" type="search" placeholder="Chỉ tiêu, mục, trang hoặc tên file" autocomplete="off"></div>
<div class="topic-list">{''.join(case_cards)}</div><p id="search-empty" hidden>Không thấy chủ đề phù hợp trong ba ca đang trình bày.</p>{''.join(case_details)}</section>
<section id="financial"><h2>Liên hệ với báo cáo tài chính</h2><p class="intro">Graph chứa {len(data['financial_records'])} record BCTC từ adapter cũ ({financial_years[2023]} năm 2023, {financial_years[2024]} năm 2024, {financial_years[2025]} năm 2025). Chỉ {len(data['financial_candidates'])} liên kết ESG–BCTC được ghi là ứng viên so sánh; chưa có kết luận mâu thuẫn từ BCTC.</p>
<article class="case-detail"><div class="case-title"><div><span class="eyebrow">Đối chiếu ứng viên · lao động BSR 2025</span><h3>Hai báo cáo nêu hai tổng lao động khác nhau</h3><p>Chênh lệch quan sát được là {h(number(financial_difference))} người. Hệ thống chưa cho phép so trực tiếp hai số.</p></div><span class="status NeedsReview">Chưa đủ điều kiện so sánh</span></div>
<div class="finance-grid"><div class="finance-value"><span class="eyebrow">Báo cáo phát triển bền vững</span><strong>{h(number(esg_total['value']))} người</strong><p class="finance-source"><b>Báo cáo Phát triển Bền vững BSR 2025</b>Tệp trong demo: <code>BSR_2025_official.pdf</code><br>PDF vật lý trang 76 · Phát triển nguồn nhân lực · bảng Quy mô lao động và ổn định nhân sự, cột 2025.</p><small>Đã đối chiếu giá trị với PDF chính thức. Ngày chốt và ranh giới tổ chức của chỉ tiêu vẫn chưa rõ.</small></div>
<div class="finance-value"><span class="eyebrow">Báo cáo tài chính hợp nhất</span><strong>{h(number(finance['value']))} người</strong><p class="finance-source"><b>{h(finance['report']['title'])}</b>Tên PDF do Extract khai báo: <code>{h(finance['source_file'])}</code><br>Trang {h(', '.join(map(str, finance['source_pages'])))} theo locator JSON Extract · chỉ tiêu tổng số lao động tại 31/12/2025.</p><small>Record BCTC trong demo đến từ JSON Extract. PDF BCTC không có trong workspace để AI đối chiếu độc lập nguyên văn và trang.</small></div></div>
<p class="finance-note"><b>Vì sao chưa gọi là mâu thuẫn?</b> {h(financial_guards)}. Số BCTC thuộc phạm vi hợp nhất; phạm vi của số ESG chưa được xác minh tương đồng. Chênh lệch {h(number(financial_difference))} người là tín hiệu để tra cứu, không phải finding KG-S-01 hoặc kết luận tẩy xanh.</p>
<details><summary>Xem truy vết và phạm vi BCTC</summary><div class="detail-body"><p>Claim ESG: <code>{h(esg_total['record_id'])}</code> · Record BCTC: <code>{h(finance['disclosure_id'])}</code>.</p><p>Locator JSON BCTC: <code>{h(finance['source_pointer'])}</code>. Liên kết: <code>{h(link['status'])}</code>, comparable=<code>{str(link['comparable']).lower()}</code>.</p>
<p>Tám record BCTC riêng 2025 là candidate chưa xác minh. Bảy cặp reconciliation riêng/hợp nhất hiện chỉ là NeedsReview, không tạo ESG finding. Sáu upload BCTC format 2.3 mới chưa được ingest hoặc đối chiếu PDF trong demo này.</p></div></details></article></section>
<section id="limits"><h2>Hiểu đúng kết quả</h2><div class="info-grid"><div class="info-card"><h3>Trạng thái có nghĩa gì?</h3><div class="legend">
<span class="status Contradicted">Có số liệu không khớp</span><span class="status NeedsReview">Cần kiểm tra thêm</span><span class="status Supported">Phù hợp với phép kiểm tra</span><span class="status Skipped">Chưa thể kiểm tra</span></div>
<p style="margin-top:14px">BSR 2025 hiện không có kết quả “có số liệu không khớp” trong ba phép kiểm tra này. Điều đó không chứng minh toàn bộ báo cáo không có mâu thuẫn hoặc doanh nghiệp không có rủi ro tẩy xanh.</p></div>
<div class="info-card"><h3>Giữa các năm và nguồn</h3><p>Có {temporal} liên kết so sánh 2023–2025 cần kiểm tra tính tương đồng; chưa tạo kết luận mâu thuẫn giữa các năm. {h(earlier_text)}</p>
<p>PDF chính thức 134 trang đã được AI đối chiếu có chọn lọc cho các đoạn 2025. Bản PDF 68 trang do Extract khai báo hiện không có để xác minh hai bản tương đương toàn bộ.</p></div>
<div class="info-card"><h3>Đọc từ nguồn theo 3 bước</h3><ol><li>Tìm đúng tên file được ghi ở thẻ nguồn.</li><li>Đi đến trang PDF vật lý được chỉ rõ.</li><li>Tìm mục/bảng và so nguyên văn với chỉ tiêu trong sơ đồ.</li></ol><p>Hệ thống không phân phối báo cáo hoặc tạo liên kết tải file.</p></div>
<div class="info-card"><h3>Phạm vi đánh giá</h3><p>Năm 2025 có {year['finding_count']} finding chính trong {sum(year['dimension_distribution'][d]['claim_count'] for d in 'ESG')} claim E/S/G. “Skipped” không được tính là đạt. Không thấy record không có nghĩa là doanh nghiệp không công bố.</p>
<p>Demo kỹ thuật: {'đã qua kiểm tra' if acceptance['technical_demo_pass'] else 'chưa qua kiểm tra'}. Chấp nhận evidence của pilot: còn chờ người adjudicate. Review của AI được ghi riêng, không thay thế review của người.</p></div></div></section>
<footer>BSR · Giao diện khám phá bằng chứng · Rule KG-E-01, KG-S-01, KG-G-01 · Kết quả phản ánh dữ liệu và giới hạn nguồn hiện có.</footer></main>
<script>const q=document.getElementById('case-search');const norm=s=>s.normalize('NFD').toLocaleLowerCase('vi').replace(/[\\u0300-\\u036f]/g,'').replace(/đ/g,'d');q.addEventListener('input',()=>{{const term=norm(q.value.trim());let shown=0;document.querySelectorAll('[data-search]').forEach(el=>{{const match=norm(el.dataset.search).includes(term);el.hidden=!match;if(match&&el.classList.contains('topic-card'))shown++}});document.getElementById('search-empty').hidden=shown!==0}});</script>
<script>{GRAPH_SCRIPT}</script>
<script>{CATALOG_SCRIPT}</script>
</body></html>'''
    (output_dir / "index.html").write_text(document, encoding="utf-8")
    (output_dir / "graph_demo.html").write_text(document, encoding="utf-8")
