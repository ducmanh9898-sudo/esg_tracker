"""Offline cross-report discovery. Candidates are not adjudicated contradictions."""
import argparse
import csv
from datetime import datetime, timezone
from collections import Counter, defaultdict
from decimal import Decimal
import html
import json
import os
from pathlib import Path
import re
import tempfile

from kg.corporate_adapter import digest
from kg.corporate_assessment import assess, proposal
from kg.corporate_pipeline import prepare, review_template, write_json
from kg.text_normalize import normalized_label
from handoff.bsr_extract_2023_2025_v1.validate import sha256


def keys(claim, profile):
    result = set()
    # `local:` IDs are extraction aliases and may be shared by unlike ratios.
    # Require label/family evidence for cross-report retrieval in those cases.
    if claim["metric_id"] and not claim["metric_id"].startswith("local:"):
        result.add("metric:" + claim["metric_id"])
    label = normalized_label(claim["label"] or "")
    if len(label) >= 12:
        result.add("label:" + label)
    for family in profile.get("metric_families", []):
        if (any(re.search(p, label) for p in family["patterns"])
                and not any(re.search(p, label) for p in family.get("exclude_patterns", []))):
            result.add("family:" + family["id"])
    return result


def known_consolidation(claim):
    boundary = (claim.get("raw_record") or {}).get("boundary") or {}
    value = boundary.get("consolidation")
    return value if value not in (None, "", "unknown") else None


def document_type(claim):
    return (claim.get("source_document_type") or
            (claim.get("raw_document") or {}).get("source_document_type") or
            ("financial_statement" if claim["report_type"] == "Financial" else
             "sustainability_report"))


def routes(profile):
    configured = profile.get("comparison_routes", [
        {"id": "esg_financial", "left": "sustainability_report",
         "right": "financial_statement", "dimensions": ["E", "S", "G"]}])
    allowed = {("sustainability_report", "financial_statement"),
               ("sustainability_report", "annual_report")}
    if (not isinstance(configured, list) or not configured or
            any(not isinstance(r, dict) or
                (r.get("left"), r.get("right")) not in allowed or
                not isinstance(r.get("id"), str) or not r["id"] or
                not isinstance(r.get("dimensions"), list) or
                not r["dimensions"] or
                not set(r["dimensions"]) <= {"E", "S", "G"}
                for r in configured)):
        raise ValueError("invalid_comparison_routes")
    if len({r["id"] for r in configured}) != len(configured):
        raise ValueError("duplicate_comparison_route_id")
    return configured


def discover(claims, profile, explicit=()):
    index = {c["record_id"]: c for c in claims}
    if len(index) != len(claims):
        raise ValueError("duplicate_record_id")
    selected_routes = routes(profile)
    groups = defaultdict(lambda: defaultdict(list))
    coverage = {}
    for c in claims:
        variant_hint = (c["report_type"] == "ESG" and c["variant"] == "unknown" and
                        c.get("metric_id") in profile.get("candidate_unknown_variant_metric_ids", []))
        eligible = (c["value_status"] == "available" and c["value"] is not None
                    and (c["variant"] == "reported_result" or variant_hint))
        labels = keys(c, profile) if eligible else set()
        coverage[c["record_id"]] = {"record_id": c["record_id"],
                                   "status": "no_candidate", "candidate_ids": [],
                                   "reason": "no_cross_report_match" if labels else "no_numeric_matching_key"}
        for key in labels:
            groups[(c["company_id"], key)][document_type(c)].append(c)
    rows = {}
    for (_, key), types in groups.items():
        for route in selected_routes:
            for a in types[route["left"]]:
                for b in types[route["right"]]:
                    if (a.get("dimension", "G") not in route["dimensions"] or
                            a.get("report_id", a["record_id"]) == b.get("report_id", b["record_id"])):
                        continue
                    ya, yb = a["observation_year"], b["observation_year"]
                    # A report year is only a retrieval hint when one side lacks
                    # an observation year. It never fills the missing period.
                    year_hint = False
                    if ya is None or yb is None:
                        if not profile.get("include_report_year_hints", False):
                            continue
                        # Only an ESG headline may enter this weaker queue.
                        # BCTC comparative columns with unknown years must not
                        # be mistaken for the current-year amount.
                        if (ya is not None or yb is None or
                                a["report_year"] != b["report_year"] or
                                yb != b["report_year"]):
                            continue
                        year_hint = True
                    elif ya != yb:
                        continue
                    ca, cb = known_consolidation(a), known_consolidation(b)
                    if ca is not None and cb is not None and ca != cb:
                        continue
                    row = proposal([a["record_id"], b["record_id"]])
                    item = rows.setdefault(row["comparison_id"],
                                           {**row, "match_basis": [], "comparison_route": route["id"]})
                    item["match_basis"].append(key)
                    if year_hint:
                        item["match_basis"].append("report_year_hint_unverified")
                    if a["variant"] == "unknown":
                        item["match_basis"].append("variant_unknown_unverified")
    for row in explicit:
        selected = [index[i] for i in row["record_ids"]]
        pair = {document_type(c) for c in selected}
        if (len(selected) != 2 or row["relation"] != "equal"
                or len({c["company_id"] for c in selected}) != 1
                or len({c.get("report_id", c["record_id"]) for c in selected}) != 2
                or not any(pair == {r["left"], r["right"]} and
                           any(c.get("dimension", "G") in r["dimensions"] and
                               document_type(c) == r["left"] for c in selected)
                           for r in selected_routes)):
            raise ValueError("explicit_pair_not_cross_report_same_company")
        p = proposal(row["record_ids"])
        route = next(r["id"] for r in selected_routes
                     if pair == {r["left"], r["right"]})
        rows.setdefault(p["comparison_id"], {**p, "match_basis": [],
                                              "comparison_route": route})["match_basis"].append("explicit")
    for row in rows.values():
        row["match_basis"] = sorted(set(row["match_basis"]))
        for identity in row["record_ids"]:
            coverage[identity]["status"] = "candidate_pending_review"
            coverage[identity]["candidate_ids"].append(row["comparison_id"])
    return sorted(rows.values(), key=lambda r: r["comparison_id"]), list(coverage.values())


def diagnostic(row, index, tolerances):
    a, b = [index[i] for i in row["record_ids"]]
    if not a["unit"] or a["unit"] != b["unit"]:
        return {"status": "not_computed_unit_unknown_or_mismatch"}
    if any(c["value_status"] != "available" or c["value"] is None for c in (a, b)):
        return {"status": "not_computed_value_unavailable"}
    values = [Decimal(str(c["value"])) for c in (a, b)]
    if not all(v.is_finite() for v in values):
        raise ValueError("non_finite_value")
    delta = values[0] - values[1]
    tol = tolerances.get(row["comparison_id"])
    if tol is not None and (isinstance(tol, bool) or not Decimal(str(tol)).is_finite() or Decimal(str(tol)) < 0):
        raise ValueError("invalid_proposed_tolerance")
    return {"status": ("equal_numeric_values" if delta == 0 else
                      "difference_precision_unknown" if tol is None else
                      "within_proposed_rounding" if abs(delta) <= Decimal(str(tol)) else
                      "outside_proposed_rounding"),
            "values": [str(v) for v in values], "delta": str(delta), "unit": a["unit"],
            "proposed_absolute_tolerance": tol, "tolerance_human_approved": False,
            "semantic_equivalence_established": False}


def run(manifest, profile, output, explicit=(), tolerances=None, confirmations=None):
    if output.exists():
        raise ValueError("output_exists")
    claims, _, inventory, sources, missing = prepare(manifest, profile)
    rows, coverage = discover(claims, profile, explicit)
    index = {c["record_id"]: c for c in claims}
    findings = []
    for row in rows:
        base = proposal(row["record_ids"])
        result = assess(base, index, {}, {}, require_source_basis=True)
        result.update(match_basis=row["match_basis"], comparison_route=row["comparison_route"],
                      numeric_diagnostic=diagnostic(row, index, tolerances or {}),
                      source_version_review="pending_audit_basis_and_restatement",
                      evidence=[{"record_id": index[i]["record_id"], "label": index[i]["label"],
                                 "observation_year": index[i]["observation_year"],
                                 "report_year": index[i]["report_year"],
                                 "report_type": index[i]["report_type"],
                                 "source_document_type": document_type(index[i]),
                                 "value": index[i]["value"], "unit": index[i]["unit"],
                                 "original_value": index[i]["source_original_value"],
                                 "original_unit": index[i]["original_unit"],
                                 "boundary": index[i]["raw_record"]["boundary"],
                                 "input_digest": index[i]["input_digest"],
                                 "evidence": index[i]["evidence"]} for i in row["record_ids"]])
        incompatible = {"company_id_mismatch", "observation_year_mismatch", "unit_mismatch",
                        "reporting_boundary_mismatch", "consolidation_mismatch",
                        "table_row_context_mismatch", "period_type_mismatch",
                        "observation_start_mismatch", "observation_end_mismatch", "measurement_date_mismatch",
                        "metric_id_not_equivalent", "metric_definition_not_equivalent"}
        result["screening_status"] = ("blocked_context_mismatch" if incompatible.intersection(result["reasons"])
                                      else "pending_context_review")
        findings.append(result)
    summary = {"schema_version": "cross-report-discovery-1.0",
               "status": "partial" if not claims or missing or any(i["status"] != "loaded" for i in inventory) else "completed",
               "manifest_sha256": sha256(manifest),
               "generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "records_scanned": len(claims), "candidate_pairs": len(rows),
               "year_unverified_candidates": sum(
                   "report_year_hint_unverified" in row["match_basis"] for row in rows),
               "variant_unverified_candidates": sum(
                   "variant_unknown_unverified" in row["match_basis"] for row in rows),
               "numeric_diagnostics": dict(Counter(f["numeric_diagnostic"]["status"] for f in findings)),
               "screening_statuses": dict(Counter(f["screening_status"] for f in findings)),
               "records_with_candidates": sum(bool(c["candidate_ids"]) for c in coverage),
               "numeric_esg_records": sum(c["report_type"] == "ESG" and c["value"] is not None for c in claims),
               "confirmed_contradictions": 0, "evaluation_status": "pending_adjudication",
               "precision": None, "recall": None, "profile_digest": digest(profile),
               "missing_expected_reports": missing,
               "limitations": ["Discovery covers delivered records, not every disclosure in PDFs.",
                              "Label/family matches are retrieval hypotheses, not semantic equivalence.",
                              "Missing extraction is never disclosure absence."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=output.name + ".", dir=output.parent))
    values = {"summary": summary, "findings": findings, "coverage": coverage,
              "inventory": inventory, "sources": sources, "profile_snapshot": profile,
              "comparisons": {"comparisons": [proposal(r["record_ids"]) for r in rows]},
              "review_template": review_template(
                  [index[i] for i in sorted({i for row in rows for i in row["record_ids"]})],
                  [proposal(r["record_ids"]) for r in rows]),
              "session_context_not_adjudication": confirmations or {}}
    values["review_pack"] = {"cases": [{"comparison_id": r["comparison_id"], "record_ids": r["record_ids"]}
                                     for r in rows]}
    for event in values["review_template"]["comparison_events"]:
        event.update(source_basis_checked=False, source_basis_note=None)
    for name, value in values.items():
        write_json(staging / (name + ".json"), value)
    with (staging / "triage_template.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["comparison_id", "input_digest", "screening_status", "numeric_status", "delta", "unit",
                  "decision", "reviewer", "reviewed_at_utc", "notes"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for f in findings:
            numeric = f["numeric_diagnostic"]
            writer.writerow(dict(comparison_id=f["comparison_id"], input_digest=f["input_digest"],
                                 screening_status=f["screening_status"],
                                 numeric_status=numeric["status"], delta=numeric.get("delta"),
                                 unit=numeric.get("unit"), decision="pending"))
    # A flat, source-linked queue for reviewing only ESG against financial statements.
    # The exact quote is often a table value; context_text retains the nearby label/header.
    with (staging / "esg_bctc_pairs.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        fields = ["comparison_id", "metric", "observation_year", "esg_report_year",
                  "esg_source_file", "esg_pdf_page", "esg_label", "esg_value", "esg_unit", "esg_quote",
                  "esg_context", "bctc_report_year", "bctc_source_file", "bctc_pdf_page", "bctc_label",
                  "bctc_value", "bctc_unit", "bctc_quote", "bctc_context",
                  "numeric_status", "delta", "review_status", "screening_status"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for finding in findings:
            if finding["comparison_route"] != "esg_financial":
                continue
            sides = {side["source_document_type"]: side for side in finding["evidence"]}
            esg, bctc = sides["sustainability_report"], sides["financial_statement"]
            esg_ev = esg["evidence"][0] if esg["evidence"] else {}
            bctc_ev = bctc["evidence"][0] if bctc["evidence"] else {}
            numeric = finding["numeric_diagnostic"]
            writer.writerow({"comparison_id": finding["comparison_id"],
                             "metric": ", ".join(finding["match_basis"]),
                             "observation_year": esg["observation_year"],
                             "esg_report_year": esg["report_year"],
                             "esg_source_file": esg_ev.get("source_file"),
                             "esg_pdf_page": esg_ev.get("physical_page"),
                             "esg_label": esg["label"], "esg_value": esg["original_value"],
                             "esg_unit": esg["original_unit"],
                             "esg_quote": esg_ev.get("exact_quote"),
                             "esg_context": esg_ev.get("context_text"),
                             "bctc_report_year": bctc["report_year"],
                             "bctc_source_file": bctc_ev.get("source_file"),
                             "bctc_pdf_page": bctc_ev.get("physical_page"),
                             "bctc_label": bctc["label"],
                             "bctc_value": bctc["original_value"],
                             "bctc_unit": bctc["original_unit"],
                             "bctc_quote": bctc_ev.get("exact_quote"),
                             "bctc_context": bctc_ev.get("context_text"),
                             "numeric_status": numeric["status"],
                             "delta": numeric.get("delta"),
                             "review_status": finding["status"],
                             "screening_status": finding["screening_status"]})
    paths = {s["source_id"]: Path(s["path"]).resolve() for s in sources}
    sections = []
    priority = {"outside_proposed_rounding": 0, "difference_precision_unknown": 1}
    for f in sorted(findings, key=lambda f: (f["screening_status"] == "blocked_context_mismatch",
                                             priority.get(f["numeric_diagnostic"]["status"], 2))):
        links = []
        for c in f["evidence"]:
            for ev in c["evidence"]:
                url = paths[ev["source_id"]].as_uri() + "#page=" + str(ev["physical_page"])
                links.append('<a href="' + html.escape(url, quote=True) + '">' +
                             html.escape(c["label"] or c["record_id"]) + " — PDF " + str(ev["physical_page"]) + "</a>")
        preview = "\n".join(
            f'{c["source_document_type"]} / report {c["report_year"]} / observation {c["observation_year"]}: '
            f'{c["label"]} = {c["original_value"]} {c["original_unit"]} '
            f'[{c["boundary"]["consolidation"]}]' for c in f["evidence"])
        sections.append("<section><h2>" + f["comparison_id"] + "</h2><pre>" +
                        html.escape(preview) + "</pre><p>" +
                        html.escape(f["screening_status"] + " / " + f["numeric_diagnostic"]["status"] +
                                    " / delta=" + str(f["numeric_diagnostic"].get("delta"))) +
                        "</p>" + "<br>".join(links) +
                        "<details><summary>Evidence, hash, context và điều kiện cần review</summary><pre>" +
                        html.escape(json.dumps(f, ensure_ascii=False, indent=2)) + "</pre></details></section>")
    (staging / "review.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>Cross-report review</title>"
        "<style>body{font:16px sans-serif;max-width:1150px;margin:32px auto;padding:0 20px}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:16px}"
        "section{border-top:2px solid #ccc;margin-top:28px;padding-top:12px}a{color:#075a9c}</style>"
        "<h1>Ứng viên đối chiếu ESG–BCTC / ESG–báo cáo thường niên</h1>"
        "<p>Chênh lệch số học chưa phải mâu thuẫn. Kiểm tra định nghĩa, kỳ, phạm vi, đơn vị và phiên bản/audit.</p>"
        "<pre>" + html.escape(json.dumps(summary, ensure_ascii=False, indent=2)) + "</pre>" + "".join(sections),
        encoding="utf-8")
    os.replace(staging, output)
    return summary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--profile", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--comparisons", type=Path, action="append",
                   help="Versioned explicit comparison files; may be repeated")
    p.add_argument("--pilot-pack", type=Path)
    p.add_argument("--session-context", type=Path)
    args = p.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    tolerances = ({c["comparison_id"]: c["suggested_rounding_tolerance_vnd"]
                   for c in load(args.pilot_pack)["cases"]} if args.pilot_pack else {})
    result = run(args.manifest, load(args.profile), args.output_dir,
                 [row for path in (args.comparisons or [])
                  for row in load(path)["comparisons"]],
                 tolerances, load(args.session_context) if args.session_context else None)
    print(json.dumps(result, ensure_ascii=True))
    return 2 if result["status"] == "partial" else 0


if __name__ == "__main__":
    raise SystemExit(main())
