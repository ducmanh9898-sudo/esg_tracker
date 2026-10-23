"""Inspect a v2 upload without dumping native checkpoints to the console."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser()
    parser.add_argument('json', type=Path)
    parser.add_argument('--pdf', type=Path)
    args = parser.parse_args()
    upload = json.loads(args.json.read_text(encoding='utf-8'))
    print('ROOT', list(upload))
    if args.pdf:
        import pymupdf
        print('PDF', hashlib.sha256(args.pdf.read_bytes()).hexdigest())
        with pymupdf.open(args.pdf) as pdf:
            print('PAGES', len(pdf))
            print('NATIVE_TEXT_LENGTHS', [len(page.get_text()) for page in pdf])
    for document in upload.get('documents', []):
        output = document['output']
        print('DOCUMENT', document['filename'], output['reports'], output['counts'])
        print('CAPTURE', document['coverage']['counts'], 'SEMANTIC', output.get('semantic_status'))
        print('ISSUES', Counter(i['code'] for i in output['issues']))
        print('MEASUREMENT_NULLS', Counter(key for r in output['records'] if r['record_type'] == 'measurement'
                    for key, value in [('period', r.get('content_period')), ('unit', r['payload'].get('unit')),
                                       ('value', r['payload'].get('parsed_value')), ('scope', r['payload'].get('statement_scope'))] if value is None))
        for block in output['source_blocks']:
            page = block['source']['pdf_page']
            if block['kind'] == 'tables':
                cells = block['original_cells'] or []
                print('TABLE', page, block['block_id'][-8:], 'CELLS', len(cells),
                      'HEADERS', [(c['start_row_offset_idx'], c['start_col_offset_idx'], c.get('text')) for c in cells if c.get('column_header')],
                      'SAMPLE', [(c['start_row_offset_idx'], c['start_col_offset_idx'], c.get('text')) for c in cells[:14]])
            elif page <= 8:
                print('TEXT', page, block.get('label'), repr(block.get('original_text')))


if __name__ == '__main__':
    main()
