"""Week and month boundary helpers.

Kept separate from the summary service so both the calendar and the summary
page agree on exactly where a week starts.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

#: ISO weekday the week starts on (1 = Monday). Overridable per app config.
DEFAULT_WEEK_START = 1


def week_bounds(day: date, week_starts_on: int = DEFAULT_WEEK_START) -> tuple[date, date]:
    """Return the (first_day, last_day) of the week containing ``day``.

    ``week_starts_on`` uses ISO weekdays: 1 = Monday ... 7 = Sunday.
    """
    if not 1 <= week_starts_on <= 7:
        raise ValueError("week_starts_on must be between 1 (Monday) and 7 (Sunday)")
    offset = (day.isoweekday() - week_starts_on) % 7
    start = day - timedelta(days=offset)
    return start, start + timedelta(days=6)


def week_days(start: date) -> list[date]:
    """Return the seven dates of the week beginning at ``start``."""
    return [start + timedelta(days=i) for i in range(7)]


def month_bounds(year: int, month: int) -> tuple[date, date]:
    """Return the (first_day, last_day) of the given month."""
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def month_grid(
    year: int, month: int, week_starts_on: int = DEFAULT_WEEK_START
) -> list[list[date]]:
    """Return the month laid out as whole weeks (leading/trailing days included)."""
    first, last = month_bounds(year, month)
    grid_start, _ = week_bounds(first, week_starts_on)
    _, grid_end = week_bounds(last, week_starts_on)

    weeks: list[list[date]] = []
    cursor = grid_start
    while cursor <= grid_end:
        weeks.append(week_days(cursor))
        cursor += timedelta(days=7)
    return weeks


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """Return ``(year, month)`` moved ``delta`` months from the given month."""
    index = (year * 12 + (month - 1)) + delta
    return index // 12, index % 12 + 1
