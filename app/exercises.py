"""Catalog of exercises and the muscle groups they train.

This module is the single source of truth for what the user can log.  Adding a
new exercise is a one-line change here: the input form, the API validation, the
weekly summary and the body map all read from :data:`EXERCISES`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

#: Muscle groups rendered on the body outline, in display order.
MUSCLE_GROUPS: tuple[str, ...] = ("chest", "back", "biceps", "triceps", "legs")

#: Human readable labels for the muscle group slugs above.
MUSCLE_LABELS: dict[str, str] = {
    "chest": "Chest",
    "back": "Back",
    "biceps": "Biceps",
    "triceps": "Triceps",
    "legs": "Legs",
}


@dataclass(frozen=True)
class Exercise:
    """A loggable movement and the muscle groups it targets."""

    id: str
    name: str
    muscles: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "muscles": list(self.muscles)}


#: The exercises a user may log, keyed by slug.
EXERCISES: dict[str, Exercise] = {
    exercise.id: exercise
    for exercise in (
        Exercise("bench_press", "Bench press", ("triceps", "chest")),
        Exercise("pull_ups", "Pull ups", ("biceps", "back")),
        Exercise("squat", "Squat", ("legs",)),
    )
}


def all_exercises() -> list[Exercise]:
    """Return every exercise in catalog order."""
    return list(EXERCISES.values())


def get_exercise(exercise_id: str) -> Exercise | None:
    """Return the exercise with ``exercise_id``, or ``None`` if unknown."""
    return EXERCISES.get(exercise_id)


def muscles_for(exercise_ids: Iterable[str]) -> set[str]:
    """Return the union of muscle groups trained by ``exercise_ids``."""
    worked: set[str] = set()
    for exercise_id in exercise_ids:
        exercise = EXERCISES.get(exercise_id)
        if exercise is not None:
            worked.update(exercise.muscles)
    return worked
