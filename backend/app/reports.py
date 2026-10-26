"""Reporting date windows and calendar helpers."""
import calendar
from datetime import date


def month_start(value: date) -> date:
    return value.replace(day=1)


def next_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def period_bounds(period: str, today: date) -> tuple[date, date]:
    current = month_start(today)
    if period == "this_month":
        return current, next_month(current)
    if period == "last_month":
        return add_months(current, -1), current
    if period == "this_quarter":
        quarter_start = date(today.year, ((today.month - 1) // 3) * 3 + 1, 1)
        return quarter_start, next_month(add_months(quarter_start, 2))
    raise ValueError("Unsupported report period")


def trailing_months(today: date, count: int = 6) -> list[date]:
    current = month_start(today)
    return [add_months(current, offset) for offset in range(1 - count, 1)]
