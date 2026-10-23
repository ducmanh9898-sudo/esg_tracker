from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.extraction.toolkit import (
    VALID_REPORT_TYPES,
    build_document_spec,
    discover_pdfs,
    load_yaml,
    run_extraction,
)


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(
        description="Extract source-linked ESG and financial claim candidates from one PDF or a corpus directory."
    )
    value.add_argument("input", type=Path, help="PDF file or directory containing PDFs")
    value.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "data" / "processed" / "extract",
        help="Parent directory for immutable run folders",
    )
    value.add_argument(
        "--config",
        type=Path,
        default=ROOT / "config" / "extraction_toolkit.yml",
        help="Company registry and extraction configuration",
    )
    value.add_argument(
        "--metrics-config",
        type=Path,
        default=ROOT / "config" / "metrics.yml",
        help="ESG metric taxonomy configuration",
    )
    value.add_argument("--run-id", help="Unique output run id; default is UTC timestamp")
    value.add_argument("--ocr-dir", type=Path, help="Optional OCR sidecar root containing page-N.txt files")
    value.add_argument("--company", help="Company id override; allowed only for a single PDF")
    value.add_argument("--year", type=int, help="Reporting year override; allowed only for a single PDF")
    value.add_argument(
        "--document-type",
        choices=sorted(VALID_REPORT_TYPES),
        help="Report type override; allowed only for a single PDF",
    )
    value.add_argument("--max-pages", type=int, help="Process only the first N pages for smoke testing")
    value.add_argument('--engine', choices=['legacy', 'docling'], default='legacy', help='PDF extraction engine')
    value.add_argument("--strict", action="store_true", help="Stop when any filename cannot be classified")
    value.add_argument("--registered-only", action="store_true", help="Process only companies listed in the registry")
    value.add_argument("--dry-run", action="store_true", help="Print the document inventory without writing outputs")
    return value


def main() -> int:
    args = parser().parse_args()
    input_path = args.input.resolve()
    if not input_path.exists():
        print(f"Input does not exist: {input_path}", file=sys.stderr)
        return 2

    toolkit_config = load_yaml(args.config.resolve())
    toolkit_config.setdefault('extraction', {})['engine'] = args.engine
    metrics_config = load_yaml(args.metrics_config.resolve())
    pdfs = discover_pdfs(input_path, toolkit_config)
    if not pdfs:
        print(f"No non-empty PDF files found: {input_path}", file=sys.stderr)
        return 2
    if len(pdfs) != 1 and any((args.company, args.year, args.document_type)):
        print("--company, --year and --document-type overrides require a single PDF input.", file=sys.stderr)
        return 2

    specs = []
    failures = []
    for pdf in pdfs:
        try:
            spec = build_document_spec(pdf, toolkit_config, args.company, args.year, args.document_type)
            if args.registered_only and spec.company_id not in toolkit_config.get("companies", {}):
                continue
            specs.append(spec)
        except (ValueError, OSError) as exc:
            failures.append({"source_file": str(pdf), "error": str(exc)})
            if args.strict:
                print(json.dumps({"classification_failures": failures}, ensure_ascii=False, indent=2), file=sys.stderr)
                return 2

    inventory = {
        "documents": [
            {
                "source_file": str(item.source_path),
                "company_id": item.company_id,
                "company_name": item.company_name,
                "industry": item.industry,
                "subsector": item.subsector,
                "report_year": item.report_year,
                "report_type": item.report_type,
                "document_key": item.document_key,
            }
            for item in specs
        ],
        "classification_failures": failures,
    }
    if args.dry_run:
        print(json.dumps(inventory, ensure_ascii=False, indent=2))
        return 0 if specs else 2

    run_id = args.run_id or datetime.utcnow().strftime("run_%Y%m%dT%H%M%SZ")
    try:
        run_dir = run_extraction(
            specs=specs,
            output_root=args.output_dir.resolve(),
            run_id=run_id,
            toolkit_config=toolkit_config,
            metrics_config=metrics_config,
            ocr_root=args.ocr_dir.resolve() if args.ocr_dir else None,
            max_pages=args.max_pages,
        )
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    print(json.dumps({
        "output": str(run_dir),
        "documents": manifest["document_count"],
        "failed_documents": manifest["failed_document_count"],
        "claim_candidates": manifest["claim_candidate_count"],
        "review_items": manifest["review_item_count"],
    }, ensure_ascii=False, indent=2))
    return 0 if manifest["document_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
