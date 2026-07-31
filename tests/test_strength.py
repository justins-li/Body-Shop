"""Personal bests estimated from the user's own sets.

Phase 6.7. Pure functions, so no app or database is needed.

The tests that matter most are the ones asserting an estimate is **refused**.
An unmeasurable movement drawing as a small node instead of a hollow ring is the
failure mode this whole module is arranged to prevent — a small circle claims a
light lift, which is a different and false statement from "not measured".
"""

from __future__ import annotations

from datetime import date

import pytest

from app.services.strength import (
    EPLEY_DIVISOR,
    MAX_ESTIMATE_REPS,
    best_from_sets,
    estimate_one_rep_max,
)


# ---- When there is no estimate to give -------------------------------------


@pytest.mark.parametrize(
    ("weight", "reps"),
    [
        (None, 5),        # bodyweight work, or a set logged as a bare count
        (100.0, None),    # weight without reps says nothing about a single
        (None, None),     # pre-Phase-4 history
    ],
)
def test_a_set_missing_either_number_has_no_estimate(weight, reps):
    """`None`, never `0`. Callers draw a hollow ring off this."""
    assert estimate_one_rep_max(weight, reps) is None


def test_a_long_set_is_not_extrapolated():
    """Every rep-max formula drifts badly past ten or so reps.

    Epley on a 20-rep set reports a single 67% above the bar. Skipping the set
    is honest; converting it is a large number nobody lifted.
    """
    assert estimate_one_rep_max(60.0, MAX_ESTIMATE_REPS) is not None
    assert estimate_one_rep_max(60.0, MAX_ESTIMATE_REPS + 1) is None
    assert estimate_one_rep_max(60.0, 20) is None


def test_nonsense_rep_counts_are_refused():
    assert estimate_one_rep_max(60.0, 0) is None
    assert estimate_one_rep_max(60.0, -3) is None


# ---- When there is ---------------------------------------------------------


def test_a_single_is_the_lift_not_an_estimate():
    """A logged single passes through untouched — there is nothing to estimate."""
    assert estimate_one_rep_max(140.0, 1) == 140.0


def test_epley_is_applied_above_one_rep():
    assert estimate_one_rep_max(100.0, 5) == pytest.approx(
        100.0 * (1 + 5 / EPLEY_DIVISOR), abs=0.05
    )
    # The familiar reading: 100 × 5 is about a 117 kg single.
    assert estimate_one_rep_max(100.0, 5) == 116.7


def test_a_zero_weight_is_a_real_reading_and_survives():
    """`0` and "not recorded" are different facts everywhere else in the app,
    and they are here too — bodyweight at 0 kg added is a legitimate entry."""
    assert estimate_one_rep_max(0.0, 5) == 0.0


def test_more_reps_at_the_same_weight_estimates_higher():
    assert estimate_one_rep_max(100.0, 8) > estimate_one_rep_max(100.0, 3)


# ---- Reducing a window's sets to one best each -----------------------------


def rows(*sets):
    """`(exercise_id, weight, reps, date)` tuples, as `loaded_sets` returns."""
    return [(e, w, r, date(2026, 7, d)) for e, w, r, d in sets]


def test_the_heaviest_estimate_wins_not_the_heaviest_weight():
    """The point of estimating at all.

    A 110 kg single is 110; 100 × 5 is ~117. The heavier *bar* is the lesser
    lift, and a graph sized on the raw weight column would say the opposite.
    """
    best = best_from_sets(rows(
        ("Barbell_Squat", 110.0, 1, 10),
        ("Barbell_Squat", 100.0, 5, 12),
    ))
    assert best["Barbell_Squat"].weight == 100.0
    assert best["Barbell_Squat"].reps == 5
    assert best["Barbell_Squat"].one_rep_max == 116.7


def test_each_movement_gets_its_own_best():
    best = best_from_sets(rows(
        ("Barbell_Squat", 100.0, 5, 10),
        ("Barbell_Bench_Press_-_Medium_Grip", 80.0, 3, 10),
    ))
    assert set(best) == {"Barbell_Squat", "Barbell_Bench_Press_-_Medium_Grip"}


def test_ties_go_to_the_earlier_date():
    """A best is when you first reached it. Re-hitting it is not a new one."""
    best = best_from_sets(rows(
        ("Barbell_Squat", 100.0, 5, 20),
        ("Barbell_Squat", 100.0, 5, 8),
    ))
    assert best["Barbell_Squat"].achieved_on == date(2026, 7, 8)


def test_sets_that_support_no_estimate_are_skipped_not_zeroed():
    """A movement whose every set is unmeasurable is **absent** from the result,
    which is what makes it draw as a ring rather than as a tiny node."""
    best = best_from_sets(rows(
        ("Pullups", None, 8, 10),
        ("Barbell_Squat", 100.0, 5, 10),
    ))
    assert "Pullups" not in best
    assert "Barbell_Squat" in best


def test_a_long_set_does_not_become_a_best():
    best = best_from_sets(rows(
        ("Barbell_Squat", 60.0, 30, 10),
        ("Barbell_Squat", 100.0, 5, 11),
    ))
    assert best["Barbell_Squat"].reps == 5


def test_no_rows_is_no_bests():
    assert best_from_sets([]) == {}


def test_to_dict_shows_its_working():
    """The estimate never travels alone. Printed on its own it is
    indistinguishable from a measurement, and it is neither measured nor a
    benchmark — naming the set it came from is what keeps it checkable."""
    best = best_from_sets(rows(("Barbell_Squat", 100.0, 5, 10)))["Barbell_Squat"]
    payload = best.to_dict()
    assert set(payload) == {"one_rep_max", "weight", "reps", "achieved_on"}
    assert payload["weight"] == 100.0
    assert payload["reps"] == 5
    assert payload["achieved_on"] == "2026-07-10"
