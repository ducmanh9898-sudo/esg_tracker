"""Show every selected BSR ESG claim without implying every claim was reviewed."""
from __future__ import annotations

import html
from collections import Counter
from decimal import Decimal


OUTCOME_LABELS = {
    "Contradicted": "Có số liệu không khớp",
    "NeedsReview": "Cần kiểm tra thêm",
    "Supported": "Phù hợp phép kiểm tra",
    "Skipped": "Chưa thể kiểm tra",
    "NotEvaluated": "Cần xác minh thêm",
}

REASON_LABELS = {
    "missing_role_record": "thiếu chỉ tiêu cần so", "missing_scope1_plus_scope2_total": "thiếu tổng Scope 1 + Scope 2 được định nghĩa rõ",
    "mapping_unverified": "mapping chỉ tiêu chưa xác minh", "period_unknown_or_unverified": "kỳ đo chưa xác minh",
    "reporting_boundary_unknown_or_unverified": "ranh giới báo cáo chưa xác minh", "source_review_or_provenance_incomplete": "nguồn chưa được review đủ",
    "missing_board_independent_count": "thiếu số thành viên độc lập", "missing_employees_female_count": "thiếu số lao động nữ",
    "board_id_unknown": "chưa xác định cùng HĐQT", "comparison_frame_unknown": "chưa xác định cùng thời điểm/quần thể",
    "graph_context_review_missing": "context so sánh chưa được review đủ", "metric_definition_unverified": "định nghĩa chỉ tiêu chưa xác minh",
    "period_type_unverified": "loại kỳ đo chưa xác minh", "reporting_boundary_unknown": "ranh giới tổ chức chưa rõ",
    "reporting_boundary_unverified": "ranh giới tổ chức chưa xác minh", "counting_method_unknown": "phương pháp đếm chưa rõ",
    "subset_within_total": "số thuộc tập con không vượt tổng",
    "boundary_unverified": "ranh giới ESG/BCTC chưa đối chiếu", "measurement_date_unverified": "ngày đo chưa xác minh",
    "measurement_period_mismatch": "kỳ đo khác nhau",
    "variant_mismatch": "biến thể số liệu khác nhau",
}

METRIC_REFERENCE_NOTE = {
    "ghg_total_unspecified": "Chưa biết tổng này gồm những Scope nào, nên chưa gán được vào một disclosure cụ thể.",
    "ghg_scope1": "Cần xác minh gross/net, các khí được tính, ranh giới và phương pháp.",
    "ghg_scope2": "Cần xác minh cách tính Scope 2, ranh giới và hệ số phát thải.",
    "ghg_intensity": "Cần xác minh mẫu số, Scope được tính và phương pháp.",
    "ghg_intensity_reduction": "Giảm cường độ không tự động là giảm tuyệt đối lượng phát thải.",
    "eii": "Cần định nghĩa EII và cách tính trước khi coi đây là cường độ năng lượng theo GRI.",
    "solar_capacity": "Công suất lắp đặt/dự kiến không phải lượng năng lượng đã tiêu thụ.",
    "freshwater_use": "Chưa rõ đây là lượng nước khai thác hay nước tiêu thụ; hai khái niệm khác nhau.",
    "waste_total": "Cần xác minh phạm vi chất thải phát sinh và phân loại cấu phần.",
    "waste_hazardous": "Cần xác minh cách xác định chất thải nguy hại và quan hệ với tổng.",
    "waste_nonhazardous": "Cần xác minh cách xác định chất thải không nguy hại và quan hệ với tổng.",
    "waste_recycled": "Cần xác minh hoạt động tái chế/thu hồi và phạm vi xử lý.",
    "waste_other_treatment": "Dòng Extract gộp chôn lấp/xử lý cuối; cần phân biệt các phương thức xử lý.",
    "employees_total": "Cần xác minh phương pháp đếm, ngày chốt và phạm vi lao động.",
    "employees_male": "Cần xác minh cùng quần thể, cách đếm và ngày đo với tổng lao động.",
    "employees_female": "Cần xác minh cùng quần thể, cách đếm và ngày đo với tổng lao động.",
    "female_share": "Tỷ lệ tổng chưa cung cấp đầy đủ phân tách theo nhóm nhân viên.",
    "male_share": "Tỷ lệ tổng chưa cung cấp đầy đủ phân tách theo nhóm nhân viên.",
    "board_total": "Số lượng HĐQT chỉ là một phần thông tin về cơ cấu quản trị.",
    "board_independent": "Số thành viên độc lập chỉ là một phần thông tin về cơ cấu quản trị.",
    "chair_ceo_separate": "Tách Chủ tịch và CEO chưa trả lời việc Chủ tịch có giữ vai trò điều hành cấp cao khác hay không.",
}

REVIEWED_MAPPING_NOTE = {
    "Disclosure 2-11": "Cần xem Chủ tịch có giữ vai trò điều hành cấp cao nào khác, không chỉ chức danh CEO.",
    "IFRS S1 26–27": "Cần thông tin về quy trình và trách nhiệm giám sát rủi ro/cơ hội bền vững; tách chức danh chưa đủ.",
    "Disclosure 305-1": "Cần kiểm tra phát thải gộp, các khí, ranh giới và phương pháp tính.",
    "IFRS S2 29(a)(i)(1)": "Số Scope 1 chỉ là một thành phần; cần kiểm tra các yêu cầu khác của IFRS S2.",
    "EM-RM-110a.1": "Cần xác minh ngành áp dụng, phát thải gộp toàn cầu và tỷ lệ chịu quy định hạn chế phát thải.",
}
RELATIONSHIP_LABELS = {"related": "liên quan", "partially_addresses": "đáp ứng một phần nội dung",
                       "equivalent": "tương đương khái niệm", "broader": "rộng hơn", "narrower": "hẹp hơn",
                       "complementary": "bổ trợ"}
FINANCIAL_SCOPE_LABELS = {"consolidated_group": "báo cáo hợp nhất", "separate_parent": "báo cáo riêng",
                          "not_stated": "chưa nêu rõ"}

UNITS = {"person": "người", "percent": "%", "tonne": "tấn", "m3": "m³",
         "kgCO2e/t_product": "kgCO₂e/tấn sản phẩm", "boolean": ""}


def esc(value):
    return html.escape(str(value if value is not None else "Chưa rõ"), quote=True)


def show_value(value, unit):
    if isinstance(value, bool):
        return "Có" if value else "Không"
    if value is None:
        return "Chưa rõ"
    formatted = format(Decimal(str(value)), ",f").replace(",", "#").replace(".", ",").replace("#", ".")
    return formatted + (" " + UNITS.get(unit, unit) if unit != "boolean" else "")


def claim_catalog(data):
    claims = sorted(data["normalized_claims"], key=lambda row: (-row["report_year"], row["dimension"], row["label"]))
    official = {row["claim_id"]: row for row in data["source_provenance_audit"]["attached_evidence"]}
    evidence_nodes = {row.get("evidenceId"): row for row in data["graph"]["nodes"] if row.get("evidenceId")}
    reviews = {row["claim_id"]: row for row in data["claim_review"]["claims"]}
    evaluated = {}
    for event in data["rule_evaluations"]:
        for claim_id in event["input_claim_ids"]:
            evaluated.setdefault(claim_id, []).append(event)
    by_year = Counter(row["report_year"] for row in claims)
    review_counts = data["claim_review"]["counts"]
    rows = []

    for claim in claims:
        claim_id = claim["record_id"]
        review = reviews[claim_id]
        ev = claim["evidence"][0]
        year = claim["report_year"]
        observation = claim.get("observation_year")
        full_value = show_value(claim["value"], claim["unit"])
        matched = official.get(claim_id)
        if matched:
            source_file = "BSR_2025_official.pdf"
            page = f"PDF vật lý trang {matched['official_page']}"
            source_status = ("Giá trị/nhãn và mã GRI do BSR tự ghi đã đối chiếu PDF bởi AI"
                             if "gri_code" in matched["review_scope"] else
                             "Giá trị/nhãn đã đối chiếu PDF bởi AI")
            source_class = "corroborated"
            quote = evidence_nodes.get(matched["evidence_id"], {}).get("originalText")
            source_note = (f"Đối chiếu giới hạn ở {matched['review_scope']}; "
                           "các trường context khác và human adjudication có thể vẫn chưa hoàn tất.")
        else:
            source_file = ev["source_file"]
            page = "Trang do Extract khai báo: " + ", ".join(map(str, ev["source_pages"]))
            source_status = "Chưa đối chiếu PDF nguồn"
            source_class = "extract_only"
            quote = None
            source_note = ("Tên file và trang đến từ JSON Extract. Chưa xác minh nguyên văn và locator trên PDF nguồn; "
                           "bản PDF 68 trang do Extract khai báo cho năm 2025 hiện không có trong workspace."
                           if year == 2025 else
                           "Tên file và trang đến từ JSON Extract; PDF năm này chưa được đối chiếu trong demo.")
            if review["source_locator_issue"]:
                issue = review["source_locator_issue"]
                source_status = "Locator Extract lệch trang · cần sửa"
                source_class = "locator_issue"
                source_note = (f"{issue['finding_vi']} PDF chính thức trang vật lý "
                               f"{issue['official_pdf_physical_page_with_value']} có đoạn “{issue['official_quote']}”. "
                               f"Issue {issue['issue_id']} thuộc Extract; chưa nối thành evidence đã xác nhận cho claim này.")
        events = evaluated.get(claim_id, [])
        if events:
            checks = "; ".join(f"{event['rule_id']}: " + ", ".join(REASON_LABELS.get(reason, reason) for reason in event["reasons"])
                               for event in events)
            status = OUTCOME_LABELS[review["rule_outcome"]]
            status_class = review["rule_outcome"]
        else:
            checks = "Chưa có cặp dữ liệu và rule đã review phù hợp; cần đối chiếu nguồn/định nghĩa trước khi kết luận."
            status = OUTCOME_LABELS["NotEvaluated"]
            status_class = "NotEvaluated"
        mappings = review["standards"]["reviewed_relationships"]
        refs = review["standards"]["reference_candidates"]
        standard_summary = ", ".join(dict.fromkeys(
            [m["family"] + " " + m["reference_code"] for m in mappings] + [r["reference"] for r in refs]))
        reference_issue = review["standard_reference_issue"]
        finance = review["financial"]["candidates"]
        finance_summary = (f"{len(finance)} liên kết ứng viên · chưa đủ điều kiện so"
                           if finance else "Chưa có chỉ tiêu BCTC tương đương")
        standard_details = "".join(
            f'<p><b>{esc(m["family"])} {esc(m["reference_code"])}:</b> quan hệ {esc(RELATIONSHIP_LABELS.get(m["relationship_type"], m["relationship_type"]))}; '
            f'{"mapping quan hệ đã xác minh" if m["verification_status"] == "verified" else "mapping ứng viên"}. '
            f'Chưa chứng minh công bố đáp ứng tiêu chuẩn. {esc(REVIEWED_MAPPING_NOTE.get(m["reference_code"], "Cần xem các điều kiện còn thiếu của tiêu chuẩn."))} '
            f'<a href="{esc(m["source_url"])}" target="_blank" rel="noopener noreferrer">Văn bản tiêu chuẩn</a></p>'
            for m in mappings)
        standard_details += "".join(
            f'<p><b>{esc(r["reference"])}:</b> tham chiếu ứng viên. {esc(METRIC_REFERENCE_NOTE[claim["metric_id"]])} '
            f'<a href="{esc(r["source_url"])}" target="_blank" rel="noopener noreferrer">Văn bản tiêu chuẩn</a></p>' for r in refs)
        if reference_issue:
            standard_details += (f'<p><b>Mã BSR tự gắn: {esc(reference_issue["source_reported_reference"])} · '
                                 f'câu hỏi review:</b> {esc(reference_issue["review_question_vi"])} '
                                 f'{esc(reference_issue["interpretation_limit_vi"])}</p>')
        finance_details = "".join(
            f'<p><b>{esc(f["financial_disclosure_id"])}:</b> {esc(show_value(f["financial_value"], f["financial_unit"]))}; '
            f'{esc(f["financial_report"])} · trang Extract {esc(", ".join(map(str, f["financial_pages"])))}, '
            f'phạm vi {esc(FINANCIAL_SCOPE_LABELS.get(f["financial_scope"], f["financial_scope"]))}. Chặn so sánh: '
            f'{esc(", ".join(REASON_LABELS.get(reason, reason.replace("_", " ")) for reason in f["reasons"]))}.</p>'
            for f in finance)
        if not finance_details:
            finance_details = "<p>Không có record BCTC cùng định nghĩa được nối; đây không phải bằng chứng BSR thiếu công bố.</p>"
        temporal_details = "".join(
            f'<p>{esc(t["from_year"])} → {esc(t["to_year"])} · '
            f'{esc(t["from_claim_id"])} / {esc(t["to_claim_id"])}: ứng viên đối chiếu, '
            f'chưa đủ điều kiện ({esc(", ".join(REASON_LABELS.get(reason, reason) for reason in t["guards"]))}).</p>'
            for t in review["cross_year_candidates"])
        signal_details = "".join(
            f'<p><b>{esc(s["rule_id"])} · {"số học sơ bộ khớp" if s["arithmetic_observation"] == "matched" else "cần giải thích chênh lệch/bối cảnh"}:</b> {esc(s["summary"])} '
            f'(ứng viên điều tra; rule demo chưa qua guard đầy đủ, không vào kết quả chính).</p>'
            for s in review["screening_signals"])
        signal_hint = (f'<small class="claim-signal">{len(review["screening_signals"])} tín hiệu thử nghiệm cần tra cứu trong Chi tiết</small>'
                       if review["screening_signals"] else "")
        claim_path = (f'<div class="claim-path" aria-label="Liên kết tri thức của claim"><div class="claim-path-root">'
                      f'Claim<br><code>{esc(claim_id)}</code></div><div class="claim-path-links">'
                      f'<span>Phép kiểm tra: {esc(status)}</span>'
                      f'<span>GRI: {esc(standard_summary or "chưa có tham chiếu")}; ứng viên/chỉ ngữ cảnh</span>'
                      f'<span>IFRS S1 §20–22: liên kết thông tin chưa xác lập</span>'
                      f'<span>BCTC: {esc(finance_summary)}</span>'
                      f'<span>Nguồn: {esc(source_file)} · {esc(page)}</span></div></div>')
        period = str(year) if observation in (None, year) else f"{year} · số liệu {observation}"
        search_text = " ".join([claim_id, claim["label"], claim["metric_id"], str(year),
                                str(observation or ""), claim["dimension"], source_file, page, status])
        rows.append(f'''<tr class="claim-row" data-year="{year}" data-dimension="{esc(claim['dimension'])}" data-search="{esc(search_text)}">
          <td><strong>{esc(period)}</strong><small>{esc(claim['dimension'])} · {esc(claim['topic'])}</small></td>
          <td><b>{esc(claim['label'])}</b><small>{esc(full_value)}</small></td>
          <td><span class="claim-status {esc(status_class)}">{esc(status)}</span><small>{esc(checks)}</small>{signal_hint}</td>
          <td><b>{esc(standard_summary or 'Chưa có tham chiếu cụ thể')}</b><small>Chưa kết luận tuân thủ tiêu chuẩn</small>{'<small class="claim-signal">Mã GRI BSR tự ghi cần review</small>' if reference_issue else ''}</td>
          <td><b>{esc(finance_summary)}</b><small>IFRS S1 §20–22: liên kết cùng reporting entity chưa xác minh</small></td>
          <td><b>{esc(source_file)}</b><small>{esc(page)}</small><span class="claim-source {esc(source_class)}">{esc(source_status)}</span></td>
          <td><details><summary>Chi tiết</summary><div class="claim-extra">{claim_path}<p><b>Claim ID:</b> <code>{esc(claim_id)}</code></p>
            <p><b>Extract:</b> <code>{esc(ev['source_extract_path'])}</code> · <code>{esc(ev['json_pointer'])}</code></p>
            {f'<p><b>Nguyên văn đã đối chiếu:</b> “{esc(quote)}”</p>' if quote else '<p>Chưa có nguyên văn PDF đã đối chiếu cho claim này.</p>'}
            <p>{esc(source_note)}</p><p><b>Lý do phép kiểm tra:</b> {esc(checks)}</p>
            <p><b>Đối chiếu tiêu chuẩn:</b> {standard_details}</p>
            <p><b>IFRS S1 §20–22:</b> Chưa xác minh cùng reporting entity với BCTC và chưa xác lập tác động tài chính của chỉ tiêu này.</p>
            <p><b>Đối chiếu BCTC:</b> {finance_details}</p>
            <p><b>Liên kết qua các năm:</b> {temporal_details or 'Chưa có cặp cùng metric để đối chiếu qua các năm.'}</p>
            <p><b>Tín hiệu điều tra sơ bộ:</b> {signal_details or 'Chưa có tín hiệu từ bộ rule thử nghiệm.'}</p>
            </div></details></td></tr>''')

    section = f'''<section id="claims"><h2>30 claim ESG đã chọn</h2>
      <p class="intro">{by_year[2023]} claim từ báo cáo 2023, {by_year[2024]} từ 2024 và {by_year[2025]} từ 2025. Mỗi claim có ba phần: phép kiểm tra dữ liệu, tham chiếu GRI/tiêu chuẩn và khả năng nối BCTC. Kết quả hiện có {review_counts.get('Supported', 0)} claim phù hợp với một phép kiểm tra, {review_counts.get('NeedsReview', 0)} cần review, {review_counts.get('Skipped', 0)} bị chặn và {review_counts.get('NotEvaluated', 0)} chưa có rule phù hợp. Đây không phải xác nhận mọi claim đều đúng hay BSR tuân thủ tiêu chuẩn.</p>
      <div class="claim-tools"><label>Năm báo cáo <select id="claim-year"><option value="all">Tất cả</option>
        <option value="2025">2025 ({by_year[2025]})</option><option value="2024">2024 ({by_year[2024]})</option><option value="2023">2023 ({by_year[2023]})</option></select></label>
        <label>Chủ đề <select id="claim-dimension"><option value="all">Tất cả E/S/G</option><option value="E">E · Môi trường</option><option value="S">S · Xã hội</option><option value="G">G · Quản trị</option></select></label>
        <label>Tìm chỉ tiêu <input id="claim-search" type="search" placeholder="Tên, giá trị, ID hoặc file"></label>
        <output id="claim-visible-count" aria-live="polite">Đang hiển thị {len(claims)}/{len(claims)} claim</output></div>
      <div class="claim-table-wrap"><table class="claim-table"><thead><tr><th scope="col">Báo cáo / kỳ đo</th><th scope="col">Chỉ tiêu và giá trị</th>
        <th scope="col">Kết quả phép kiểm tra</th><th scope="col">GRI / tiêu chuẩn</th><th scope="col">BCTC / IFRS S1</th><th scope="col">Nguồn và trang</th><th scope="col">Truy vết</th></tr></thead>
        <tbody>{''.join(rows)}</tbody></table></div>
      <p class="claim-help">“Đã đối chiếu PDF” chỉ áp dụng cho giá trị/nhãn được ghi rõ trên từng claim; không có nghĩa toàn bộ context đã được người duyệt. Trang của các claim còn lại chỉ là locator do Extract khai báo.</p></section>'''
    return section


CATALOG_STYLE = '''
.claim-table-wrap .claim-table{min-width:1350px}.claim-table td:nth-child(3){min-width:185px}.claim-table td:nth-child(4),.claim-table td:nth-child(5){min-width:170px}.claim-table td:nth-child(6){min-width:190px}
.claim-tools{display:flex;align-items:end;gap:12px;flex-wrap:wrap;margin:22px 0}.claim-tools label{display:grid;gap:5px;font-size:13px;font-weight:700;color:#385662}.claim-tools select,.claim-tools input{font:15px 'Segoe UI',Arial,sans-serif;padding:9px 11px;border:1px solid #b9c9c8;border-radius:8px;background:white;color:#142b37}.claim-tools input{min-width:245px}
.claim-tools output{font-size:14px;color:#385662;padding:10px 0}.claim-table-wrap{overflow:auto;background:white;border:1px solid #dce5e3;border-radius:16px;box-shadow:0 8px 24px #163f3610}.claim-table{width:100%;border-collapse:collapse;min-width:900px}.claim-table th,.claim-table td{text-align:left;vertical-align:top;padding:13px 14px;border-bottom:1px solid #e4ece9}.claim-table th{background:#eaf3f1;font-size:13px}.claim-table td{font-size:14px}.claim-table td small{display:block;color:#55717d;font-size:12px;margin-top:4px}.claim-table tr:last-child td{border-bottom:0}.claim-table b,.claim-table strong{font-weight:700}
.claim-table details{min-width:72px}.claim-table summary{cursor:pointer;color:#076965;font-weight:700}.claim-extra{min-width:260px;max-width:370px;font-size:12px;color:#385662}.claim-extra p{margin:7px 0}.claim-extra code{font-size:11px;overflow-wrap:anywhere}.claim-status{display:inline-block;border-radius:100px;padding:4px 8px;font-size:12px;font-weight:800;background:#edf1f2;color:#455f6a}.claim-status.NeedsReview{background:#fff0d4;color:#7c4c07}.claim-status.Supported{background:#ddf5e8;color:#12633e}.claim-status.Contradicted{background:#ffe5e6;color:#9d2d35}.claim-status.not_assessed{background:#f2f3f4;color:#53656c}.claim-source{display:block;font-size:12px;margin-top:6px;color:#6a5965}.claim-source.corroborated{color:#12633e}.claim-help{font-size:13px;color:#55717d;margin-top:12px}
.claim-table-wrap{overflow:visible}.claim-table-wrap .claim-table{min-width:0}.claim-table thead{display:none}.claim-table tbody{display:block}.claim-table tr.claim-row{display:grid;grid-template-columns:110px minmax(150px,1fr) minmax(230px,1.4fr) minmax(190px,1.1fr);gap:0 16px;border-bottom:1px solid #e4ece9}.claim-table tr.claim-row[hidden]{display:none}.claim-table td{display:block;border:0;min-width:0!important;padding:12px 8px}.claim-table td:nth-child(1){grid-column:1;grid-row:1 / span 2}.claim-table td:nth-child(2){grid-column:2;grid-row:1}.claim-table td:nth-child(3){grid-column:3;grid-row:1}.claim-table td:nth-child(4){grid-column:2;grid-row:2}.claim-table td:nth-child(5){grid-column:3;grid-row:2}.claim-table td:nth-child(6){grid-column:4;grid-row:1}.claim-table td:nth-child(7){grid-column:4;grid-row:2}.claim-table td:nth-child(4)::before,.claim-table td:nth-child(5)::before{display:block;font-size:11px;font-weight:800;letter-spacing:.05em;color:#607a81;margin-bottom:5px}.claim-table td:nth-child(4)::before{content:'GRI / TIÊU CHUẨN'}.claim-table td:nth-child(5)::before{content:'BCTC / IFRS S1'}.claim-table .claim-extra{max-width:450px}.claim-table tr.claim-row:hover{background:#f8fbfa}
@media(max-width:800px){.claim-table tr.claim-row{grid-template-columns:1fr 1fr}.claim-table td:nth-child(1){grid-column:1;grid-row:1}.claim-table td:nth-child(2){grid-column:2;grid-row:1}.claim-table td:nth-child(3){grid-column:1 / -1;grid-row:2}.claim-table td:nth-child(4){grid-column:1;grid-row:3}.claim-table td:nth-child(5){grid-column:2;grid-row:3}.claim-table td:nth-child(6){grid-column:1;grid-row:4}.claim-table td:nth-child(7){grid-column:2;grid-row:4}}
.claim-table td:nth-child(7){grid-column:1/-1;grid-row:3;padding-top:0}.claim-table .claim-extra{max-width:none}.claim-path{display:grid;grid-template-columns:110px 1fr;gap:12px;align-items:center;margin:12px 0;padding:10px;border:1px solid #d8e6e2;border-radius:10px;background:#f7fbfa}.claim-path-root{padding:10px 6px;border-radius:8px;background:#dcefeb;text-align:center;font-weight:800}.claim-path-root code{font-size:9px}.claim-path-links{display:grid;gap:5px}.claim-path-links span{border-left:3px solid #7eb7ad;padding:4px 6px;background:white;font-size:11px}@media(max-width:800px){.claim-table td:nth-child(7){grid-column:1/-1;grid-row:5}}
'''


CATALOG_SCRIPT = '''
const claimYear=document.getElementById('claim-year');
const claimDimension=document.getElementById('claim-dimension');
const claimSearch=document.getElementById('claim-search');
const claimRows=document.querySelectorAll('.claim-row');
const claimCount=document.getElementById('claim-visible-count');
const normalizeClaim=s=>s.normalize('NFD').toLocaleLowerCase('vi').replace(/[\\u0300-\\u036f]/g,'').replace(/đ/g,'d');
function filterClaims(){
  const year=claimYear.value, dimension=claimDimension.value, term=normalizeClaim(claimSearch.value.trim());
  let count=0;
  claimRows.forEach(row=>{
    const visible=(year==='all'||row.dataset.year===year)&&(dimension==='all'||row.dataset.dimension===dimension)&&normalizeClaim(row.dataset.search).includes(term);
    row.hidden=!visible;
    if(visible)count++;
  });
  claimCount.textContent=`Đang hiển thị ${count}/${claimRows.length} claim`;
}
[claimYear,claimDimension,claimSearch].forEach(control=>control.addEventListener('input',filterClaims));
'''
