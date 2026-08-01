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

    #: Marks a routine reconstructed from press coverage of a real athlete.
    #:
    #: These are shown with an **[experimental]** tag, and the tag is not
    #: decoration. Everything else here is a session we wrote and stand behind.
    #: These are a best reading of what has been *reported* about somebody
    #: else's training — second-hand, often years old, and stripped of the
    #: coaching, the training age and the whole rest of the week that made it
    #: make sense for them. Interesting to look at; not advice.
    experimental: bool = False

    #: Whose training this approximates. Required when ``experimental``.
    inspired_by: str | None = None

    #: Where the reporting came from, so the claim is checkable.
    source: str | None = None

    #: Minutes one working set costs in *this* session, if not the usual.
    #:
    #: **Judgement, and the only per-routine number here.** A continuous band
    #: circuit at twenty-plus reps does not cost what a heavy triple with three
    #: minutes' rest costs, and pricing them the same put a badly wrong figure
    #: on one card. Note this still *derives* the duration from the sets listed
    #: — editing the exercises still moves the estimate — which is the property
    #: worth protecting. What is typed is the pace, not the answer.
    minutes_per_set: float | None = None

    @property
    def total_sets(self) -> int:
        return sum(item.sets for item in self.exercises)

    @property
    def minutes(self) -> int:
        """Estimated session length. Derived from the sets above, never typed."""
        return estimate_minutes(self.total_sets, self.minutes_per_set)

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "name": self.name,
            "focus": self.focus,
            "blurb": self.blurb,
            "level": self.level,
            "experimental": self.experimental,
            "inspired_by": self.inspired_by,
            "source": self.source,
            "total_sets": self.total_sets,
            "minutes": self.minutes,
            "exercises": [item.to_dict() for item in self.exercises],
        }


def estimate_minutes(total_sets: int, minutes_per_set: float | None = None) -> int:
    """Estimate how long ``total_sets`` of working sets takes, in minutes.

    Sets plus their rest, and then the fixed per-session overhead that
    :data:`app.training.SESSION_OVERHEAD_MINUTES` already names — changing rooms,
    walking to the rack, waiting for it. Rounded to the nearest five, because a
    minute of precision on an estimate this rough would be a lie about how well
    it is known.

    ``minutes_per_set`` overrides the usual pace for a session that does not
    work at it — see :attr:`Routine.minutes_per_set`.
    """
    per_set = minutes_for_sets(total_sets)
    if minutes_per_set is not None:
        per_set = max(0, total_sets) * minutes_per_set
    return max(5, int(round((per_set + SESSION_OVERHEAD_MINUTES) / 5.0) * 5))


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

#: Sessions reconstructed from published coverage of well-known athletes.
#:
#: **Every one of these is tagged [experimental], and the tag is the point.**
#: The five routines above are sessions we wrote and stand behind. These are a
#: best reading of what has been *reported* about somebody else's training:
#: second-hand, often years old, and separated from the coaching, the training
#: age, the sport-specific work and the rest of the week that made it make sense
#: for them. A sprinter's lifting session is a small part of being a sprinter.
#:
#: So they are offered as something to look at rather than something to follow,
#: they name their source, and they say plainly that they are approximations
#: nobody involved has endorsed. Movements are mapped onto the nearest thing in
#: the catalog, which is itself a judgement — "rotational squats" is not a
#: catalog entry, and "Squats - With Bands" is the closest honest stand-in.
ATHLETE_ROUTINES: tuple[Routine, ...] = (
    Routine(
        key="rock_legs",
        name="Leg day",
        focus="Glutes, quads, hamstrings, calves",
        blurb=(
            "Reported as hips and glutes first, squats late rather than first, and "
            "no deadlift at all — the opposite order to most leg days. Around four "
            "sets of everything, with a minute or so between them."
        ),
        level="intermediate",
        experimental=True,
        inspired_by="Dwayne “The Rock” Johnson",
        source="Coach / Steel Supplements coverage of Dave Rienzi's programming",
        exercises=(
            RoutineExercise("Barbell_Hip_Thrust", 4, "8-12", "Hips first, while you are fresh."),
            RoutineExercise("Barbell_Glute_Bridge", 4, "8-12", "More hip extension, shorter range."),
            RoutineExercise("Leg_Extensions", 4, "12-15", "Quads in isolation."),
            RoutineExercise("Lying_Leg_Curls", 4, "12", "Knee flexion, which hinging misses."),
            RoutineExercise("Barbell_Squat", 4, "10-12", "Late and lighter than you would expect."),
            RoutineExercise("Standing_Calf_Raises", 4, "15-20", "High reps, to finish."),
        ),
    ),
    Routine(
        key="brady_bands",
        name="Band circuit",
        focus="Whole body, bands only",
        blurb=(
            "The TB12 idea in one session: bands rather than iron, high reps, and "
            "speed over load. Reported at seventeen to twenty-five reps a set, moving "
            "between movements rather than resting long."
        ),
        level="beginner",
        experimental=True,
        inspired_by="Tom Brady",
        source="TB12 Sports' own published nine-exercise routine",
        # A continuous band circuit does not cost what a heavy triple costs.
        minutes_per_set=1.6,
        exercises=(
            RoutineExercise("Squats_-_With_Bands", 3, "20", "Fast out of the bottom."),
            RoutineExercise("Bench_Press_-_With_Bands", 3, "20", "Resisted pressing, not loaded."),
            RoutineExercise("Band_Pull_Apart", 3, "25", "The pull against all that pressing."),
            RoutineExercise("Shoulder_Press_-_With_Bands", 3, "20", "Overhead, under tension."),
            RoutineExercise("Speed_Band_Overhead_Triceps", 3, "20", "Triceps, at speed."),
            RoutineExercise("Bodyweight_Walking_Lunge", 3, "20", "Controlled on the way down."),
        ),
    ),
    Routine(
        key="phelps_dryland",
        name="Dryland",
        focus="Pulling, hinging, core",
        blurb=(
            "What a swimmer does out of the water: heavy compounds for the engine, "
            "pull-ups for the lats, and core work that imitates the kick. Reported at "
            "one to two hours, four or five times a week — on top of swimming twice."
        ),
        level="intermediate",
        experimental=True,
        inspired_by="Michael Phelps",
        source="Steel Supplements / Your Swim Log accounts of Bob Bowman's dryland",
        exercises=(
            RoutineExercise("Pullups", 4, "10", "The swimmer's lift."),
            RoutineExercise("Barbell_Deadlift", 3, "5", "Heavy, for the posterior chain."),
            RoutineExercise("Barbell_Squat", 3, "8", "Legs, for the start and the turns."),
            RoutineExercise("Barbell_Bench_Press_-_Medium_Grip", 3, "8", "Pressing, to balance the pulling."),
            RoutineExercise("Hanging_Leg_Raise", 4, "15", "Reported as imitating the butterfly kick."),
            RoutineExercise("Plank", 3, "60 sec", "Braced, not held slack."),
        ),
    ),
    Routine(
        key="bolt_power",
        name="Power session",
        focus="Explosive strength, legs and core",
        blurb=(
            "Speed work happens on the track; this is the ninety minutes in the weight "
            "room that feeds it. Low reps and fast bars — the aim is force in a hurry, "
            "not fatigue. Reported at three sessions a week."
        ),
        level="intermediate",
        experimental=True,
        inspired_by="Usain Bolt",
        source="Bret Contreras / RunnerClick summaries of his published training",
        exercises=(
            RoutineExercise("Power_Clean", 5, "3", "Fast. Stop the moment speed drops."),
            RoutineExercise("Barbell_Squat", 4, "5", "Heavy, but never grinding."),
            RoutineExercise("Front_Box_Jump", 4, "5", "Land quiet. Step down, never jump down."),
            RoutineExercise("Barbell_Lunge", 3, "10", "One leg at a time, as sprinting is."),
            RoutineExercise("Good_Morning", 3, "8", "Hamstrings, which is where sprinters break."),
            RoutineExercise("Hanging_Leg_Raise", 3, "15", "He credits the core repeatedly."),
        ),
    ),
    Routine(
        key="serena_court",
        name="Court conditioning",
        focus="Whole body, at speed",
        blurb=(
            "Reported as three to five sets of eight to twelve, kept deliberately "
            "varied, and closer to a circuit than to a lifting session — strength in "
            "service of a match rather than for its own sake."
        ),
        level="intermediate",
        experimental=True,
        inspired_by="Serena Williams",
        source="Dr Workout / Jacked Gorilla summaries of published interviews",
        minutes_per_set=2.4,
        exercises=(
            RoutineExercise("Barbell_Squat", 4, "12", "Legs and glutes, for the first step."),
            RoutineExercise("Dumbbell_Lunges", 3, "12", "Single leg, changing direction."),
            RoutineExercise("Alternating_Renegade_Row", 3, "10", "The plank row she is often filmed doing."),
            RoutineExercise("Pushups", 3, "15", "Reported as done in thirty-second bursts."),
            RoutineExercise("One-Arm_Medicine_Ball_Slam", 3, "10", "Rotational power, as a serve is."),
            RoutineExercise("Plank", 3, "45 sec", "The trunk that everything else works through."),
        ),
    ),
)

#: Everything offered on ``/routines``: ours first, then the reconstructions.
ALL_ROUTINES: tuple[Routine, ...] = ROUTINES + ATHLETE_ROUTINES

#: Keyed for lookup; the tuple above stays the display order.
ROUTINES_BY_KEY: dict[str, Routine] = {routine.key: routine for routine in ALL_ROUTINES}


class RoutineError(RuntimeError):
    """Raised at import when a routine does not match the catalog."""


def _check_routines(routines: tuple[Routine, ...] | None = None) -> None:
    """Every routine must name real movements, and say something about itself.

    An id that stopped resolving would render a card with a blank name and a
    dead log button — the same silent failure ``STAPLE_EXERCISE_IDS`` is checked
    against, and worth the same import-time error.

    The attribution check is the one that matters most. An **[experimental]**
    routine puts a real person's name on a session they did not write, so it may
    not ship without saying whose training it approximates and where that came
    from. A tag with nothing behind it is worse than no tag.
    """
    routines = ALL_ROUTINES if routines is None else routines
    keys = [routine.key for routine in routines]
    if len(set(keys)) != len(keys):
        raise RoutineError(f"Duplicate routine keys: {keys}.")

    for routine in routines:
        if not routine.exercises:
            raise RoutineError(f"Routine {routine.key!r} has no exercises.")

        if routine.experimental and not (routine.inspired_by and routine.source):
            raise RoutineError(
                f"Routine {routine.key!r} is experimental but names no athlete or no "
                "source. A reconstruction of someone's training must say whose it is "
                "and where the reporting came from."
            )
        if routine.inspired_by and not routine.experimental:
            raise RoutineError(
                f"Routine {routine.key!r} is attributed to {routine.inspired_by!r} but "
                "is not tagged experimental. Anything reconstructed from coverage of a "
                "real person's training must carry the tag."
            )

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
    """Every routine, in display order — ours first, then the reconstructions."""
    return list(ALL_ROUTINES)


def get_routine(key: str) -> Routine | None:
    """Return the routine with ``key``, or ``None`` if there is none."""
    return ROUTINES_BY_KEY.get(key)
