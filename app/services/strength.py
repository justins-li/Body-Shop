"""Personal bests: how heavy a movement has gone, estimated from your own sets.

Phase 6.7. Until now nothing in the app was strength-relative — deliberately, and
the reasoning is worth restating because this module is the exception rather than
a reversal of it.

**What was ruled out, and still is: a strength *standard*.** Colouring a lift
against what a 80 kg intermediate lifter "should" press requires a bodyweight the
app does not store and a population the app has no business comparing anyone to.
That remains out.

**What this does instead: your own best, from your own log.** A one-rep max
estimated off a set you actually performed is arithmetic on data the user
entered, not a benchmark imported from elsewhere. It is the difference between
"you have pressed the equivalent of 98 kg" and "you are intermediate".

Even so it is an *estimate*, and the honesty rules from
:mod:`app.services.graph` carry over intact:

* **A movement with no recorded load has no estimate**, and must render as a
  hollow ring rather than a guess. That covers bodyweight work, every row logged
  before Phase 4 added the weight column, and anything logged as a bare count.
* **Reps beyond :data:`MAX_ESTIMATE_REPS` are not extrapolated.** Every rep-max
  formula degrades as the set gets longer; a 20-rep set says a great deal about
  endurance and very little about a single. Those sets are ignored for the
  estimate rather than converted into a large number nobody lifted.
* **One rep is not an estimate at all.** A logged single *is* the best single,
  and passes through untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

#: Longest set an estimate is drawn from.
#:
#: **Judgement, and the usual one.** Rep-max formulae are fitted in the 1–10
#: range and every one of them drifts badly past it — Epley on a 20-rep set
#: reports a single 67% above the weight on the bar. Twelve is the common
#: practical ceiling, so longer sets are skipped rather than converted.
MAX_ESTIMATE_REPS = 12

#: Epley's coefficient: ``1RM = weight x (1 + reps / 30)``.
#:
#: Chosen over Brzycki because it does not divide by a term that collapses near
#: 37 reps, so a bad row cannot produce an infinity. The two agree closely under
#: ten reps, which is where nearly every working set lives, and the difference
#: between them is far smaller than the difference between a good day and a bad
#: one — which is the honest bound on what any of this means.
EPLEY_DIVISOR = 30.0


def estimate_one_rep_max(weight: float | None, reps: int | None) -> float | None:
    """Estimate a one-rep max from a single set, or ``None`` if it cannot.

    ``None`` — not zero, and not the raw weight — whenever the set does not
    support an estimate: no load recorded, no reps recorded, or a set long
    enough that the formula stops meaning anything. Callers must treat that as
    *unknown* and draw nothing, which is what keeps an unloaded movement a
    hollow ring instead of a small one.

    A zero weight is a real bodyweight reading and is preserved as ``0.0``
    rather than discarded — ``is None`` is the test everywhere, never falsiness.
    """
    if weight is None or reps is None:
        return None
    if reps < 1 or reps > MAX_ESTIMATE_REPS:
        return None
    if reps == 1:
        # Not an estimate: it is the lift.
        return round(float(weight), 1)
    return round(float(weight) * (1 + reps / EPLEY_DIVISOR), 1)


@dataclass(frozen=True)
class PersonalBest:
    """The heaviest single a movement's logged sets support.

    ``one_rep_max`` is the estimate; ``weight``/``reps`` are the actual set it
    came from, kept so the page can show its working rather than a number with
    no provenance.
    """

    exercise_id: str
    one_rep_max: float
    weight: float
    reps: int
    achieved_on: date

    def to_dict(self) -> dict:
        return {
            "one_rep_max": self.one_rep_max,
            "weight": self.weight,
            "reps": self.reps,
            "achieved_on": self.achieved_on.isoformat(),
        }


def best_from_sets(rows) -> dict[str, PersonalBest]:
    """Reduce ``(exercise_id, weight, reps, entry_date)`` rows to one best each.

    Warm-ups are already excluded by the query. Sets that cannot support an
    estimate are skipped here rather than filtered in SQL, so the rule lives in
    one place and :mod:`app.models` stays free of training opinions.

    Ties go to the **earlier** date: a best is when you first reached it, and
    re-hitting the same estimate is not a new personal best.
    """
    best: dict[str, PersonalBest] = {}
    for exercise_id, weight, reps, entry_date in rows:
        estimate = estimate_one_rep_max(weight, reps)
        if estimate is None:
            continue

        current = best.get(exercise_id)
        beats_it = (
            current is None
            or estimate > current.one_rep_max
            or (estimate == current.one_rep_max and entry_date < current.achieved_on)
        )
        if beats_it:
            best[exercise_id] = PersonalBest(
                exercise_id=exercise_id,
                one_rep_max=estimate,
                weight=float(weight),
                reps=int(reps),
                achieved_on=entry_date,
            )
    return best
