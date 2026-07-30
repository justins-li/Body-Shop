"""Tests for the vendored exercise catalog and its invariants.

The catalog is generated data (``tools/build_exercise_catalog.py``), so these
guard the *contract* the rest of the app relies on rather than any individual
row: known muscle slugs, unique ids, two frames each, and the primary/secondary
weighting that the weekly summary reads.
"""

import pytest

from app.exercises import (
    EXERCISE_REGIONS,
    EXERCISES,
    MUSCLE_GROUPS,
    MUSCLE_LABELS,
    MUSCLE_TARGETS,
    PRIMARY_WEIGHT,
    REGION_LABELS,
    REGION_PARENTS,
    RETIRED_EXERCISE_IDS,
    SECONDARY_WEIGHT,
    VOLUME_CATEGORIES,
    STAPLE_EXERCISE_IDS,
    UNRANKED_RANK_BASE,
    all_exercises,
    format_sets,
    get_exercise,
    muscles_for,
    regions_for,
    regions_of,
)


def test_catalog_is_the_full_dataset():
    assert len(EXERCISES) == 873


def test_every_muscle_group_has_a_label_and_a_target():
    assert set(MUSCLE_LABELS) == set(MUSCLE_GROUPS)
    assert set(MUSCLE_TARGETS) == set(MUSCLE_GROUPS)
    assert len(MUSCLE_GROUPS) == 12


def test_every_exercise_names_only_known_muscle_groups():
    for exercise in all_exercises():
        assert set(exercise.muscles) <= set(MUSCLE_GROUPS), exercise.id


def test_every_exercise_has_a_primary_muscle_and_two_frames():
    for exercise in all_exercises():
        assert exercise.primary, exercise.id
        assert len(exercise.images) == 2, exercise.id


def test_no_muscle_is_both_primary_and_secondary():
    """Otherwise the group would be counted at both weights."""
    for exercise in all_exercises():
        assert not set(exercise.primary) & set(exercise.secondary), exercise.id


def test_every_muscle_group_has_at_least_one_exercise():
    covered = muscles_for(EXERCISES)
    assert covered == set(MUSCLE_GROUPS)


def test_ids_are_unique_and_indexed_by_id():
    for exercise_id, exercise in EXERCISES.items():
        assert exercise.id == exercise_id


def test_catalog_is_ordered_by_name():
    names = [e.name.lower() for e in all_exercises()]
    assert names == sorted(names)


def test_weight_for_grades_primary_above_secondary():
    bench = get_exercise("Barbell_Bench_Press_-_Medium_Grip")
    assert bench.weight_for("chest") == PRIMARY_WEIGHT
    assert bench.weight_for("triceps") == SECONDARY_WEIGHT
    assert bench.weight_for("quads") == 0.0


def test_non_strength_movements_carry_no_volume_weight():
    stretch = get_exercise("90_90_Hamstring")
    assert stretch.category not in VOLUME_CATEGORIES
    assert stretch.counts_toward_volume is False
    # It targets hamstrings, but contributes nothing to them.
    assert "hamstrings" in stretch.muscles
    assert stretch.weight_for("hamstrings") == 0.0


def test_muscles_lists_primary_before_secondary():
    pullup = get_exercise("Pullups")
    assert pullup.muscles == ("back", "biceps")


def test_unknown_exercise_is_none():
    assert get_exercise("bench_press") is None  # retired in Phase 2


def test_every_retired_id_maps_to_a_real_exercise():
    for old_id, new_id in RETIRED_EXERCISE_IDS.items():
        assert get_exercise(old_id) is None, old_id
        assert get_exercise(new_id) is not None, new_id


def test_detail_dict_resolves_image_urls_against_the_base():
    detail = get_exercise("Pullups").to_detail_dict("https://cdn.example/exercises")
    assert detail["images"] == [
        "https://cdn.example/exercises/Pullups/0.jpg",
        "https://cdn.example/exercises/Pullups/1.jpg",
    ]


def test_detail_dict_tolerates_a_trailing_slash_on_the_base():
    detail = get_exercise("Pullups").to_detail_dict("https://cdn.example/exercises/")
    assert detail["images"][0] == "https://cdn.example/exercises/Pullups/0.jpg"


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0, "0"), (12, "12"), (12.0, "12"), (12.5, "12.5"), (0.5, "0.5"), (7.25, "7.2")],
)
def test_format_sets_drops_a_trailing_zero(value, expected):
    assert format_sets(value) == expected


# ---- Ranking ---------------------------------------------------------------


def test_every_staple_id_exists():
    """A rename upstream must not silently demote a staple to the bottom."""
    for exercise_id in STAPLE_EXERCISE_IDS:
        assert get_exercise(exercise_id) is not None, exercise_id


def test_staple_ids_are_unique():
    assert len(set(STAPLE_EXERCISE_IDS)) == len(STAPLE_EXERCISE_IDS)


def test_staples_rank_in_the_order_they_are_listed():
    ranks = [get_exercise(i).rank for i in STAPLE_EXERCISE_IDS]
    assert ranks == sorted(ranks)
    assert ranks == list(range(len(STAPLE_EXERCISE_IDS)))


def test_no_facet_combination_lifts_an_unranked_movement_above_a_staple():
    """The two tiers must not interleave, or 'common lifts first' stops holding."""
    worst_staple = max(get_exercise(i).rank for i in STAPLE_EXERCISE_IDS)
    unranked = [e for e in all_exercises() if e.id not in STAPLE_EXERCISE_IDS]
    assert worst_staple < UNRANKED_RANK_BASE <= min(e.rank for e in unranked)


def test_every_muscle_group_has_a_staple_that_trains_it_primarily():
    """Browse opens on a ranked list for all 12 groups, not just the popular ones."""
    covered = {m for i in STAPLE_EXERCISE_IDS for m in get_exercise(i).primary}
    assert covered == set(MUSCLE_GROUPS)


def test_zero_volume_movements_rank_behind_every_strength_movement():
    """A hamstring stretch must not lead a hamstrings browse list."""
    unranked = [e for e in all_exercises() if e.id not in STAPLE_EXERCISE_IDS]
    graded = [e.rank for e in unranked if e.counts_toward_volume]
    ungraded = [e.rank for e in unranked if not e.counts_toward_volume]
    assert max(graded) < min(ungraded)


def test_browse_order_leads_with_the_obvious_lifts():
    """The ordering log.js applies, asserted end to end for chest."""
    chest = [e for e in all_exercises() if "chest" in e.muscles]
    chest.sort(key=lambda e: (0 if "chest" in e.primary else 1, e.rank, e.name))
    assert [e.name for e in chest[:4]] == [
        "Barbell Bench Press - Medium Grip",
        "Barbell Incline Bench Press - Medium Grip",
        "Pushups",
        "Dumbbell Bench Press",
    ]
    # Pushups used to sit 70th of 147 alphabetically, past the picker's row cap.
    assert chest.index(get_exercise("Pushups")) < 40


def test_light_payload_carries_the_rank_the_picker_sorts_by():
    assert get_exercise("Barbell_Squat").to_dict()["rank"] == 1


# ---- Regions ---------------------------------------------------------------


def test_every_region_belongs_to_a_real_muscle_group():
    for region, parent in REGION_PARENTS.items():
        assert parent in MUSCLE_GROUPS, region
        assert region in REGION_LABELS


def test_a_movement_is_only_attributed_to_a_muscle_it_trains():
    """The check that keeps invented numbers off the summary page."""
    for region, exercise_ids in EXERCISE_REGIONS.items():
        parent = REGION_PARENTS[region]
        for exercise_id in exercise_ids:
            exercise = get_exercise(exercise_id)
            assert exercise is not None, exercise_id
            assert parent in exercise.muscles, (exercise_id, region)


def test_regions_for_is_empty_when_emphasis_is_not_defensible():
    # A deadlift trains the back, but says nothing about lats vs mid back.
    assert regions_for("Barbell_Deadlift", "back") == ()
    # Quads are not subdivided at all.
    assert regions_for("Barbell_Squat", "quads") == ()


def test_regions_for_only_returns_regions_of_the_muscle_asked_about():
    bench = "Barbell_Bench_Press_-_Medium_Grip"
    assert regions_for(bench, "chest") == ("chest_mid_lower",)
    assert regions_for(bench, "shoulders") == ("delt_front",)
    # Pressing is deliberately *not* attributed to a triceps region.
    assert regions_for(bench, "triceps") == ()


def test_every_region_has_at_least_one_movement():
    """A region nothing maps to would read as permanently neglected."""
    for region in REGION_PARENTS:
        assert EXERCISE_REGIONS.get(region), region


def test_biceps_and_abs_are_not_subdivided():
    """Their subdivisions are EMG folklore; see docs/VOLUME_SCIENCE.md."""
    assert regions_of("biceps") == ()
    assert regions_of("abs") == ()
