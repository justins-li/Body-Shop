"""The trainer setup: how experience and session time decide weekly targets.

Phase 6. These are pure functions over :mod:`app.training`, so no app or
database is needed — the same shape as ``tests/test_weeks.py``.

The tests worth reading before changing a number are
:func:`test_experience_and_plan_combine_with_min` and
:func:`test_no_target_falls_below_the_evidence_floor`. The first pins the model
itself (``min``, never a product); the second pins the one sourced constant.
"""

from __future__ import annotations

import pytest

from app.exercises import MUSCLE_GROUPS, MUSCLE_TARGETS
from app.training import (
    DEFAULT_EXPERIENCE,
    DEFAULT_PROFILE,
    EXPERIENCE_BY_KEY,
    EXPERIENCE_LEVELS,
    MAX_MINUTES,
    MAX_SESSIONS,
    MIN_GROUP_TARGET,
    MIN_MINUTES,
    MIN_SESSIONS,
    REFERENCE_PLAN,
    SessionPlan,
    TrainerProfile,
    resolve_profile,
)


# ---- The levels themselves -------------------------------------------------


def test_experience_keys_are_unique_and_include_the_default():
    keys = [level.key for level in EXPERIENCE_LEVELS]
    assert len(set(keys)) == len(keys)
    assert DEFAULT_EXPERIENCE in keys


def test_levels_ascend_in_volume():
    """The three setups must stay ordered, or the selector lies about itself."""
    scales = [level.volume_scale for level in EXPERIENCE_LEVELS]
    assert scales == sorted(scales)
    assert scales[0] < scales[-1]


def test_only_the_top_level_unlocks_rpe():
    """RPE is the advanced setup's field — see the roadmap's Phase 6."""
    with_rpe = [level.key for level in EXPERIENCE_LEVELS if level.rpe]
    assert with_rpe == [EXPERIENCE_LEVELS[-1].key]


# ---- The default is the pre-Phase-6 behaviour ------------------------------


def test_default_profile_reproduces_the_baseline_targets():
    """Nothing re-grades itself when Phase 6 lands.

    The default multiplies by exactly 1.0, so a log recorded before the trainer
    setup existed reads the same afterwards. This is the reason the default is
    the *middle* level rather than the first one.
    """
    assert DEFAULT_PROFILE.volume_scale == 1.0
    assert DEFAULT_PROFILE.targets() == dict(MUSCLE_TARGETS)


def test_default_profile_is_the_reference_plan():
    assert DEFAULT_PROFILE.plan == REFERENCE_PLAN
    assert REFERENCE_PLAN.volume_scale == 1.0


def test_targets_cover_every_muscle_group():
    assert set(DEFAULT_PROFILE.targets()) == set(MUSCLE_GROUPS)


# ---- The model -------------------------------------------------------------


def test_experience_and_plan_combine_with_min():
    """**The model, pinned.** The smaller of the two, never their product.

    Multiplying double-counts: training fewer hours *is* how a beginner's lower
    volume shows up, so charging for both drove every group onto the floor. If
    this test starts failing because someone reached for ``*``, read the module
    docstring before changing the assertion.
    """
    beginner = EXPERIENCE_BY_KEY["beginner"]
    short = SessionPlan(sessions_per_week=3, minutes_per_session=45)
    profile = TrainerProfile(experience=beginner, plan=short)

    assert profile.volume_scale == pytest.approx(
        min(beginner.volume_scale, short.volume_scale), abs=1e-3
    )
    # Both factors are below 1, so their product is below either of them — that
    # gap is exactly the double-count `min` avoids.
    assert profile.volume_scale > beginner.volume_scale * short.volume_scale


def test_a_plan_beyond_the_level_stops_raising_targets():
    """The plan is a ceiling, so it stops mattering once it clears the level.

    Two very different weeks, both roomier than the advanced setup asks for,
    produce identical targets: having *more* time than your experience calls for
    is not a reason for the app to ask for more sets.
    """
    advanced = EXPERIENCE_BY_KEY["advanced"]
    roomy = SessionPlan(sessions_per_week=7, minutes_per_session=100)
    roomier = SessionPlan(sessions_per_week=MAX_SESSIONS, minutes_per_session=MAX_MINUTES)

    assert roomy.volume_scale > advanced.volume_scale
    assert TrainerProfile(advanced, roomy).targets() == (
        TrainerProfile(advanced, roomier).targets()
    )


def test_the_baseline_week_cannot_afford_the_advanced_targets():
    """The consequence of the reference plan being the *baseline's* week.

    ``REFERENCE_PLAN`` is defined as the week the 20/10 targets already
    describe, so an advanced lifter asking for 1.3× that has to find 1.3× the
    time. Switching to Advanced without lengthening the week therefore changes
    nothing — which is honest rather than inert, and the summary page says which
    input is holding the numbers down.
    """
    advanced = TrainerProfile(EXPERIENCE_BY_KEY["advanced"], REFERENCE_PLAN)
    assert advanced.volume_scale == 1.0
    assert advanced.limited_by == "plan"
    assert advanced.targets() == DEFAULT_PROFILE.targets()


def test_a_shorter_plan_lowers_targets():
    experienced = EXPERIENCE_BY_KEY["experienced"]
    full = TrainerProfile(experienced, REFERENCE_PLAN)
    cramped = TrainerProfile(
        experienced, SessionPlan(sessions_per_week=2, minutes_per_session=40)
    )
    assert cramped.target_for("chest") < full.target_for("chest")


def test_the_shape_of_the_week_survives_scaling():
    """Large groups keep asking about twice what small ones do, at every level.

    The 2:1 split is the part of ``MUSCLE_TARGETS`` worth preserving; one
    multiplier across all twelve is what preserves it. Checked away from the
    ``MIN_GROUP_TARGET`` floor, which deliberately compresses the ratio.
    """
    for level in EXPERIENCE_LEVELS:
        targets = TrainerProfile(level, REFERENCE_PLAN).targets()
        assert targets["chest"] == pytest.approx(2 * targets["abs"], abs=1)


def test_levels_separate_once_the_week_can_afford_them():
    """Given a week roomy enough not to be the binding constraint, the three
    setups produce three different targets, in order."""
    roomy = SessionPlan(sessions_per_week=6, minutes_per_session=105)
    chest = {
        level.key: TrainerProfile(level, roomy).target_for("chest")
        for level in EXPERIENCE_LEVELS
    }
    assert chest["beginner"] < chest["experienced"] < chest["advanced"]


# ---- The floor -------------------------------------------------------------


def test_no_target_falls_below_the_evidence_floor():
    """Roughly four sets a week is where a muscle responds at all.

    The one sourced number in ``app/training.py`` (Pelland et al. 2025, via
    docs/VOLUME_SCIENCE.md §1). No combination of the shortest week and the
    lowest level may take a group under it — below four the app would be asking
    for less than training.
    """
    tiny = SessionPlan(sessions_per_week=MIN_SESSIONS, minutes_per_session=MIN_MINUTES)
    for level in EXPERIENCE_LEVELS:
        targets = TrainerProfile(level, tiny).targets()
        assert min(targets.values()) == MIN_GROUP_TARGET


def test_targets_are_always_whole_numbers():
    """`12 / 16` on the summary page; a fractional target there is false
    precision about a number that is a convention to begin with."""
    for level in EXPERIENCE_LEVELS:
        for sessions, minutes in ((3, 45), (4, 60), (5, 75), (6, 90)):
            targets = TrainerProfile(level, SessionPlan(sessions, minutes)).targets()
            assert all(isinstance(value, int) for value in targets.values())


def test_session_overhead_makes_two_short_sessions_worth_less_than_one_long():
    """Warm-up and setup are per session, not per minute — so the model has to
    say that 2 × 30 holds fewer working sets than 1 × 60."""
    split = SessionPlan(sessions_per_week=2, minutes_per_session=30)
    single = SessionPlan(sessions_per_week=1, minutes_per_session=60)
    assert split.working_minutes < single.working_minutes


# ---- resolve_profile: everything here is untrusted --------------------------


@pytest.mark.parametrize(
    "experience", [None, "", "nonsense", "BEGINNER", 7, {"key": "advanced"}]
)
def test_unknown_experience_falls_back_to_the_default(experience):
    """A stale localStorage key must show the usual targets, not a 400.

    Same discipline as ``window`` on the graph endpoint: this arrives from a
    view control, and the honest answer to a bad preference is the default one.
    """
    assert resolve_profile(experience).experience.key == DEFAULT_EXPERIENCE


@pytest.mark.parametrize(
    ("sessions", "minutes", "expected_sessions", "expected_minutes"),
    [
        (0, 0, MIN_SESSIONS, MIN_MINUTES),
        (999, 999, MAX_SESSIONS, MAX_MINUTES),
        (-4, -30, MIN_SESSIONS, MIN_MINUTES),
        ("3", "45", 3, 45),
        ("3.7", "45.2", 3, 45),
        (None, None, REFERENCE_PLAN.sessions_per_week, REFERENCE_PLAN.minutes_per_session),
        ("abc", "", REFERENCE_PLAN.sessions_per_week, REFERENCE_PLAN.minutes_per_session),
    ],
)
def test_plan_values_are_clamped_not_rejected(
    sessions, minutes, expected_sessions, expected_minutes
):
    plan = resolve_profile("experienced", sessions, minutes).plan
    assert plan.sessions_per_week == expected_sessions
    assert plan.minutes_per_session == expected_minutes


def test_resolve_profile_with_nothing_is_the_default_profile():
    assert resolve_profile().to_dict() == DEFAULT_PROFILE.to_dict()


# ---- The payload -----------------------------------------------------------


def test_to_dict_carries_the_inputs_and_the_resolved_targets():
    """Clients render the targets they were graded against rather than
    re-deriving them, so both have to be in one payload."""
    payload = resolve_profile("advanced", 6, 90).to_dict()
    assert payload["experience"] == "advanced"
    assert payload["shows_rpe"] is True
    assert payload["sessions_per_week"] == 6
    assert payload["minutes_per_session"] == 90
    assert payload["targets"] == resolve_profile("advanced", 6, 90).targets()


@pytest.mark.parametrize(
    ("experience", "sessions", "minutes", "expected"),
    [
        # A week roomier than the level asks for: the level is the constraint.
        ("beginner", 6, 90, "experience"),
        ("experienced", 6, 90, "experience"),
        # The baseline week cannot afford advanced volume, so the plan binds.
        ("advanced", 5, 75, "plan"),
        ("experienced", 2, 30, "plan"),
    ],
)
def test_limited_by_names_the_binding_input(experience, sessions, minutes, expected):
    """Someone whose targets fell because their week is short should be able to
    read that — it is the input they can change."""
    profile = resolve_profile(experience, sessions, minutes)
    assert profile.limited_by == expected
