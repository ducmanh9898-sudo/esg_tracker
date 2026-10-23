"""Export full page text, every OCR numeric occurrence and monetary groups.

This is a lossless OCR coverage export, not a claim that all table cells have
been verified. Missing spatial information is represented explicitly.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
from datetime import datetime, timezone

NUMERIC = re.compile(r"(?<![A-Za-z0-9])\(?-?\d+(?:[.,/]\d+)*\)?(?:\s*%)?")
MONEY = re.compile(r"^\(?-?\d{1,3}(?:[.,]\d{3}){2,}\)?$")


def parse_money(text):
    sign = -1 if text.startswith(('(', '-')) else 1
    return sign * int(re.sub(r'\D', '', text))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_pdf', type=Path)
    parser.add_argument('pages_json', type=Path)
    parser.add_argument('claims_json', type=Path)
    parser.add_argument('output_json', type=Path)
    args = parser.parse_args()
    extracted = json.loads(args.pages_json.read_text(encoding='utf-8'))
    digest = hashlib.sha256(args.source_pdf.read_bytes()).hexdigest()
    assert digest == extracted['document']['source_sha256'], 'Source PDF differs from OCR input'
    claims = json.loads(args.claims_json.read_text(encoding='utf-8'))['records']
    pages, numbers, groups = [], [], []
    for page in extracted['pages']:
        p = page['page_number']
        lines = page['text'].splitlines()
        section = ('disclosure_and_cover' if p <= 4 else 'management_report' if p <= 6
                   else 'audit_report' if p <= 8 else 'balance_sheet' if p <= 10
                   else 'income_statement' if p == 11 else 'cash_flow_statement' if p <= 13
                   else 'notes_to_financial_statements')
        page_numbers = []
        for i, line in enumerate(lines):
            for match in NUMERIC.finditer(line):
                identifier = f'BSR-2025-P{p:02d}-N{len(page_numbers)+1:04d}'
                raw = match.group()
                monetary = bool(MONEY.fullmatch(raw.strip()))
                item = {
                    'number_id': identifier, 'pdf_page': p, 'line_number': i+1,
                    'original_text': raw, 'original_line': line,
                    'value': parse_money(raw.strip()) if monetary else None,
                    'value_kind': 'grouped_numeric_candidate' if monetary else 'unclassified_numeric_token',
                    'unit': None, 'period_year': None, 'column_label': None,
                    'context_before': lines[max(0,i-3):i],
                    'context_after': lines[i+1:i+4],
                    'extraction_method': page['extraction_method'],
                    'review_status': 'unreviewed',
                }
                numbers.append(item)
                page_numbers.append(identifier)
        i = 0
        while i < len(lines):
            if not MONEY.fullmatch(lines[i].strip()):
                i += 1
                continue
            start = i
            raw_values = []
            while i < len(lines) and MONEY.fullmatch(lines[i].strip()):
                raw_values.append(lines[i].strip())
                i += 1
            groups.append({
                'group_id': f'BSR-2025-P{p:02d}-G{start+1:04d}',
                'pdf_page': p, 'section': section,
                'label_context_ocr': lines[max(0,start-4):start],
                'line_start': start+1, 'line_end': i,
                'original_values': raw_values,
                'values_in_ocr_order': [parse_money(v) for v in raw_values],
                'following_context_ocr': lines[i:i+3],
                'unit_candidates': ['VND'] if 'VND' in page['text'].upper() else [],
                'column_mapping': None, 'period_mapping': None,
                'review_status': 'needs_table_alignment',
                'uncertainty_reason': 'OCR text lacks cell coordinates; sequence alone cannot identify empty cells, column years or merged labels.',
            })
        pages.append({
            **page, 'section': section,
            'printed_page_number_candidate': p-4 if p >= 5 else None,
            'lines': [{'line_number': n+1, 'original_text': line} for n,line in enumerate(lines)],
            'numeric_occurrence_ids': page_numbers,
        })
    payload = {
        'schema_version': '1.0',
        'document': {
            **extracted['document'], 'source_path': str(args.source_pdf.resolve()),
            'financial_statement_scope': 'Separate',
            'financial_year': 2025, 'comparative_year': 2024,
            'reporting_date': '2025-12-31',
        },
        'coverage': {
            'pdf_pages': len(pages), 'pages_with_text': sum(bool(p['text']) for p in pages),
            'numeric_occurrences': len(numbers), 'monetary_groups': len(groups),
            'structured_key_metrics': len(claims),
            'complete_page_text_preserved': True,
            'all_detected_numeric_tokens_preserved': True,
            'all_financial_parameters_verified': False,
            'limitation': 'Full OCR content is included. OCR can omit or misread text, digits and blank cells. Detailed groups do not assert row/column mappings; only structured_key_metrics has current/comparative mappings.',
        },
        'structured_key_metrics': claims,
        'monetary_groups': groups,
        'numeric_occurrences': numbers,
        'pages': pages,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'guardrail': 'Dữ liệu hỗ trợ phân tích; không phải ý kiến kiểm toán hoặc kết luận greenwashing.',
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    saved = json.loads(args.output_json.read_text(encoding='utf-8'))
    assert len(saved['pages']) == 44
    assert len({x['number_id'] for x in numbers}) == len(numbers)
    print(json.dumps({'output': str(args.output_json.resolve()), 'coverage': payload['coverage']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
