"""Weekly aggregation: turn logged entries into per-muscle-group coverage.

The body map on the summary page shades a muscle group on a volume scale: from
light green at one set to dark green at the group's weekly target, then from
light red to dark red once the target is passed.  ``worked`` remains true from
the very first set, which is the rule the ``/log`` page and the breakdown list
key off.
"""

from __future__ import annotations

from datetime import date

from ..exercises import MUSCLE_GROUPS, MUSCLE_LABELS, target_for
from ..models import WorkoutEntry, list_entries
from .weeks import week_bounds, week_days


def overshoot_span(target: int) -> int:
    """Sets past ``target`` that take a group from light red to dark red.

    Half the target, so an extra set is a visible step on either scale: ten
    sets of overshoot saturate a large group, five a small one.
    """
    return max(1, target // 2)


def grade(sets: int, target: int) -> tuple[str, float]:
    """Grade ``sets`` against ``target`` as a ``(state, intensity)`` pair.

    ``state`` is ``rest``, ``trained`` or ``over``; ``intensity`` runs 0–1
    *within that state's colour ramp*, so it restarts at the bottom when a
    group crosses its target and turns from green to red.
    """
    if sets <= 0:
        return "rest", 0.0
    if sets <= target:
        return "trained", round(sets / target, 3)
    over = sets - target
    return "over", round(min(1.0, over / overshoot_span(target)), 3)


def summarise_entries(entries: list[WorkoutEntry]) -> dict[str, dict]:
    """Aggregate ``entries`` into ``{muscle: {worked, sets, state, ...}}``.

    ``sets`` counts every set of every exercise that targets the muscle group,
    so 3 sets of bench press add 3 sets to both *chest* and *triceps*.

    Each group also carries its weekly ``target``, how many sets it is ``over``
    by, and the ``state``/``intensity`` pair the body map shades with.
    """
    summary: dict[str, dict] = {
        muscle: {
            "muscle": muscle,
            "label": MUSCLE_LABELS[muscle],
            "worked": False,
            "sets": 0,
            "target": target_for(muscle),
            "over": 0,
            "state": "rest",
            "intensity": 0.0,
            "exercises": [],
        }
        for muscle in MUSCLE_GROUPS
    }

    for entry in entries:
        for muscle in entry.muscles:
            bucket = summary.get(muscle)
            if bucket is None:  # pragma: no cover - guards future exercise data
                continue
            bucket["sets"] += entry.sets
            bucket["worked"] = True
            if entry.exercise_name not in bucket["exercises"]:
                bucket["exercises"].append(entry.exercise_name)

    for bucket in summary.values():
        bucket["over"] = max(0, bucket["sets"] - bucket["target"])
        bucket["state"], bucket["intensity"] = grade(bucket["sets"], bucket["target"])

    return summary


def weekly_summary(day: date, week_starts_on: int = 1) -> dict:
    """Build the full payload backing the weekly summary page for ``day``."""
    start, end = week_bounds(day, week_starts_on)
    entries = list_entries(start, end)
    muscles = summarise_entries(entries)

    per_day = {d.isoformat(): 0 for d in week_days(start)}
    for entry in entries:
        key = entry.entry_date.isoformat()
        if key in per_day:
            per_day[key] += entry.sets

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "total_sets": sum(entry.sets for entry in entries),
        "total_entries": len(entries),
        "muscles": muscles,
        "muscles_worked": [m for m in MUSCLE_GROUPS if muscles[m]["worked"]],
        "muscles_at_target": [m for m in MUSCLE_GROUPS if muscles[m]["sets"] >= muscles[m]["target"]],
        "muscles_over": [m for m in MUSCLE_GROUPS if muscles[m]["state"] == "over"],
        "sets_per_day": per_day,
        "entries": [entry.to_dict() for entry in entries],
    }
