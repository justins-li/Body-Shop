"""Catalog of exercises and the muscle groups they train.

This module is the single source of truth for what the user can log.  Adding a
new exercise is a one-line change here: the input form, the API validation, the
weekly summary and the body map all read from :data:`EXERCISES`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

#: Muscle groups rendered on the body outline, in display order.
#:
#: Front view shows chest, abs, biceps and quads; the back view shows back,
#: triceps and hamstrings.  No group appears in both figures, so the two
#: silhouettes carry genuinely different information.
MUSCLE_GROUPS: tuple[str, ...] = (
    "chest",
    "abs",
    "back",
    "biceps",
    "triceps",
    "quads",
    "hamstrings",
)

#: Human readable labels for the muscle group slugs above.
MUSCLE_LABELS: dict[str, str] = {
    "chest": "Chest",
    "abs": "Abs",
    "back": "Back",
    "biceps": "Biceps",
    "triceps": "Triceps",
    "quads": "Quads",
    "hamstrings": "Hamstrings",
}


#: Weekly set target for a large muscle group.
LARGE_MUSCLE_TARGET = 20

#: Weekly set target for a small muscle group, which recovers on less volume.
SMALL_MUSCLE_TARGET = 10

#: Sets per week each group is aiming for.  Reaching the target is the darkest
#: green; going past it starts the red overshoot scale (see
#: :func:`app.services.summary.grade`).
MUSCLE_TARGETS: dict[str, int] = {
    "chest": LARGE_MUSCLE_TARGET,
    "abs": SMALL_MUSCLE_TARGET,
    "back": LARGE_MUSCLE_TARGET,
    "biceps": SMALL_MUSCLE_TARGET,
    "triceps": SMALL_MUSCLE_TARGET,
    "quads": LARGE_MUSCLE_TARGET,
    "hamstrings": LARGE_MUSCLE_TARGET,
}


def target_for(muscle: str) -> int:
    """Return the weekly set target for ``muscle``."""
    return MUSCLE_TARGETS.get(muscle, LARGE_MUSCLE_TARGET)


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
        # A squat counts for the whole thigh until a hinge movement
        # (deadlift / leg curl) is added to separate the two.
        Exercise("squat", "Squat", ("quads", "hamstrings")),
        Exercise("sit_ups", "Sit ups", ("abs",)),
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
