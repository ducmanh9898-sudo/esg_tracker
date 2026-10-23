from src.extraction.docling_backend import table_rows


def test_table_rows_preserve_empty_and_merged_cells():
    empty = {'text': '', 'start_row_offset_idx': 0, 'end_row_offset_idx': 1,
             'start_col_offset_idx': 1, 'end_col_offset_idx': 2}
    merged = {'text': 'Doanh thu', 'start_row_offset_idx': 0, 'end_row_offset_idx': 2,
              'start_col_offset_idx': 0, 'end_col_offset_idx': 1}
    rows = table_rows({'data': {'num_rows': 2, 'table_cells': [empty, merged]}})
    assert rows[0]['cells'] == [merged, empty]
    assert rows[1]['cells'] == [merged]
