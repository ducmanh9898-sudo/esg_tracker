"""Source-only repairs for misindexed headers and combined amount cells.

Never changes native checkpoints or supplies a code/value from a dictionary.
Geometry, observed headers and body cells must agree; otherwise abstain.
"""
import re

from src.extraction.financial_context_v2 import normalized


def code_header(text):
    return bool(re.search(r'^ma\s+s\b|\bma so\b|\bcode\b', normalized(text)))


def resolve_code_columns(headers, indexed, label_column):
    result = set()
    for _, header in headers:
        if not code_header(header.get('text', '')):
            continue
        box = header.get('bbox')
        if not box or label_column is None:
            if not re.search(r'thuyet|minh|notes?', normalized(header.get('text', ''))):
                result.update(range(header['start_col_offset_idx'], header['end_col_offset_idx']))
            continue
        # The first body column under the physical code header is the code.
        # A note header may have been merged into the same header rectangle.
        columns = {}
        for _, c in indexed:
            b = c.get('bbox')
            col = c['start_col_offset_idx']
            if c.get('column_header') or col <= label_column or not b:
                continue
            if b.get('coord_origin') != box.get('coord_origin'):
                continue
            if box['l'] <= (b['l'] + b['r']) / 2 <= box['r']:
                columns.setdefault(col, []).append(c)
        if columns:
            col = min(columns)
            values = [c.get('text', '').strip() for c in columns[col] if c.get('text', '').strip()]
            valid = sum(bool(re.fullmatch(r'\d{2,3}', value)) for value in values)
            if valid >= 3 and valid >= .7 * len(values):
                result.add(col)
                continue
        # Do not reinterpret an ambiguous merged code/note header as a code.
        if not re.search(r'thuyet|minh|notes?', normalized(header.get('text', ''))):
            result.update(range(header['start_col_offset_idx'], header['end_col_offset_idx']))
    return result


def split_amount_pair(index, cell, row, headers):
    """Return two virtual cells only for two explicit, aligned period columns.

Substring spans point into the unchanged native cell. The bbox remains the
whole native cell, NOT an invented token bbox. No splitting of spaced integers.
"""
    if cell['end_row_offset_idx'] - cell['start_row_offset_idx'] != 1:
        return [(index, cell)]
    raw = cell.get('text', '')
    tokens = list(re.finditer(r'\S+', raw))
    number = r'\(?-?\d{1,3}(?:[.,]\d{3}){2,}(?:[.,]\d+)?\)?'
    if len(tokens) != 2 or not all(re.fullmatch(number, t.group()) for t in tokens):
        return [(index, cell)]
    box = cell.get('bbox')
    if not box:
        return [(index, cell)]
    roles = {}
    for _, h in headers:
        text = normalized(h.get('text', ''))
        role = 'current' if re.search(r'\b(?:nam nay|so cuoi nam|current year)\b', text) else 'comparative' if re.search(r'\b(?:nam truoc|so dau nam|previous year)\b', text) else None
        if role and h['start_row_offset_idx'] < cell['start_row_offset_idx']:
            roles.setdefault(role, []).append(h)
    if set(roles) != {'current', 'comparative'} or any(len(v) != 1 for v in roles.values()):
        return [(index, cell)]
    hs = sorted([v[0] for v in roles.values()], key=lambda h: h['start_col_offset_idx'])
    boxes = [h.get('bbox') for h in hs]
    cols = [h['start_col_offset_idx'] for h in hs]
    if cols[0] == cols[1] or not all(boxes) or any(b.get('coord_origin') != box.get('coord_origin') for b in boxes):
        return [(index, cell)]
    if not (box['l'] <= boxes[0]['l'] < boxes[0]['r'] < boxes[1]['l'] <= box['r']):
        return [(index, cell)]
    # Never duplicate a separately detected value in either target column.
    if any(i != index and c['start_col_offset_idx'] in cols for i, c in row):
        return [(index, cell)]
    return [(index, {**cell, 'text': token.group(), 'start_col_offset_idx': col,
                    'end_col_offset_idx': col + 1, 'col_span': 1,
                    '_native_cell': cell, '_text_span': [token.start(), token.end()],
                    '_mapping_basis': 'two_amount_tokens_in_one_cell_under_two_explicit_period_headers'})
            for token, col in zip(tokens, cols)]
