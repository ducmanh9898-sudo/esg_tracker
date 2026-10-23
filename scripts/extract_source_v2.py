"""P0/P1 source capture CLI. Semantic parsers are not implemented here."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extraction.source_v2 import capture_pdf


def main():
    parser = argparse.ArgumentParser(description='Docling source v2: checkpoint/resume and honest page coverage; not semantic extraction.')
    parser.add_argument('input', type=Path)
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'data/processed/source_v2')
    parser.add_argument('--company')
    parser.add_argument('--report-type', choices=['ESG', 'financial_statements', 'annual_report'])
    parser.add_argument('--report-year', type=int)
    parser.add_argument('--max-pages', type=int)
    parser.add_argument('--start-page', type=int, default=1)
    parser.add_argument('--retries', type=int, default=1)
    args = parser.parse_args()
    try:
        work = capture_pdf(args.input, args.output_dir, company_id=args.company,
                           report_type=args.report_type, report_year=args.report_year,
                           max_pages=args.max_pages, start_page=args.start_page, retries=args.retries,
                           progress_callback=lambda event: print(json.dumps(event), flush=True))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1
    bundle = json.loads((work / 'canonical.json').read_text(encoding='utf-8'))
    print(json.dumps({'output': str(work), 'batch': bundle['batch'], 'coverage': bundle['coverage']['counts']}, indent=2))
    return 2 if bundle['batch']['capture_status'] == 'partial' else 0


if __name__ == '__main__':
    raise SystemExit(main())
