"""Apply source, mapping and context reviews without editing Extract JSON."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
import fitz

from kg.ready_rules import RULES


COMMON_CONTEXT = (
    "observation_year", "period_type", "reporting_boundary", "unit",
    "variant", "metric_definition", "scope",
)
CONTEXT_FIELDS = {
    "KG-E-01": COMMON_CONTEXT + (
        "organizational_scope", "emission_basis", "scope2_method",
        "calculation_method", "precision",
    ),
    "KG-S-01": COMMON_CONTEXT + ("population_id", "counting_method", "measurement_date", "comparison_frame_id"),
    "KG-G-01": COMMON_CONTEXT + ("board_id", "measurement_date", "comparison_frame_id"),
}
OPTIONAL_CONTEXT = ("baseline_id", "total_definition")


def alias_id(alias):
    return "|".join((alias["rule_id"], alias["metric_id"], alias["role"]))


def _known(value):
    return value is not None and str(value).strip().lower() not in {"", "unknown", "unspecified"}


def comparison_frame_id(source):
    """Identity of one source statement, not a fabricated measurement date."""
    parts = (source["source_path"], source["source_sha256"], str(source["physical_page"]),
             re.sub(r"\s+", " ", source["quote"]).strip())
    return "FRAME-" + hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20].upper()


def _source_path(root, relative_path):
    if not isinstance(relative_path, str) or not relative_path:
        return None
    path = (Path(root) / relative_path).resolve()
    return path if path.is_relative_to(Path(root).resolve()) and path.is_file() else None


def _fingerprint(root, relative_path):
    path = _source_path(root, relative_path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path else None


def _refs(claim):
    return [{"evidence_id": e.get("evidence_id"), "source_file": e.get("source_file"),
             "source_pages": e.get("source_pages", []), "json_pointer": e.get("json_pointer"),
             "original_text": e.get("original_text")}
            for e in claim.get("evidence", [])]


def _target(claim, root):
    paths = sorted({e.get("source_extract_path") for e in claim.get("evidence", [])
                    if e.get("source_extract_path")})
    path = paths[0] if len(paths) == 1 else None
    return {"company_id": claim["company_id"], "report_id": claim["report_id"],
            "record_id": claim["record_id"], "extract_path": path,
            "extract_sha256": _fingerprint(root, path), "source_refs": _refs(claim)}


def _metadata(annotation_id, target):
    return {"annotation_id": annotation_id, **target, "status": "pending",
            "reviewer": None, "reviewed_at": None, "review_basis": None}


def _required_context(rule_id, role, claim):
    fields = list(CONTEXT_FIELDS[rule_id])
    if rule_id == "KG-E-01" and role == "scope1_plus_scope2_total":
        fields.append("total_definition")
    if _known(claim.get("baseline_id")):
        fields.append("baseline_id")
    return fields


def _missing_context_fields(rule_id, fields, required):
    alternatives = {"measurement_date", "comparison_frame_id"} if rule_id in {"KG-S-01", "KG-G-01"} else set()
    missing = [field for field in required if field not in alternatives and not _known(fields.get(field))]
    if alternatives and not any(_known(fields.get(field)) for field in alternatives):
        missing.append("measurement_date_or_comparison_frame_id")
    return missing


def _frame_reasons(entry, claim, root):
    frame = entry.get("frame_source")
    if not isinstance(frame, dict):
        return ["comparison_frame_source_missing"]
    expected = {"source_path", "source_sha256", "physical_page", "quote", "subject_phrase",
                "subset_phrase", "display_value"}
    if not expected.issubset(frame) or any(not _known(frame.get(key)) for key in expected):
        return ["comparison_frame_source_incomplete"]
    if _fingerprint(root, frame["source_path"]) != frame["source_sha256"]:
        return ["comparison_frame_source_hash_mismatch"]
    if entry["fields"]["comparison_frame_id"] != comparison_frame_id(frame):
        return ["comparison_frame_id_mismatch"]
    path = _source_path(root, frame["source_path"])
    try:
        with fitz.open(path) as pdf:
            page = frame["physical_page"]
            if not isinstance(page, int) or not 1 <= page <= len(pdf):
                return ["comparison_frame_page_invalid"]
            text = re.sub(r"\s+", " ", pdf[page - 1].get_text()).strip()
    except (OSError, ValueError, RuntimeError):
        return ["comparison_frame_pdf_unreadable"]
    quote = re.sub(r"\s+", " ", frame["quote"]).strip()
    if quote not in text or frame["subject_phrase"] not in quote or frame["subset_phrase"] not in quote:
        return ["comparison_frame_quote_mismatch"]
    if frame["display_value"] not in quote:
        return ["comparison_frame_value_not_in_quote"]
    displayed = re.sub(r"[.\s]", "", str(frame["display_value"])).lstrip("0") or "0"
    if not displayed.isdigit() or int(displayed) != claim.get("value"):
        return ["comparison_frame_claim_value_mismatch"]
    return []


def make_pending_template(claims, findings, aliases, root):
    """Create review requests from current primary findings; every status stays pending."""
    by_id = {claim["record_id"]: claim for claim in claims}
    alias_lookup = defaultdict(list)
    for alias in aliases.get("aliases", []):
        alias_lookup[(alias["rule_id"], alias["metric_id"])].append(alias)
    role_pairs = sorted({(finding["rule_id"], claim_id)
                         for finding in findings for claim_id in finding["input_claim_ids"]})
    selected_ids = sorted({claim_id for _, claim_id in role_pairs})
    source_reviews, mapping_reviews, context_reviews = [], [], []
    for claim_id in selected_ids:
        claim = by_id[claim_id]
        target = _target(claim, root)
        row = _metadata("SRC-" + claim_id, target)
        row["missing_fields"] = ["reviewer", "reviewed_at", "review_basis"]
        if not all(_known(ref.get("original_text")) for ref in target["source_refs"]):
            row["missing_fields"].append("source_refs.original_text")
        if target["extract_sha256"] is None:
            row["missing_fields"].append("extract_path_or_fingerprint")
        source_reviews.append(row)
    for rule_id, claim_id in role_pairs:
        claim = by_id[claim_id]
        target = _target(claim, root)
        matching = alias_lookup.get((rule_id, claim.get("metric_id")), [])
        for alias in matching:
            row = _metadata("MAP-" + rule_id + "-" + claim_id + "-" + alias["role"], target)
            row["alias_id"] = alias_id(alias)
            row["missing_fields"] = ["reviewer", "reviewed_at", "review_basis"]
            if not all(_known(ref.get("original_text")) for ref in target["source_refs"]):
                row["missing_fields"].append("source_refs.original_text")
            mapping_reviews.append(row)
        roles = {alias["role"] for alias in matching}
        role = next(iter(roles)) if len(roles) == 1 else None
        required = _required_context(rule_id, role, claim) if role else list(CONTEXT_FIELDS[rule_id])
        row = _metadata("CTX-" + rule_id + "-" + claim_id, target)
        row["rule_id"] = rule_id
        row["fields"] = {field: copy.deepcopy(claim.get(field)) for field in required}
        if isinstance(row["fields"].get("precision"), dict):
            row["fields"]["precision"].pop("verification_status", None)
        row["missing_fields"] = ["reviewer", "reviewed_at", "review_basis"] + [
            "fields." + field for field in _missing_context_fields(rule_id, row["fields"], required)]
        if not all(_known(ref.get("original_text")) for ref in target["source_refs"]):
            row["missing_fields"].append("source_refs.original_text")
        context_reviews.append(row)
    return {"schema_version": "1.0", "purpose": "Graph review template; pending is never verified",
            "source_reviews": source_reviews, "mapping_reviews": mapping_reviews,
            "context_reviews": context_reviews}


def _annotation_key(kind, entry):
    return (kind, entry.get("record_id"), entry.get("report_id"),
            entry.get("alias_id") if kind == "mapping_reviews" else
            entry.get("rule_id") if kind == "context_reviews" else None)


def _identity_reasons(entry, claim, root):
    reasons = []
    if claim is None or any(entry.get(field) != claim.get(field) for field in
                            ("company_id", "report_id", "record_id")):
        return ["claim_or_report_reference_mismatch"]
    paths = {e.get("source_extract_path") for e in claim.get("evidence", [])}
    if entry.get("extract_path") not in paths or not entry.get("extract_path"):
        reasons.append("extract_path_mismatch")
    current_hash = _fingerprint(root, entry.get("extract_path"))
    if current_hash is None:
        reasons.append("extract_file_missing")
    elif entry.get("extract_sha256") != current_hash:
        reasons.append("extract_fingerprint_stale")
    return reasons


def _provenance_reasons(entry, claim, require_all=False):
    reasons = []
    originals = {e.get("evidence_id"): e for e in claim.get("evidence", [])}
    refs = entry.get("source_refs") or []
    if not refs:
        return ["source_reference_missing"]
    if len({ref.get("evidence_id") for ref in refs}) != len(refs):
        reasons.append("duplicate_evidence_reference")
    if require_all and set(originals) != {ref.get("evidence_id") for ref in refs}:
        reasons.append("source_evidence_incomplete")
    for ref in refs:
        original = originals.get(ref.get("evidence_id"))
        if original is None:
            reasons.append("evidence_id_mismatch")
            continue
        if ref.get("source_file") != original.get("source_file"):
            reasons.append("source_file_mismatch")
        if not _known(ref.get("source_file")):
            reasons.append("source_file_missing")
        if ref.get("source_pages") != original.get("source_pages", []):
            reasons.append("source_pages_mismatch")
        if ref.get("json_pointer") != original.get("json_pointer"):
            reasons.append("json_pointer_mismatch")
        if not ref.get("source_pages") and not _known(ref.get("json_pointer")):
            reasons.append("source_locator_missing")
        raw_text = original.get("original_text")
        reviewed_text = ref.get("original_text")
        if _known(raw_text) and _known(reviewed_text) and raw_text != reviewed_text:
            reasons.append("original_text_conflict")
        if not _known(raw_text) and not _known(reviewed_text):
            reasons.append("reviewed_original_text_missing")
    return reasons


def _review_metadata_reasons(entry):
    return ["review_metadata_missing"] if not all(_known(entry.get(field)) for field in
                                             ("reviewer", "reviewed_at", "review_basis")) else []


def _context_reasons(entry, claim, aliases, root):
    rule_id = entry.get("rule_id")
    matching = [a for a in aliases if a.get("rule_id") == rule_id
                and a.get("metric_id") == claim.get("metric_id")]
    roles = {a["role"] for a in matching}
    if rule_id not in RULES or len(roles) != 1:
        return ["context_rule_or_alias_ambiguous"]
    fields = entry.get("fields") or {}
    required = _required_context(rule_id, next(iter(roles)), claim)
    reasons = ["context_field_missing:" + field for field in
               _missing_context_fields(rule_id, fields, required)]
    if _known(fields.get("comparison_frame_id")):
        reasons.extend(_frame_reasons(entry, claim, root))
    if rule_id == "KG-E-01" and "precision" in fields:
        precision = fields["precision"] or {}
        if not isinstance(precision, dict) or precision.get("mode") not in {"exact", "rounded_half_up"} \
                or not _known(precision.get("source_basis")):
            reasons.append("precision_basis_missing")
        elif precision["mode"] == "rounded_half_up" and not _known(precision.get("step")):
            reasons.append("precision_step_missing")
    for field, reviewed_value in fields.items():
        raw_value = claim.get(field)
        if field != "precision" and _known(raw_value) and raw_value != reviewed_value:
            reasons.append("source_context_conflict:" + field)
    return reasons


def apply_review_annotations(claims, alias_config, annotation_path, root):
    """Apply only independently grounded reviews; return copies and an audit report."""
    reviewed = copy.deepcopy(claims)
    for claim in reviewed:
        claim["extract_review_status"] = claim.get("review_status")
        claim["review_status"] = "unreviewed"
        claim["period_type_verified"] = False
        claim["reporting_boundary_verified"] = False
        claim["metric_definition_verified"] = False
        claim["graph_context_review_required"] = True
        claim["graph_context_review_status"] = "pending"
        claim["graph_context_reviewed_rules"] = []
        claim["graph_review_annotation_ids"] = []
        claim.pop("precision", None)
    result_config = copy.deepcopy(alias_config)
    result_config["require_claim_mapping_review"] = True
    result_config["verified_claim_mappings"] = []
    audit = {"schema_version": "1.0", "annotation_file": str(annotation_path) if annotation_path else None,
             "applied": [], "partial_applied": [], "pending": [], "rejected": [], "file_errors": []}
    if not annotation_path:
        audit["file_errors"].append("annotation_file_not_configured")
        audit["counts"] = {name: len(audit[name]) for name in ("applied", "pending", "rejected", "file_errors")}
        return reviewed, result_config, audit
    try:
        data = json.loads(Path(annotation_path).read_text(encoding="utf-8-sig"))
        schema = json.loads((Path(root) / "schemas" / "graph-review-annotations-v1.json").read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        audit["file_errors"].append(type(exc).__name__ + ": " + str(exc))
        audit["counts"] = {name: len(audit[name]) for name in ("applied", "pending", "rejected", "file_errors")}
        return reviewed, result_config, audit
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(data))
    invalid_rows = defaultdict(set)
    root_errors = []
    for error in errors:
        path = list(error.absolute_path)
        if len(path) >= 2 and path[0] in {"source_reviews", "mapping_reviews", "context_reviews"} and isinstance(path[1], int):
            invalid_rows[path[0]].add(path[1])
            audit["rejected"].append({"section": path[0], "index": path[1],
                                      "reasons": ["schema_invalid: " + error.message]})
        else:
            root_errors.append(error.message)
    if root_errors:
        audit["file_errors"].extend(root_errors)
        audit["counts"] = {name: len(audit[name]) for name in ("applied", "pending", "rejected", "file_errors")}
        return reviewed, result_config, audit
    by_id = defaultdict(list)
    for claim in reviewed:
        by_id[(claim["report_id"], claim["record_id"])].append(claim)
    alias_by_id = {alias_id(a): a for a in alias_config.get("aliases", [])}
    counts = Counter(_annotation_key(kind, row) for kind in
                     ("source_reviews", "mapping_reviews", "context_reviews")
                     for row in data[kind])
    for kind in ("source_reviews", "mapping_reviews", "context_reviews"):
        for index, entry in enumerate(data[kind]):
            if index in invalid_rows[kind]:
                continue
            target = by_id.get((entry["report_id"], entry["record_id"]), [])
            claim = target[0] if len(target) == 1 else None
            reasons = []
            if counts[_annotation_key(kind, entry)] > 1:
                reasons.append("duplicate_annotation_target")
            reasons.extend(_identity_reasons(entry, claim, root))
            if entry["status"] == "pending":
                # A source-backed comparison frame can be recorded without
                # approving the remaining context fields or the whole row.
                if kind == "context_reviews" and claim is not None:
                    fields = entry.get("fields") or {}
                    field_reviews = entry.get("field_reviews") or {}
                    frame_review = field_reviews.get("comparison_frame_id") or {}
                    if (_known(fields.get("comparison_frame_id"))
                            and frame_review.get("status") == "source_supported"):
                        partial_reasons = reasons + _review_metadata_reasons(entry)
                        partial_reasons.extend(_provenance_reasons(entry, claim))
                        partial_reasons.extend(_frame_reasons(entry, claim, root))
                        if partial_reasons:
                            reasons.extend(partial_reasons)
                        else:
                            claim["comparison_frame_id"] = fields["comparison_frame_id"]
                            applied_fields = ["comparison_frame_id"]
                            population_review = field_reviews.get("population_id") or {}
                            if (entry.get("rule_id") == "KG-S-01"
                                    and population_review.get("status") == "source_supported"
                                    and _known(fields.get("population_id"))):
                                claim["population_id"] = fields["population_id"]
                                applied_fields.append("population_id")
                            audit["partial_applied"].append({"annotation_id": entry["annotation_id"],
                                                             "record_id": claim["record_id"],
                                                             "fields": applied_fields})
                audit["pending"].append({"annotation_id": entry["annotation_id"],
                                          "section": kind, "reasons": sorted(set(reasons + ["awaiting_review"]))})
                continue
            if entry["status"] == "rejected":
                audit["rejected"].append({"annotation_id": entry["annotation_id"],
                                           "section": kind, "reasons": ["review_rejected"]})
                continue
            reasons.extend(_review_metadata_reasons(entry))
            if claim is not None:
                reasons.extend(_provenance_reasons(entry, claim, require_all=kind == "source_reviews"))
                if kind == "mapping_reviews":
                    alias = alias_by_id.get(entry.get("alias_id"))
                    if alias is None or alias.get("metric_id") != claim.get("metric_id") \
                            or alias.get("rule_id") not in RULES \
                            or claim.get("dimension") != RULES[alias["rule_id"]]["dimension"]:
                        reasons.append("alias_reference_mismatch")
                elif kind == "context_reviews":
                    reasons.extend(_context_reasons(entry, claim, alias_config.get("aliases", []), root))
            if reasons:
                audit["rejected"].append({"annotation_id": entry["annotation_id"],
                                           "section": kind, "reasons": sorted(set(reasons))})
                continue
            claim["graph_review_annotation_ids"].append(entry["annotation_id"])
            if kind == "source_reviews":
                claim["review_status"] = "reviewed"
                for ref in entry["source_refs"]:
                    evidence = next(e for e in claim["evidence"] if e["evidence_id"] == ref["evidence_id"])
                    if not _known(evidence.get("original_text")):
                        evidence["reviewed_source_text"] = ref["original_text"]
            elif kind == "mapping_reviews":
                result_config["verified_claim_mappings"].append({
                    "alias_id": entry["alias_id"], "record_id": claim["record_id"],
                    "report_id": claim["report_id"], "review_basis": entry["review_basis"],
                    "annotation_id": entry["annotation_id"]})
            else:
                for field, value in entry["fields"].items():
                    if field == "precision":
                        claim["precision"] = {**value, "verification_status": "verified"}
                    else:
                        claim[field] = value
                claim["period_type_verified"] = True
                claim["reporting_boundary_verified"] = True
                claim["metric_definition_verified"] = True
                claim["graph_context_review_status"] = "verified"
                claim["graph_context_reviewed_rules"].append(entry["rule_id"])
            audit["applied"].append({"annotation_id": entry["annotation_id"], "section": kind,
                                     "record_id": claim["record_id"]})
    audit["counts"] = {name: len(audit[name]) for name in ("applied", "pending", "rejected", "file_errors")}
    return reviewed, result_config, audit


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate a pending Graph review template")
    parser.add_argument("--claims", type=Path, required=True)
    parser.add_argument("--findings", type=Path, required=True)
    parser.add_argument("--aliases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("Output already exists; preserve reviewer edits and choose a new path")
    root = Path(__file__).resolve().parents[1]
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    template = make_pending_template(load(args.claims), load(args.findings), load(args.aliases), root)
    schema = load(root / "schemas" / "graph-review-annotations-v1.json")
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(template)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({kind: len(template[kind]) for kind in
                      ("source_reviews", "mapping_reviews", "context_reviews")}))


if __name__ == "__main__":
    main()
