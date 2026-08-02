"""The trainer setup: who is training, how long for, and what that does to targets.

Phase 6. Until now every user was graded against one weekly set target per muscle
group — :data:`app.exercises.MUSCLE_TARGETS`, 20 for a large group and 10 for a
small one. That is a defensible convention (docs/VOLUME_SCIENCE.md §1) rather
than a finding, and it silently assumed one kind of lifter with one amount of
time. This module keeps the convention as the *baseline* and scales it by two
things the user actually knows about themselves:

* **How long they have been training** (:data:`EXPERIENCE_LEVELS`) — a beginner's
  week is smaller than an advanced lifter's, and only the advanced setup asks for
  RPE, which is a reading you have to have trained a while to give honestly.
* **How much time they intend to spend** (:class:`SessionPlan`) — a target that
  cannot fit in the week the user actually has is not a target, it is a
  standing failure notice.

The two combine with :func:`min`, **not** by multiplying, and that is the whole
model in one line:

    your target is the smaller of what your experience asks for and what your
    week can hold.

Multiplying them was the first attempt and it double-counts. A beginner training
three short sessions is not asking for 60% of a small week — training less time
*is* how their lower volume shows up, so applying both factors charged them
twice for the same fact and drove every group onto the floor. Under ``min`` the
session plan can only ever *reduce* a target, which is the honest direction: more
hours in the gym is not a reason the app should ask for more sets, but fewer
hours is a reason it cannot ask for as many.

Two further rules, both from docs/VOLUME_SCIENCE.md:

* **The targets scale together, never independently.** One multiplier applies to
  every group, so the *shape* of the week — large groups asking twice what small
  ones do — is the part the evidence supports and is preserved exactly.
* **Nothing drops below :data:`MIN_GROUP_TARGET`.** Four sets a week is the
  literature's approximate floor for a muscle responding at all (Pelland et al.
  2025), so it is the one number here that is sourced rather than chosen.
* **No range is ever printed as advice.** The profile resolves to *one* integer
  per group, exactly as before. The scaling changes the number, not the grammar
  of the claim.

Everything else in this module is convention, and is named and documented as
such. There is no evidence that a beginner needs 60% of an intermediate's
volume; there is evidence that beginners grow on less, and 0.6 is a calibration
you may tune (see :data:`ExperienceLevel.volume_scale`).

**Where the setup lives.** On the user row, as of the Phase 5 carryover — three
nullable columns, all NULL meaning the account has never chosen. It reaches this
module through ``api._user_profile``, and :func:`resolve_profile` still treats
every input as untrusted: a stored value predates any tuning of the bounds above,
and a settings control can send anything. It falls back rather than raising, the
same discipline ``window`` follows in :mod:`app.services.graph`.
"""

from __future__ import annotations

from dataclasses import dataclass

from .exercises import MUSCLE_GROUPS, target_for


@dataclass(frozen=True)
class ExperienceLevel:
    """One trainer setup: how much volume it asks for, and what it unlocks."""

    key: str
    label: str
    #: One line under the selector saying who this is.
    blurb: str
    #: Multiplier on every group's baseline weekly target.
    #:
    #: **Convention, not a finding.** The dose-response curve rises for everyone
    #: (docs/VOLUME_SCIENCE.md §1); what differs is how much a lifter can recover
    #: from and hold to. These are calibration numbers — tune them, but do not
    #: defend them as results, and keep them applying to every group at once.
    volume_scale: float
    #: Whether ``/log`` offers an RPE field on every set.
    #:
    #: RPE is a self-report that only means anything once you know what a real
    #: 8 feels like, so it is the advanced setup's field. Existing RPE values
    #: are always shown and are never dropped — see ``log.js``.
    rpe: bool


#: The three setups, in the order the selector offers them.
#:
#: ``experienced`` is deliberately 1.0: it is the calibration the app shipped
#: with, so it is also the default (see :data:`DEFAULT_EXPERIENCE`) and a log
#: recorded before Phase 6 does not re-grade itself the moment this lands.
EXPERIENCE_LEVELS: tuple[ExperienceLevel, ...] = (
    ExperienceLevel(
        key="beginner",
        label="Beginner",
        blurb="New to lifting, or coming back after time off. Lower weekly targets.",
        volume_scale=0.6,
        rpe=False,
    ),
    ExperienceLevel(
        key="experienced",
        label="Experienced",
        blurb="Training consistently for a while. The app's baseline targets.",
        volume_scale=1.0,
        rpe=False,
    ),
    ExperienceLevel(
        key="advanced",
        label="Advanced",
        blurb="Years of steady training. Higher targets, and RPE on every set.",
        volume_scale=1.3,
        rpe=True,
    ),
)

#: Keyed for lookup; the tuple above stays the display order.
EXPERIENCE_BY_KEY: dict[str, ExperienceLevel] = {
    level.key: level for level in EXPERIENCE_LEVELS
}

#: The setup used when nothing has been chosen.
#:
#: The middle one, and not by symmetry: it multiplies by 1.0, so an app that has
#: never been told anything grades exactly as it did before Phase 6.
DEFAULT_EXPERIENCE = "experienced"


#: Sets a week below which a muscle group has nothing to aim at.
#:
#: **The one sourced number in this module.** Pelland et al. (2025) put roughly
#: four sets a week as the floor at which a muscle reliably responds at all, so
#: no combination of a short week and a beginner's multiplier may take a target
#: under it — below four the app would be asking for less than training.
MIN_GROUP_TARGET = 4

#: Minutes of a session that never become working sets.
#:
#: **Judgement, not a finding**, and the only invented number in the session
#: maths. Warm-ups, changing, walking to the rack and waiting for it are roughly
#: fixed per session rather than proportional to it, which is why two 30-minute
#: sessions hold fewer working sets than one 60-minute session. Subtracting it is
#: what makes the model say so.
SESSION_OVERHEAD_MINUTES = 10

#: The week the baseline targets already describe: five sessions of 75 minutes.
#:
#: **Derived, not picked.** The twelve baseline targets sum to 180 weighted set
#: units. A set of a typical logged movement is worth about 2.0 of those — one
#: primary group at full weight plus two secondaries at half (measured over
#: ``STAPLE_EXERCISE_IDS``: mean 1.8, and higher across the strength catalog) —
#: so the baseline asks for roughly 90 working sets a week. At about three and a
#: half minutes for a set and the rest after it, that is ~315 working minutes:
#: five sessions of 75, or four of 79.
#:
#: The arithmetic lives in this comment rather than in code on purpose. Deriving
#: it at import would make every user's targets move when the catalog's
#: composition changed, which is not a fact about the user. Scaling is a *ratio*
#: against this plan, so the minutes a set costs cancels and never has to be a
#: constant of its own.
REFERENCE_SESSIONS = 5
REFERENCE_MINUTES = 75

#: Bounds on the session plan, so a typo cannot produce a nonsense week.
MIN_SESSIONS, MAX_SESSIONS = 1, 14
MIN_MINUTES, MAX_MINUTES = 15, 240

#: How long one working set takes, including the rest after it.
#:
#: **Judgement.** Phase 6 deliberately needed no such constant: scaling targets is
#: a *ratio* against :data:`REFERENCE_PLAN`, and a per-set cost appears in both
#: halves and cancels. Phase 8's routines need an absolute answer — "about 50
#: minutes" — where nothing cancels, so the number has to be stated rather than
#: implied.
#:
#: It is the same figure the reference plan's arithmetic assumes, and it is the
#: one place it is written down. Compound work with three minutes' rest runs
#: longer and isolation work shorter; three and a half is the middle, and the
#: estimate is rounded to five minutes downstream precisely because it is not
#: known better than that.
MINUTES_PER_WORKING_SET = 3.5


def minutes_for_sets(sets: int) -> float:
    """Minutes of working time ``sets`` sets take, excluding session overhead."""
    return max(0, sets) * MINUTES_PER_WORKING_SET


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class SessionPlan:
    """How much training time the user intends to spend in a week."""

    sessions_per_week: int
    minutes_per_session: int

    @property
    def working_minutes(self) -> float:
        """Weekly minutes left once each session's fixed overhead is removed.

        Never negative: :data:`MIN_MINUTES` is above
        :data:`SESSION_OVERHEAD_MINUTES`, and :func:`resolve_profile` clamps to
        it, but the ``max`` keeps a directly-constructed plan honest too.
        """
        per_session = max(0, self.minutes_per_session - SESSION_OVERHEAD_MINUTES)
        return self.sessions_per_week * per_session

    @property
    def volume_scale(self) -> float:
        """This plan's working time as a fraction of :data:`REFERENCE_PLAN`'s.

        A pure ratio, so the minutes a single set costs never has to be guessed
        — it appears in both halves and cancels. Above 1.0 for a plan roomier
        than the reference, which :attr:`TrainerProfile.volume_scale` then
        discards: this number is a ceiling on the targets, not a licence.
        """
        reference = SessionPlan(REFERENCE_SESSIONS, REFERENCE_MINUTES).working_minutes
        if not reference:  # pragma: no cover - the constants above rule this out
            return 1.0
        return self.working_minutes / reference

    def to_dict(self) -> dict:
        return {
            "sessions_per_week": self.sessions_per_week,
            "minutes_per_session": self.minutes_per_session,
        }


#: The plan the baseline targets assume, as an object.
REFERENCE_PLAN = SessionPlan(REFERENCE_SESSIONS, REFERENCE_MINUTES)


@dataclass(frozen=True)
class TrainerProfile:
    """An experience level and a session plan, and the targets they produce."""

    experience: ExperienceLevel
    plan: SessionPlan

    @property
    def volume_scale(self) -> float:
        """The single multiplier applied to every group's baseline target.

        The smaller of the two inputs, never their product — see the module
        docstring. The consequence worth knowing: a plan roomier than
        :data:`REFERENCE_PLAN` changes nothing, because having the time to train
        more is not a reason for the app to ask for more.
        """
        return round(min(self.experience.volume_scale, self.plan.volume_scale), 3)

    @property
    def shows_rpe(self) -> bool:
        """Whether ``/log`` offers an RPE field."""
        return self.experience.rpe

    def target_for(self, muscle: str) -> int:
        """This profile's weekly set target for ``muscle``.

        An integer, like the baseline it scales: the summary page prints
        ``12 / 16``, and a fractional target there would read as false precision
        about a number that is a convention to begin with.
        """
        scaled = target_for(muscle) * self.volume_scale
        return max(MIN_GROUP_TARGET, round(scaled))

    def targets(self) -> dict[str, int]:
        """Every group's target under this profile, in body-map order."""
        return {muscle: self.target_for(muscle) for muscle in MUSCLE_GROUPS}

    @property
    def limited_by(self) -> str:
        """Which input is holding the targets down: ``experience`` or ``plan``.

        Said plainly rather than left for the page to infer from two numbers.
        Someone whose targets fell because their week is short should be able to
        read that, since it is the input they can change.
        """
        return (
            "plan"
            if self.plan.volume_scale < self.experience.volume_scale
            else "experience"
        )

    def to_dict(self) -> dict:
        """The shape the API returns and the front end stores.

        Carries the resolved ``targets`` as well as the inputs, so a client
        never re-derives a target and cannot disagree with the grading it was
        sent alongside.
        """
        return {
            "experience": self.experience.key,
            "label": self.experience.label,
            "shows_rpe": self.shows_rpe,
            "volume_scale": self.volume_scale,
            "limited_by": self.limited_by,
            **self.plan.to_dict(),
            "targets": self.targets(),
        }


def _int_or_none(raw) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None


def resolve_profile(
    experience=None, sessions=None, minutes=None
) -> TrainerProfile:
    """Build a profile from untrusted input, falling back rather than raising.

    These arrive as query-string values chosen in a settings control, and the
    honest response to a bad preference is the default one — a 400 would blank
    the summary page over a stale ``localStorage`` key. Out-of-range numbers are
    clamped into the bounds above rather than rejected, for the same reason.
    """
    level = EXPERIENCE_BY_KEY.get(str(experience or ""), None)
    if level is None:
        level = EXPERIENCE_BY_KEY[DEFAULT_EXPERIENCE]

    raw_sessions = _int_or_none(sessions)
    raw_minutes = _int_or_none(minutes)
    plan = SessionPlan(
        sessions_per_week=int(
            _clamp(
                REFERENCE_SESSIONS if raw_sessions is None else raw_sessions,
                MIN_SESSIONS,
                MAX_SESSIONS,
            )
        ),
        minutes_per_session=int(
            _clamp(
                REFERENCE_MINUTES if raw_minutes is None else raw_minutes,
                MIN_MINUTES,
                MAX_MINUTES,
            )
        ),
    )
    return TrainerProfile(experience=level, plan=plan)


#: The profile used by any caller that does not supply one.
#:
#: Equal to the pre-Phase-6 behaviour in every respect: baseline targets, no RPE.
DEFAULT_PROFILE = TrainerProfile(
    experience=EXPERIENCE_BY_KEY[DEFAULT_EXPERIENCE], plan=REFERENCE_PLAN
)


def level_options() -> list[dict]:
    """The experience levels as plain data, for the settings control's template."""
    return [
        {
            "key": level.key,
            "label": level.label,
            "blurb": level.blurb,
            "rpe": level.rpe,
        }
        for level in EXPERIENCE_LEVELS
    ]
