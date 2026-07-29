"""Tests for the weekly muscle-coverage aggregation."""

from datetime import date

import pytest

from app.exercises import LARGE_MUSCLE_TARGET, MUSCLE_GROUPS, SMALL_MUSCLE_TARGET
from app.models import WorkoutEntry, add_entry
from app.services.summary import grade, summarise_entries, weekly_summary


def entry(exercise_id: str, sets: int, day: str = "2026-07-28") -> WorkoutEntry:
    return WorkoutEntry(id=1, entry_date=date.fromisoformat(day), exercise_id=exercise_id, sets=sets)


def test_empty_week_marks_nothing_worked():
    summary = summarise_entries([])
    assert set(summary) == set(MUSCLE_GROUPS)
    assert all(not group["worked"] for group in summary.values())
    assert all(group["sets"] == 0 for group in summary.values())


def test_bench_press_works_chest_and_triceps():
    summary = summarise_entries([entry("bench_press", 3)])
    assert summary["chest"]["worked"] and summary["chest"]["sets"] == 3
    assert summary["triceps"]["worked"] and summary["triceps"]["sets"] == 3
    assert not summary["back"]["worked"]
    assert not summary["biceps"]["worked"]
    assert not summary["quads"]["worked"]


def test_pull_ups_work_biceps_and_back():
    summary = summarise_entries([entry("pull_ups", 4)])
    assert summary["biceps"]["worked"] and summary["back"]["worked"]
    assert not summary["chest"]["worked"]


def test_squat_works_both_thigh_groups():
    summary = summarise_entries([entry("squat", 5)])
    assert [m for m, g in summary.items() if g["worked"]] == ["quads", "hamstrings"]
    assert summary["quads"]["sets"] == summary["hamstrings"]["sets"] == 5


def test_sit_ups_work_abs_only():
    summary = summarise_entries([entry("sit_ups", 2)])
    assert [m for m, g in summary.items() if g["worked"]] == ["abs"]


def test_a_single_set_is_enough_to_mark_worked():
    summary = summarise_entries([entry("squat", 1)])
    assert summary["quads"]["worked"] is True


def test_sets_accumulate_across_entries_and_exercises():
    summary = summarise_entries(
        [entry("bench_press", 3), entry("pull_ups", 2), entry("squat", 4), entry("sit_ups", 1)]
    )
    assert summary["chest"]["sets"] == 3
    assert summary["triceps"]["sets"] == 3
    assert summary["back"]["sets"] == 2
    assert summary["quads"]["sets"] == 4
    assert summary["hamstrings"]["sets"] == 4
    assert summary["abs"]["sets"] == 1
    assert all(group["worked"] for group in summary.values())


@pytest.mark.parametrize(
    ("sets", "expected"),
    [
        (0, ("rest", 0.0)),
        (1, ("trained", 0.05)),  # lightest green
        (10, ("trained", 0.5)),
        (20, ("trained", 1.0)),  # darkest green: exactly on target
        (21, ("over", 0.1)),  # lightest red: one set past
        (30, ("over", 1.0)),  # darkest red: half the target over
        (60, ("over", 1.0)),  # and it clamps there
    ],
)
def test_grade_ramps_green_to_target_then_red(sets, expected):
    assert grade(sets, LARGE_MUSCLE_TARGET) == expected


def test_small_muscles_saturate_on_half_the_volume():
    assert grade(10, SMALL_MUSCLE_TARGET) == ("trained", 1.0)
    assert grade(11, SMALL_MUSCLE_TARGET) == ("over", 0.2)
    assert grade(15, SMALL_MUSCLE_TARGET) == ("over", 1.0)


def test_targets_are_larger_for_large_muscle_groups():
    summary = summarise_entries([])
    assert summary["chest"]["target"] == LARGE_MUSCLE_TARGET
    assert summary["quads"]["target"] == LARGE_MUSCLE_TARGET
    assert summary["biceps"]["target"] == SMALL_MUSCLE_TARGET
    assert summary["abs"]["target"] == SMALL_MUSCLE_TARGET


def test_group_over_its_target_reports_the_overshoot():
    summary = summarise_entries([entry("sit_ups", 14)])
    abs_group = summary["abs"]
    assert abs_group["state"] == "over"
    assert abs_group["over"] == 4
    assert abs_group["intensity"] == 0.8


def test_group_under_its_target_is_not_over():
    summary = summarise_entries([entry("sit_ups", 9)])
    assert summary["abs"]["state"] == "trained"
    assert summary["abs"]["over"] == 0


def test_weekly_summary_lists_groups_at_and_over_target(app):
    with app.app_context():
        add_entry("2026-07-28", "sit_ups", 12)  # small target 10 → over
        add_entry("2026-07-28", "bench_press", 20)  # chest target 20 → exactly at it
        summary = weekly_summary(date(2026, 7, 28))

    # Bench press pushes triceps (small target) past 10 on the same sets.
    assert summary["muscles_over"] == ["abs", "triceps"]
    assert summary["muscles_at_target"] == ["chest", "abs", "triceps"]
    assert summary["muscles"]["chest"]["state"] == "trained"
    assert summary["muscles"]["chest"]["intensity"] == 1.0


def test_exercise_names_are_listed_without_duplicates():
    summary = summarise_entries([entry("bench_press", 3), entry("bench_press", 2)])
    assert summary["chest"]["exercises"] == ["Bench press"]
    assert summary["chest"]["sets"] == 5


def test_weekly_summary_only_includes_the_target_week(app):
    with app.app_context():
        add_entry("2026-07-27", "squat", 5)  # Monday, in week
        add_entry("2026-08-02", "pull_ups", 2)  # Sunday, in week
        add_entry("2026-08-03", "bench_press", 3)  # next Monday, out of week

        summary = weekly_summary(date(2026, 7, 28))

    assert summary["week_start"] == "2026-07-27"
    assert summary["week_end"] == "2026-08-02"
    assert summary["total_sets"] == 7
    assert sorted(summary["muscles_worked"]) == ["back", "biceps", "hamstrings", "quads"]
    assert summary["sets_per_day"]["2026-07-27"] == 5
    assert summary["sets_per_day"]["2026-07-30"] == 0
