import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_METADATA_FIELDS = ("source_file", "source_pages", "json_pointer", "source_text")


def load_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def evidence_metadata(evidence):
    return {
        "source_file": evidence["source_file"],
        "source_pages": list(evidence["source_pages"]),
        "json_pointer": evidence["json_pointer"],
        "source_text": evidence.get("source_text"),
    }


def build_graph(claims, findings):
    nodes = {}
    edges = []
    claims_by_id = {claim["claim_id"]: claim for claim in claims}
    evidence_registry = {}

    for c in claims:
        company_value = c["company_id"]
        company_node_id = f"company:{company_value}"
        if company_node_id not in nodes:
            company_node = {
                "id": company_node_id,
                "type": "Company",
                "label": c.get("company_name") or company_value,
                "company_id": company_value,
            }
            if c.get("company_name"):
                company_node["company_name"] = c["company_name"]
            nodes[company_node_id] = company_node
        elif c.get("company_name") and "company_name" not in nodes[company_node_id]:
            nodes[company_node_id]["label"] = c["company_name"]
            nodes[company_node_id]["company_name"] = c["company_name"]

        report_id = f"report:{company_value}:{c['report_year']}"
        if report_id not in nodes:
            nodes[report_id] = {
                "id": report_id,
                "type": "Report",
                "label": f"{company_value} · {c['report_year']}",
                "company_id": company_value,
                "report_year": c["report_year"],
            }
            edges.append({"source": company_node_id, "target": report_id, "label": "HAS_REPORT"})

        node_id = "claim:" + c["claim_id"]
        measurement_id = "measurement:" + c["claim_id"]
        claim_node = {
            "id": node_id, "type": "Claim", "dimension": c["dimension"],
            "label": f"{c['label']} ({c['observation_year']})",
            "details": f"{c['claim_type']} | {c['topic']} | scope: {c['scope']}",
            "claim_id": c["claim_id"], "metric_id": c["metric_id"],
        }
        if "expected_evidence_class" in c:
            claim_node["expected_evidence_class"] = c["expected_evidence_class"]
        nodes[node_id] = claim_node

        measurement_details = f"Kỳ {c['observation_year']} | scope: {c['scope']}"
        measurement_node = {
            "id": measurement_id, "type": "Measurement", "dimension": c["dimension"],
            "label": f"{c['value']} {c['unit']}",
            "details": measurement_details,
            "value": c["value"], "unit": c["unit"], "observation_year": c["observation_year"],
            "scope": c["scope"]
        }
        if "variant" in c:
            measurement_node["variant"] = c["variant"]
            measurement_node["details"] += f" | variant: {c['variant']}"
        nodes[measurement_id] = measurement_node
        edges.append({"source": report_id, "target": node_id, "label": "CONTAINS"})
        edges.append({"source": node_id, "target": measurement_id, "label": "HAS_MEASUREMENT"})
        for evidence in c["evidence"]:
            evidence_id = "evidence:" + evidence["evidence_id"]
            pages = ", ".join(map(str, evidence["source_pages"]))
            metadata = evidence_metadata(evidence)
            previous = evidence_registry.get(evidence["evidence_id"])
            if previous:
                conflicting_fields = [
                    field for field in EVIDENCE_METADATA_FIELDS
                    if previous["metadata"][field] != metadata[field]
                ]
                if conflicting_fields:
                    fields = ", ".join(conflicting_fields)
                    raise ValueError(
                        f"Conflicting metadata for evidence_id '{evidence['evidence_id']}' "
                        f"between claims '{previous['claim_id']}' and '{c['claim_id']}': {fields}"
                    )
            else:
                evidence_registry[evidence["evidence_id"]] = {
                    "claim_id": c["claim_id"],
                    "metadata": metadata,
                }
            if evidence_id not in nodes:
                evidence_node = {
                    "id": evidence_id,
                    "type": "Evidence",
                    "dimension": c["dimension"],
                    "label": f"{evidence['source_file']} · p.{pages}",
                    "source_file": evidence["source_file"],
                    "source_pages": evidence["source_pages"],
                    "json_pointer": evidence["json_pointer"],
                }
                if evidence.get("source_text") is not None:
                    evidence_node["details"] = evidence["source_text"]
                for field in ("report_id", "period_type", "metric_period_year", "original_text",
                              "original_text_type", "original_text_verbatim", "extraction_status",
                              "boundary", "missing_fields", "uncertainty_reason", "source_pdf",
                              "source_pdf_path", "data_quality_flags", "provenance_update",
                              "source_interpretation_note"):
                    if field in evidence:
                        evidence_node[field] = evidence[field]
                nodes[evidence_id] = evidence_node
            edges.append({"source": measurement_id, "target": evidence_id, "label": "SOURCED_FROM"})

    for rule_id in sorted({f["rule_id"] for f in findings}):
        sample = next(f for f in findings if f["rule_id"] == rule_id)
        rule_node_id = "rule:" + rule_id
        nodes[rule_node_id] = {
            "id": rule_node_id, "type": "Rule", "label": rule_id,
            "details": sample["rule_name"], "guard": sample["guard"], "basis": sample["basis"]
        }

    for f in findings:
        node_id = "finding:" + f["finding_id"]
        finding_node = {
            "id": node_id, "type": "Finding", "status": f["status"], "label": f"{f['rule_id']} · {f['status']}",
            "details": f["summary"], "calculation": f["calculation"], "guard": f["guard"], "basis": f["basis"],
        }
        if f.get("source_files"):
            finding_node["source_files"] = f["source_files"]
        if f.get("source_pages"):
            finding_node["source_pages"] = f["source_pages"]
        nodes[node_id] = finding_node
        provenance_edges = set()
        for claim_id in f["input_claim_ids"]:
            edges.append({"source": "claim:" + claim_id, "target": node_id, "label": "INPUT_TO"})
            claim = claims_by_id.get(claim_id)
            if not claim:
                continue
            direct_edges = [
                (node_id, "claim:" + claim_id, "BASED_ON_CLAIM"),
                (node_id, f"report:{claim['company_id']}:{claim['report_year']}", "DERIVED_FROM_REPORT"),
            ]
            direct_edges.extend(
                (node_id, "evidence:" + evidence["evidence_id"], "BASED_ON_EVIDENCE")
                for evidence in claim["evidence"]
            )
            for source, target, label in direct_edges:
                key = (source, target, label)
                if key not in provenance_edges:
                    edges.append({"source": source, "target": target, "label": label})
                    provenance_edges.add(key)
        edges.append({"source": node_id, "target": "rule:" + f["rule_id"], "label": "GENERATED_BY"})
    return {"nodes": list(nodes.values()), "edges": edges}


def _render_html_legacy(graph, findings):
    payload = json.dumps({"graph": graph, "findings": findings}, ensure_ascii=False).replace("</", "<\\/")
    rows = []
    for f in findings:
        pages = ", ".join(map(str, f.get("source_pages", [])))
        rows.append(f'''<tr data-status="{html.escape(f['status'])}" data-node="finding:{f['finding_id']}">
<td>{html.escape(f['rule_id'])}</td><td><span class="pill {html.escape(f['status'])}">{html.escape(f['status'])}</span></td>
<td>{html.escape(f['summary'])}</td><td>{html.escape(pages)}</td></tr>''')
    counts = {s: sum(x["status"] == s for x in findings) for s in ("Contradicted", "NeedsReview", "Supported", "InsufficientEvidence")}
    return f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESG Knowledge Graph Demo</title><style>
:root{{--bg:#08111f;--panel:#0f1d31;--text:#e8f0fb;--muted:#92a4bd;--line:#324760;--red:#ff5d6c;--amber:#ffb547;--green:#36d399;--blue:#5aa9ff}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(140deg,#07101d,#0c1930);color:var(--text);font:14px Segoe UI,Arial,sans-serif}}
header{{padding:24px 28px 10px}} h1{{margin:0;font-size:25px}} header p{{color:var(--muted);max-width:900px;line-height:1.5}}
.stats{{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:12px;padding:0 28px 18px}} .card,.panel{{background:rgba(15,29,49,.94);border:1px solid #243954;border-radius:14px;box-shadow:0 12px 35px #0004}}
.card{{padding:15px}} .card b{{display:block;font-size:25px;margin-top:4px}} .card span{{color:var(--muted)}}
.layout{{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:14px;padding:0 28px 22px}} .panel{{overflow:hidden}} .toolbar{{display:flex;gap:8px;align-items:center;padding:12px;border-bottom:1px solid #243954;flex-wrap:wrap}}
button{{background:#172b46;color:var(--text);border:1px solid #355274;padding:7px 11px;border-radius:999px;cursor:pointer}} button.active{{border-color:#7bb8ff;background:#23466d}}
#canvas{{height:64vh;overflow:auto;background:radial-gradient(circle at 40% 45%,#17304b88,transparent 42%)}} svg{{display:block;min-width:3000px}}
.edge{{stroke:var(--line);stroke-width:1.2;opacity:.72}} .edge-label{{fill:#6f86a1;font-size:9px}} .node circle{{stroke:#d9e8ff;stroke-width:1.2;cursor:pointer}} .node text{{fill:#eaf2ff;font-size:11px;pointer-events:none}}
.details{{padding:18px;line-height:1.55}} .details h2{{font-size:17px;margin:0 0 12px}} .details dt{{color:var(--muted);margin-top:10px}} .details dd{{margin:2px 0;word-break:break-word}}
.table-panel{{margin:0 28px 28px;padding:0;overflow:auto}} table{{width:100%;border-collapse:collapse;min-width:820px}} th,td{{padding:11px 13px;border-bottom:1px solid #243954;text-align:left;vertical-align:top}} th{{color:#a9bad0;background:#11223a;position:sticky;top:0}} tbody tr{{cursor:pointer}} tbody tr:hover{{background:#152a45}}
.pill{{display:inline-block;padding:3px 8px;border-radius:10px;font-size:12px}} .Contradicted{{background:#6d1f2a;color:#ffb8c0}} .NeedsReview{{background:#63451c;color:#ffd38a}} .Supported{{background:#164f42;color:#8cf2ce}} .InsufficientEvidence{{background:#3c4560;color:#c7d1e5}}
.note{{padding:0 28px 25px;color:var(--muted)}} @media(max-width:900px){{.layout{{grid-template-columns:1fr}}.stats{{grid-template-columns:1fr 1fr}}}}
</style></head><body>
<header><h1>ESG Disclosure Consistency Graph</h1><p>Graph dùng {len([n for n in graph['nodes'] if n['type']=='Claim'])} disclosure record. Mỗi finding truy vết qua Company → Report → Claim → Measurement → Evidence và Rule. Màu đỏ là mâu thuẫn đủ điều kiện; màu cam cần đối soát; màu xanh đã vượt qua quy tắc. Đây là tín hiệu phân tích trong corpus, không phải cáo buộc gian lận.</p></header>
<section class="stats"><div class="card"><span>Claims chuẩn hóa</span><b>{len([n for n in graph['nodes'] if n['type']=='Claim'])}</b></div><div class="card"><span>Mâu thuẫn</span><b style="color:var(--red)">{counts['Contradicted']}</b></div><div class="card"><span>Cần đối soát</span><b style="color:var(--amber)">{counts['NeedsReview']}</b></div><div class="card"><span>Đạt quy tắc</span><b style="color:var(--green)">{counts['Supported']}</b></div></section>
<main class="layout"><section class="panel"><div class="toolbar"><strong>Lọc finding:</strong><button data-filter="All">Tất cả</button><button class="active" data-filter="Contradicted">Mâu thuẫn</button><button data-filter="NeedsReview">Cần đối soát</button><button data-filter="Supported">Đạt</button></div><div id="canvas"><svg id="graph"></svg></div></section><aside class="panel details" id="details"><h2>Chi tiết graph</h2><p>Bấm node để xem dữ liệu nguồn, trang, JSON Pointer, phép tính và guard khi các trường này được cung cấp.</p></aside></main>
<section class="panel table-panel"><table><thead><tr><th>Rule</th><th>Trạng thái</th><th>Kết quả</th><th>Trang nguồn</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
<p class="note">Supported chỉ xác nhận quy tắc trong phạm vi dữ liệu demo. NeedsReview giữ nguyên chênh lệch để con người kiểm tra scope, phương pháp hoặc lỗi trích xuất.</p>
<script>const DATA={payload};
const colors={{Company:'#ae7bff',Report:'#5aa9ff',Claim:'#78b7ff',Measurement:'#55d6be',Evidence:'#d6a85a',CanonicalConcept:'#52c7ea',StandardReference:'#f59e72',TemporalSeries:'#48b7a7',TemporalComparison:'#e59d5f',Rule:'#bd8cff',E:'#4bd6a2',S:'#ffcf66',G:'#ef8cff',Contradicted:'#ff5d6c',NeedsReview:'#ffb547',Supported:'#36d399',InsufficientEvidence:'#8393aa'}};
const svg=document.querySelector('#graph'), details=document.querySelector('#details'); const nodes=DATA.graph.nodes, edges=DATA.graph.edges;
const typeOrder=['Company','Report','Claim','Measurement','Evidence','Finding','Rule','CanonicalConcept','StandardReference','TemporalSeries','TemporalComparison'];
const columns={{Company:85,Report:300,Claim:550,Measurement:820,Evidence:1090,Finding:1370,Rule:1650,CanonicalConcept:1920,StandardReference:2200,TemporalSeries:2470,TemporalComparison:2740}};
const map=Object.fromEntries(nodes.map(n=>[n.id,n]));
function esc(s){{return String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
function visibleIds(filter){{
  if(filter==='All')return new Set(nodes.map(n=>n.id));
  const visible=new Set(nodes.filter(n=>n.type==='Finding'&&n.status===filter).map(n=>n.id));
  let changed=true;
  while(changed){{changed=false;edges.forEach(e=>{{
    if(visible.has(e.target)&&!visible.has(e.source)){{visible.add(e.source);changed=true}}
    if(visible.has(e.source)&&['HAS_MEASUREMENT','SOURCED_FROM','GENERATED_BY','HAS_CONCEPT','MAPPED_TO','BASED_ON_CLAIM','DERIVED_FROM_REPORT','BASED_ON_EVIDENCE','HAS_TEMPORAL_CLAIM','HAS_TEMPORAL_MEASUREMENT','HAS_TEMPORAL_TARGET','NEXT_YEAR_CLAIM','NEXT_YEAR_MEASUREMENT','NEXT_YEAR_TARGET','PART_OF_SERIES','FROM_CLAIM','TO_CLAIM','FROM_MEASUREMENT','TO_MEASUREMENT'].includes(e.label)&&!visible.has(e.target)){{visible.add(e.target);changed=true}}
  }})}}
  return visible;
}}
function draw(filter='Contradicted'){{
  const visible=visibleIds(filter); const byType=Object.fromEntries(typeOrder.map(t=>[t,[]]));
  nodes.filter(n=>visible.has(n.id)).forEach(n=>byType[n.type].push(n));
  Object.values(byType).forEach(list=>list.sort((a,b)=>a.id.localeCompare(b.id)));
  const maxCount=Math.max(1,...Object.values(byType).map(x=>x.length)); const H=Math.max(720,maxCount*58+100);
  svg.setAttribute('viewBox',`0 0 3000 ${{H}}`);svg.setAttribute('height',H);
  Object.entries(byType).forEach(([type,list])=>list.forEach((n,i)=>{{n.x=columns[type];n.y=(i+1)*H/(list.length+1)}}));
  svg.innerHTML='';edges.forEach(e=>{{const a=map[e.source],b=map[e.target];if(!a||!b||!visible.has(a.id)||!visible.has(b.id))return;svg.insertAdjacentHTML('beforeend',`<line class="edge" x1="${{a.x}}" y1="${{a.y}}" x2="${{b.x}}" y2="${{b.y}}"/>`)}});
  nodes.filter(n=>visible.has(n.id)).forEach(n=>{{const color=n.type==='Finding'?colors[n.status]:['Claim','Measurement','Evidence'].includes(n.type)?colors[n.dimension]:colors[n.type];const label=n.label.length>38?n.label.slice(0,36)+'…':n.label;svg.insertAdjacentHTML('beforeend',`<g class="node" data-id="${{n.id}}"><circle cx="${{n.x}}" cy="${{n.y}}" r="${{n.type==='Company'?25:n.type==='Finding'?19:15}}" fill="${{color}}"/><text x="${{n.x+23}}" y="${{n.y+4}}">${{esc(label)}}</text></g>`)}});document.querySelectorAll('.node').forEach(g=>g.onclick=()=>show(map[g.dataset.id]));
}}
function show(n){{const fields=Object.entries(n).filter(([k])=>!['x','y','id','label'].includes(k));details.innerHTML=`<h2>${{esc(n.label)}}</h2><dl>${{fields.map(([k,v])=>`<dt>${{esc(k)}}</dt><dd>${{esc(Array.isArray(v)?v.join(', '):v)}}</dd>`).join('')}}</dl>`;document.querySelectorAll('.node circle').forEach(x=>x.style.strokeWidth='1.2');const g=document.querySelector(`[data-id="${{CSS.escape(n.id)}}"] circle`);if(g)g.style.strokeWidth='4'}}
document.querySelectorAll('button[data-filter]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('button').forEach(x=>x.classList.remove('active'));b.classList.add('active');draw(b.dataset.filter);document.querySelectorAll('tbody tr').forEach(r=>r.style.display=b.dataset.filter==='All'||r.dataset.status===b.dataset.filter?'':'none')}});document.querySelectorAll('tbody tr').forEach(r=>r.onclick=()=>{{const f=map[r.dataset.node];const button=document.querySelector(`button[data-filter="${{f.status}}"]`);if(button)button.click();show(f)}});document.querySelectorAll('tbody tr').forEach(r=>r.style.display=r.dataset.status==='Contradicted'?'':'none');draw('Contradicted');
</script></body></html>'''


def render_html(graph, findings, assessments=None):
    from tools.report_renderer import render_report_html

    return render_report_html(graph, findings, assessments)


def run():
    from tools.standards_crosswalk import apply_crosswalk, load_crosswalk

    claims = load_json(ROOT / "output" / "normalized_claims.json")
    findings = load_json(ROOT / "output" / "findings.json")
    graph = build_graph(claims, findings)
    graph = apply_crosswalk(graph, claims, load_crosswalk())
    out = ROOT / "output"
    (out / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out / "graph_demo.html").write_text(render_html(graph, findings), encoding="utf-8")
    return graph


if __name__ == "__main__":
    graph = run()
    print(f"Đã tạo graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
