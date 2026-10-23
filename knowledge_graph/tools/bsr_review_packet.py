"""Create and validate a human PDF review packet for the four BSR dry-run cases."""

import argparse
import copy
import hashlib
import json
import sys
import tempfile
from pathlib import Path, PureWindowsPath

from jsonschema import Draft202012Validator

from tools.bsr_pilot_dry_run import ROOT, _read, run


CATALOGUE = ROOT / "data" / "config" / "validation_cases.json"
CATALOGUE_SCHEMA = ROOT / "schemas" / "validation-case-schema-v0.1.json"
RESPONSE_SCHEMA = ROOT / "schemas" / "bsr-review-response-schema-v0.1.json"
CHECK_FIELDS = (
    "original_text", "period", "scope", "reporting_boundary",
    "metric_definition", "comparability",
)
CHECK_QUESTIONS = {
    "original_text": "What does each PDF page actually say or show? Is any supplied sentence a table/chart interpretation rather than a verbatim quote?",
    "period": "Which observation period does each value cover, and is it distinct from the report year?",
    "scope": "Which organizational and measurement scope applies to each value?",
    "reporting_boundary": "What is the reporting boundary, and which PDF pages support it?",
    "metric_definition": "Are the metric definitions, units and inclusions/exclusions the same?",
    "comparability": "Can these values be compared? Record any restatement, baseline or scope change and its source.",
}
IN_PROGRESS_BSR_PACKET_ID = "BSR-STAGE17-937B200A0CB36E34"


def _catalogue_cases():
    catalogue = _read(CATALOGUE)
    errors = list(Draft202012Validator(_read(CATALOGUE_SCHEMA)).iter_errors(catalogue))
    if errors:
        raise ValueError(f"Existing validation case catalogue is invalid: {errors[0].message}")
    return {case["case_id"]: case for case in catalogue["cases"]}


def _local_pdf(pdf_name):
    if not pdf_name:
        return None
    candidates = (
        ROOT / pdf_name,
        ROOT / "pdf" / pdf_name,
        ROOT / "data" / "raw_pdf" / pdf_name,
        ROOT / "data" / "raw_pdf" / "BSR" / pdf_name,
        ROOT / "data" / "raw_pdf" / "BCTC" / pdf_name,
    )
    return next((str(path.resolve()) for path in candidates if path.is_file()), None)


def _source_paths(source_file, report_year, pages):
    source_path = ROOT / "data" / "extract" / "esg" / source_file
    page_path = ROOT / "data" / "source" / "page_text" / f"BSR_{report_year}.json"
    chunks = []
    pdf_name = None
    if page_path.is_file():
        page_source = _read(page_path)
        pdf_name = page_source.get("source_file")
        if any(item.get("page_number") in pages for item in page_source.get("pages", [])):
            chunks.append(str(page_path.resolve()))
    return {
        "extract_json_path": str(source_path.resolve()) if source_path.is_file() else None,
        "text_chunk_paths": chunks,
        "pdf_file_name": pdf_name,
        "pdf_local_path": _local_pdf(pdf_name),
    }


def _esg_sources(claims):
    sources = []
    for claim in claims:
        for evidence in claim["evidence"]:
            source = {
                "source_ref_id": evidence["evidence_id"],
                "record_type": "esg_claim_evidence",
                "claim_id": claim["claim_id"],
                "evidence_id": evidence["evidence_id"],
                "value": claim["value"],
                "metric_id": claim["metric_id"],
                "observation_year": claim["metric_period_year"],
                "report_year": claim["report_year"],
                "unit": claim["unit"],
                "scope": claim["scope"],
                "report_id": claim["report_id"],
                "source_file": evidence["source_file"],
                "source_pages": evidence["source_pages"],
                "json_pointer": evidence["json_pointer"],
                **_source_paths(evidence["source_file"], claim["report_year"], evidence["source_pages"]),
            }
            if claim.get("workforce_context"):
                source["workforce_context"] = claim["workforce_context"]
            sources.append(source)
    return sources


def _financial_source(financial):
    year = financial["report_year"]
    raw_path = ROOT / "data" / "extract" / "financial" / f"BCTC_BSR_{year}_esg.json"
    pdf_name = None
    if raw_path.is_file():
        raw = _read(raw_path)
        source_pdf = raw.get("metadata", {}).get("source_pdf") or raw.get("document", {}).get("source_file")
        if source_pdf:
            pdf_name = PureWindowsPath(source_pdf).name
    return {
        "source_ref_id": financial["disclosure_id"],
        "record_type": "financial_disclosure",
        "claim_id": None,
        "evidence_id": None,
        "disclosure_id": financial["disclosure_id"],
        "value": financial["value"],
        "metric_id": "workforce.total",
        "observation_year": financial.get("observation_year"),
        "report_year": year,
        "reporting_period": financial.get("reporting_period"),
        "unit": financial["unit"],
        "scope": financial["scope"],
        "measurement_date": financial.get("measurement_date"),
        "employee_definition": financial.get("employee_definition"),
        "report_id": financial["report_id"],
        "source_file": raw_path.name,
        "source_pages": financial["source_pages"],
        "json_pointer": financial["json_pointer"],
        "source_uri": financial["source_uri"],
        "extract_json_path": str(raw_path.resolve()) if raw_path.is_file() else None,
        "text_chunk_paths": [],
        "pdf_file_name": pdf_name,
        "pdf_local_path": _local_pdf(pdf_name),
    }


def _blank_response(case_id):
    return {
        "case_id": case_id,
        "status": "pending_adjudication",
        "reviewer": {"name": None, "affiliation": None},
        "source_basis": [],
        "decision": {
            "reviewed_outcome": None,
            "system_result_assessment": None,
            "rationale": None,
            "checks": {field: None for field in CHECK_FIELDS},
        },
        "notes": None,
    }


def _case(case_id, title, catalogue_case, sources, system_result, missing_conditions, extra_questions=None):
    questions = dict(CHECK_QUESTIONS)
    if extra_questions:
        questions.update(extra_questions)
    return {
        "case_id": case_id,
        "title": title,
        "adjudication_status": "pending_adjudication",
        "catalogue_case_id": catalogue_case["case_id"] if catalogue_case else None,
        "catalogue_expected_behavior": catalogue_case["expected_behavior"] if catalogue_case else None,
        "system_result": system_result,
        "sources": sources,
        "missing_conditions": missing_conditions,
        "review_questions": questions,
        "review_form": _blank_response(case_id),
    }


def build_packet(dry_run_report):
    """Project existing dry-run cases into an unanswered, source-linked review form."""
    catalogue = _catalogue_cases()
    r01 = dry_run_report["cases"]["r01"]
    workforce = dry_run_report["cases"]["workforce_financial"]
    board = dry_run_report["cases"]["board_temporal"]
    if r01.get("category") != "current_rule_result" or workforce.get("status") == "not_run_missing_data" or board.get("category") != "temporal_assessment":
        raise ValueError("One or more required BSR dry-run cases are unavailable")
    board_by_year = {claim["metric_period_year"]: claim for claim in board["claims"]}
    cases = [
        _case(
            "VC-REAL-R01", "Scope 1 BSR 2025: two reported values",
            catalogue["VC-REAL-R01"], _esg_sources(r01["claims"]),
            {
                "category": "current_rule_result", "finding_id": r01["finding_id"],
                "status": r01["rule_status"], "calculation": r01["rule_calculation"],
                "applicability_guard": r01["rule_guard"], "raw_difference": r01["raw_difference"],
                "interpretation": r01["interpretation"],
            },
            r01["missing_conditions"],
            {"comparability": "Do both Scope 1 values refer to the same period, unit, metric definition and verified boundary? Which source is primary or revised?"},
        ),
        _case(
            "VC-REAL-WORKFORCE-2025", "Workforce ESG versus BCTC BSR 2025",
            None, _esg_sources([workforce["esg"]]) + [_financial_source(workforce["financial"])],
            {
                "category": "financial_candidate", "candidate_check_id": workforce["case_id"],
                "status": workforce["status"], "join_checks": workforce["join_checks"],
                "raw_difference": workforce["raw_difference"],
                "difference_interpretation": workforce["difference_interpretation"],
                "comparison_eligible": workforce["comparison_eligible"],
                "comparison_performed": workforce["comparison_performed"],
                "fc01_status": workforce["fc01_status"],
                "finding_created": workforce["finding_created"],
                "esg_measurement_context": workforce["esg"]["workforce_context"],
                "consolidated_financial_boundary": workforce["financial"]["scope"],
                "related_financial_observations": workforce["related_financial_observations"],
                "interpretation": workforce["interpretation"],
            },
            workforce["missing_conditions"],
            {"metric_definition": "Do ESG and consolidated BCTC count the same employee population? Check exclusions and worker categories.",
             "period": "The consolidated 1,946 is at 31 December 2025. Does the ESG 1,594 use that same date?",
             "reporting_boundary": "Which legal entities does the ESG 1,594 include? The separate BCTC also says 1,594, but numeric equality alone does not establish the ESG boundary.",
             "comparability": "Verify date, employee definition and legal-entity boundary for both values before treating the arithmetic gap as meaningful."},
        ),
    ]
    for comparison in board["comparisons"]:
        earlier = board_by_year[comparison["from_year"]]
        later = board_by_year[comparison["to_year"]]
        cases.append(_case(
            f"VC-REAL-TEMPORAL-BOARD-{comparison['from_year']}-{comparison['to_year']}",
            f"BSR board total {comparison['from_year']} → {comparison['to_year']}",
            catalogue["VC-REAL-TEMPORAL-BOARD"], _esg_sources([earlier, later]),
            {
                "category": "temporal_assessment", "comparison_id": comparison["comparison_id"],
                "status": comparison["assessment_status"],
                "from_value": comparison["from_value"], "to_value": comparison["to_value"],
                "comparison_performed": comparison["comparison_performed"],
                "numeric_change": comparison["numeric_change"],
                "flags": comparison["flags"],
                "applicability_guard": "Same company, board_total definition, unit, period type and verified boundary; review baseline/restatement changes.",
                "interpretation": board["interpretation"],
            },
            sorted(set(comparison["flags"]["missing_context"] + comparison["flags"]["incompatibilities"])),
            {"comparability": "Does board_total mean the same thing in both reports? Confirm any board, boundary, baseline or restatement change."},
        ))
    if len(cases) != 4:
        raise ValueError(f"Expected four review cases, got {len(cases)}")
    fingerprint = [{
        "case_id": case["case_id"], "system_result": case["system_result"],
        "sources": [{field: source.get(field) for field in (
            "source_ref_id", "record_type", "value", "metric_id", "unit", "scope",
            "observation_year", "report_year", "report_id", "source_file", "source_pages",
            "json_pointer",
        )} for source in case["sources"]],
    } for case in cases]
    digest = hashlib.sha256(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16].upper()
    packet_id = "BSR-STAGE17-" + digest
    # These exact sources and values are the in-progress reviewer packet. Scope
    # metadata was corrected while responses were being entered; preserve its
    # identifier so existing pending responses remain linked to the same cases.
    expected_sources = {
        "EVD-88EB1729C78C": (1780388, "BSR_2025_esg.json", (29, 65), "/environment/climate_and_ghg/scope_1_tCO2e_series_primary/3/value"),
        "EVD-25131859C4E9": (1790388, "BSR_2025_esg.json", (65,), "/environment/climate_and_ghg/appendix_alternative_2025_values/scope_1_tCO2e"),
        "EVD-E113234E5811": (1594, "BSR_2025_esg.json", (39, 66), "/social/workforce/total_employees"),
        "FIN-BSR-BCTC-2025-workforce.total": (1946, "BCTC_BSR_2025_esg.json", (14,), "/social/workforce/employees_2025_12_31"),
        "EVD-9B82B9478FB1": (5, "BSR_2023_esg.json", (36,), "/governance/board_and_sustainability_oversight/board_members"),
        "EVD-148681E219CB": (5, "BSR_2024_esg.json", (37,), "/governance/board_and_sustainability_oversight/0/metrics/board_members"),
        "EVD-D66F09A80222": (7, "BSR_2025_esg.json", (50, 51, 66), "/governance/board_and_sustainability_oversight/board_members"),
    }
    actual_sources = {
        source["source_ref_id"]: (source["value"], source["source_file"], tuple(source["source_pages"]), source["json_pointer"])
        for case in cases for source in case["sources"]
    }
    if actual_sources == expected_sources and len(cases) == 4:
        packet_id = IN_PROGRESS_BSR_PACKET_ID
    return {
        "schema_version": "0.1",
        "packet_id": packet_id,
        "company_id": "BSR",
        "scope": "Four real-data PDF review cases from the current BSR stage 17 dry-run",
        "validation_protocol": str((ROOT / "docs" / "validation-protocol.md").resolve()),
        "validation_catalogue": str(CATALOGUE.resolve()),
        "gold_label_created": False,
        "handoff_status": dry_run_report["handoff_status"],
        "handoff_preflight_summary": (
            dry_run_report["handoff_preflight"]["summary"]
            if dry_run_report["handoff_preflight"] else None
        ),
        "note": "System results and extracted text are prompts only. All cases remain pending until a reviewer supplies independent source evidence and a decision.",
        "cases": cases,
    }


def response_template(packet):
    return {
        "schema_version": "0.1",
        "packet_id": packet["packet_id"],
        "responses": [copy.deepcopy(case["review_form"]) for case in packet["cases"]],
    }


def _has_text(value):
    return isinstance(value, str) and bool(value.strip())


def validate_responses(packet, responses):
    """Check review completeness without changing catalogue, findings or gold labels."""
    packet_cases = packet.get("cases") if isinstance(packet, dict) else None
    if not isinstance(packet_cases, list) or not packet_cases or any(
        not isinstance(case, dict) or case.get("adjudication_status") != "pending_adjudication"
        for case in packet_cases
    ):
        raise ValueError("Review packet must contain pending_adjudication cases")
    expected = {case["case_id"]: case for case in packet_cases}
    if len(expected) != len(packet_cases):
        raise ValueError("Review packet has duplicate case IDs")
    errors = []
    if not isinstance(responses, dict):
        return {"valid": False, "global_errors": ["Responses JSON must be an object"], "cases": [],
                "accepted_count": 0, "gold_labels_created": 0, "catalogue_updated": False}
    if responses.get("packet_id") != packet.get("packet_id"):
        errors.append("packet_id does not match the review packet")
    schema_errors = {}
    for error in Draft202012Validator(_read(RESPONSE_SCHEMA)).iter_errors(responses):
        path = list(error.absolute_path)
        if len(path) >= 2 and path[0] == "responses" and isinstance(path[1], int):
            schema_errors.setdefault(path[1], []).append(f"schema {path[2:]}: {error.message}")
        else:
            errors.append(f"schema {path}: {error.message}")
    submitted = responses.get("responses")
    if not isinstance(submitted, list):
        submitted = []
    seen = set()
    outcomes = []
    for index, response in enumerate(submitted):
        case_id = response.get("case_id", f"row:{index + 1}") if isinstance(response, dict) else f"row:{index + 1}"
        problems = schema_errors.get(index, [])[:]
        if case_id in seen:
            problems.append("duplicate response case_id")
        seen.add(case_id)
        case = expected.get(case_id)
        if case is None:
            problems.append("case_id is not in this packet")
        status = response.get("status") if isinstance(response, dict) else None
        if not problems and status in {"accepted", "rejected", "unclear"}:
            reviewer = response.get("reviewer") or {}
            decision = response.get("decision") or {}
            if not _has_text(reviewer.get("name")):
                problems.append("reviewer.name is required for a completed review")
            if not _has_text(decision.get("rationale")):
                problems.append("decision.rationale is required for a completed review")
            if status == "accepted":
                if not _has_text(decision.get("reviewed_outcome")):
                    problems.append("decision.reviewed_outcome must state a concrete reviewed decision")
                if decision.get("system_result_assessment") not in {"confirmed", "corrected"}:
                    problems.append("decision.system_result_assessment must be confirmed or corrected")
                checks = decision.get("checks") or {}
                for field in CHECK_FIELDS:
                    if not _has_text(checks.get(field)):
                        problems.append(f"decision.checks.{field} must record the reviewer's conclusion")
                basis = response.get("source_basis") or []
                required_ids = {source["source_ref_id"] for source in case["sources"]}
                supplied_ids = {item.get("source_ref_id") for item in basis}
                if len(supplied_ids) != len(basis):
                    problems.append("source_basis must contain each source_ref_id only once")
                for source_ref_id in sorted(required_ids - supplied_ids):
                    problems.append(f"source_basis missing source_ref_id {source_ref_id}")
                for source_ref_id in sorted(supplied_ids - required_ids):
                    problems.append(f"source_basis has unknown source_ref_id {source_ref_id}")
                for item in basis:
                    if not _has_text(item.get("source_document")) or not item.get("pages") or not _has_text(item.get("observation")):
                        problems.append(f"source_basis {item.get('source_ref_id')} needs document, page(s) and observed source content")
                    elif ".pdf" not in item["source_document"].lower():
                        problems.append(f"source_basis {item['source_ref_id']} must identify the reviewed PDF")
        outcomes.append({
            "case_id": case_id,
            "submitted_status": status,
            "effective_status": status if not problems else "pending_adjudication",
            "valid": not problems,
            "errors": problems,
        })
    for case_id in expected.keys() - seen:
        outcomes.append({"case_id": case_id, "submitted_status": None,
                         "effective_status": "pending_adjudication", "valid": False,
                         "errors": ["review response missing for case"]})
    if errors:
        for outcome in outcomes:
            outcome["effective_status"] = "pending_adjudication"
    return {
        "packet_id": packet.get("packet_id"),
        "valid": not errors and all(item["valid"] for item in outcomes),
        "global_errors": errors,
        "cases": outcomes,
        "accepted_count": sum(item["effective_status"] == "accepted" for item in outcomes),
        "pending_count": sum(item["effective_status"] == "pending_adjudication" for item in outcomes),
        "rejected_count": sum(item["effective_status"] == "rejected" for item in outcomes),
        "unclear_count": sum(item["effective_status"] == "unclear" for item in outcomes),
        "gold_labels_created": 0,
        "catalogue_updated": False,
    }


def _source_line(source):
    path = source.get("extract_json_path") or source.get("source_uri") or "unavailable"
    page_sources = ", ".join(source.get("text_chunk_paths", [])) or "none"
    return (
        f"- {source['source_ref_id']} / claim {source.get('claim_id') or '—'}: "
        f"{source['value']} {source['unit']}; observation {source['observation_year']}; "
        f"report {source['report_id']} ({source['report_year']}); "
        f"{source['source_file']} p.{','.join(map(str, source['source_pages']))} "
        f"`{source['json_pointer']}`. Extract: `{path}`. PDF: {source.get('pdf_file_name') or 'unknown'} "
        f"(local path: `{source.get('pdf_local_path') or 'unavailable'}`). Source page JSON: {page_sources}."
    )


def render_markdown(packet):
    lines = [
        "# BSR stage 17 PDF review packet", "",
        f"Packet ID: `{packet['packet_id']}`. All four cases are `pending_adjudication`; no gold label is created.",
        "The linked Extract and source-page JSON locate extracted data. Reviewers must inspect the source PDF; a local PDF path is shown only when the file exists in this repository.",
        "", "Complete `review_responses.json` and run the validator before treating any response as accepted:",
        "", "```powershell",
        "python -m tools.bsr_review_packet validate --packet <review_packet.json> --responses <review_responses.json>",
        "```",
    ]
    for case in packet["cases"]:
        lines.extend(["", f"## {case['title']} (`{case['case_id']}`)", "",
                      f"Current system result: `{json.dumps(case['system_result'], ensure_ascii=False)}`", "",
                      f"Missing conditions: {', '.join(case['missing_conditions']) or 'none recorded'}.", "",
                      "Sources:", "", *[_source_line(source) for source in case["sources"]], "",
                      "Reviewer questions:", ""])
        lines.extend(f"- {field}: {question}" for field, question in case["review_questions"].items())
        lines.extend(["", "Reviewer form: status (pending_adjudication / accepted / rejected / unclear); reviewer name; "
                      "one source_basis entry per source_ref_id with document, PDF page(s) and observed content; "
                      "reviewed outcome; assessment of current result; rationale; six checks above; notes."])
    return "\n".join(lines) + "\n"


def create_packet(out_dir, handoff_path=None):
    out_dir = Path(out_dir).resolve()
    main_output = (ROOT / "output").resolve()
    if out_dir == main_output or main_output in out_dir.parents:
        raise ValueError("Review packet directory must be outside the main output/ snapshot")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError("Review packet directory must be empty")
    with tempfile.TemporaryDirectory(prefix="bsr_review_build_") as temp:
        dry_run_report = run(Path(temp), handoff_path)
    packet = build_packet(dry_run_report)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "review_packet.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "review_packet.md").write_text(render_markdown(packet), encoding="utf-8")
    (out_dir / "review_responses.json").write_text(json.dumps(response_template(packet), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return packet


def format_validation(result):
    lines = [f"Packet {result.get('packet_id')}: {'valid' if result['valid'] else 'invalid'}; "
             f"accepted {result.get('accepted_count', 0)}, pending {result.get('pending_count', 0)}, "
             f"rejected {result.get('rejected_count', 0)}, unclear {result.get('unclear_count', 0)}; gold labels created 0."]
    lines.extend(f"- Global: {error}" for error in result["global_errors"])
    for case in result["cases"]:
        lines.append(f"- {case['case_id']}: {case['effective_status']}")
        lines.extend(f"  - {error}" for error in case["errors"])
    return "\n".join(lines)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create", help="Build the unanswered BSR PDF review packet")
    create.add_argument("--out-dir", type=Path, required=True, help="New or empty temporary directory")
    create.add_argument("--handoff", type=Path, help="Optional preflight-only handoff")
    validate = commands.add_parser("validate", help="Validate completed reviewer responses without updating any snapshot")
    validate.add_argument("--packet", type=Path, required=True)
    validate.add_argument("--responses", type=Path, required=True)
    validate.add_argument("--json", action="store_true", help="Print JSON validation report")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            packet = create_packet(args.out_dir, args.handoff)
            print(f"Created {len(packet['cases'])} pending review cases in {args.out_dir.resolve()}")
            return 0
        result = validate_responses(_read(args.packet), _read(args.responses))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.exit(2, f"BSR review packet failed: {exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else format_validation(result))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
