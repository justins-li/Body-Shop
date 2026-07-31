"""Suggested routines and their contract with the catalog.

Phase 8.1. Routines are editorial content in code — the same status as
``STAPLE_EXERCISE_IDS`` — so these guard the contract rather than the taste:
that every movement resolves, that the time estimate is derived from the sets
rather than typed beside them, and that a routine cannot double-count itself.
"""

from __future__ import annotations

import pytest

from app.exercises import EXERCISES
from app.routines import (
    ROUTINES,
    Routine,
    RoutineExercise,
    RoutineError,
    _check_routines,
    all_routines,
    estimate_minutes,
    get_routine,
)
from app.training import MINUTES_PER_WORKING_SET, SESSION_OVERHEAD_MINUTES


# ---- The contract with the catalog -----------------------------------------


def test_every_routine_names_movements_that_exist():
    """An id that stopped resolving would render a card with a blank name and a
    dead log button — the failure `STAPLE_EXERCISE_IDS` is checked against."""
    for routine in ROUTINES:
        for item in routine.exercises:
            assert item.exercise_id in EXERCISES, (routine.key, item.exercise_id)


def test_routine_keys_are_unique():
    keys = [routine.key for routine in ROUTINES]
    assert len(set(keys)) == len(keys)


def test_no_routine_lists_a_movement_twice():
    """The set count and the time estimate would both double-count it."""
    for routine in ROUTINES:
        ids = [item.exercise_id for item in routine.exercises]
        assert len(set(ids)) == len(ids), routine.key


def test_every_routine_says_what_it_is_for():
    """Each one focuses on something. A routine that trains everything a bit is
    the thing the body map already tells you not to do."""
    for routine in ROUTINES:
        assert routine.name and routine.focus and routine.blurb
        assert routine.exercises


def test_routines_are_built_from_movements_the_picker_already_offers():
    """Every movement in a routine should be findable on /log without a search,
    or following one leaves you unable to log the next session by hand."""
    from app.exercises import STAPLE_EXERCISE_IDS

    staples = set(STAPLE_EXERCISE_IDS)
    for routine in ROUTINES:
        for item in routine.exercises:
            assert item.exercise_id in staples, (routine.key, item.exercise_id)


# ---- Validation actually fires ---------------------------------------------


def test_an_unknown_movement_is_an_import_time_error(monkeypatch):
    broken = Routine(
        key="broken", name="Broken", focus="-", blurb="-", level="beginner",
        exercises=(RoutineExercise("No_Such_Movement", 3, "5", "-"),),
    )
    monkeypatch.setattr("app.routines.ROUTINES", (broken,))
    with pytest.raises(RoutineError, match="not"):
        _check_routines()


def test_a_repeated_movement_is_an_import_time_error(monkeypatch):
    broken = Routine(
        key="broken", name="Broken", focus="-", blurb="-", level="beginner",
        exercises=(
            RoutineExercise("Barbell_Squat", 3, "5", "-"),
            RoutineExercise("Barbell_Squat", 3, "5", "-"),
        ),
    )
    monkeypatch.setattr("app.routines.ROUTINES", (broken,))
    with pytest.raises(RoutineError, match="twice"):
        _check_routines()


# ---- The time estimate is derived ------------------------------------------


def test_the_estimate_is_built_from_the_sets_listed():
    """Never typed beside them. A hand-written "45 min" drifts the first time
    anybody edits the exercise list."""
    for routine in ROUTINES:
        assert routine.minutes == estimate_minutes(routine.total_sets)


def test_more_sets_is_never_less_time():
    assert estimate_minutes(10) < estimate_minutes(30)


def test_the_estimate_rounds_to_five_minutes():
    """A minute of precision would be a lie about how well this is known."""
    for total in range(1, 40):
        assert estimate_minutes(total) % 5 == 0


def test_the_estimate_includes_the_per_session_overhead():
    """Changing, walking to the rack, waiting for it — fixed per session, and
    already named in app/training.py rather than invented again here."""
    raw = 12 * MINUTES_PER_WORKING_SET + SESSION_OVERHEAD_MINUTES
    assert abs(estimate_minutes(12) - raw) <= 2.5


def test_total_sets_is_the_sum_of_the_exercises():
    for routine in ROUTINES:
        assert routine.total_sets == sum(i.sets for i in routine.exercises)


def test_every_routine_is_a_plausible_session_length():
    """A routine nobody has time for is not a suggestion. These are all one
    session of Phase 6's reference week, which is where the arithmetic comes
    from — see REFERENCE_PLAN."""
    for routine in ROUTINES:
        assert 30 <= routine.minutes <= 100, (routine.key, routine.minutes)


# ---- The payload -----------------------------------------------------------


def test_to_dict_joins_the_catalog_onto_each_movement():
    """The page needs the name, the muscles and the weight mode to render a card
    and open a quick log; none of that is worth restating in the routine."""
    payload = get_routine("push").to_dict()
    first = payload["exercises"][0]
    assert first["name"] == "Barbell Bench Press - Medium Grip"
    assert first["weight_mode"] == "barbell"
    assert first["primary"] == ["Chest"]
    assert first["counts_toward_volume"] is True


def test_get_routine_is_none_for_an_unknown_key():
    assert get_routine("nope") is None


def test_all_routines_is_display_order():
    assert [r.key for r in all_routines()] == [r.key for r in ROUTINES]
