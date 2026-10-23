"""Extra delivery checks: nine-slot matrix, exact numeric product, native quotes.

Runs the supplied validator first. Does not adjudicate PDF/OCR semantics.
"""
import argparse
from decimal import Decimal, localcontext
import json
from pathlib import Path
import sys
import importlib.util
import re
from datetime import datetime, timezone



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('delivery', type=Path)
    parser.add_argument('--bsr-nine', action='store_true')
    parser.add_argument('--pending-only', action='store_true', help='Pre-handoff gate: no record may already be reviewed')
    args = parser.parse_args()
    folder = args.delivery.resolve()
    spec = importlib.util.spec_from_file_location('standalone_delivery_validator', folder/'validation/validate.py')
    v = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v)
    if v.main(['--manifest', str(folder/'manifest.json'), '--pdf-dir', str(folder/'pdf')]):
        return 1
    manifest = v.load_json(folder/'manifest.json')
    errors, products, quotes, checkpoints = [], 0, 0, 0
    if args.bsr_nine:
        expected = {(y, k, s) for y in (2023,2024,2025) for k,s in
                    (('ESG',None),('Financial','Separate'),('Financial','Consolidated'))}
        delivered = [r for r in manifest['files'] if r['status'] != 'unavailable']
        slots = {(r['report_year'],r['report_type'],r['financial_scope']) for r in delivered}
        if len(delivered) != 9 or slots != expected:
            errors.append('BSR_NINE_SLOT_MATRIX_INCOMPLETE_OR_DUPLICATED')
    for row in manifest['files']:
        if row['status'] == 'unavailable':
            continue
        h = v.load_json(folder / row['json_path'])
        digest = row['pdf_sha256']
        original = v.load_json(folder/'notes/native'/f'{digest}.json')
        records = {r['record_id']:r for r in original['records']}
        pages = {}
        for a in original['source_artifacts']:
            if a['kind'] != 'page_checkpoint':
                continue
            path = (folder/'notes/native'/digest/a['path']).resolve()
            if not path.is_relative_to(folder) or v.sha256(path) != a['sha256']:
                errors.append(f'{digest}: native_checkpoint_hash_mismatch')
                continue
            page = v.load_json(path)
            pages[page['pdf_page']] = page
            checkpoints += 1
        for record in h['records']:
            if args.pending_only and (record['quality']['review_status'] != 'pending_human_review' or record['boundary']['verified']):
                errors.append(f"{record['record_id']}: unexpected_automatic_review")
            if record['value']['status'] == 'available':
                try:
                    # V2 may recover a source sentence not previously mapped to
                    # a native measurement. Check literal amount against its
                    # checkpoint evidence, not against a fabricated native row.
                    if (record['value']['normalization_note'] or '').startswith('Explicit Vietnamese source notation;'):
                        literal = record['value']['original_value'].strip()
                        if not any(literal in e['exact_quote'] for e in record['evidence']):
                            raise ValueError('source amount absent')
                        if not re.fullmatch(r'\(?-?(?:\d{1,3}(?:\.\d{3})+|\d+)(?:,\d+)?\)?', literal):
                            raise ValueError('not unambiguous Vietnamese notation')
                        raw = literal.replace('.', '').replace(',', '.')
                        if raw.startswith('(') and raw.endswith(')'):
                            raw = '-' + raw[1:-1]
                    else:
                        payload = records[record['record_id']]['payload']
                        raw = payload.get('parsed_value', payload.get('value', payload.get('target_value')))
                    with localcontext() as ctx:
                        ctx.prec = 256
                        expected_value = Decimal(str(raw)) * Decimal(str(record['value']['normalization_factor']))
                        if expected_value != Decimal(str(record['value']['normalized_value'])):
                            errors.append(f"{record['record_id']}: normalized_value_product_mismatch")
                    products += 1
                except Exception:
                    errors.append(f"{record['record_id']}: normalization_not_reproducible")
            for ev in record['evidence']:
                try:
                    target = pages[ev['physical_page']]
                    for token in ev['element_id'].lstrip('/').split('/'):
                        token = token.replace('~1','/').replace('~0','~')
                        target = target[int(token)] if isinstance(target,list) else target[token]
                    if ev['exact_quote'] not in target['text']:
                        raise ValueError('quote mismatch')
                    quotes += 1
                except Exception:
                    errors.append(f"{record['record_id']}: quote_not_resolved_in_native_checkpoint")
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'passed': not errors, 'errors': errors,
              'normalized_values_recomputed': products, 'native_quotes_checked': quotes,
              'native_checkpoint_hashes_checked': checkpoints, 'human_semantic_review_pending': True}
    (folder/'validation/extra_checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
