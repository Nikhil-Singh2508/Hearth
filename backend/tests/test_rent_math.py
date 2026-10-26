from datetime import date
from decimal import Decimal

import pytest

from app.rent_math import LateFeeRule, due_date, late_fee, prorated_rent


@pytest.mark.parametrize("year,month,day,expected", [
    (2024, 2, 31, date(2024, 2, 29)), (2025, 2, 31, date(2025, 2, 28)),
    (2025, 4, 30, date(2025, 4, 30)),
])
def test_due_day_clamps_to_month_end(year, month, day, expected):
    assert due_date(year, month, day) == expected


def test_actual_day_proration_records_snapshot_and_rounds_half_up():
    amount, snapshot = prorated_rent(Decimal("30000"), 15, 30)
    assert amount == Decimal("15000.00")
    assert snapshot == {"method": "actual", "monthly_rent": "30000", "billable_days": 15,
                        "basis_days": 30, "amount": "15000.00"}


def test_fixed_30_day_proration_is_available():
    amount, snapshot = prorated_rent(Decimal("31000"), 31, 31, "30_day")
    assert amount == Decimal("32033.33")
    assert snapshot["basis_days"] == 30


def test_late_fee_is_calculated_on_remaining_principal_after_grace_and_capped():
    rule = LateFeeRule("daily", Decimal("100"), grace_days=3, cap=Decimal("250"))
    assert late_fee(Decimal("20000"), 5, rule) == Decimal("200.00")
    assert late_fee(Decimal("20000"), 10, rule) == Decimal("250.00")
    assert late_fee(Decimal("0"), 10, rule) == Decimal("0.00")
