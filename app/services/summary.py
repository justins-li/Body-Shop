"""Weekly aggregation: turn logged entries into per-muscle-group coverage.

The body map on the summary page colours a muscle group red when
``worked`` is true — i.e. the user completed **at least one set** of an
exercise that targets that group during the week.
"""

from __future__ import annotations

from datetime import date

from ..exercises import MUSCLE_GROUPS, MUSCLE_LABELS
from ..models import WorkoutEntry, list_entries
from .weeks import week_bounds, week_days


def summarise_entries(entries: list[WorkoutEntry]) -> dict[str, dict]:
    """Aggregate ``entries`` into ``{muscle: {worked, sets, exercises}}``.

    ``sets`` counts every set of every exercise that targets the muscle group,
    so 3 sets of bench press add 3 sets to both *chest* and *triceps*.
    """
    summary: dict[str, dict] = {
        muscle: {
            "muscle": muscle,
            "label": MUSCLE_LABELS[muscle],
            "worked": False,
            "sets": 0,
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
        "sets_per_day": per_day,
        "entries": [entry.to_dict() for entry in entries],
    }
