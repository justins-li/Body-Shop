"""Tests for the weekly muscle-coverage aggregation."""

from datetime import date

from app.exercises import MUSCLE_GROUPS
from app.models import WorkoutEntry, add_entry
from app.services.summary import summarise_entries, weekly_summary


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
    assert not summary["legs"]["worked"]


def test_pull_ups_work_biceps_and_back():
    summary = summarise_entries([entry("pull_ups", 4)])
    assert summary["biceps"]["worked"] and summary["back"]["worked"]
    assert not summary["chest"]["worked"]


def test_squat_works_legs_only():
    summary = summarise_entries([entry("squat", 5)])
    assert summary["legs"]["worked"]
    assert [m for m, g in summary.items() if g["worked"]] == ["legs"]


def test_a_single_set_is_enough_to_mark_worked():
    summary = summarise_entries([entry("squat", 1)])
    assert summary["legs"]["worked"] is True


def test_sets_accumulate_across_entries_and_exercises():
    summary = summarise_entries([entry("bench_press", 3), entry("pull_ups", 2), entry("squat", 4)])
    assert summary["chest"]["sets"] == 3
    assert summary["triceps"]["sets"] == 3
    assert summary["back"]["sets"] == 2
    assert summary["legs"]["sets"] == 4
    assert all(group["worked"] for group in summary.values())


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
    assert sorted(summary["muscles_worked"]) == ["back", "biceps", "legs"]
    assert summary["sets_per_day"]["2026-07-27"] == 5
    assert summary["sets_per_day"]["2026-07-30"] == 0
