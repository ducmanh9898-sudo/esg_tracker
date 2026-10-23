"""Find exact, source-located governance/policy text overlap for human review."""
import argparse
import hashlib
import json
from pathlib import Path
import unicodedata

import fitz

from kg.corporate_adapter import digest
from kg.text_normalize import normalized_label


def normalized_with_offsets(value):
    chars, offsets = [], []
    for index, char in enumerate(value):
        for part in unicodedata.normalize("NFD", char.lower().replace("đ", "d")):
            if unicodedata.combining(part):
                continue
            if "a" <= part <= "z" or "0" <= part <= "9":
                chars.append(part)
                offsets.append(index)
            elif chars and chars[-1] != " ":
                chars.append(" ")
                offsets.append(index)
    while chars and chars[-1] == " ":
        chars.pop()
        offsets.pop()
    return "".join(chars), offsets


def scan(claims_path, registry_path, output_path, min_words=12):
    output_path = Path(output_path)
    if output_path.exists():
        raise ValueError("output_exists_choose_new_path")
    claims = json.loads(Path(claims_path).read_text(encoding="utf-8"))
    registry = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    cases, coverage = [], []
    for source in registry["sources"]:
        if source["status"] != "available":
            coverage.append({"report_year": source["report_year"], "status": "source_unavailable"})
            continue
        pdf_path = Path(source["path"])
        with pdf_path.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != source["sha256"]:
                raise ValueError("source_hash_mismatch:" + str(pdf_path))
        matched = 0
        with fitz.open(pdf_path) as pdf:
            pages = [(page.get_text(), None) for page in pdf]
            pages = [(text, *normalized_with_offsets(text)) for text, _ in pages]
            for claim in claims:
                raw = claim.get("raw_record") or {}
                if (claim.get("report_type") != "ESG" or claim.get("report_year") != source["report_year"] or
                        (claim.get("raw_document") or {}).get("source_document_type") != "sustainability_report" or
                        raw.get("record_type") not in {"policy", "governance_evidence"}):
                    continue
                quote = raw["statement"]["original_quote"]
                needle = normalized_label(quote)
                if len(needle.split()) < min_words:
                    continue
                for page_index, (text, normalized, offsets) in enumerate(pages):
                    start = normalized.find(needle)
                    if start < 0 or normalized.find(needle, start + 1) >= 0:
                        continue
                    end = start + len(needle)
                    char_start, char_end = offsets[start], offsets[end - 1] + 1
                    annual_quote = text[char_start:char_end]
                    case_id = "NAR-" + digest([claim["record_id"], source["sha256"],
                                               page_index + 1, char_start, char_end])[:20]
                    cases.append({"candidate_id": case_id, "relation": "exact_normalized_text_overlap",
                                  "assessment_status": "review_only_not_graph_verdict",
                                  "esg_record_id": claim["record_id"], "esg_input_digest": claim["input_digest"],
                                  "esg_evidence": claim["evidence"],
                                  "company_id": claim["company_id"],
                                  "annual_source_id": source["source_id"],
                                  "annual_report_year": source["report_year"],
                                  "annual_source_sha256": source["sha256"],
                                  "annual_pdf_path": str(pdf_path.resolve()),
                                  "annual_physical_page": page_index + 1,
                                  "annual_char_start": char_start, "annual_char_end": char_end,
                                  "annual_exact_quote": annual_quote,
                                  "annual_context": text[max(0, char_start - 180):min(len(text), char_end + 180)],
                                  "uncertainty": ["text_reuse_may_share_underlying_disclosure",
                                                  "semantic_equivalence_unreviewed"],
                                  "decision": "pending", "reviewer": None,
                                  "reviewed_at_utc": None, "notes": None})
                    matched += 1
        coverage.append({"report_year": source["report_year"], "pages_text_checked": len(pages),
                         "status": "pdf_text_encoding_unreliable" if source["identity_method"] == "visual_cover_sha256"
                         else "partial_exact_text_search", "candidates": matched})
    result = {"schema_version": "annual-narrative-review-1.0", "gold_status": "pending_adjudication",
              "limitations": ["Only exact normalized overlaps of long policy/governance quotes are retrieved.",
                              "Text reuse is not independent corroboration; no contradiction is inferred.",
                              "Garbled PDF text cannot establish search absence."],
              "coverage": coverage, "cases": cases}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = scan(args.claims, args.registry, args.output)
    print(json.dumps({"candidates": len(result["cases"]), "coverage": result["coverage"]},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()
