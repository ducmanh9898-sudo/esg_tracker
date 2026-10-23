"""Conservative recovery of missed statement tables from searchable OCR words.

Only pages with an explicit primary-statement title and explicit metric/code/
current/comparative headers qualify. Coordinates are PDF points, TOPLEFT.
No company-specific names, values, row counts or page numbers are configured.
Docling's texts remain unchanged. Derived tables are labelled for review.
"""
import re

from src.extraction.financial_context_v2 import normalized


def recover_statement_table(document, words, page_height):
    if document.get('tables'):
        return False
    titles = [t for t in document.get('texts', []) if re.match(
        r'^(?:bang can doi ke toan|bao cao ket qua hoat dong kinh doanh|bao cao luu chuyen tien te)\b',
        normalized(t.get('text', '')))]
    if not titles:
        return False
    headers = []
    for t in document.get('texts', []):
        text = normalized(t.get('text', ''))
        role = 'label' if text == 'chi tieu' else 'code' if text == 'ma so' else 'current' if text.startswith(('nam nay', 'so cuoi nam')) else 'comparative' if text in ('nam truoc', 'so dau nam') else None
        if role and t.get('prov'):
            box = t['prov'][0]['bbox']
            top = page_height - box['t'] if box.get('coord_origin') == 'BOTTOMLEFT' else box['t']
            bottom = page_height - box['b'] if box.get('coord_origin') == 'BOTTOMLEFT' else box['b']
            headers.append((role, t['text'], box['l'], box['r'], min(top, bottom), max(top, bottom)))
    by_role = {h[0]: h for h in headers}
    if set(by_role) != {'label', 'code', 'current', 'comparative'}:
        return False
    hs = [by_role[r] for r in ('label', 'code', 'current', 'comparative')]
    if not all(hs[i][2] < hs[i + 1][2] for i in range(3)):
        return False
    # Midpoint between header edges, not metric-dependent hard-coded columns.
    limits = [hs[1][2] - 8, (hs[1][3] + hs[2][2]) / 2, (hs[2][3] + hs[3][2]) / 2]
    first_y = max(h[5] for h in hs)
    code_words = sorted([w for w in words if first_y < w[1] < page_height * .85
                         and limits[0] <= (w[0] + w[2]) / 2 < limits[1]
                         and re.fullmatch(r'\d{2,3}', w[4])], key=lambda w: w[1])
    if len(code_words) < 3:
        return False
    # A row must have at least one numeric value aligned with the code.
    rows = []
    for code in code_words:
        center = (code[1] + code[3]) / 2
        aligned = [w for w in words if abs((w[1] + w[3]) / 2 - center) < max(5, (code[3] - code[1]) * .7)]
        if any((w[0] + w[2]) / 2 >= limits[1] and re.search(r'\d', w[4]) for w in aligned):
            rows.append(code)
    if len(rows) < 3:
        return False
    cells = []

    def add(text, row, col, box, header=False):
        cells.append({'text': text, 'row_span': 1, 'col_span': 1,
            'start_row_offset_idx': row, 'end_row_offset_idx': row + 1,
            'start_col_offset_idx': col, 'end_col_offset_idx': col + 1,
            'column_header': header, 'row_header': False, 'row_section': False,
            'bbox': {'l': box[0], 't': box[1], 'r': box[2], 'b': box[3], 'coord_origin': 'TOPLEFT'}})

    for col, h in enumerate(hs):
        # Preserve the whole observed header, including a unit on a second line.
        add(h[1], 0, col, (h[2], h[4], h[3], h[5]), True)
    for index, code in enumerate(rows):
        center = (code[1] + code[3]) / 2
        upper = (rows[index - 1][3] + code[1]) / 2 if index else code[1] - 4
        lower = (code[3] + rows[index + 1][1]) / 2 if index + 1 < len(rows) else code[3] + 16
        for col in range(4):
            selected = [w for w in words if upper <= (w[1] + w[3]) / 2 < lower and w[0] <= hs[3][3] + 3
                        and sum((w[0] + w[2]) / 2 >= edge for edge in limits) == col]
            if col == 1:
                selected = [code]
            if col > 0:
                selected = [w for w in selected if abs((w[1] + w[3]) / 2 - center) < max(5, (code[3] - code[1]) * .7)]
            if selected:
                selected.sort(key=lambda w: (round(w[1] / 4), w[0]))
                add(' '.join(w[4] for w in selected), index + 1, col,
                    (min(w[0] for w in selected), min(w[1] for w in selected), max(w[2] for w in selected), max(w[3] for w in selected)))
    box = {'l': min(c['bbox']['l'] for c in cells), 't': min(c['bbox']['t'] for c in cells),
           'r': max(c['bbox']['r'] for c in cells), 'b': max(c['bbox']['b'] for c in cells), 'coord_origin': 'TOPLEFT'}
    table = {'self_ref': '#/tables/0', 'label': 'table', 'parent': {'$ref': '#/body'},
             'prov': [{'page_no': 1, 'bbox': box}],
             'data': {'num_rows': len(rows) + 1, 'num_cols': 4, 'table_cells': cells},
             'layout_recovery': {'method': 'explicit_statement_headers_and_ocr_word_alignment',
                                 'status': 'needs_review', 'raw_texts_preserved': True}}
    document.setdefault('tables', []).append(table)
    document.setdefault('body', {}).setdefault('children', []).append({'$ref': '#/tables/0'})
    return True
