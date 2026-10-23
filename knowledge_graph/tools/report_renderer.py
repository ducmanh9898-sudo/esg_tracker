import html
import json


def render_report_html(graph, findings, assessments=None, demo_findings=None):
    demo_findings = demo_findings or []
    assessments = assessments or {
        "claim_assessments": [],
        "company_assessments": {
            "company_year_assessments": [],
            "company_multiyear_assessments": [],
        },
    }
    companies = sorted(
        {
            node["company_id"]
            for node in graph["nodes"]
            if node["type"] == "Company" and not node.get("synthetic")
        }
    )
    company_options = "".join(
        f'<option value="{html.escape(company)}">{html.escape(company)}</option>'
        for company in companies
    )
    synthetic_count = sum(
        node.get("synthetic") is True or str(node.get("source_uri", "")).startswith("synthetic://")
        for node in graph["nodes"]
    )
    payload = json.dumps(
        {"graph": graph, "findings": findings, "assessments": assessments,
         "demo_findings": demo_findings},
        ensure_ascii=False,
    ).replace("</", "<\\/")
    counts = {
        status: sum(finding["status"] == status for finding in findings)
        for status in ("Contradicted", "NeedsReview", "Supported", "InsufficientEvidence")
    }
    synthetic_banner = (
        f'<div class="synthetic-banner">SYNTHETIC — {synthetic_count} node thử nghiệm; '
        "không thuộc assessment doanh nghiệp thật.</div>"
        if synthetic_count else ""
    )
    demo_rows = "".join(
        "<tr>" + "".join(
            f"<td>{html.escape(str(value))}</td>" for value in (
                finding.get("finding_id", ""), finding.get("rule_id", ""),
                finding.get("status", ""), finding.get("company_id", ""),
                ", ".join(finding.get("input_claim_ids", [])),
                finding.get("summary", ""),
            )
        ) + "</tr>"
        for finding in demo_findings
    ) or '<tr><td colspan="6">Không có finding demo trong lần build này.</td></tr>'
    demo_statuses = ", ".join(
        f"{status}: {sum(item.get('status') == status for item in demo_findings)}"
        for status in sorted({item.get("status") for item in demo_findings})
    ) or "không có"

    return f'''<!doctype html><html lang="vi"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ESG Disclosure Risk — Knowledge Graph</title><style>
:root{{--bg:#08111f;--panel:#0f1d31;--text:#e8f0fb;--muted:#9eb0c7;--line:#324760;--red:#ff6574;--amber:#ffbd5a;--green:#43d6a5;--blue:#67b2ff}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(140deg,#07101d,#0c1930);color:var(--text);font:14px Segoe UI,Arial,sans-serif}}
header{{padding:22px 28px 10px}} h1{{margin:0;font-size:25px}} header p,.note{{color:var(--muted);line-height:1.55;max-width:1100px}}
.stats{{display:grid;grid-template-columns:repeat(4,minmax(130px,1fr));gap:12px;padding:0 28px 16px}} .card,.panel{{background:#0f1d31ee;border:1px solid #243954;border-radius:13px;box-shadow:0 12px 35px #0004}}
.card{{padding:14px}} .card b{{display:block;font-size:24px;margin-top:4px}} .card span{{color:var(--muted)}}
.controls{{display:flex;gap:10px;align-items:end;flex-wrap:wrap;padding:12px 28px}} label{{display:grid;gap:4px;color:var(--muted)}} select,button{{background:#172b46;color:var(--text);border:1px solid #355274;padding:7px 10px;border-radius:8px;min-width:150px}} button{{min-width:auto;cursor:pointer;border-radius:999px}} button.active{{border-color:#7bb8ff;background:#23466d}}
.status-buttons{{display:flex;gap:6px;flex-wrap:wrap}} .layout{{display:grid;grid-template-columns:minmax(0,1fr) 390px;gap:14px;padding:0 28px 20px}} .panel{{overflow:hidden}}
#canvas{{height:58vh;overflow:auto;background:radial-gradient(circle at 40% 45%,#17304b88,transparent 42%)}} svg{{display:block;min-width:4500px}} .edge{{stroke:var(--line);stroke-width:1.1;opacity:.7}} .node circle{{stroke:#d9e8ff;stroke-width:1.2;cursor:pointer}} .node text{{fill:#eaf2ff;font-size:10px;pointer-events:none}}
.details{{padding:16px;overflow:auto;height:58vh}} .details h2{{font-size:17px;margin:0 0 10px}} .details h3{{font-size:13px;color:#9dccff;margin:16px 0 5px}} .details ul{{padding-left:18px;margin:5px 0}} .details code{{white-space:normal;color:#d8e7fb}}
.empty{{display:none;margin:24px;padding:20px;border:1px dashed #5d718b;border-radius:10px;color:#c8d4e3;text-align:center}} .empty.show{{display:block}}
.table-panel{{margin:0 28px 20px;overflow:auto}} table{{width:100%;border-collapse:collapse;min-width:850px}} th,td{{padding:10px 12px;border-bottom:1px solid #243954;text-align:left}} th{{color:#b6c5d8;background:#11223a}} tbody tr{{cursor:pointer}} tbody tr:hover{{background:#152a45}}
.table-panel h2{{font-size:17px;margin:16px 12px}} .demo-audit p{{color:var(--muted);margin:0 12px 12px}} .demo-audit tbody tr{{cursor:default}}
.pill{{display:inline-block;padding:3px 8px;border-radius:10px;font-size:12px}} .Contradicted{{background:#6d1f2a;color:#ffbbc2}} .NeedsReview{{background:#63451c;color:#ffd590}} .Supported{{background:#164f42;color:#91f1d1}} .InsufficientEvidence{{background:#3c4560;color:#ccd5e2}}
.synthetic-banner{{margin:0 28px 14px;padding:10px 12px;border:1px solid #f0a64b;background:#51391c;color:#ffe0aa;border-radius:8px;font-weight:700}} .note{{padding:0 28px 22px}}
@media(max-width:950px){{.layout{{grid-template-columns:1fr}}.details{{height:auto}}.stats{{grid-template-columns:1fr 1fr}}}}
</style></head><body>
<header><h1>ESG Disclosure Risk — Knowledge Graph</h1><p>Đánh giá chính chỉ gồm KG-E-01, KG-S-01 và KG-G-01. Điều hướng từ doanh nghiệp đến finding, claim và evidence; finding không phải kết luận gian lận, tuân thủ hay vi phạm tiêu chuẩn.</p></header>
{synthetic_banner}
<section class="stats"><div class="card"><span>Claims</span><b>{sum(node['type'] == 'Claim' for node in graph['nodes'])}</b></div><div class="card"><span>Contradicted</span><b style="color:var(--red)">{counts['Contradicted']}</b></div><div class="card"><span>NeedsReview</span><b style="color:var(--amber)">{counts['NeedsReview']}</b></div><div class="card"><span>Supported</span><b style="color:var(--green)">{counts['Supported']}</b></div></section>
<section class="controls">
<label>1. Company<select id="company-filter"><option value="All">Tất cả</option>{company_options}</select></label>
<label>2. Finding<select id="finding-select"><option value="">Chọn finding</option></select></label>
<label>3. Claim<select id="claim-select"><option value="">Chọn claim</option></select></label>
<label>4. Evidence<select id="evidence-select"><option value="">Chọn evidence</option></select></label>
<div><span style="display:block;color:var(--muted);margin-bottom:4px">Trạng thái</span><div class="status-buttons"><button data-status="All" class="active">Tất cả</button><button data-status="Contradicted">Contradicted</button><button data-status="NeedsReview">NeedsReview</button><button data-status="Supported">Supported</button><button data-status="InsufficientEvidence">InsufficientEvidence</button></div></div>
</section>
<main class="layout"><section class="panel"><div id="empty-state" class="empty">Không có finding phù hợp với bộ lọc đã chọn.</div><div id="canvas"><svg id="graph"></svg></div></section><aside class="panel details" id="details"><h2>Chi tiết kiểm tra</h2><p>Chọn company → finding → claim → evidence. Report, trang và JSON pointer được hiển thị từ provenance đã cung cấp.</p></aside></main>
<section class="panel table-panel"><h2>Findings đánh giá chính</h2><table><thead><tr><th>Finding</th><th>Rule</th><th>Status</th><th>Company</th><th>Kết quả</th></tr></thead><tbody id="finding-table"></tbody></table></section>
<section class="panel table-panel demo-audit"><h2>Đối soát demo — chỉ để audit</h2><p>Nhóm này giữ nguyên trạng thái demo gốc ({html.escape(demo_statuses)}). Không thuộc findings, RDF hoặc assessments chính.</p><table><thead><tr><th>Finding demo</th><th>Rule demo</th><th>Status gốc</th><th>Company</th><th>Claim IDs</th><th>Kết quả demo</th></tr></thead><tbody id="demo-finding-table">{demo_rows}</tbody></table></section>
<p class="note"><strong>Giới hạn:</strong> “Supported” chỉ có nghĩa rule tương ứng đạt trên dữ liệu đã kiểm tra. Standard mapping chỉ là ngữ cảnh đã xác minh, không tự tạo kết luận compliance/violation. Paraphrase duplicate chưa được tự động gộp nếu chưa adjudication.</p>
<script>const DATA={payload};
const nodes=DATA.graph.nodes, edges=DATA.graph.edges, findings=DATA.findings, assessments=DATA.assessments||{{}};
const claimAssessments=assessments.claim_assessments||[]; const nodeMap=Object.fromEntries(nodes.map(n=>[n.id,n]));
const svg=document.querySelector('#graph'), details=document.querySelector('#details'), empty=document.querySelector('#empty-state'), canvas=document.querySelector('#canvas');
const companySelect=document.querySelector('#company-filter'), findingSelect=document.querySelector('#finding-select'), claimSelect=document.querySelector('#claim-select'), evidenceSelect=document.querySelector('#evidence-select');
let activeStatus='All';
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const findingCompany=f=>f.company_id||claimAssessments.find(a=>a.finding_id===f.finding_id)?.company_id||'';
function setOptions(select,items,placeholder){{const current=select.value;select.innerHTML=`<option value="">${{esc(placeholder)}}</option>`+items.map(x=>`<option value="${{esc(x.value)}}">${{esc(x.label)}}</option>`).join('');if(items.some(x=>x.value===current))select.value=current;}}
function filteredFindings(){{return findings.filter(f=>(companySelect.value==='All'||findingCompany(f)===companySelect.value)&&(activeStatus==='All'||f.status===activeStatus));}}
function assessmentFor(findingId,claimId){{return claimAssessments.find(a=>a.finding_id===findingId&&(!claimId||a.claim_id===claimId));}}
function showFinding(findingId){{const f=findings.find(x=>x.finding_id===findingId);if(!f)return;const a=assessmentFor(findingId);const facts=a?.facts||[];const standards=a?.standard_context||[];const unknown=a?.uncertainty?.conditions_unverified||[];
details.innerHTML=`<h2>${{esc(f.finding_id)}} · ${{esc(f.status)}}</h2><h3>Fact</h3><ul>${{facts.map(x=>`<li>${{esc(x.claim_id)}} — ${{esc(x.value)}} ${{esc(x.unit)}}; report ${{esc(x.report_year)}}, observation ${{esc(x.observation_year)}}, scope ${{esc(x.scope)}}</li>`).join('')||'<li>Không có fact đã liên kết.</li>'}}</ul><h3>Suy luận theo rule</h3><p><b>${{esc(f.rule_id)}}:</b> ${{esc(f.summary)}}</p><p><code>${{esc(f.explanation|| (typeof f.calculation==='object'?JSON.stringify(f.calculation):f.calculation))}}</code></p><h3>Điều kiện chưa xác minh</h3><p>${{esc(unknown.join(', ')||'Không ghi nhận trong assessment này.')}}</p><p>${{esc(f.guard)}}</p><h3>Giới hạn dữ liệu</h3><p>${{esc(a?.uncertainty?.status_interpretation||'Chỉ diễn giải trong phạm vi rule và evidence đầu vào.')}}</p><h3>Standard context</h3><ul>${{standards.map(s=>`<li>${{esc(s.standard_name)}} — ${{esc(s.reference_code)}} (${{esc(s.relationship_type)}})</li>`).join('')||'<li>Không có mapping chuẩn đã xác minh cho claim này.</li>'}}</ul><p><small>Standard context only; not a compliance or violation conclusion.</small></p>`;
const claimIds=[...new Set((a?.facts||[]).map(x=>x.claim_id))];setOptions(claimSelect,claimIds.map(id=>({{value:id,label:id}})),'Chọn claim');claimSelect.dataset.finding=findingId;populateEvidence();}}
function populateEvidence(){{const findingId=claimSelect.dataset.finding||findingSelect.value;const claimId=claimSelect.value;const a=assessmentFor(findingId,claimId)||assessmentFor(findingId);const fact=(a?.facts||[]).find(x=>x.claim_id===claimId);const evidence=fact?.evidence||[];setOptions(evidenceSelect,evidence.map(x=>({{value:x.evidence_id,label:x.evidence_id}})),'Chọn evidence');evidenceSelect.dataset.finding=findingId;evidenceSelect.dataset.claim=claimId;if(claimId&&nodeMap['claim:'+claimId])showNode(nodeMap['claim:'+claimId]);}}
function showEvidence(){{const a=assessmentFor(evidenceSelect.dataset.finding,evidenceSelect.dataset.claim);const fact=(a?.facts||[]).find(x=>x.claim_id===evidenceSelect.dataset.claim);const e=(fact?.evidence||[]).find(x=>x.evidence_id===evidenceSelect.value);if(!e)return;details.innerHTML=`<h2>${{esc(e.evidence_id)}}</h2><h3>Fact source</h3><p>Report year: ${{esc(fact.report_year)}}<br>Source: ${{esc(e.source_file)}}<br>Trang: ${{esc((e.source_pages||[]).join(', '))}}<br>JSON pointer: <code>${{esc(e.json_pointer)}}</code></p><h3>Original text</h3><p>${{esc(e.source_text||'Chưa được Extract cung cấp; pending source review.')}}</p>`;}}
function showNode(n){{const fields=Object.entries(n).filter(([k])=>!['x','y','id','label'].includes(k));details.innerHTML=`<h2>${{esc(n.label||n.id)}}</h2><dl>${{fields.map(([k,v])=>`<dt>${{esc(k)}}</dt><dd>${{esc(typeof v==='object'?JSON.stringify(v):v)}}</dd>`).join('')}}</dl>`;}}
const colors={{Company:'#ae7bff',Report:'#5aa9ff',Claim:'#78b7ff',Measurement:'#55d6be',Evidence:'#d6a85a',Finding:'#36d399',Rule:'#bd8cff',CanonicalConcept:'#52c7ea',StandardReference:'#f59e72',TemporalSeries:'#48b7a7',TemporalComparison:'#e59d5f',ClaimAssessment:'#72d1a5',CompanyAssessment:'#b99af7',E:'#4bd6a2',S:'#ffcf66',G:'#ef8cff'}};
const typeOrder=['Company','Report','Claim','Measurement','Evidence','FinancialReport','FinancialDisclosure','FinancialEvidence','FinancialObservation','Finding','Rule','CanonicalConcept','StandardReference','TemporalSeries','TemporalComparison','ClaimAssessment','CompanyAssessment'];const columns=Object.fromEntries(typeOrder.map((t,i)=>[t,80+i*245]));
function visibleIds(fs){{const visible=new Set(fs.map(f=>'finding:'+f.finding_id));const forward=new Set(['BASED_ON_CLAIM','DERIVED_FROM_REPORT','BASED_ON_EVIDENCE','GENERATED_BY','HAS_MEASUREMENT','SOURCED_FROM','SOURCED_FROM_FINANCIAL','HAS_FINANCIAL_CANDIDATE','RELATED_FINANCIAL_OBSERVATION','HAS_CONCEPT','MAPPED_TO','ASSESSES_CLAIM','HAS_STANDARD_CONTEXT','NEXT_YEAR_CLAIM','NEXT_YEAR_MEASUREMENT','NEXT_YEAR_TARGET','HAS_TEMPORAL_CLAIM','HAS_TEMPORAL_MEASUREMENT','HAS_TEMPORAL_TARGET','PART_OF_SERIES','FROM_CLAIM','TO_CLAIM','FROM_MEASUREMENT','TO_MEASUREMENT']);const reverse=new Set(['INPUT_TO','CONTAINS','HAS_REPORT','HAS_FINANCIAL_REPORT','CONTAINS_FINANCIAL_DISCLOSURE','CONTAINS_FINANCIAL_OBSERVATION','DERIVED_FROM_FINDING','SUMMARIZES_FINDING']);let changed=true;while(changed){{changed=false;for(const e of edges){{if(visible.has(e.source)&&forward.has(e.label)&&!visible.has(e.target)){{visible.add(e.target);changed=true}}if(visible.has(e.target)&&reverse.has(e.label)&&!visible.has(e.source)){{visible.add(e.source);changed=true}}}}}}return visible;}}
function draw(fs){{const visible=visibleIds(fs),byType=Object.fromEntries(typeOrder.map(t=>[t,[]]));nodes.filter(n=>visible.has(n.id)&&byType[n.type]).forEach(n=>byType[n.type].push(n));Object.values(byType).forEach(x=>x.sort((a,b)=>a.id.localeCompare(b.id)));const max=Math.max(1,...Object.values(byType).map(x=>x.length)),H=Math.max(720,max*54+90);svg.setAttribute('viewBox',`0 0 4500 ${{H}}`);svg.setAttribute('height',H);for(const [type,list] of Object.entries(byType))list.forEach((n,i)=>{{n.x=columns[type];n.y=(i+1)*H/(list.length+1)}});svg.innerHTML='';for(const e of edges){{const a=nodeMap[e.source],b=nodeMap[e.target];if(!a||!b||!visible.has(a.id)||!visible.has(b.id))continue;svg.insertAdjacentHTML('beforeend',`<line class="edge" x1="${{a.x}}" y1="${{a.y}}" x2="${{b.x}}" y2="${{b.y}}"/>`)}}for(const n of nodes.filter(n=>visible.has(n.id)&&byType[n.type])){{const color=n.type==='Finding'?({{Contradicted:'#ff6574',NeedsReview:'#ffbd5a',Supported:'#43d6a5',InsufficientEvidence:'#8393aa'}}[n.status]||colors.Finding):(['Claim','Measurement','Evidence'].includes(n.type)?colors[n.dimension]:colors[n.type]);const label=String(n.label||n.id);svg.insertAdjacentHTML('beforeend',`<g class="node" data-id="${{esc(n.id)}}"><circle cx="${{n.x}}" cy="${{n.y}}" r="${{n.type==='Finding'?18:14}}" fill="${{color||'#8aa0b8'}}"/><text x="${{n.x+20}}" y="${{n.y+4}}">${{esc(label.length>34?label.slice(0,32)+'…':label)}}</text></g>`)}}document.querySelectorAll('.node').forEach(g=>g.onclick=()=>showNode(nodeMap[g.dataset.id]));}}
function refresh(){{const fs=filteredFindings();empty.classList.toggle('show',fs.length===0);canvas.style.display=fs.length?'block':'none';setOptions(findingSelect,fs.map(f=>({{value:f.finding_id,label:`${{f.finding_id}} · ${{f.rule_id}} · ${{f.status}}`}})),'Chọn finding');document.querySelector('#finding-table').innerHTML=fs.map(f=>`<tr data-id="${{esc(f.finding_id)}}"><td>${{esc(f.finding_id)}}</td><td>${{esc(f.rule_id)}}</td><td><span class="pill ${{esc(f.status)}}">${{esc(f.status)}}</span></td><td>${{esc(findingCompany(f))}}</td><td>${{esc(f.summary)}}</td></tr>`).join('');document.querySelectorAll('#finding-table tr').forEach(r=>r.onclick=()=>{{findingSelect.value=r.dataset.id;showFinding(r.dataset.id)}});draw(fs);if(fs.length&&(!findingSelect.value||!fs.some(f=>f.finding_id===findingSelect.value))){{findingSelect.value=fs[0].finding_id;showFinding(fs[0].finding_id)}}if(!fs.length){{setOptions(claimSelect,[],'Chọn claim');setOptions(evidenceSelect,[],'Chọn evidence');details.innerHTML='<h2>Không có kết quả</h2><p>Hãy đổi company hoặc trạng thái finding.</p>'}}}}
companySelect.onchange=refresh;findingSelect.onchange=()=>showFinding(findingSelect.value);claimSelect.onchange=populateEvidence;evidenceSelect.onchange=showEvidence;document.querySelectorAll('[data-status]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('[data-status]').forEach(x=>x.classList.remove('active'));b.classList.add('active');activeStatus=b.dataset.status;refresh()}});refresh();
</script></body></html>'''
