from datetime import date

import pytest

from app.exports import build_csv, safe_csv_cell
from app.reports import period_bounds, trailing_months


def test_report_periods_use_half_open_calendar_boundaries():
    today = date(2026, 10, 20)
    assert period_bounds("this_month", today) == (date(2026, 10, 1), date(2026, 11, 1))
    assert period_bounds("last_month", today) == (date(2026, 9, 1), date(2026, 10, 1))
    assert period_bounds("this_quarter", today) == (date(2026, 10, 1), date(2027, 1, 1))


def test_trailing_report_months_include_current_month_in_order():
    assert trailing_months(date(2026, 1, 20), 4) == [
        date(2025, 10, 1), date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)
    ]


def test_unknown_report_period_rejected():
    with pytest.raises(ValueError, match="Unsupported"):
        period_bounds("all_time", date(2026, 10, 20))


@pytest.mark.parametrize("value", ["=1+1", "+cmd", "-1+2", "@SUM(A1:A2)", "  =2+2", "\t=3+3", "\r=4+4", "\x00=5+5"])
def test_csv_cells_neutralize_spreadsheet_formula_prefixes(value):
    assert safe_csv_cell(value).startswith("'")


def test_csv_uses_quoted_rfc_style_rows_and_formula_safe_text():
    content = build_csv(["description", "amount"], [["Tap, replaced", "1200.00"], ["=HYPERLINK(1)", "20.00"]])
    assert '"Tap, replaced",1200.00\r\n' in content
    assert "'=HYPERLINK(1),20.00" in content
