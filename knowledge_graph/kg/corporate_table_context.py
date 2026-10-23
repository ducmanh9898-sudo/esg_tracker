"""Conservative table row context shared by Extract pairing and Graph guards."""
import re


def table_row_number(record):
    """Read an explicit row number beside the label, never infer it from a value."""
    label = record["metric_label"].strip().casefold()
    numbers = set()
    for evidence in record["evidence"]:
        lines = [line.strip() for line in (evidence.get("context_text") or "").splitlines()]
        for index, line in enumerate(lines[:-1]):
            if line.casefold() == label and re.fullmatch(r"[1-9]\d?\.\d{1,2}", lines[index + 1]):
                numbers.add(lines[index + 1])
    return next(iter(numbers)) if len(numbers) == 1 else None


def table_rows_compatible(left, right):
    left_row, right_row = table_row_number(left), table_row_number(right)
    return not (left_row or right_row) or left_row == right_row
