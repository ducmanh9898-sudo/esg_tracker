"""Discover year-over-year numeric series within ESG or consolidated BCTC.

The arithmetic is descriptive. A change never becomes a contradiction without
review of the source, population, definition, boundary, and restatements.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from decimal import Decimal
import html
import json
from pathlib import Path
import re

from kg.corporate_adapter import digest
from kg.cross_report_scan import keys, normalized_label


YEARS = (2023, 2024, 2025)
SAFE_FAMILIES = {"employees", "profit_after_tax", "profit_before_tax"}


def _metric_key(claim, profile):
    """Use narrow families and exact labels; a local ID alone is not a metric."""
    families = sorted(k for k in keys(claim, profile)
                      if k.startswith("family:") and k[7:] in SAFE_FAMILIES)
    if len(families) == 1:
        return families[0]
    if len(families) > 1:
        return None
    label = normalized_label(claim.get("label") or "")
    if len(label) < 12:
        return None
    if label == "dau tho trong nuoc":
        context = ((claim.get("evidence") or [{}])[0].get("context_text") or "")
        row = re.search(r"(?:^|\n)\s*([12]\.[14])\s*(?:\n|$)", context)
        # This label occurs in two different source tables. A missing row code
        # is not enough to identify which denominator or quantity it means.
        return "label:" + label + ":row:" + row.group(1) if row else None
    metric = claim.get("metric_id")
    if metric and not metric.startswith("local:"):
        return "metric:" + metric + ":label:" + label
    return "label:" + label


def _eligible(claim):
    return (claim.get("company_id") == "BSR"
            and claim.get("source_document_type") in
            {"sustainability_report", "financial_statement"}
            and claim.get("observation_year") in YEARS
            and claim.get("value_status") == "available"
            and claim.get("value") is not None
            and claim.get("unit")
            and claim.get("variant") == "reported_result"
            and claim.get("dimension") in {"E", "S", "G", "X"})


def _source(claim):
    ev = (claim.get("evidence") or [{}])[0]
    alternate_page = ({76: 39, 106: 54}.get(ev.get("physical_page"))
                      if ev.get("source_file") == "BSR_2025_official.pdf" else None)
    return {"record_id": claim["record_id"], "report_year": claim["report_year"],
            "observation_year": claim["observation_year"],
            "report_type": "BCTC" if claim["report_type"] == "Financial" else "ESG",
            "source_file": ev.get("source_file"), "pdf_page": ev.get("physical_page"),
            "alternate_68page_pdf_page": alternate_page,
            "label": claim.get("label"), "value": claim["value"], "unit": claim["unit"],
            "quote": ev.get("exact_quote"), "context": ev.get("context_text"),
            "metric_id": claim.get("metric_id"),
            "period_type": claim.get("period_type"),
            "measurement_date": (claim.get("raw_record") or {}).get("period", {}).get("measurement_date"),
            "boundary": (claim.get("raw_record") or {}).get("boundary"),
            "restatement": (claim.get("raw_record") or {}).get("restatement")}


def _quality(claim):
    """Prefer the report for the observation year, then closest later report."""
    lag = claim["report_year"] - claim["observation_year"]
    return (0 if lag == 0 else 1 if lag > 0 else 2,
            abs(lag), claim["report_year"], claim["record_id"])


def _workforce_note_audit(selected):
    """Screen prior-year headcount stated in a later BCTC note's source quote."""
    results = []
    for report_year, later in selected.items():
        quote = ((later.get("evidence") or [{}])[0].get("exact_quote") or "")
        # This narrow pattern applies only to total-employee notes. The dot is
        # a Vietnamese thousands separator, not a decimal fraction.
        match = re.search(r"\([^)]*(20\d{2})[^)]*?(\d{1,3}\.\d{3})[^)]*\)", quote)
        if not match:
            continue
        observed_year, stated = int(match.group(1)), int(match.group(2).replace(".", ""))
        if observed_year not in selected or observed_year >= report_year:
            continue
        earlier = selected[observed_year]
        delta = stated - int(Decimal(str(earlier["value"])))
        results.append({"observation_year": observed_year,
                        "earlier_report": _source(earlier), "later_report": _source(later),
                        "later_report_comparative_value": stated,
                        "earlier_report_current_value": earlier["value"],
                        "delta": delta,
                        "screening_result": "different_source_text_values" if delta else "same_source_text_values",
                        "status": "NeedsReview",
                        "note": "Comparative value parsed from a source quote; not an extracted numeric record."})
    return results


def discover(claims, profile):
    groups = defaultdict(lambda: defaultdict(list))
    eligible_count = 0
    for claim in claims:
        if not _eligible(claim):
            continue
        eligible_count += 1
        metric = _metric_key(claim, profile)
        if not metric:
            continue
        key = (claim["company_id"], claim["source_document_type"],
               claim["dimension"], metric, claim["unit"])
        groups[key][claim["observation_year"]].append(claim)

    series, comparisons, blocked = [], [], []
    for group_key, by_year in sorted(groups.items()):
        if len(by_year) < 2:
            continue
        company, source_type, dimension, metric, unit = group_key
        # If one year has several distinct records at equal source priority,
        # keep the entire group for review rather than choosing one silently.
        selected, alternatives, ambiguous = {}, {}, []
        for year in sorted(by_year):
            ranked = sorted(by_year[year], key=_quality)
            best = _quality(ranked[0])[:3]
            tied = [c for c in ranked if _quality(c)[:3] == best]
            if len({str(c["value"]) for c in tied}) > 1:
                ambiguous.append(year)
                continue
            selected[year] = ranked[0]
            alternatives[year] = [_source(c) for c in ranked[1:]]
        if len(selected) < 2:
            if ambiguous:
                blocked.append({"report_type": "ESG" if source_type == "sustainability_report" else "BCTC",
                                "dimension": dimension, "metric_key": metric, "unit": unit,
                                "ambiguous_years": ambiguous,
                                "alternatives": {str(y): [_source(c) for c in by_year[y]]
                                                 for y in ambiguous}})
            continue
        series_id = "SER-" + digest(group_key)[:20]
        dimension_review_needed = dimension == "E" and metric == "label:nop ngan sach nha nuoc"
        series_row = {"series_id": series_id, "company_id": company,
                      "report_type": "ESG" if source_type == "sustainability_report" else "BCTC",
                      "source_document_type": source_type, "dimension": dimension,
                      "dimension_review_needed": dimension_review_needed,
                      "metric_key": metric, "unit": unit,
                      "observation_years": sorted(selected),
                      "complete_three_years": set(YEARS) <= set(selected),
                      "ambiguous_years_omitted": ambiguous,
                      "observations": [_source(selected[y]) for y in sorted(selected)],
                      "alternative_source_versions": {
                          str(y): values for y, values in alternatives.items() if values}}
        if source_type == "financial_statement" and metric == "family:employees":
            series_row["comparative_note_audit"] = _workforce_note_audit(selected)
        series.append(series_row)
        years = sorted(selected)
        year_pairs = list(zip(years, years[1:]))
        if len(years) > 2:
            year_pairs.append((years[0], years[-1]))
        for earlier_year, later_year in year_pairs:
            earlier, later = selected[earlier_year], selected[later_year]
            a, b = Decimal(str(earlier["value"])), Decimal(str(later["value"]))
            delta = b - a
            percent = None if a == 0 else delta / abs(a) * 100
            reasons = ["source_and_metric_definition_pending_human_review",
                       "restatement_pending_human_review"]
            for field in ("period_type", "metric_definition"):
                values = [earlier.get(field), later.get(field)]
                if any(v in (None, "", "unknown") for v in values):
                    reasons.append(field + "_unknown")
                elif values[0] != values[1]:
                    reasons.append(field + "_mismatch")
            for field in ("reporting_entity", "scope", "population", "counting_method"):
                values = [c["raw_record"]["boundary"].get(field) for c in (earlier, later)]
                if any(v in (None, "", "unknown") for v in values):
                    reasons.append(field + "_unknown")
                elif values[0] != values[1]:
                    reasons.append(field + "_mismatch")
            dates = [c["raw_record"]["period"].get("measurement_date") for c in (earlier, later)]
            if earlier.get("period_type") == later.get("period_type") == "at_date":
                if any(not date for date in dates):
                    reasons.append("measurement_date_unknown")
                elif len({date[5:] for date in dates}) != 1:
                    reasons.append("measurement_day_month_mismatch")
            if earlier["report_year"] == later["report_year"]:
                reasons.append("historical_values_from_one_report")
            comparison_id = "YRY-" + digest([series_id, earlier_year, later_year,
                                              earlier["record_id"], later["record_id"]])[:20]
            comparisons.append({"comparison_id": comparison_id, "series_id": series_id,
                                "comparison_kind": ("full_span" if later_year - earlier_year > 1
                                                    else "year_over_year"),
                                "from_year": earlier_year, "to_year": later_year,
                                "from": _source(earlier), "to": _source(later),
                                "delta": str(delta),
                                "percent_change": str(percent) if percent is not None else None,
                                "direction": "increase" if delta > 0 else "decrease" if delta < 0 else "unchanged",
                                "arithmetic_computed": True, "semantic_comparison_verified": False,
                                "status": "NeedsReview", "review_reasons": sorted(set(reasons))})
    summary = {"schema_version": "bsr-longitudinal-1.0",
               "records_available_for_screening": eligible_count,
               "series": len(series), "complete_three_year_series": sum(s["complete_three_years"] for s in series),
               "comparisons": len(comparisons),
               "series_by_report_type": dict(Counter(s["report_type"] for s in series)),
               "series_by_dimension": dict(Counter(s["dimension"] for s in series)),
               "dimension_review_needed_series": sum(s["dimension_review_needed"] for s in series),
               "blocked_ambiguous_groups": len(blocked),
               "blocked_groups": blocked,
               "comparative_notes_checked": sum(len(s.get("comparative_note_audit", [])) for s in series),
               "comparative_note_differences": sum(
                   a["screening_result"] == "different_source_text_values"
                   for s in series for a in s.get("comparative_note_audit", [])),
               "all_comparison_status": "NeedsReview",
               "limitations": ["Only extracted numeric records with explicit observation years are screened.",
                               "Matching labels and families are retrieval hypotheses, not verified definitions.",
                               "Arithmetic change is not evidence of a contradiction or a verified trend."]}
    return summary, series, comparisons


def run(records_path: Path, profile_path: Path, output: Path):
    if output.exists():
        raise ValueError("output_exists_choose_new_directory")
    claims = json.loads(records_path.read_text(encoding="utf-8"))
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    summary, series, comparisons = discover(claims, profile)
    output.mkdir(parents=True)
    for name, value in (("summary", summary), ("series", series), ("comparisons", comparisons)):
        (output / (name + ".json")).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    graph = {"base_graph": "../graph/graph.json",
             "nodes": [{"id": s["series_id"], "type": "TemporalSeries",
                        "report_type": s["report_type"], "metric_key": s["metric_key"]}
                       for s in series], "edges": []}
    for c in comparisons:
        graph["nodes"].append({"id": c["comparison_id"], "type": "TemporalComparison",
                               "status": c["status"], "from_year": c["from_year"],
                               "to_year": c["to_year"], "delta": c["delta"]})
        for source, target, relation in ((c["comparison_id"], c["series_id"], "PART_OF_SERIES"),
                                         (c["comparison_id"], "claim:" + c["from"]["record_id"], "FROM_RECORD"),
                                         (c["comparison_id"], "claim:" + c["to"]["record_id"], "TO_RECORD")):
            graph["edges"].append({"source": source, "target": target, "relation": relation})
    for s in series:
        for audit in s.get("comparative_note_audit", []):
            audit_id = "AUD-" + digest([s["series_id"], audit["observation_year"],
                                        audit["later_report"]["record_id"]])[:20]
            graph["nodes"].append({"id": audit_id, "type": "SourceVersionAudit",
                                   "status": audit["status"], "delta": audit["delta"],
                                   "screening_result": audit["screening_result"]})
            for target, relation in ((s["series_id"], "PART_OF_SERIES"),
                                     ("claim:" + audit["earlier_report"]["record_id"], "EARLIER_SOURCE"),
                                     ("claim:" + audit["later_report"]["record_id"], "LATER_SOURCE")):
                graph["edges"].append({"source": audit_id, "target": target, "relation": relation})
    (output / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n",
                                       encoding="utf-8")
    rows = []
    for c in comparisons:
        left, right = c["from"], c["to"]
        cells = [c["comparison_kind"], c["from_year"], c["to_year"],
                 left["report_type"], left["label"], left["value"], right["value"],
                 left["unit"], c["delta"],
                 f"{Decimal(c['percent_change']):.2f}" if c["percent_change"] is not None else "—",
                 left["source_file"],
                 f"{left['pdf_page']} (68 trang: {left['alternate_68page_pdf_page']})"
                 if left["alternate_68page_pdf_page"] else left["pdf_page"], left["quote"],
                 right["source_file"],
                 f"{right['pdf_page']} (68 trang: {right['alternate_68page_pdf_page']})"
                 if right["alternate_68page_pdf_page"] else right["pdf_page"],
                 right["quote"], c["status"]]
        rows.append("<tr>" + "".join("<td>" + html.escape(str(v)) + "</td>" for v in cells) + "</tr>")
    header = ["Kiểu", "Từ năm", "Đến năm", "Báo cáo", "Chỉ tiêu", "Giá trị đầu",
              "Giá trị cuối", "Đơn vị", "Chênh lệch", "% thay đổi", "PDF đầu",
              "Trang", "Trích dẫn đầu", "PDF cuối", "Trang", "Trích dẫn cuối", "Trạng thái"]
    page = "<!doctype html><meta charset='utf-8'><title>BSR theo năm</title>"
    page += "<h1>BSR: so sánh chỉ tiêu theo năm đo</h1>"
    page += "<p>Chênh lệch chỉ là phép tính từ dữ liệu đã trích. Mọi cặp cần kiểm tra nguồn, phạm vi và định nghĩa.</p>"
    page += (f"<p>{summary['series']} chuỗi; {summary['comparisons']} phép tính; "
             f"{summary['blocked_ambiguous_groups']} nhóm nhãn trùng nhưng giá trị khác nhau bị giữ lại để rà soát.</p>")
    if summary["dimension_review_needed_series"]:
        page += "<p>Nhãn ‘Nộp Ngân sách nhà nước’ được Extract gắn E; cần xem lại phân loại, không xem đây là chuỗi môi trường đã xác nhận.</p>"
    page += "<table border='1'><thead><tr>" + "".join("<th>" + html.escape(h) + "</th>" for h in header)
    page += "</tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    audit_rows = []
    for s in series:
        for a in s.get("comparative_note_audit", []):
            cells = [a["observation_year"], a["earlier_report"]["source_file"],
                     a["earlier_report"]["pdf_page"], a["earlier_report_current_value"],
                     a["later_report"]["source_file"], a["later_report"]["pdf_page"],
                     a["later_report_comparative_value"], a["delta"],
                     a["later_report"]["quote"], a["status"]]
            audit_rows.append("<tr>" + "".join("<td>" + html.escape(str(v)) + "</td>" for v in cells) + "</tr>")
    if audit_rows:
        page += "<h2>Kiểm tra số so sánh của BCTC năm sau</h2>"
        page += "<p>Giá trị ở báo cáo năm sau được đọc từ câu trích dẫn, chưa thành bản ghi số riêng.</p>"
        page += "<table border='1'><thead><tr>" + "".join(
            "<th>" + html.escape(h) + "</th>" for h in
            ["Năm đo", "BCTC gốc", "Trang", "Giá trị gốc", "BCTC sau", "Trang",
             "Số so sánh", "Chênh lệch", "Câu nguồn", "Trạng thái"])
        page += "</tr></thead><tbody>" + "".join(audit_rows) + "</tbody></table>"
    (output / "report.html").write_text(page, encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.records, args.profile, args.output_dir), ensure_ascii=False))


if __name__ == "__main__":
    main()
