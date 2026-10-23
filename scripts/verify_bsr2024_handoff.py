"""Source-reviewed sample oracle, NOT a repair/extraction rule for BSR reports.

Expected values were read visually from the supplied PDF. This script only
compares parser output and writes a separate QA report; it never fills cells.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.extraction.financial_semantics_v3 import relative_role
from src.extraction.source_v2 import atomic_json, file_hash
from src.extraction.financial_v2 import validate_financial

SHA = 'f31fb2cb6282c9b87a7ce5a7d4027493743e066264c597daf15cf05931f275a6'
# page, code, current, comparative; original PDF pages are 1-based.
SAMPLES = [
    (7, '270', '88386867728798', '86594660994410'),
    (8, '300', '32848858696659', '29325965248034'),
    (8, '400', '55538009032139', '57268695746376'),
    (8, '440', '88386867728798', '86594660994410'),
    (9, '01', '123027063879559', '147423365943576'),
    (9, '50', '735998810618', '9639335022241'),
    (9, '60', '591091587455', '8592578972011'),
    (9, '61', '631130749304', '8649771483353'),
    (9, '62', '-40039161849', '-57192511342'),
    (10, '20', '-80470180397', '11673333341157'),
    (10, '30', '7989760008964', '-17874057088730'),
    (11, '33', '105385797629326', '95396377675905'),
    (11, '34', '-99372436672700', '-93407413272657'),
    (11, '36', '-2180488607515', '-2165547068085'),
    (11, '40', '3832872349111', '-176582664837'),
    (11, '50', '11742162177678', '-6377306412410'),
    (11, '60', '17000621246736', '22853096476348'),
    (11, '61', '252207175416', '524831182798'),
    (11, '70', '28994990599830', '17000621246736'),
]


def verify(package):
    package = Path(package).resolve()
    manifest = json.loads((package / 'manifest.json').read_text(encoding='utf8'))
    entry = next(d for d in manifest['documents'] if d['source_pdf_sha256'] == SHA)
    path = package / entry['json_path']
    data = json.loads(path.read_text(encoding='utf8'))
    assert file_hash(package / entry['source_pdf_path']) == SHA
    assert file_hash(path) == entry['json_sha256']
    measurements = [r for r in data['records'] if r['record_type'] == 'measurement']
    samples = []
    for page, code, current, comparative in SAMPLES:
        for is_current, expected in [(True, current), (False, comparative)]:
            found = [r for r in measurements if r['field_sources']['/payload/raw_value'][0]['pdf_page'] == page
                and (r['payload'].get('item_code_raw') or '').strip() == code
                and relative_role(' | '.join(r['payload']['column_headers_raw'])) in
                    (('current', 'current_flow') if is_current else ('comparative', 'opening_balance'))]
            record = found[0] if len(found) == 1 else None
            samples.append({'pdf_page': page, 'code': code, 'column_role': 'current' if is_current else 'comparative',
                'expected_decimal': expected, 'observed_decimal': record['payload']['parsed_value'] if record else None,
                'status': 'pass' if record and record['payload']['parsed_value'] == expected else 'mismatch_or_missing',
                'record_id': record['record_id'] if record else None,
                'source': record['field_sources']['/payload/raw_value'] if record else [],
                'meaning': 'Sample raw/parsed value comparison only; not full record/boundary verification.'})
    integrity = validate_financial(data, path.parent)
    result = {'source_pdf_sha256': SHA, 'json_sha256': file_hash(path),
        'source_and_reference_errors': integrity,
        'sample_counts': {'checked': len(samples), 'pass': sum(s['status'] == 'pass' for s in samples)},
        'samples': samples,
        'visual_review_scope': {'main_tables_pdf_pages': [7, 8, 9, 10, 11],
                                'metadata_pdf_pages': [1, 2, 5, 6], 'suspect_notes_pdf_pages': [26, 27]},
        'known_limits': [
            'Missing or malformed item codes remain unresolved/raw OCR; formulas requiring these codes may not be eligible.',
            'Multiple contaminated amount tokens in one column are not assigned to rows without additional positional evidence.',
            'Many note tables still have unresolved periods/units, split labels or missing/damaged note numbers.',
            'Blank/dash nulls are not automatically OCR errors and are not converted to zero.',
            'Sample passes do not establish all cells, narratives, reporting boundary or audit assurance. Semantic status remains partial.'],
        'all_values_verified': False, 'source_values_modified': False}
    atomic_json(package / 'verification.json', result)
    if integrity or any(s['status'] != 'pass' for s in samples):
        raise ValueError('Handoff sample QA failed; see verification.json')
    print(json.dumps(result['sample_counts']))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', type=Path)
    verify(parser.parse_args().package)
