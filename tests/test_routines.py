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
    ATHLETE_ROUTINES,
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
    for routine in all_routines():
        for item in routine.exercises:
            assert item.exercise_id in EXERCISES, (routine.key, item.exercise_id)


def test_routine_keys_are_unique():
    keys = [routine.key for routine in all_routines()]
    assert len(set(keys)) == len(keys)


def test_no_routine_lists_a_movement_twice():
    """The set count and the time estimate would both double-count it."""
    for routine in all_routines():
        ids = [item.exercise_id for item in routine.exercises]
        assert len(set(ids)) == len(ids), routine.key


def test_every_routine_says_what_it_is_for():
    """Each one focuses on something. A routine that trains everything a bit is
    the thing the body map already tells you not to do."""
    for routine in all_routines():
        assert routine.name and routine.focus and routine.blurb
        assert routine.exercises


def test_our_routines_are_built_from_movements_the_picker_already_offers():
    """Every movement in a routine we wrote should be findable on /log without a
    search, or following one leaves you unable to log it by hand next time.

    **Scoped to ours on purpose.** A reconstruction follows what an athlete was
    reported to do, and band work, box jumps and medicine-ball slams are not on
    the staple list — bending the routine to fit the list would be inventing a
    session and attributing it to a real person.
    """
    from app.exercises import STAPLE_EXERCISE_IDS

    staples = set(STAPLE_EXERCISE_IDS)
    for routine in ROUTINES:
        for item in routine.exercises:
            assert item.exercise_id in staples, (routine.key, item.exercise_id)


# ---- Validation actually fires ---------------------------------------------


def test_an_unknown_movement_is_an_import_time_error():
    broken = Routine(
        key="broken", name="Broken", focus="-", blurb="-", level="beginner",
        exercises=(RoutineExercise("No_Such_Movement", 3, "5", "-"),),
    )
    with pytest.raises(RoutineError, match="not in the catalog"):
        _check_routines((broken,))


def test_a_repeated_movement_is_an_import_time_error():
    broken = Routine(
        key="broken", name="Broken", focus="-", blurb="-", level="beginner",
        exercises=(
            RoutineExercise("Barbell_Squat", 3, "5", "-"),
            RoutineExercise("Barbell_Squat", 3, "5", "-"),
        ),
    )
    with pytest.raises(RoutineError, match="twice"):
        _check_routines((broken,))


# ---- The time estimate is derived ------------------------------------------


def test_the_estimate_is_built_from_the_sets_listed():
    """Never typed beside them. A hand-written "45 min" drifts the first time
    anybody edits the exercise list."""
    for routine in all_routines():
        assert routine.minutes == estimate_minutes(
            routine.total_sets, routine.minutes_per_set
        )


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
    for routine in all_routines():
        assert routine.total_sets == sum(i.sets for i in routine.exercises)


def test_every_routine_is_a_plausible_session_length():
    """A routine nobody has time for is not a suggestion. These are all one
    session of Phase 6's reference week, which is where the arithmetic comes
    from — see REFERENCE_PLAN."""
    for routine in all_routines():
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


def test_all_routines_is_ours_first_then_the_reconstructions():
    """Sessions we stand behind lead; the tagged approximations follow."""
    keys = [r.key for r in all_routines()]
    assert keys == [r.key for r in ROUTINES] + [r.key for r in ATHLETE_ROUTINES]
    assert not any(r.experimental for r in ROUTINES)
    assert all(r.experimental for r in ATHLETE_ROUTINES)


# ---- Attribution: the [experimental] tag has to mean something --------------


def test_every_athlete_routine_names_who_and_where_from():
    """The tag puts a real person's name on a session they did not write, so it
    may not ship without saying whose training it approximates and where the
    reporting came from. A tag with nothing behind it is worse than no tag."""
    for routine in ATHLETE_ROUTINES:
        assert routine.experimental is True, routine.key
        assert routine.inspired_by, routine.key
        assert routine.source, routine.key


def test_an_experimental_routine_without_attribution_is_refused():
    broken = Routine(
        key="broken", name="Broken", focus="-", blurb="-", level="beginner",
        exercises=(RoutineExercise("Barbell_Squat", 3, "5", "-"),),
        experimental=True,
    )
    with pytest.raises(RoutineError, match="no athlete or no source"):
        _check_routines((broken,))


def test_attributing_a_routine_without_the_tag_is_refused():
    """The other direction, and the one that would actually slip through: a
    session named after someone but presented as though we wrote it."""
    broken = Routine(
        key="broken", name="Broken", focus="-", blurb="-", level="beginner",
        exercises=(RoutineExercise("Barbell_Squat", 3, "5", "-"),),
        inspired_by="Someone Real", source="A magazine",
    )
    with pytest.raises(RoutineError, match="not tagged experimental"):
        _check_routines((broken,))


def test_the_five_athletes_are_all_there():
    named = {r.inspired_by for r in ATHLETE_ROUTINES}
    assert len(named) == len(ATHLETE_ROUTINES), "two routines share an athlete"
    assert len(ATHLETE_ROUTINES) == 5


def test_the_tag_reaches_the_payload():
    """The page renders it from here, on the card *and* on the opened routine."""
    payload = get_routine("bolt_power").to_dict()
    assert payload["experimental"] is True
    assert payload["inspired_by"] == "Usain Bolt"
    assert payload["source"]

    ours = get_routine("push").to_dict()
    assert ours["experimental"] is False
    assert ours["inspired_by"] is None


def test_a_circuit_is_not_priced_like_a_heavy_session():
    """A band circuit at twenty-plus reps does not cost what a heavy triple with
    three minutes' rest costs. The pace is typed; the duration is still derived
    from the sets, which is the property worth protecting."""
    brady = get_routine("brady_bands")
    assert brady.minutes_per_set is not None
    assert brady.minutes < estimate_minutes(brady.total_sets)
