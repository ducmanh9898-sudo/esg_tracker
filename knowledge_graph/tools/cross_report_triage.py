"""Import human screening decisions without promoting record grounding or gold."""
import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile

from kg.corporate_adapter import digest
from kg.corporate_assessment import human_event


def ingest(run, decisions, output):
    if output.exists():
        raise ValueError("output_exists_choose_new_history_file")
    findings = json.loads((run / "findings.json").read_text(encoding="utf-8"))
    index = {f["comparison_id"]: f for f in findings}
    events, seen = [], set()
    with decisions.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            identity = row["comparison_id"]
            if identity in seen or identity not in index:
                raise ValueError("duplicate_or_unknown_comparison:" + identity)
            seen.add(identity)
            if row["input_digest"] != index[identity]["input_digest"]:
                raise ValueError("stale_comparison:" + identity)
            if row["decision"] not in {"pending", "rounding_match", "potential_contradiction",
                                       "not_comparable", "extraction_error", "uncertain"}:
                raise ValueError("invalid_triage_decision:" + identity)
            event = {**row, "reviewer_kind": "human", "basis": row.get("notes")}
            if row["decision"] != "pending":
                if not human_event(event):
                    raise ValueError("reviewer_timestamp_and_notes_required:" + identity)
                events.append(event)
    payload = {"schema_version": "cross-report-triage-1.0", "scope": "screening_only",
               "imported_at_utc": datetime.now(timezone.utc).isoformat(),
               "source_decisions": str(decisions.resolve()), "events": events,
               "events_digest": digest(events), "gold_status": "not_adjudicated",
               "note": "Does not accept record layers, alter Extract, or promote Graph verdicts."}
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=output.parent, prefix=output.name + ".")
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2, allow_nan=False)
    # Atomic exclusive creation, preserving any concurrent history writer.
    try:
        os.link(temporary, output)
    finally:
        Path(temporary).unlink()
    return {"status": "imported_screening_only", "decisions": len(events)}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--decisions", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    print(json.dumps(ingest(args.run, args.decisions, args.output)))


if __name__ == "__main__":
    main()
