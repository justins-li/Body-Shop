"""Tests for the weekly muscle-coverage aggregation.

Set counts are weighted: a movement's primary muscles take the whole set, its
secondary muscles half. The four movements below are used throughout because
their muscle maps are stable and cover both weights:

    Sit-Up            abs
    Pullups           back / biceps
    Barbell Squat     quads / back, calves, glutes, hamstrings
    Barbell Bench...  chest / shoulders, triceps
"""

from datetime import date

import pytest

from app.exercises import LARGE_MUSCLE_TARGET, MUSCLE_GROUPS, SMALL_MUSCLE_TARGET
from app.models import WorkoutEntry, add_entry
from app.services.summary import grade, summarise_entries, weekly_summary

BENCH = "Barbell_Bench_Press_-_Medium_Grip"
PULLUP = "Pullups"
SQUAT = "Barbell_Squat"
SITUP = "Sit-Up"
#: A stretch — loggable, but outside VOLUME_CATEGORIES.
HAMSTRING_STRETCH = "90_90_Hamstring"


def entry(exercise_id: str, sets: int, day: str = "2026-07-28") -> WorkoutEntry:
    return WorkoutEntry(id=1, entry_date=date.fromisoformat(day), exercise_id=exercise_id, sets=sets)


def worked(summary: dict) -> set[str]:
    return {muscle for muscle, group in summary.items() if group["worked"]}


def test_empty_week_marks_nothing_worked():
    summary = summarise_entries([])
    assert set(summary) == set(MUSCLE_GROUPS)
    assert all(not group["worked"] for group in summary.values())
    assert all(group["sets"] == 0 for group in summary.values())


def test_primary_muscle_takes_the_whole_set():
    summary = summarise_entries([entry(BENCH, 3)])
    assert summary["chest"]["worked"] and summary["chest"]["sets"] == 3


def test_secondary_muscles_take_half_a_set_each():
    summary = summarise_entries([entry(BENCH, 3)])
    assert summary["triceps"]["sets"] == 1.5
    assert summary["shoulders"]["sets"] == 1.5
    assert summary["triceps"]["worked"] and summary["shoulders"]["worked"]


def test_untargeted_groups_stay_untouched():
    summary = summarise_entries([entry(BENCH, 3)])
    assert not worked(summary) & {"back", "biceps", "quads", "calves"}


def test_pull_ups_work_back_and_biceps():
    summary = summarise_entries([entry(PULLUP, 4)])
    assert worked(summary) == {"back", "biceps"}
    assert summary["back"]["sets"] == 4
    assert summary["biceps"]["sets"] == 2


def test_squat_spreads_across_the_whole_lower_body():
    summary = summarise_entries([entry(SQUAT, 5)])
    assert worked(summary) == {"quads", "back", "calves", "glutes", "hamstrings"}
    assert summary["quads"]["sets"] == 5
    assert summary["hamstrings"]["sets"] == summary["glutes"]["sets"] == 2.5


def test_sit_ups_work_abs_only():
    summary = summarise_entries([entry(SITUP, 2)])
    assert worked(summary) == {"abs"}
    assert summary["abs"]["sets"] == 2


def test_a_single_set_is_enough_to_mark_worked():
    summary = summarise_entries([entry(SQUAT, 1)])
    assert summary["quads"]["worked"] is True
    # Even at half weight, a secondary group counts as trained.
    assert summary["glutes"]["worked"] is True
    assert summary["glutes"]["sets"] == 0.5


def test_non_strength_movements_do_not_count_toward_volume():
    """A hamstring stretch is loggable, but must not shade the body map."""
    summary = summarise_entries([entry(HAMSTRING_STRETCH, 4)])
    assert worked(summary) == set()
    assert summary["hamstrings"]["sets"] == 0
    assert summary["hamstrings"]["state"] == "rest"


def test_sets_accumulate_across_entries_and_exercises():
    summary = summarise_entries(
        [entry(BENCH, 3), entry(PULLUP, 2), entry(SQUAT, 4), entry(SITUP, 1)]
    )
    assert summary["chest"]["sets"] == 3
    assert summary["abs"]["sets"] == 1
    assert summary["quads"]["sets"] == 4
    # back: 2 primary from pull-ups + half of 4 squat sets.
    assert summary["back"]["sets"] == 4
    # biceps: half of 2 pull-up sets.
    assert summary["biceps"]["sets"] == 1
    assert summary["triceps"]["sets"] == 1.5


@pytest.mark.parametrize(
    ("sets", "expected"),
    [
        (0, ("rest", 0.0)),
        (1, ("trained", 0.05)),  # lightest green
        (10, ("trained", 0.5)),
        (12.5, ("trained", 0.625)),  # a weighted total grades like any other
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
    for muscle in ("chest", "back", "shoulders", "quads", "hamstrings", "glutes"):
        assert summary[muscle]["target"] == LARGE_MUSCLE_TARGET
    for muscle in ("abs", "biceps", "triceps", "forearms", "traps", "calves"):
        assert summary[muscle]["target"] == SMALL_MUSCLE_TARGET


def test_group_over_its_target_reports_the_overshoot():
    summary = summarise_entries([entry(SITUP, 14)])
    abs_group = summary["abs"]
    assert abs_group["state"] == "over"
    assert abs_group["over"] == 4
    assert abs_group["intensity"] == 0.8


def test_overshoot_can_be_fractional():
    """21 sets of bench press put triceps on 10.5 — half a set past their target."""
    summary = summarise_entries([entry(BENCH, 21)])
    assert summary["triceps"]["sets"] == 10.5
    assert summary["triceps"]["over"] == 0.5
    assert summary["triceps"]["state"] == "over"


def test_group_under_its_target_is_not_over():
    summary = summarise_entries([entry(SITUP, 9)])
    assert summary["abs"]["state"] == "trained"
    assert summary["abs"]["over"] == 0


def test_weekly_summary_lists_groups_at_and_over_target(app):
    with app.app_context():
        add_entry("2026-07-28", SITUP, 12)  # abs: small target 10 -> over
        add_entry("2026-07-28", BENCH, 20)  # chest: large target 20 -> exactly at it
        summary = weekly_summary(date(2026, 7, 28))

    # Bench press gives triceps and shoulders 10 sets each at half weight:
    # triceps (target 10) land exactly on target, shoulders (target 20) do not.
    assert summary["muscles_over"] == ["abs"]
    assert summary["muscles_at_target"] == ["chest", "abs", "triceps"]
    assert summary["muscles"]["chest"]["state"] == "trained"
    assert summary["muscles"]["chest"]["intensity"] == 1.0
    assert summary["muscles"]["triceps"]["sets"] == 10


def test_exercise_names_are_listed_without_duplicates():
    summary = summarise_entries([entry(BENCH, 3), entry(BENCH, 2)])
    assert summary["chest"]["exercises"] == ["Barbell Bench Press - Medium Grip"]
    assert summary["chest"]["sets"] == 5


def test_weekly_summary_only_includes_the_target_week(app):
    with app.app_context():
        add_entry("2026-07-27", SITUP, 5)  # Monday, in week
        add_entry("2026-08-02", PULLUP, 2)  # Sunday, in week
        add_entry("2026-08-03", BENCH, 3)  # next Monday, out of week

        summary = weekly_summary(date(2026, 7, 28))

    assert summary["week_start"] == "2026-07-27"
    assert summary["week_end"] == "2026-08-02"
    # total_sets counts sets performed, not weighted volume.
    assert summary["total_sets"] == 7
    assert sorted(summary["muscles_worked"]) == ["abs", "back", "biceps"]
    assert summary["sets_per_day"]["2026-07-27"] == 5
    assert summary["sets_per_day"]["2026-07-30"] == 0


# ---- Regions ---------------------------------------------------------------
#
# Six groups subdivide into regions. Regions are a *distribution*, never a grade:
# no target, no state, no intensity. See docs/VOLUME_SCIENCE.md.

INCLINE_DB = "Incline_Dumbbell_Press"
LATERAL_RAISE = "Side_Lateral_Raise"
FACE_PULL = "Face_Pull"
DEADLIFT = "Barbell_Deadlift"
PULLDOWN = "Wide-Grip_Lat_Pulldown"


def test_only_six_groups_carry_regions():
    summary = summarise_entries([])
    subdivided = [m for m in MUSCLE_GROUPS if summary[m]["regions"]]
    assert subdivided == ["chest", "shoulders", "back", "triceps", "hamstrings", "calves"]


def test_regions_never_carry_a_target_or_a_grade():
    """The whole point: there is no evidence to grade a muscle head against."""
    summary = summarise_entries([entry(BENCH, 6)])
    for muscle in MUSCLE_GROUPS:
        for region in summary[muscle]["regions"]:
            assert set(region) == {"region", "label", "sets", "share", "neglected"}


def test_regions_split_a_groups_volume_by_emphasis():
    summary = summarise_entries([entry(BENCH, 4), entry(INCLINE_DB, 2)])
    chest = summary["chest"]
    assert chest["sets"] == 6
    assert chest["region_sets"] == 6
    assert {r["region"]: r["sets"] for r in chest["regions"]} == {
        "chest_upper": 2.0,
        "chest_mid_lower": 4.0,
    }


def test_secondary_weighting_carries_into_regions():
    """Bench press gives shoulders half a set each, all of it front delt."""
    shoulders = summarise_entries([entry(BENCH, 6)])["shoulders"]
    assert shoulders["sets"] == 3.0
    assert {r["region"]: r["sets"] for r in shoulders["regions"]}["delt_front"] == 3.0


def test_pressing_leaves_the_other_delt_heads_flagged():
    summary = summarise_entries([entry(BENCH, 10)])
    by_region = {r["region"]: r for r in summary["shoulders"]["regions"]}
    assert by_region["delt_front"]["share"] == 1.0
    assert by_region["delt_side"]["neglected"] is True
    assert by_region["delt_rear"]["neglected"] is True


def test_a_balanced_shoulder_week_flags_nothing():
    entries = [entry(BENCH, 6), entry(LATERAL_RAISE, 4), entry(FACE_PULL, 4)]
    regions = summarise_entries(entries)["shoulders"]["regions"]
    assert not any(r["neglected"] for r in regions)


def test_unplaceable_volume_is_reported_rather_than_spread():
    """A deadlift trains the back without saying lats or mid back."""
    back = summarise_entries([entry(DEADLIFT, 6), entry(PULLDOWN, 4)])["back"]
    assert back["sets"] == 10.0  # both movements train back primarily
    assert back["region_sets"] == 4.0  # only the pulldown could be placed
    by_region = {r["region"]: r for r in back["regions"]}
    # The pulldown's 4 sets are all the lats', and shares are of what was placed.
    assert by_region["lats"]["sets"] == 4.0
    assert by_region["lats"]["share"] == 1.0
    assert by_region["mid_back"]["sets"] == 0.0


def test_a_barely_trained_group_is_not_reported_as_imbalanced():
    """Under the parent floor, thin regions mean nothing yet."""
    regions = summarise_entries([entry(INCLINE_DB, 3)])["chest"]["regions"]
    assert not any(r["neglected"] for r in regions)


def test_untrained_groups_have_zero_shares_and_no_flags():
    chest = summarise_entries([])["chest"]
    assert chest["region_sets"] == 0.0
    assert all(r["share"] == 0.0 and not r["neglected"] for r in chest["regions"])


def test_weekly_summary_lists_every_neglected_region(app):
    with app.app_context():
        add_entry("2026-07-28", BENCH, 10)
        summary = weekly_summary(date(2026, 7, 28))

    flagged = {(r["muscle"], r["region"]) for r in summary["regions_neglected"]}
    assert ("shoulders", "delt_side") in flagged
    assert ("shoulders", "delt_rear") in flagged
    assert ("chest", "chest_upper") in flagged
    # Every entry names its parent and carries a label for display.
    assert all({"muscle", "region", "label"} == set(r) for r in summary["regions_neglected"])
