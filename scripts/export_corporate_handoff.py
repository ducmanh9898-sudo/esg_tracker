"""Export saved extraction results to a strict, partial corporate handoff."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.extraction.corporate_handoff import build_delivery, zip_delivery
from dashboard.extraction_history import history_options, load_saved_result
from src.extraction.financial_context_v2 import resolve_scope


def bsr_slot(doc):
    output = doc['output']
    report = output['reports'][0]
    def pdf_value(name, fallback):
        field = output.get('metadata', {}).get(name, {})
        return field.get('value') if field.get('status') == 'available' else fallback
    company = pdf_value('ticker_from_pdf', report.get('company_id', '')).upper()
    year = pdf_value('reporting_year', report.get('reporting_year'))
    financial = output.get('schema_version', '').startswith('esg-financial-')
    scope = pdf_value('statement_scope', None) if financial else None
    if financial and scope is None and output.get('source_blocks'):
        scope = resolve_scope(output['source_blocks'][0], output)['value']
    return company, year, 'Financial' if financial else 'ESG', scope.lower() if scope else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--result', type=Path, help='Saved worker result.json or existing upload export JSON')
    source.add_argument('--saved-id', help='History job ID or run:<id>')
    source.add_argument('--bsr-history', action='store_true', help='Latest distinct BSR PDF results in local history; always include nine expected slots')
    parser.add_argument('--destination', type=Path, required=True, help='New directory only; never overwrite an existing delivery')
    parser.add_argument('--source-info', type=Path, help='JSON keyed by PDF SHA256 with url/downloaded_at_utc; never inferred')
    parser.add_argument('--zip', action='store_true')
    args = parser.parse_args()
    if args.bsr_history:
        documents, seen, slots, excluded = [], set(), set(), []
        for option in history_options(ROOT):
            result = load_saved_result(ROOT, option['value'])
            for doc in result.get('documents', []) if result else []:
                report = doc['output']['reports'][0]
                company, year, kind, scope = bsr_slot(doc)
                if company != 'BSR' or year not in (2023, 2024, 2025):
                    continue
                digest = report['source_sha256']
                if digest not in seen:
                    financial = kind == 'Financial'
                    slot = (year, kind, scope)
                    if slot in slots and (not financial or scope is not None):
                        excluded.append({'filename': doc['filename'], 'sha256': digest, 'saved_id': option['value'],
                                         'reason': 'Older source version for the same year/type/scope; original remains in local history.'})
                        seen.add(digest)
                        continue
                    documents.append(doc)
                    seen.add(digest)
                    slots.add(slot)
        result = {'documents': documents, 'excluded_source_versions': excluded}
    elif args.saved_id:
        result = load_saved_result(ROOT, args.saved_id)
        if not result or result.get('status') != 'completed':
            parser.error('Saved result not available/completed')
    else:
        result = json.loads(args.result.read_text(encoding='utf-8'))
        if any('workspace' not in d for d in result.get('documents', [])):
            parser.error('Portable JSON lacks local workspace. Use --saved-id or a worker result.json to include original PDFs.')
    source_info = json.loads(args.source_info.read_text(encoding='utf-8')) if args.source_info else None
    report = build_delivery(result, args.destination, source_info=source_info, expected_bsr=args.bsr_history)
    if args.zip:
        report['zip'] = str(zip_delivery(args.destination))
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
