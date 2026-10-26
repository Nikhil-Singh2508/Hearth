"""CSV generation safeguards for spreadsheet formula injection."""
import csv
from io import StringIO
from typing import Iterable


def safe_csv_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value)
    probe = text.lstrip()
    if (text and ord(text[0]) < 32) or probe.startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def build_csv(headers: Iterable[str], rows: Iterable[Iterable[object]]) -> str:
    output = StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    writer.writerow(headers)
    for row in rows:
        writer.writerow([safe_csv_cell(value) for value in row])
    return output.getvalue()
