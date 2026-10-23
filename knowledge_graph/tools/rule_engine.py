import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_json(path):
    with Path(path).open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def finding_id(rule_id, claim_ids):
    key = rule_id + "|" + "|".join(sorted(claim_ids))
    return "FND-" + hashlib.sha1(key.encode()).hexdigest()[:10].upper()


def make_finding(rule, claims, status, summary, calculation):
    ids = [c["claim_id"] for c in claims]
    pages = []
    sources = []
    for claim in claims:
        for evidence in claim["evidence"]:
            sources.append(evidence["source_file"])
            pages.extend(evidence["source_pages"])
    return {
        "finding_id": finding_id(rule["id"], ids),
        "rule_id": rule["id"],
        "rule_name": rule["name"],
        "status": status,
        "severity": "high" if status == "Contradicted" else "medium" if status == "NeedsReview" else "info",
        "company_id": claims[0]["company_id"] if claims else "BSR",
        "report_years": sorted({c["report_year"] for c in claims}),
        "observation_years": sorted({c["observation_year"] for c in claims}),
        "topic": claims[0]["topic"] if claims else "unknown",
        "summary": summary,
        "calculation": calculation,
        "basis": rule["basis"],
        "guard": rule["guard"],
        "input_claim_ids": ids,
        "source_files": sorted(set(sources)),
        "source_pages": sorted(set(pages))
    }


def boundary_key(claim):
    """Return a boundary only when the claim explicitly marks it verified."""
    boundary = claim.get("reporting_boundary")
    if boundary in (None, "") or claim.get("reporting_boundary_verified") is not True:
        return None
    return boundary


def comparison_key(claim, fields):
    return tuple(claim.get(field) for field in fields) + (boundary_key(claim),)


def comparison_status(rule, passed, claims):
    status = "Supported" if passed else rule["failure"]
    if status == "Contradicted" and any(boundary_key(claim) is None for claim in claims):
        return "NeedsReview", " Điều kiện reporting boundary chưa được xác minh; chưa đủ cơ sở kết luận Contradicted."
    return status, ""


def has_evidence_gap(claims):
    """A present claim with null value is an explicit evidence gap; no row is not."""
    return any(claim.get("value") is None for claim in claims)


def add_evidence_gap_finding(findings, rule, claims):
    findings.append(make_finding(
        rule,
        claims,
        "InsufficientEvidence",
        f"Evidence gap đã được xác nhận cho input của {rule['name']}.",
        "Không thực hiện phép tính vì có giá trị null.",
    ))


def evaluate(claims, rules):
    findings = []

    def select(metric=None, report_year=None, observation_year=None, unit=None):
        return [c for c in claims
                if (metric is None or c["metric_id"] == metric)
                and (report_year is None or c["report_year"] == report_year)
                and (observation_year is None or c["observation_year"] == observation_year)
                and (unit is None or c["unit"] == unit)]

    for rule in rules:
        kind = rule["kind"]

        if kind == "same_report_conflict":
            groups = defaultdict(list)
            for metric in rule["metrics"]:
                for c in select(metric=metric, unit=rule["unit"]):
                    key = comparison_key(c, (
                        "company_id", "report_year", "observation_year",
                        "metric_id", "unit", "scope",
                    ))
                    groups[key].append(c)
            for key, group in groups.items():
                if len(group) < 2:
                    continue
                if has_evidence_gap(group):
                    add_evidence_gap_finding(findings, rule, group)
                    continue
                values = [float(c["value"]) for c in group]
                delta = max(values) - min(values)
                status, applicability_note = comparison_status(
                    rule, delta <= rule["tolerance"], group
                )
                findings.append(make_finding(rule, group, status,
                    f"Cùng {key[3]} năm {key[2]} có {len(set(values))} giá trị trong báo cáo {key[1]}."
                    f"{applicability_note}",
                    f"max - min = {delta:,.2f} {rule['unit']}"))

        elif kind == "sum_parts":
            year = rule["report_year"]
            metrics = [rule["total"]] + rule["parts"]
            groups = defaultdict(lambda: defaultdict(list))
            for metric in metrics:
                for c in select(metric, year, unit=rule["unit"]):
                    key = comparison_key(c, (
                        "company_id", "report_year", "observation_year", "unit", "scope",
                    ))
                    groups[key][metric].append(c)
            for by_metric in groups.values():
                if any(not by_metric[metric] for metric in metrics):
                    continue
                selected = [by_metric[metric][0] for metric in metrics]
                if has_evidence_gap(selected):
                    add_evidence_gap_finding(findings, rule, selected)
                    continue
                total = float(selected[0]["value"])
                part_sum = sum(float(c["value"]) for c in selected[1:])
                delta = total - part_sum
                status, applicability_note = comparison_status(
                    rule, abs(delta) <= rule["tolerance"], selected
                )
                findings.append(make_finding(rule, selected, status,
                    f"Tổng công bố {total:,.2f}; tổng thành phần {part_sum:,.2f}; chênh lệch {delta:,.2f} {rule['unit']}."
                    f"{applicability_note}",
                    f"{total:,.2f} - {part_sum:,.2f} = {delta:,.2f} {rule['unit']}"))

        elif kind == "cross_report_revision":
            groups = defaultdict(list)
            for metric in rule["metrics"]:
                for c in select(metric=metric, unit=rule["unit"]):
                    key = comparison_key(c, (
                        "company_id", "metric_id", "observation_year", "unit", "scope",
                    ))
                    groups[key].append(c)
            for key, group in groups.items():
                if len({c["report_year"] for c in group}) < 2:
                    continue
                if has_evidence_gap(group):
                    add_evidence_gap_finding(findings, rule, group)
                    continue
                values = [float(c["value"]) for c in group]
                delta = max(values) - min(values)
                status, applicability_note = comparison_status(
                    rule, delta <= rule["tolerance"], group
                )
                findings.append(make_finding(rule, group, status,
                    f"Giá trị {key[1]} của năm {key[2]} thay đổi giữa các báo cáo."
                    f"{applicability_note}",
                    f"max - min = {delta:,.2f} {rule['unit']}"))

        elif kind == "subset":
            metrics = [rule["total"], rule["part"]]
            groups = defaultdict(lambda: defaultdict(list))
            for metric in metrics:
                for c in select(metric, unit=rule["unit"]):
                    key = comparison_key(c, (
                        "company_id", "report_year", "observation_year", "unit", "scope",
                    ))
                    groups[key][metric].append(c)
            for key, by_metric in groups.items():
                if any(not by_metric[metric] for metric in metrics):
                    continue
                total = by_metric[rule["total"]][0]
                part = by_metric[rule["part"]][0]
                selected = [total, part]
                if has_evidence_gap(selected):
                    add_evidence_gap_finding(findings, rule, selected)
                    continue
                ok = float(part["value"]) <= float(total["value"]) + rule["tolerance"]
                status, applicability_note = comparison_status(rule, ok, selected)
                findings.append(make_finding(rule, selected, status,
                    f"Năm {key[1]}: thành viên độc lập {part['value']}, tổng HĐQT {total['value']}."
                    f"{applicability_note}",
                    f"{part['value']} <= {total['value']}"))

        elif kind == "percent_change":
            year = rule["report_year"]
            roles = {
                "old": select(rule["metric"], year, rule["from_year"], rule["unit"]),
                "new": select(rule["metric"], year, rule["to_year"], rule["unit"]),
                "stated": select(rule["claim_metric"], year, rule["to_year"]),
            }
            groups = defaultdict(lambda: defaultdict(list))
            for role, rows in roles.items():
                for c in rows:
                    key = comparison_key(c, ("company_id", "report_year", "scope"))
                    groups[key][role].append(c)
            for by_role in groups.values():
                if any(not by_role[role] for role in roles):
                    continue
                selected = [by_role[role][0] for role in ("old", "new", "stated")]
                if has_evidence_gap(selected):
                    add_evidence_gap_finding(findings, rule, selected)
                    continue
                old, new, stated = selected
                if float(old["value"]) == 0:
                    findings.append(make_finding(rule, selected, "NeedsReview",
                        "Mẫu số bằng 0; rule không thể tính phần trăm thay đổi.",
                        "Không thực hiện phép tính"))
                    continue
                calculated = (float(old["value"]) - float(new["value"])) / float(old["value"]) * 100
                delta = abs(calculated - float(stated["value"]))
                status, applicability_note = comparison_status(
                    rule, delta <= rule["tolerance"], selected
                )
                findings.append(make_finding(rule, selected, status,
                    f"Mức giảm tính được {calculated:.2f}%; báo cáo công bố {stated['value']}%."
                    f"{applicability_note}",
                    f"({old['value']} - {new['value']}) / {old['value']} × 100 = {calculated:.2f}%"))

        elif kind == "target":
            rows = select(rule["metric"], rule["report_year"], unit=rule["unit"])
            groups = defaultdict(list)
            for c in rows:
                key = comparison_key(c, (
                    "company_id", "report_year", "observation_year", "unit", "scope",
                ))
                groups[key].append(c)
            for group in groups.values():
                actual = next((c for c in group if c["variant"] != "target"), None)
                target = next((c for c in group if c["variant"] == "target"), None)
                if not actual or not target:
                    continue
                selected = [actual, target]
                if has_evidence_gap(selected):
                    add_evidence_gap_finding(findings, rule, selected)
                    continue
                if rule["direction"] == "lower_is_better":
                    ok = float(actual["value"]) <= float(target["value"]) + rule["tolerance"]
                else:
                    ok = float(actual["value"]) + rule["tolerance"] >= float(target["value"])
                status, applicability_note = comparison_status(rule, ok, selected)
                findings.append(make_finding(rule, selected, status,
                    f"Actual {actual['value']} {rule['unit']}; target {target['value']} {rule['unit']}."
                    f"{applicability_note}",
                    f"{actual['value']} <= {target['value']} (lower-is-better)"))

        elif kind == "sum_constant":
            groups = defaultdict(lambda: defaultdict(list))
            for metric in rule["metrics"]:
                for c in select(metric, rule["report_year"], unit=rule["unit"]):
                    key = comparison_key(c, (
                        "company_id", "report_year", "observation_year", "unit", "scope",
                    ))
                    groups[key][metric].append(c)
            for by_metric in groups.values():
                if any(not by_metric[metric] for metric in rule["metrics"]):
                    continue
                rows = [by_metric[metric][0] for metric in rule["metrics"]]
                if has_evidence_gap(rows):
                    add_evidence_gap_finding(findings, rule, rows)
                    continue
                total = sum(float(c["value"]) for c in rows)
                delta = total - rule["expected"]
                status, applicability_note = comparison_status(
                    rule, abs(delta) <= rule["tolerance"], rows
                )
                findings.append(make_finding(rule, rows, status,
                    f"Tổng tỷ lệ là {total:.2f}%, chênh {delta:.2f} điểm phần trăm."
                    f"{applicability_note}",
                    " + ".join(str(c["value"]) for c in rows) + f" = {total:.2f}%"))
    return findings


def run():
    claims = load_json(ROOT / "output" / "normalized_claims.json")
    rules = load_json(ROOT / "data" / "config" / "rules.json")
    findings = evaluate(claims, rules)
    out = ROOT / "output"
    (out / "findings.json").write_text(json.dumps(findings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    columns = ["finding_id", "rule_id", "status", "severity", "topic", "report_years",
               "observation_years", "summary", "calculation", "source_files", "source_pages"]
    with (out / "findings.csv").open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for finding in findings:
            row = {k: finding[k] for k in columns}
            for k in ("report_years", "observation_years", "source_files", "source_pages"):
                row[k] = ", ".join(map(str, row[k]))
            writer.writerow(row)
    return findings


if __name__ == "__main__":
    result = run()
    counts = {s: sum(f["status"] == s for f in result) for s in sorted({f["status"] for f in result})}
    print(f"Đã tạo {len(result)} findings: {counts}")
