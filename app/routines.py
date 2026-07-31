"""Suggested routines: sessions someone can follow instead of a blank log.

Phase 8.1. The app could always tell you what your week *was*; it had nothing to
say about what a session could be. A new user's first screen was an empty picker
over 873 movements, which is the worst possible introduction to a catalog.

**These are editorial content, and they live in code.** Same reasoning as
:data:`app.exercises.STAPLE_EXERCISE_IDS`: ``exercises.json`` is generated from a
pinned upstream commit and never hand-edited, and a routine is a judgement about
training rather than a fact about the source data. They are validated against the
catalog at import, so an upstream rename fails loudly instead of rendering a
routine with a hole in it.

Three rules they obey:

* **Each one focuses on something and says so.** A push day, a pull day, legs, a
  beginner full body, an athletic whole-body session. A routine that trains
  everything a bit is the thing the body map already tells you not to do.
* **The time estimate is derived, never typed.** It comes from the prescribed
  sets (see :func:`estimate_minutes`), so it cannot drift from the exercises
  listed above it — which is exactly what a hand-written "45 min" does the first
  time anybody edits the list.
* **A routine is a suggestion, and is labelled as one.** It carries no claim about
  being optimal, no medical or injury claim, and no weekly volume target. Rep
  ranges here are a *prescription inside a session someone else wrote*, which is
  a different object from the weekly set targets docs/VOLUME_SCIENCE.md §4 bans
  printing as ranges.
"""

from __future__ import annotations

from dataclasses import dataclass

from .exercises import EXERCISES, MUSCLE_LABELS, get_exercise
from .training import SESSION_OVERHEAD_MINUTES, minutes_for_sets


@dataclass(frozen=True)
class RoutineExercise:
    """One movement in a routine, and how much of it to do."""

    exercise_id: str
    #: Working sets. A whole number, and what the time estimate is built from.
    sets: int
    #: Rep guidance, as written. A string because "8-10", "max" and "30 sec" are
    #: all things a routine legitimately says, and none of them are arithmetic.
    reps: str
    #: Why this movement is in this routine, in one line. Shown beside it.
    note: str

    def to_dict(self) -> dict:
        """The shape the routines page renders, with the catalog joined on."""
        exercise = get_exercise(self.exercise_id)
        return {
            "exercise_id": self.exercise_id,
            "sets": self.sets,
            "reps": self.reps,
            "note": self.note,
            "name": exercise.name,
            "primary": [MUSCLE_LABELS.get(m, m) for m in exercise.primary],
            "secondary": [MUSCLE_LABELS.get(m, m) for m in exercise.secondary],
            "weight_mode": exercise.weight_mode,
            "counts_toward_volume": exercise.counts_toward_volume,
        }


@dataclass(frozen=True)
class Routine:
    """A session worth following, and what it is for."""

    key: str
    name: str
    #: What this session trains, in the words someone would use to choose it.
    focus: str
    #: One paragraph: who it is for and what it is trying to do.
    blurb: str
    #: ``beginner`` | ``intermediate``, matching the catalog's own vocabulary.
    level: str
    exercises: tuple[RoutineExercise, ...]

    @property
    def total_sets(self) -> int:
        return sum(item.sets for item in self.exercises)

    @property
    def minutes(self) -> int:
        """Estimated session length. Derived from the sets above, never typed."""
        return estimate_minutes(self.total_sets)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "focus": self.focus,
            "blurb": self.blurb,
            "level": self.level,
            "total_sets": self.total_sets,
            "minutes": self.minutes,
            "exercises": [item.to_dict() for item in self.exercises],
        }


def estimate_minutes(total_sets: int) -> int:
    """Estimate how long ``total_sets`` of working sets takes, in minutes.

    Sets plus their rest, and then the fixed per-session overhead that
    :data:`app.training.SESSION_OVERHEAD_MINUTES` already names — changing rooms,
    walking to the rack, waiting for it. Rounded to the nearest five, because a
    minute of precision on an estimate this rough would be a lie about how well
    it is known.
    """
    raw = minutes_for_sets(total_sets) + SESSION_OVERHEAD_MINUTES
    return max(5, int(round(raw / 5.0) * 5))


#: The routines offered on ``/routines``, in the order they are listed.
#:
#: Deliberately few. Five sessions someone can actually choose between beats
#: thirty they have to read, and every one here is built out of movements in
#: :data:`app.exercises.STAPLE_EXERCISE_IDS` so the picker will already have been
#: offering them.
ROUTINES: tuple[Routine, ...] = (
    Routine(
        key="full_body_start",
        name="Full body, to start",
        focus="Everything, three times a week",
        blurb=(
            "Six movements covering the whole body. If you are new, this is the one "
            "to run — three sessions a week of this trains every group more than a "
            "split will while you are still learning the lifts."
        ),
        level="beginner",
        exercises=(
            RoutineExercise("Barbell_Squat", 3, "5", "The session's main lift. Warm up to it."),
            RoutineExercise(
                "Barbell_Bench_Press_-_Medium_Grip", 3, "5", "Horizontal press."
            ),
            RoutineExercise("Bent_Over_Barbell_Row", 3, "6-8", "Pulls against the press."),
            RoutineExercise("Standing_Military_Press", 3, "6-8", "Overhead, for the shoulders."),
            RoutineExercise("Romanian_Deadlift", 3, "8-10", "Hamstrings and glutes, hinging."),
            RoutineExercise("Plank", 3, "30-45 sec", "Braced, not held slack."),
        ),
    ),
    Routine(
        key="push",
        name="Push day",
        focus="Chest, shoulders, triceps",
        blurb=(
            "Everything that presses. Two compound presses first while you are fresh, "
            "then the side delts and triceps that pressing alone under-trains."
        ),
        level="intermediate",
        exercises=(
            RoutineExercise(
                "Barbell_Bench_Press_-_Medium_Grip", 4, "6-8", "Flat, heaviest first."
            ),
            RoutineExercise(
                "Incline_Dumbbell_Press", 3, "8-10", "Upper chest, which flat pressing misses."
            ),
            RoutineExercise("Dumbbell_Shoulder_Press", 3, "8-10", "Overhead press, seated or standing."),
            RoutineExercise(
                "Side_Lateral_Raise", 3, "12-15", "Side delts get almost nothing from pressing."
            ),
            RoutineExercise("Triceps_Pushdown", 3, "10-12", "Lateral and medial heads."),
            RoutineExercise(
                "Cable_Rope_Overhead_Triceps_Extension", 3, "10-12",
                "Overhead, so the long head is loaded stretched.",
            ),
        ),
    ),
    Routine(
        key="pull",
        name="Pull day",
        focus="Back, rear delts, biceps",
        blurb=(
            "Everything that pulls. One vertical and one horizontal pull, because they "
            "grow different parts of the back, then rear delts and arms."
        ),
        level="intermediate",
        exercises=(
            RoutineExercise("Pullups", 4, "6-10", "Vertical pull. Add weight when 10 is easy."),
            RoutineExercise("Bent_Over_Barbell_Row", 4, "6-8", "Horizontal pull, for the mid back."),
            RoutineExercise("Wide-Grip_Lat_Pulldown", 3, "10-12", "More lat work, easier to control."),
            RoutineExercise("Face_Pull", 3, "15", "Rear delts, which rowing only partly covers."),
            RoutineExercise("Barbell_Curl", 3, "8-10", "Biceps, directly."),
            RoutineExercise("Hammer_Curls", 3, "10-12", "Neutral grip, so the forearms get work too."),
        ),
    ),
    Routine(
        key="legs",
        name="Leg day",
        focus="Quads, hamstrings, glutes, calves",
        blurb=(
            "A squat and a hinge carry most of it. The isolation afterwards is there "
            "because hamstrings and calves are the two groups a squat alone leaves thin."
        ),
        level="intermediate",
        exercises=(
            RoutineExercise("Barbell_Squat", 4, "5-8", "The session. Everything else is accessory."),
            RoutineExercise("Romanian_Deadlift", 3, "8-10", "Hinge, for hamstrings and glutes."),
            RoutineExercise("Leg_Press", 3, "10-12", "More quad volume without more spinal load."),
            RoutineExercise("Lying_Leg_Curls", 3, "10-12", "Knee flexion, which hinging does not train."),
            RoutineExercise("Standing_Calf_Raises", 4, "12-15", "Calves respond to the volume."),
        ),
    ),
    Routine(
        key="athletic",
        name="Athletic whole body",
        focus="Power, then strength, whole body",
        blurb=(
            "Built around moving a bar fast rather than grinding it. The Olympic lifts "
            "come first because they are technical and go badly when you are tired. "
            "Learn them light before loading them."
        ),
        level="intermediate",
        exercises=(
            RoutineExercise("Hang_Clean", 5, "3", "Fast and clean. Stop when speed drops."),
            RoutineExercise("Push_Press", 4, "5", "Overhead, driven with the legs."),
            RoutineExercise("Front_Squat_Clean_Grip", 3, "5", "Upright squat, quad dominant."),
            RoutineExercise("Pullups", 3, "8", "Upper-body pull."),
            RoutineExercise("Romanian_Deadlift", 3, "8", "Posterior chain."),
            RoutineExercise("Farmers_Walk", 3, "30-40 m", "Grip, trunk and everything holding you upright."),
        ),
    ),
)

#: Keyed for lookup; the tuple above stays the display order.
ROUTINES_BY_KEY: dict[str, Routine] = {routine.key: routine for routine in ROUTINES}


class RoutineError(RuntimeError):
    """Raised at import when a routine does not match the catalog."""


def _check_routines() -> None:
    """Every routine must name real movements, and say something about itself.

    An id that stopped resolving would render a card with a blank name and a
    dead log button — the same silent failure ``STAPLE_EXERCISE_IDS`` is checked
    against, and worth the same import-time error.
    """
    keys = [routine.key for routine in ROUTINES]
    if len(set(keys)) != len(keys):
        raise RoutineError(f"Duplicate routine keys: {keys}.")

    for routine in ROUTINES:
        if not routine.exercises:
            raise RoutineError(f"Routine {routine.key!r} has no exercises.")

        seen: set[str] = set()
        for item in routine.exercises:
            if item.exercise_id not in EXERCISES:
                raise RoutineError(
                    f"Routine {routine.key!r} names {item.exercise_id!r}, which is not "
                    "in the catalog. The upstream pin probably renamed it."
                )
            if item.exercise_id in seen:
                raise RoutineError(
                    f"Routine {routine.key!r} lists {item.exercise_id!r} twice; the "
                    "set count and the time estimate would both double-count it."
                )
            seen.add(item.exercise_id)

            if item.sets < 1:
                raise RoutineError(
                    f"Routine {routine.key!r}: {item.exercise_id!r} has {item.sets} sets."
                )


_check_routines()


def all_routines() -> list[Routine]:
    """Every routine, in display order."""
    return list(ROUTINES)


def get_routine(key: str) -> Routine | None:
    """Return the routine with ``key``, or ``None`` if there is none."""
    return ROUTINES_BY_KEY.get(key)
