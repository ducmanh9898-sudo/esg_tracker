"""Interactive, reader-facing projection of BSR rule and provenance graph paths."""
from __future__ import annotations

import html
import textwrap


def esc(value):
    return html.escape(str(value if value is not None else "Chưa rõ"), quote=True)


def wrap(label, width=22, limit=3):
    lines = textwrap.wrap(str(label), width=width, break_long_words=False, break_on_hyphens=False)
    return lines[:limit] or [""]


def node(key, x, y, title, value, detail, locator="", kind="fact", width=210, height=92):
    return {"key": key, "x": x, "y": y, "w": width, "h": height, "title": title,
            "value": value, "detail": detail, "locator": locator, "kind": kind}


def svg_text(row):
    lines = wrap(row["title"], 25 if row["w"] > 190 else 18)
    y = row["y"] + 26
    spans = "".join(f'<tspan x="{row["x"] + 14}" dy="{0 if i == 0 else 17}">{esc(line)}</tspan>'
                    for i, line in enumerate(lines))
    value_y = row["y"] + row["h"] - 15
    return f'''<g class="kg-node kg-{esc(row['kind'])}" data-title="{esc(row['title'])}" data-detail="{esc(row['detail'])}"
        data-locator="{esc(row['locator'])}" tabindex="0" role="button" aria-label="{esc(row['title'])}: {esc(row['value'])}">
      <rect x="{row['x']}" y="{row['y']}" width="{row['w']}" height="{row['h']}" rx="14"/>
      <text class="kg-node-title" x="{row['x'] + 14}" y="{y}">{spans}</text>
      <text class="kg-node-value" x="{row['x'] + 14}" y="{value_y}">{esc(row['value'])}</text></g>'''


def edge(source, target, evidence=False):
    if evidence:
        x1 = source["x"] + source["w"] / 2
        y1 = source["y"]
        x2 = target["x"] + target["w"] / 2
        y2 = target["y"] + target["h"]
    else:
        x1 = source["x"] + source["w"]
        y1 = source["y"] + source["h"] / 2
        x2 = target["x"]
        y2 = target["y"] + target["h"] / 2
    return (f'<line class="kg-edge{" kg-evidence-edge" if evidence else ""}" '
            f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"/>')


def panel(key, label, nodes, edges):
    lines = "".join(edge(nodes[a], nodes[b], evidence) for a, b, evidence in edges)
    shapes = "".join(svg_text(row) for row in nodes.values())
    return f'''<div class="kg-panel" data-graph-panel="{esc(key)}" {'hidden' if key != 'E' else ''}>
      <div class="kg-scroll"><svg viewBox="0 0 1100 650" xmlns="http://www.w3.org/2000/svg" role="group"
        aria-label="Đồ thị bằng chứng {esc(label)}: doanh nghiệp, chỉ tiêu, phép kiểm tra, kết quả và nguồn">
        {lines}{shapes}</svg></div></div>'''


def graph_fragment(data, cases, status, guards, financial_guards, number):
    claims = {row["record_id"]: row for row in data["normalized_claims"]}
    evidence_nodes = {row.get("evidenceId"): row for row in data["graph"]["nodes"] if row.get("evidenceId")}
    official = {row["claim_id"]: row for row in data["source_provenance_audit"]["attached_evidence"]}
    evaluations = {(row["report_year"], row["rule_id"]): row for row in data["rule_evaluations"]}
    panels = []

    for dim, meta in cases.items():
        evaluation = evaluations[(2025, meta["rule"])]
        outcome = evaluation["outcome"]
        claim_ids = evaluation["input_claim_ids"]
        positions = {2: [180, 340], 3: [100, 250, 400]}[len(claim_ids)]
        rows = {"company": node("company", 30, 275, "Doanh nghiệp", "BSR",
                                "Công ty Cổ phần Lọc hóa dầu Bình Sơn; lát cắt dữ liệu năm 2025.", kind="company", width=155)}
        edges = []
        page_set = set()
        for i, claim_id in enumerate(claim_ids):
            claim = claims[claim_id]
            support = official.get(claim_id)
            source = evidence_nodes.get(support["evidence_id"], {}) if support else {}
            page = support["official_page"] if support else "chưa rõ"
            page_set.add(page)
            quote = source.get("originalText") or "Chưa có nguyên văn PDF được đối chiếu"
            label = claim.get("label") or claim.get("metric_id")
            unit = "người" if claim["unit"] == "person" else claim["unit"]
            rows[f"claim{i}"] = node(f"claim{i}", 265, positions[i], label,
                                     f"{number(claim['value'])} {unit}",
                                     f"Record {claim_id}. Nguyên văn đã đối chiếu: “{quote}”",
                                     f"Báo cáo Phát triển Bền vững BSR 2025 · PDF vật lý trang {page} · {meta['section']} · {meta['table']}.",
                                     width=215)
            edges += [("company", f"claim{i}", False), (f"claim{i}", "rule", False), ("source", f"claim{i}", True)]
        reasons = "; ".join(guards.get(r, r.replace("_", " ")) for r in evaluation["reasons"])
        rows["rule"] = node("rule", 555, 255, "Phép kiểm tra", meta["rule"],
                            f"{meta['question']} Điều kiện: {reasons}.", kind="rule", width=225, height=116)
        rows["result"] = node("result", 865, 266, "Trạng thái", status[outcome][0],
                              f"{meta['why']} {status[outcome][1]}", kind=outcome, width=205, height=96)
        rows["source"] = node("source", 555, 515, "Nguồn đã đối chiếu", "Báo cáo BSR 2025",
                              "PDF chính thức được AI đối chiếu có chọn lọc cho các record đang hiển thị. Human adjudication của pilot vẫn chờ.",
                              f"Tệp trong demo: BSR_2025_official.pdf · PDF vật lý trang {', '.join(map(str, sorted(page_set)))} · {meta['section']} · {meta['table']}.",
                              kind="source", width=225, height=92)
        edges.append(("rule", "result", False))
        panels.append(panel(dim, meta["title"], rows, edges))

    s_eval = evaluations[(2025, cases["S"]["rule"])]
    esg = next(claims[cid] for cid in s_eval["input_claim_ids"] if claims[cid]["metric_id"] == "employees_total")
    fin = next(row for row in data["financial_records"] if row["report_year"] == 2025
               and row["record_type"] == "financial_disclosure" and row.get("item", {}).get("item_id") == "workforce.total")
    link = next(row for row in data["financial_candidates"] if row["claim_id"] == esg["record_id"]
                and row["financial_disclosure_id"] == fin["disclosure_id"])
    why = "; ".join(financial_guards.get(r, r.replace("_", " ")) for r in link["reasons"])
    frows = {
        "company": node("company", 30, 275, "Doanh nghiệp", "BSR", "BSR, năm 2025.", kind="company", width=155),
        "esg": node("esg", 265, 175, "Tổng lao động ESG", f"{number(esg['value'])} người",
                    f"Record {esg['record_id']}. Chỉ tiêu trong báo cáo phát triển bền vững.",
                    "Báo cáo Phát triển Bền vững BSR 2025 · BSR_2025_official.pdf · PDF vật lý trang 76 · bảng Quy mô lao động và ổn định nhân sự.", width=215),
        "finance": node("finance", 265, 345, "Tổng lao động BCTC", f"{number(fin['value'])} người",
                        f"Record {fin['disclosure_id']}. BCTC hợp nhất; chưa đối chiếu PDF độc lập trong workspace.",
                        f"Tên PDF do Extract khai báo: {fin['source_file']} · trang {', '.join(map(str, fin['source_pages']))} theo JSON Extract.", width=215),
        "rule": node("rule", 555, 255, "Khả năng so sánh", "Ứng viên", f"Hai giá trị chỉ được so khi ngày chốt, quần thể và định nghĩa tương đồng. Còn thiếu: {why}.", kind="rule", width=225, height=116),
        "result": node("result", 865, 266, "Trạng thái", "Chưa thể so trực tiếp",
                       "Liên kết ESG–BCTC có comparable=false; hai số khác nhau chưa tạo finding mâu thuẫn.", kind="NeedsReview", width=205, height=96),
        "esg_source": node("esg_source", 260, 515, "Nguồn ESG", "PDF trang 76",
                           "PDF phát triển bền vững chính thức đã được đối chiếu có chọn lọc.",
                           "BSR_2025_official.pdf · PDF vật lý trang 76 · Phát triển nguồn nhân lực.", kind="source", width=215),
        "fin_source": node("fin_source", 555, 515, "Nguồn BCTC", "Locator Extract",
                           "PDF BCTC không có trong workspace để AI đối chiếu độc lập.",
                           f"{fin['source_file']} · trang {', '.join(map(str, fin['source_pages']))} do JSON Extract khai báo · {fin['source_pointer']}.", kind="source", width=225),
    }
    fedges = [("company", "esg", False), ("company", "finance", False),
              ("esg", "rule", False), ("finance", "rule", False), ("rule", "result", False),
              ("esg_source", "esg", True), ("fin_source", "finance", True)]
    panels.append(panel("F", "liên kết báo cáo tài chính", frows, fedges))

    return f'''<section id="graph"><h2>Đồ thị bằng chứng tương tác</h2>
      <p class="intro">Chọn một lát cắt, rồi bấm vào nút để đọc dữ kiện hoặc vị trí nguồn. Nét liền là đường từ chỉ tiêu qua phép kiểm tra đến trạng thái; nét đứt dẫn về tài liệu. Đồ thị chỉ hiển thị các record của ca trình diễn, không phải toàn bộ RDF.</p>
      <div class="kg-controls" role="group" aria-label="Chọn lát cắt đồ thị">
        <button type="button" data-graph-tab="E" aria-pressed="true">E · Khí thải</button>
        <button type="button" data-graph-tab="S" aria-pressed="false">S · Lao động</button>
        <button type="button" data-graph-tab="G" aria-pressed="false">G · Quản trị</button>
        <button type="button" data-graph-tab="F" aria-pressed="false">ESG ↔ BCTC</button></div>
      <div class="kg-layout"><div class="kg-stage">{''.join(panels)}</div>
        <aside class="kg-inspector" aria-live="polite"><span class="eyebrow">Nút đang chọn</span>
          <h3 id="kg-inspector-title">Chọn một nút trong đồ thị</h3><p id="kg-inspector-detail">Bấm vào chỉ tiêu, phép kiểm tra, trạng thái hoặc nguồn.</p>
          <div id="kg-inspector-locator" hidden><span class="eyebrow">Vị trí trong tài liệu</span><p id="kg-inspector-location"></p></div></aside></div>
      <p class="kg-help">Có thể dùng phím Tab để tới từng nút, rồi Enter hoặc Space để mở phần giải thích. Đồ thị không cung cấp file PDF.</p></section>'''


GRAPH_STYLE = '''
.kg-controls{display:flex;gap:9px;flex-wrap:wrap;margin:21px 0}.kg-controls button{border:1px solid #bed3cf;background:#fff;color:#245452;padding:10px 15px;border-radius:100px;cursor:pointer;font:700 14px 'Segoe UI',Arial,sans-serif}
.kg-controls button[aria-pressed="true"]{background:#0a605c;color:white;border-color:#0a605c}.kg-controls button:focus-visible,.kg-node:focus-visible{outline:3px solid #edaa43;outline-offset:3px}
.kg-layout{display:grid;grid-template-columns:1fr;gap:15px}.kg-stage,.kg-inspector{background:white;border:1px solid #dce5e3;border-radius:16px;box-shadow:0 8px 24px #163f3610}
.kg-stage{min-width:0}.kg-panel[hidden]{display:none}.kg-scroll{overflow-x:auto}.kg-scroll svg{display:block;width:100%;min-width:720px;height:auto;background:#fcfdfb;border-radius:16px}
.kg-inspector{padding:22px;align-self:start;min-height:130px}.kg-inspector h3{font-size:20px;margin:8px 0}.kg-inspector p{font-size:14px;color:#385662}.kg-inspector #kg-inspector-locator{border-top:1px solid #dce5e3;padding-top:14px;margin-top:18px}
.kg-node{cursor:pointer}.kg-node rect{fill:#f4faf8;stroke:#aacbc5;stroke-width:1.5}.kg-node:hover rect,.kg-node.kg-selected rect{stroke:#0b6c65;stroke-width:3}.kg-node.kg-company rect{fill:#dbefed}.kg-node.kg-rule rect{fill:#eaf3f2}.kg-node.kg-source rect{fill:#edf3f9;stroke:#a7bed0}.kg-node.kg-Supported rect{fill:#e3f5e9;stroke:#87c59f}.kg-node.kg-NeedsReview rect{fill:#fff4df;stroke:#d8ab5f}.kg-node.kg-Skipped rect{fill:#eef1f2;stroke:#a8b9be}.kg-node.kg-Contradicted rect{fill:#fde6e7;stroke:#df969c}
.kg-node-title{font:700 14px 'Segoe UI',Arial,sans-serif;fill:#173541}.kg-node-value{font:800 16px 'Segoe UI',Arial,sans-serif;fill:#173541}.kg-edge{stroke:#6a9c96;stroke-width:2.5}.kg-evidence-edge{stroke:#8aa8bb;stroke-dasharray:7 5}.kg-help{color:#55717d;font-size:13px;margin-top:12px}
@media(max-width:900px){.kg-layout{grid-template-columns:1fr}.kg-inspector{min-height:0}}
'''


GRAPH_SCRIPT = '''
const graphTabs=document.querySelectorAll('[data-graph-tab]');
const graphPanels=document.querySelectorAll('[data-graph-panel]');
const graphTitle=document.getElementById('kg-inspector-title');
const graphDetail=document.getElementById('kg-inspector-detail');
const graphLocator=document.getElementById('kg-inspector-locator');
const graphLocation=document.getElementById('kg-inspector-location');
function selectGraphNode(node){
  document.querySelectorAll('.kg-node.kg-selected').forEach(n=>n.classList.remove('kg-selected'));
  node.classList.add('kg-selected');
  graphTitle.textContent=node.dataset.title;
  graphDetail.textContent=node.dataset.detail;
  graphLocation.textContent=node.dataset.locator||'';
  graphLocator.hidden=!node.dataset.locator;
}
graphTabs.forEach(tab=>tab.addEventListener('click',()=>{
  const key=tab.dataset.graphTab;
  graphTabs.forEach(item=>item.setAttribute('aria-pressed',item===tab?'true':'false'));
  graphPanels.forEach(item=>item.hidden=item.dataset.graphPanel!==key);
  const first=document.querySelector(`[data-graph-panel="${key}"] .kg-node.kg-${key==='F'?'NeedsReview':key==='G'?'Supported':key==='E'?'Skipped':'NeedsReview'}`);
  if(first)selectGraphNode(first);
}));
document.querySelectorAll('.kg-node').forEach(node=>{
  node.addEventListener('click',()=>selectGraphNode(node));
  node.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();selectGraphNode(node)}});
});
const initial=document.querySelector('[data-graph-panel="E"] .kg-node.kg-Skipped');
if(initial)selectGraphNode(initial);
'''
