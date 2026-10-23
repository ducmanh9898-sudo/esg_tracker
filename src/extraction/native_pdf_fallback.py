"""Literal native-PDF fallback; never certifies layout/semantic completeness.

PyMuPDF supplies text, table cells and bounding boxes. No value, header or
coordinate is generated from a language model or guessed from adjacent years.
"""
import pymupdf


def read_native_page(path, number):
    with pymupdf.open(path) as pdf:
        page = pdf[number-1]
        raw_text = page.get_text()
        if len(raw_text.strip()) < 40:
            raise ValueError('Native fallback insufficient; image-only/scan needs OCR. No successful capture asserted.')
        blocks = page.get_text('dict')['blocks']
        tables, warnings, table_regions = [], [], []
        try:
            detected = page.find_tables().tables
        except Exception as exc:
            detected = []
            warnings.append(f'Native table parser failed: {type(exc).__name__}: {exc}')
        for t in detected:
            rows = t.extract()
            cells = []
            external = bool(t.header.external)
            boxes = [box for row in t.rows for box in row.cells if box is not None]
            xs = sorted({v for box in boxes for v in (box[0], box[2])})
            ys = sorted({v for box in boxes for v in (box[1], box[3])})
            if external:
                for col, (text, box) in enumerate(zip(t.header.names, t.header.cells)):
                    if box and text:
                        cells.append(_cell(text, box, 0, col, True))
            for row_index, (row, native_row) in enumerate(zip(rows, t.rows)):
                for col, (text, box) in enumerate(zip(row, native_row.cells)):
                    if box is not None:
                        cell = _cell(text or '', box, row_index + int(external), col, not external and row_index == 0)
                        # Span indices are derived only when the parser's actual
                        # cell-edge grid matches its reported row/column counts.
                        if len(xs) == t.col_count+1:
                            right = next((i for i,v in enumerate(xs) if abs(v-box[2]) < .01), None)
                            if right is not None and right > col:
                                cell['end_col_offset_idx'] = right
                        if len(ys) == len(rows)+1:
                            bottom = next((i for i,v in enumerate(ys) if abs(v-box[3]) < .01), None)
                            if bottom is not None and bottom > row_index:
                                cell['end_row_offset_idx'] = bottom + int(external)
                        cells.append(cell)
            tables.append({'label': 'table', 'data': {'table_cells': cells, 'num_rows': len(rows) + int(external),
                                                     'num_cols': t.col_count},
                           'prov': [_prov(t.bbox, 0)]})
            table_regions.append(pymupdf.Rect(t.bbox))
        texts, pictures, ordered = [], [], []
        for b in blocks:
            if b.get('type') != 0:
                pictures.append({'label': 'picture', 'prov': [_prov(b['bbox'], 0)]})
                continue
            for line in b.get('lines', []):
                # Native line geometry separates adjacent visual cards that
                # MuPDF groups into one paragraph block. Retain each source
                # line's exact text and box; do not reconstruct via search.
                box = pymupdf.Rect(line['bbox'])
                if any(region.contains(box) for region in table_regions):
                    continue
                text = ''.join(span['text'] for span in line.get('spans', []))
                if not text.strip():
                    continue
                texts.append({'label': 'text', 'text': text,
                              'prov': [_prov(line['bbox'], len(text))]})
                ordered.append((box.y0, box.x0, {'$ref': f'#/texts/{len(texts)-1}'}))
        for i, t in enumerate(tables):
            box = t['prov'][0]['bbox']
            ordered.append((box['t'], box['l'], {'$ref': f'#/tables/{i}'}))
        native = {'texts': texts, 'tables': tables, 'pictures': pictures,
                  'body': {'children': [ref for _, _, ref in sorted(ordered, key=lambda x: (x[0], x[1]))]},
                  'pages': {'1': {'size': {'width': page.rect.width, 'height': page.rect.height}}}}
        return {'status': 'partial', 'conversion_status': 'native_fallback_layout_unverified',
                'read_method': 'pymupdf_native_text_and_tables_fallback', 'document': native,
                'markdown': raw_text, 'native_text_full': raw_text, 'fallback_warnings': warnings,
                'error': {'type': 'FALLBACK_REQUIRES_REVIEW',
                          'message': 'Docling completion unavailable; literal native text/cells retained. Charts, merged headers and layout need review.'}}


def _prov(box, length):
    return {'page_no': 1, 'bbox': {'l': box[0], 't': box[1], 'r': box[2], 'b': box[3], 'coord_origin': 'TOPLEFT'},
            'charspan': [0, length]}


def _cell(text, box, row, col, header):
    return {'text': text, 'start_row_offset_idx': row, 'end_row_offset_idx': row+1,
            'start_col_offset_idx': col, 'end_col_offset_idx': col+1, 'column_header': header,
            'row_header': False, 'bbox': {'l': box[0], 't': box[1], 'r': box[2], 'b': box[3], 'coord_origin': 'TOPLEFT'}}
