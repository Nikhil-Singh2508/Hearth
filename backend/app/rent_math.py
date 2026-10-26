"""Pure rental calendar and INR arithmetic functions (posting is not implemented)."""
import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal

RUPEE = Decimal("0.01")


def money(value: Decimal) -> Decimal:
    return value.quantize(RUPEE, rounding=ROUND_HALF_UP)


def due_date(year: int, month: int, due_day: int) -> date:
    if not 1 <= due_day <= 31:
        raise ValueError("due_day must be between 1 and 31")
    return date(year, month, min(due_day, calendar.monthrange(year, month)[1]))


def prorated_rent(monthly_rent: Decimal, billable_days: int, days_in_month: int,
                  method: Literal["actual", "30_day"] = "actual") -> tuple[Decimal, dict[str, str | int]]:
    if monthly_rent < 0 or billable_days < 0 or days_in_month not in range(28, 32):
        raise ValueError("Invalid rent or calendar day count")
    basis = days_in_month if method == "actual" else 30
    amount = money(monthly_rent * Decimal(billable_days) / Decimal(basis))
    return amount, {"method": method, "monthly_rent": str(monthly_rent),
                    "billable_days": billable_days, "basis_days": basis, "amount": str(amount)}


@dataclass(frozen=True)
class LateFeeRule:
    kind: Literal["fixed", "daily", "percentage"]
    amount: Decimal
    grace_days: int = 0
    cap: Decimal | None = None


def late_fee(principal_remaining: Decimal, days_past_due: int, rule: LateFeeRule) -> Decimal:
    """Fees are based only on unpaid rent principal, never on prior fees."""
    if (principal_remaining < 0 or rule.amount < 0 or rule.grace_days < 0
            or (rule.cap is not None and rule.cap < 0)
            or rule.kind not in {"fixed", "daily", "percentage"}):
        raise ValueError("Late fee values cannot be negative")
    chargeable_days = max(0, days_past_due - rule.grace_days)
    if chargeable_days == 0 or principal_remaining == 0:
        return Decimal("0.00")
    if rule.kind == "fixed":
        fee = rule.amount
    elif rule.kind == "daily":
        fee = rule.amount * chargeable_days
    else:
        fee = principal_remaining * rule.amount / Decimal("100")
    if rule.cap is not None:
        fee = min(fee, rule.cap)
    return money(fee)
