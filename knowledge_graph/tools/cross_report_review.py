"""Make and preflight a small, digest-bound review file for cross-report pairs.

This tool never supplies a human decision. The resulting file is a template;
reviewers save their answers to a different path before Graph ingestion.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from kg.corporate_assessment import LAYERS, human_event
from tools.corporate_extract_alignment import write_json


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def select_template(run, pack):
    template = read(Path(run) / "review_template.json")
    cases = read(pack)["cases"]
    record_ids = {identity for case in cases for identity in case["record_ids"]}
    comparison_ids = {case["comparison_id"] for case in cases}
    records = [row for row in template["record_events"] if row["record_id"] in record_ids]
    comparisons = [row for row in template["comparison_events"]
                   if row["comparison_id"] in comparison_ids]
    if (len(records), len(comparisons)) != (len(record_ids), len(comparison_ids)):
        raise ValueError("review_template_missing_candidate_ids")
    return {"schema_version": "corporate-graph-review-1.0",
            "record_events": records, "comparison_events": comparisons}


def check(run, pack, reviews):
    expected = select_template(run, pack)
    actual = read(reviews)
    if actual.get("schema_version") != expected["schema_version"]:
        raise ValueError("unknown_review_version")
    issues = []
    for key, identity in (("record_events", "record_id"),
                          ("comparison_events", "comparison_id")):
        index = {row[identity]: row for row in expected[key]}
        seen = set()
        for row in actual.get(key, []):
            ident = row.get(identity)
            if ident in seen:
                issues.append(f"duplicate_{identity}:{ident}")
            seen.add(ident)
            if ident not in index:
                issues.append(f"unexpected_{identity}:{ident}")
                continue
            if row.get("input_digest") != index[ident]["input_digest"]:
                issues.append(f"stale_input_digest:{ident}")
            decision = row.get("decision")
            allowed = ({"pending", "accept", "reject"} if key == "record_events" else
                       {"pending", "comparable", "not_comparable"})
            if decision not in allowed:
                issues.append(f"invalid_decision:{ident}")
            if decision != "pending" and not human_event(row):
                issues.append(f"missing_human_identity_or_time:{ident}")
            if decision == "accept" and any(row.get("checks", {}).get(layer) is not True
                                            for layer in LAYERS):
                issues.append(f"record_layers_not_confirmed:{ident}")
            if decision == "comparable":
                tolerance = row.get("absolute_tolerance")
                if (isinstance(tolerance, bool) or not isinstance(tolerance, (int, float))
                        or not math.isfinite(tolerance) or tolerance < 0):
                    issues.append(f"tolerance_missing_or_invalid:{ident}")
                if row.get("restatement_checked") is not True:
                    issues.append(f"restatement_not_checked:{ident}")
        issues.extend(f"missing_{identity}:{ident}" for ident in sorted(set(index) - seen))
    return {"status": "valid" if not issues else "invalid", "issues": issues,
            "record_events": len(actual.get("record_events", [])),
            "comparison_events": len(actual.get("comparison_events", []))}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    make = sub.add_parser("make-template")
    make.add_argument("--run", type=Path, required=True)
    make.add_argument("--pack", type=Path, required=True)
    make.add_argument("--output", type=Path, required=True)
    verify = sub.add_parser("check")
    verify.add_argument("--run", type=Path, required=True)
    verify.add_argument("--pack", type=Path, required=True)
    verify.add_argument("--reviews", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "make-template":
            if args.output.exists():
                raise ValueError("output_exists_choose_new_file")
            value = select_template(args.run, args.pack)
            write_json(args.output, value)
            result = {"status": "template_created_pending_human_review",
                      "record_events": len(value["record_events"]),
                      "comparison_events": len(value["comparison_events"])}
        else:
            result = check(args.run, args.pack, args.reviews)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"status": "failed", "reason": str(exc)}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] in {"valid", "template_created_pending_human_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
