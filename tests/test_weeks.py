"""Tests for week/month boundary maths."""

from datetime import date

import pytest

from app.services.weeks import month_grid, shift_month, week_bounds, week_days


def test_week_bounds_monday_start():
    # 2026-07-28 is a Tuesday.
    start, end = week_bounds(date(2026, 7, 28))
    assert start == date(2026, 7, 27)  # Monday
    assert end == date(2026, 8, 2)  # Sunday


def test_week_bounds_on_the_start_day_is_identity():
    start, _ = week_bounds(date(2026, 7, 27))
    assert start == date(2026, 7, 27)


def test_week_bounds_sunday_start():
    start, end = week_bounds(date(2026, 7, 28), week_starts_on=7)
    assert start == date(2026, 7, 26)
    assert end == date(2026, 8, 1)


def test_week_bounds_rejects_bad_start_day():
    with pytest.raises(ValueError):
        week_bounds(date(2026, 7, 28), week_starts_on=0)


def test_week_days_returns_seven_consecutive_dates():
    days = week_days(date(2026, 7, 27))
    assert len(days) == 7
    assert days[0] == date(2026, 7, 27)
    assert days[-1] == date(2026, 8, 2)


def test_month_grid_covers_whole_weeks():
    grid = month_grid(2026, 7)
    assert all(len(week) == 7 for week in grid)
    assert grid[0][0].isoweekday() == 1
    flat = [day for week in grid for day in week]
    assert date(2026, 7, 1) in flat
    assert date(2026, 7, 31) in flat


def test_shift_month_wraps_years():
    assert shift_month(2026, 1, -1) == (2025, 12)
    assert shift_month(2026, 12, 1) == (2027, 1)
