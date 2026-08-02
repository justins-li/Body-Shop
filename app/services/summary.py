"""Weekly aggregation: turn logged entries into per-muscle-group coverage.

The body map on the summary page shades a muscle group on a volume scale: from
light green at one set to dark green at the group's weekly target, then from
light red to dark red once the target is passed.  ``worked`` remains true from
the very first set, which is the rule the ``/log`` page and the breakdown list
key off.

Sets are **weighted by how directly a movement trains a group**: a primary
muscle takes the whole set, a secondary muscle half of it, so totals are
fractional (see :data:`app.exercises.PRIMARY_WEIGHT`). Movements outside
:data:`app.exercises.VOLUME_CATEGORIES` — stretches, cardio, plyometrics —
contribute nothing and never mark a group worked.

Six groups also break down into **regions** (see :data:`app.exercises.MUSCLE_REGIONS`).
Regions are graded differently — which is to say, not at all. They carry no
target, no state and no intensity, because no study has established how many
weekly sets a muscle *head* needs. They report where a group's volume landed and
whether a region was left out, which is a statement of fact rather than a
prescription. See docs/VOLUME_SCIENCE.md.
"""

from __future__ import annotations

from datetime import date

from ..exercises import (
    MUSCLE_GROUPS,
    MUSCLE_LABELS,
    REGION_LABELS,
    get_exercise,
    regions_for,
    regions_of,
)
from ..models import WorkoutEntry, list_entries
from ..training import DEFAULT_PROFILE, TrainerProfile
from .weeks import week_bounds, week_days


#: Share of a group's attributed volume below which a region reads as left out.
#:
#: **This is a judgement, not a finding**, and one of only two invented numbers
#: in the region feature. An even split across three delt heads is 33% and across
#: two chest regions 50%, so 15% is well clear of "merely less" in either case.
REGION_NEGLECT_SHARE = 0.15

#: A group must have had this much volume before a thin region means anything.
#:
#: Set to the approximate floor at which a muscle responds to training at all
#: (Pelland et al. 2025), so a group that was barely trained is reported as
#: barely trained rather than as three separate imbalances.
REGION_NEGLECT_MIN_PARENT_SETS = 4.0


def overshoot_span(target: int) -> int:
    """Sets past ``target`` that take a group from light red to dark red.

    Half the target, so an extra set is a visible step on either scale: ten
    sets of overshoot saturate a large group, five a small one.
    """
    return max(1, target // 2)


def grade(sets: float, target: int) -> tuple[str, float]:
    """Grade ``sets`` against ``target`` as a ``(state, intensity)`` pair.

    ``state`` is ``rest``, ``trained`` or ``over``; ``intensity`` runs 0–1
    *within that state's colour ramp*, so it restarts at the bottom when a
    group crosses its target and turns from green to red.

    ``sets`` is a float because secondary muscles count half (see the module
    docstring); the grading maths is unchanged by that.
    """
    if sets <= 0:
        return "rest", 0.0
    if sets <= target:
        return "trained", round(sets / target, 3)
    over = sets - target
    return "over", round(min(1.0, over / overshoot_span(target)), 3)


def summarise_entries(
    entries: list[WorkoutEntry], profile: TrainerProfile | None = None
) -> dict[str, dict]:
    """Aggregate ``entries`` into ``{muscle: {worked, sets, state, ...}}``.

    ``sets`` weights each set by how directly the movement trains the group: 3
    sets of bench press add 3 to *chest* (primary) and 1.5 to *triceps* and
    *shoulders* (secondary). Totals are therefore fractional.

    A movement outside :data:`app.exercises.VOLUME_CATEGORIES` is skipped
    entirely — it adds no sets and does not mark a group ``worked``, so a week
    of stretching leaves the body map grey rather than lit at zero intensity.

    Each group also carries its weekly ``target``, how many sets it is ``over``
    by, and the ``state``/``intensity`` pair the body map shades with.

    ``profile`` is the Phase 6 trainer setup, which decides what each group's
    target actually is; omitting it grades against the baseline convention,
    which is exactly what happened before that phase. Nothing else here changes
    with it — the aggregation is the same sets either way, and only the number
    they are measured against moves.
    """
    profile = profile or DEFAULT_PROFILE
    summary: dict[str, dict] = {
        muscle: {
            "muscle": muscle,
            "label": MUSCLE_LABELS[muscle],
            "worked": False,
            "sets": 0.0,
            "target": profile.target_for(muscle),
            "over": 0.0,
            "state": "rest",
            "intensity": 0.0,
            "exercises": [],
            "regions": [
                {
                    "region": region,
                    "label": REGION_LABELS[region],
                    "sets": 0.0,
                    "share": 0.0,
                    "neglected": False,
                }
                for region in regions_of(muscle)
            ],
            "region_sets": 0.0,
        }
        for muscle in MUSCLE_GROUPS
    }

    for entry in entries:
        exercise = get_exercise(entry.exercise_id)
        if exercise is None or not exercise.counts_toward_volume:
            continue

        for muscle in exercise.muscles:
            bucket = summary.get(muscle)
            if bucket is None:  # pragma: no cover - guards future exercise data
                continue
            weighted = entry.sets * exercise.weight_for(muscle)
            bucket["sets"] += weighted
            # Zero is reachable now: an entry of only warm-up sets has
            # entry.sets == 0, so weighted is 0 for every muscle it touches.
            # Before Phase 4 this branch was unreachable — CHECK (sets > 0)
            # guaranteed at least one real set — so don't drop the guard back
            # to an unconditional assignment; that would light the body map
            # for a group that received no volume.
            if weighted > 0:
                bucket["worked"] = True
                if entry.exercise_name not in bucket["exercises"]:
                    bucket["exercises"].append(entry.exercise_name)

            # A movement with no defensible emphasis inside the group — a
            # deadlift for the back — leaves this volume unattributed rather
            # than spreading it over regions it says nothing about. Movements
            # emphasising two regions split evenly between them.
            emphasised = regions_for(exercise.id, muscle)
            if not emphasised:
                continue
            per_region = weighted / len(emphasised)
            for region in bucket["regions"]:
                if region["region"] in emphasised:
                    region["sets"] += per_region
                    bucket["region_sets"] += per_region

    for bucket in summary.values():
        # Half-set weights land on .5 exactly, but round anyway so float error
        # never leaks a 12.499999999 into the payload.
        bucket["sets"] = round(bucket["sets"], 1)
        bucket["over"] = round(max(0.0, bucket["sets"] - bucket["target"]), 1)
        bucket["state"], bucket["intensity"] = grade(bucket["sets"], bucket["target"])
        _finish_regions(bucket)

    return summary


def _finish_regions(bucket: dict) -> None:
    """Fill in each region's share of its group, and whether it was left out.

    Shares are of the volume that could be *attributed* to a region, not of the
    group's total — so a week of deadlifts and pulldowns reports the lats' share
    of the pulldowns, and ``region_sets`` says how much of the back's volume that
    was. Reporting a share of the total instead would silently blame the deadlift
    for neglecting the mid back.
    """
    attributed = bucket["region_sets"]
    bucket["region_sets"] = round(attributed, 1)

    for region in bucket["regions"]:
        region["sets"] = round(region["sets"], 1)
        region["share"] = round(region["sets"] / attributed, 3) if attributed else 0.0
        region["neglected"] = (
            attributed >= REGION_NEGLECT_MIN_PARENT_SETS
            and region["share"] < REGION_NEGLECT_SHARE
        )


def weekly_summary(
    user_id: str,
    day: date,
    week_starts_on: int = 1,
    profile: TrainerProfile | None = None,
) -> dict:
    """Build the full payload backing the weekly summary page for ``day``.

    The resolved ``profile`` is echoed back beside the grading it produced, so a
    client renders the targets it was actually graded against rather than
    re-deriving them from a preference it holds locally.
    """
    profile = profile or DEFAULT_PROFILE
    start, end = week_bounds(day, week_starts_on)
    entries = list_entries(user_id, start, end)
    muscles = summarise_entries(entries, profile)

    per_day = {d.isoformat(): 0 for d in week_days(start)}
    for entry in entries:
        key = entry.entry_date.isoformat()
        if key in per_day:
            per_day[key] += entry.sets

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "profile": profile.to_dict(),
        "total_sets": sum(entry.sets for entry in entries),
        "total_entries": len(entries),
        "muscles": muscles,
        "muscles_worked": [m for m in MUSCLE_GROUPS if muscles[m]["worked"]],
        "muscles_at_target": [m for m in MUSCLE_GROUPS if muscles[m]["sets"] >= muscles[m]["target"]],
        "muscles_over": [m for m in MUSCLE_GROUPS if muscles[m]["state"] == "over"],
        # Flat list so the page can say "two regions were left out" without
        # walking every group. Order follows MUSCLE_GROUPS, then region order.
        "regions_neglected": [
            {"muscle": m, "region": r["region"], "label": r["label"]}
            for m in MUSCLE_GROUPS
            for r in muscles[m]["regions"]
            if r["neglected"]
        ],
        "sets_per_day": per_day,
        "entries": [entry.to_dict() for entry in entries],
    }
