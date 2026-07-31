"""Data access layer for workout entries.

Every SQL statement in the project lives here so routes and services stay free
of database details.  Queries are SQLAlchemy Core, which is what lets the same
code run on SQLite and Postgres: the dialect decides ``lastrowid`` versus
``RETURNING``, and ``entry_date`` is a real ``DATE`` column rather than a string
the caller has to format.

Dates cross this boundary as :class:`datetime.date` objects and leave it as
ISO-8601 strings, in :meth:`WorkoutEntry.to_dict` and :func:`sets_by_date`. The
backend performs no time-zone conversion anywhere.

Phase 4 split the flat ``workout_entry.sets`` count into a ``workout_set``
child table: an entry is the parent row (date, exercise), and each set — its
weight, reps, RPE and type — lives in its own child row. ``WorkoutEntry.sets``
is derived from those rows rather than stored, so it can never disagree with
them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

import sqlalchemy as sa

from .db import get_db
from .exercises import DEFAULT_WEIGHT_MODE, get_exercise
from .tables import workout_entry, workout_set

#: The four set types. Only ``warmup`` is excluded from weekly volume.
SET_TYPES = ("normal", "warmup", "drop", "failure")
MAX_SETS_PER_ENTRY = 100
MAX_REPS = 1000


class ValidationError(ValueError):
    """Raised when user supplied entry data is not acceptable."""


@dataclass(frozen=True)
class WorkoutSet:
    """One set: what was lifted, how many times, and how hard it felt."""

    id: str
    set_index: int
    weight: float | None   # kilograms; None when not recorded
    reps: int | None
    rpe: float | None
    set_type: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "set_index": self.set_index,
            "weight": self.weight,
            "reps": self.reps,
            "rpe": self.rpe,
            "set_type": self.set_type,
        }


@dataclass(frozen=True)
class WorkoutEntry:
    """One logged movement on a given day, plus the sets that made it up."""

    id: int
    entry_date: date
    exercise_id: str
    set_rows: tuple[WorkoutSet, ...] = ()

    @property
    def sets(self) -> int:
        """Sets counting toward weekly volume — warm-ups excluded.

        Derived rather than stored, which is what keeps ``services/summary.py``
        unchanged across Phase 4: it still reads ``entry.sets`` as an int.

        Excluding warm-ups is a correctness requirement, not a nicety. Counting
        them would inflate the muscle map the moment anyone logged properly, and
        the volume ramp would start overstating the week.
        """
        return sum(1 for row in self.set_rows if row.set_type != "warmup")

    @property
    def exercise_name(self) -> str:
        exercise = get_exercise(self.exercise_id)
        return exercise.name if exercise else self.exercise_id

    @property
    def muscles(self) -> tuple[str, ...]:
        exercise = get_exercise(self.exercise_id)
        return exercise.muscles if exercise else ()

    @property
    def weight_mode(self) -> str:
        """How this movement's weights should be read back — Phase 6.5.

        Carried on the entry so a rendered set line does not need the catalog:
        ``+20kg × 8`` for a weighted pull-up and ``20kg × 8`` for a curl are the
        same stored number meaning different things, and every surface that
        lists entries has to say which.
        """
        exercise = get_exercise(self.exercise_id)
        return exercise.weight_mode if exercise else DEFAULT_WEIGHT_MODE

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.entry_date.isoformat(),
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise_name,
            "muscles": list(self.muscles),
            "weight_mode": self.weight_mode,
            # Named so no client reads it as len(sets): warm-ups are in `sets`
            # but not in this count.
            "set_count": self.sets,
            "sets": [row.to_dict() for row in self.set_rows],
        }


def parse_date(value: str | date | None, *, field: str = "date") -> date:
    """Coerce ``value`` to a :class:`datetime.date` or raise ValidationError."""
    if isinstance(value, date):
        return value
    if not value:
        raise ValidationError(f"'{field}' is required.")
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValidationError(
            f"'{field}' must be an ISO date such as 2026-07-28."
        ) from exc


def validate_entry(entry_date, exercise_id) -> tuple[date, str]:
    """Validate the entry's own fields. Sets are validated separately."""
    parsed_date = parse_date(entry_date)
    if not exercise_id or get_exercise(str(exercise_id)) is None:
        raise ValidationError(f"Unknown exercise: {exercise_id!r}.")
    return parsed_date, str(exercise_id)


def _weight(raw, index: int) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Set {index}: 'weight' must be a number.") from exc
    if value < 0:
        raise ValidationError(f"Set {index}: 'weight' cannot be negative.")
    return value


def _reps(raw, index: int) -> int | None:
    if raw is None or raw == "":
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Set {index}: 'reps' must be a whole number.") from exc
    if not 1 <= value <= MAX_REPS:
        raise ValidationError(f"Set {index}: 'reps' must be between 1 and {MAX_REPS}.")
    return value


def _rpe(raw, index: int) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"Set {index}: 'rpe' must be a number.") from exc
    if not 1.0 <= value <= 10.0:
        raise ValidationError(f"Set {index}: 'rpe' must be between 1 and 10.")
    # RPE is recorded in half points — 7, 7.5, 8. Anything finer is false
    # precision about a subjective reading, so it is rejected rather than
    # rounded, which would silently change what the user said.
    if (value * 2) % 1 != 0:
        raise ValidationError(f"Set {index}: 'rpe' must be in steps of 0.5.")
    return value


def _set_type(raw, index: int) -> str:
    if raw is None or raw == "":
        return "normal"
    value = str(raw)
    if value not in SET_TYPES:
        raise ValidationError(
            f"Set {index}: 'set_type' must be one of {', '.join(SET_TYPES)}."
        )
    return value


def validate_sets(raw_sets) -> list[dict]:
    """Validate the ``sets`` array and return rows ready to insert.

    ``set_index`` is assigned here from submission order rather than read from
    the payload, so it cannot arrive duplicated or with a gap.
    """
    if not isinstance(raw_sets, list):
        raise ValidationError("'sets' must be a list of sets.")
    if not raw_sets:
        raise ValidationError("'sets' must contain at least one set.")
    if len(raw_sets) > MAX_SETS_PER_ENTRY:
        raise ValidationError(
            f"'sets' must contain {MAX_SETS_PER_ENTRY} sets or fewer."
        )

    rows = []
    for index, raw in enumerate(raw_sets, start=1):
        if not isinstance(raw, dict):
            raise ValidationError(f"Set {index} must be an object.")
        rows.append(
            {
                "set_index": index,
                "weight": _weight(raw.get("weight"), index),
                "reps": _reps(raw.get("reps"), index),
                "rpe": _rpe(raw.get("rpe"), index),
                "set_type": _set_type(raw.get("set_type"), index),
            }
        )
    return rows


def _rows_to_sets(rows) -> dict[int, list[WorkoutSet]]:
    grouped: dict[int, list[WorkoutSet]] = {}
    for row in rows:
        grouped.setdefault(row.entry_id, []).append(
            WorkoutSet(
                # SQLAlchemy's Uuid returns the hyphenated form of the hex it
                # stored, so this is a 36-character string. str() rather than a
                # cast because Postgres hands back a UUID-like object.
                id=str(row.id),
                set_index=row.set_index,
                weight=row.weight,
                reps=row.reps,
                rpe=row.rpe,
                set_type=row.set_type,
            )
        )
    return grouped


def _sets_for(entry_ids: list[int]) -> dict[int, list[WorkoutSet]]:
    """Fetch every set for the given entries in **one** query.

    One batched query rather than one per entry: the day panel renders every
    entry's sets, and a per-entry fetch would be an N+1 the moment anyone logs
    a full session.
    """
    if not entry_ids:
        return {}
    rows = (
        get_db()
        .execute(
            sa.select(workout_set)
            .where(workout_set.c.entry_id.in_(entry_ids))
            .order_by(workout_set.c.entry_id, workout_set.c.set_index)
        )
        .all()
    )
    return _rows_to_sets(rows)


def _entries_from(rows) -> list[WorkoutEntry]:
    by_entry = _sets_for([row.id for row in rows])
    return [
        WorkoutEntry(
            id=row.id,
            entry_date=row.entry_date,
            exercise_id=row.exercise_id,
            set_rows=tuple(by_entry.get(row.id, ())),
        )
        for row in rows
    ]


def add_entry(entry_date, exercise_id: str, sets: list[dict]) -> WorkoutEntry:
    """Insert an entry and its sets after validating both."""
    parsed_date, parsed_exercise = validate_entry(entry_date, exercise_id)
    rows = validate_sets(sets)

    db = get_db()
    result = db.execute(
        sa.insert(workout_entry).values(
            entry_date=parsed_date, exercise_id=parsed_exercise
        )
    )
    # The dialect supplies this from lastrowid on SQLite and RETURNING on
    # Postgres; Core papers over the difference.
    entry_id = int(result.inserted_primary_key[0])
    db.execute(
        sa.insert(workout_set),
        [{"id": uuid4().hex, "entry_id": entry_id, **row} for row in rows],
    )
    db.commit()

    # Re-read rather than rebuilding in Python, so the returned ids are in the
    # same canonical form every other read produces.
    stored = get_entry(entry_id)
    if stored is None:  # pragma: no cover - the insert just succeeded
        raise ValidationError("Entry could not be stored.")
    return stored


def get_entry(entry_id: int) -> WorkoutEntry | None:
    """Return a single entry with its sets, or ``None``."""
    rows = (
        get_db()
        .execute(sa.select(workout_entry).where(workout_entry.c.id == entry_id))
        .all()
    )
    entries = _entries_from(rows)
    return entries[0] if entries else None


def list_entries(start: date | None = None, end: date | None = None) -> list[WorkoutEntry]:
    """Return entries within the inclusive ``start``–``end`` range, with sets."""
    query = sa.select(workout_entry)
    if start is not None:
        query = query.where(workout_entry.c.entry_date >= start)
    if end is not None:
        query = query.where(workout_entry.c.entry_date <= end)
    query = query.order_by(
        workout_entry.c.entry_date.desc(), workout_entry.c.id.desc()
    )
    return _entries_from(get_db().execute(query).all())


def delete_entry(entry_id: int) -> bool:
    """Delete an entry. Returns ``True`` if a row was removed."""
    db = get_db()
    result = db.execute(
        sa.delete(workout_entry).where(workout_entry.c.id == entry_id)
    )
    db.commit()
    return result.rowcount > 0


def recent_exercise_usage(limit: int = 12) -> list[tuple[str, int]]:
    """Return ``(exercise_id, times logged)`` pairs, most recently used first.

    Backs the picker's default view on ``/log``. Ordering is recency of last
    use, with total uses breaking ties, which is what makes the 10–20 movements
    someone actually cycles through surface without a search.

    The count comes back with the id because the picker ranks *every* list by
    it: a movement you have logged twelve times belongs above a movement the
    curated staple order merely thinks is popular.
    """
    last_used = sa.func.max(workout_entry.c.entry_date).label("last_used")
    uses = sa.func.count().label("uses")
    rows = (
        get_db()
        .execute(
            sa.select(workout_entry.c.exercise_id, last_used, uses)
            .group_by(workout_entry.c.exercise_id)
            .order_by(last_used.desc(), uses.desc())
            .limit(limit)
        )
        .all()
    )
    return [(row.exercise_id, int(row.uses)) for row in rows]


def recent_exercise_ids(limit: int = 12) -> list[str]:
    """Return recently-logged exercise ids, most recently used first."""
    return [exercise_id for exercise_id, _uses in recent_exercise_usage(limit)]


def last_sets_for_exercise(exercise_id: str) -> tuple[date | None, list[WorkoutSet]]:
    """The most recent entry's sets for ``exercise_id`` — the /log prefill.

    **Joins back through ``workout_entry`` rather than reading ``workout_set``
    directly.** That costs nothing today and is mandatory from Phase 5: once
    entries carry a ``user_id``, a set query that skips this join is the same
    IDOR as an unguarded ``delete_entry``, wearing a different hat.
    """
    row = (
        get_db()
        .execute(
            sa.select(workout_entry.c.id, workout_entry.c.entry_date)
            .where(workout_entry.c.exercise_id == exercise_id)
            .order_by(
                workout_entry.c.entry_date.desc(), workout_entry.c.id.desc()
            )
            .limit(1)
        )
        .first()
    )
    if row is None:
        return None, []
    return row.entry_date, _sets_for([row.id]).get(row.id, [])


def _counted_sessions(start: date, end: date):
    """Distinct ``(entry_date, exercise_id)`` pairs that carry real volume.

    The building block both graph queries share, and the reason they cannot
    disagree: an entry of nothing but warm-ups is excluded here once, so it can
    neither become a node nor pull an edge toward a node that does not exist.
    """
    return (
        sa.select(workout_entry.c.entry_date, workout_entry.c.exercise_id)
        .select_from(
            workout_entry.join(
                workout_set, workout_set.c.entry_id == workout_entry.c.id
            )
        )
        .where(
            workout_entry.c.entry_date.between(start, end),
            workout_set.c.set_type != "warmup",
        )
        .distinct()
        .subquery()
    )


def exercise_activity(start: date, end: date) -> list[tuple[str, int, int, date]]:
    """Return ``(exercise_id, sets, sessions, last_logged)`` over a date range.

    Backs the nodes of the training graph on ``/progress``. Warm-ups are
    excluded exactly as they are everywhere else, so a movement logged only as
    a warm-up does not appear at all.
    """
    sets_logged = sa.func.count(workout_set.c.id).label("sets")
    sessions = sa.func.count(sa.distinct(workout_entry.c.entry_date)).label("sessions")
    last_logged = sa.func.max(workout_entry.c.entry_date).label("last_logged")

    rows = (
        get_db()
        .execute(
            sa.select(
                workout_entry.c.exercise_id, sets_logged, sessions, last_logged
            )
            .select_from(
                workout_entry.join(
                    workout_set, workout_set.c.entry_id == workout_entry.c.id
                )
            )
            .where(
                workout_entry.c.entry_date.between(start, end),
                workout_set.c.set_type != "warmup",
            )
            .group_by(workout_entry.c.exercise_id)
            .order_by(sets_logged.desc(), workout_entry.c.exercise_id)
        )
        .all()
    )
    return [
        (row.exercise_id, int(row.sets), int(row.sessions), row.last_logged)
        for row in rows
    ]


def exercise_co_occurrence(start: date, end: date) -> list[tuple[str, str, int]]:
    """Return ``(a, b, days)`` for movements logged on the same day.

    The graph's edges. A self-join on ``entry_date`` over the distinct
    ``(date, exercise)`` pairs above; ``a < b`` keeps each unordered pair once
    and drops the self-pair, so the result is an undirected edge list with no
    duplicates and no loops.
    """
    left = _counted_sessions(start, end).alias("a")
    right = _counted_sessions(start, end).alias("b")
    days = sa.func.count().label("days")

    rows = (
        get_db()
        .execute(
            sa.select(left.c.exercise_id, right.c.exercise_id, days)
            .select_from(
                left.join(right, left.c.entry_date == right.c.entry_date)
            )
            .where(left.c.exercise_id < right.c.exercise_id)
            .group_by(left.c.exercise_id, right.c.exercise_id)
            .order_by(days.desc())
        )
        .all()
    )
    return [(row[0], row[1], int(row.days)) for row in rows]


def loaded_sets(start: date, end: date) -> list[tuple[str, float, int, date]]:
    """Return ``(exercise_id, weight, reps, entry_date)`` for every scored set.

    Backs the personal bests on ``/progress``. Only rows carrying **both** a
    weight and a rep count come back, since a set missing either cannot support
    a one-rep-max estimate — that filter is here because it is a statement about
    the columns being NULL, not a training judgement. Which of the surviving
    sets is worth an estimate is :mod:`app.services.strength`'s call.

    Warm-ups are excluded, the same rule as everywhere else: a warm-up single is
    not a personal best, and it would routinely outrank real work on movements
    where the warm-up is the heaviest thing logged.

    Ordered so the reduction downstream is deterministic on either dialect.
    """
    rows = (
        get_db()
        .execute(
            sa.select(
                workout_entry.c.exercise_id,
                workout_set.c.weight,
                workout_set.c.reps,
                workout_entry.c.entry_date,
            )
            .select_from(
                workout_entry.join(
                    workout_set, workout_set.c.entry_id == workout_entry.c.id
                )
            )
            .where(
                workout_entry.c.entry_date.between(start, end),
                workout_set.c.set_type != "warmup",
                workout_set.c.weight.is_not(None),
                workout_set.c.reps.is_not(None),
            )
            .order_by(workout_entry.c.entry_date, workout_entry.c.id)
        )
        .all()
    )
    return [
        (row.exercise_id, float(row.weight), int(row.reps), row.entry_date)
        for row in rows
    ]


def sets_by_date(start: date, end: date) -> dict[str, int]:
    """Return ``{iso_date: total_sets}`` for the inclusive range (calendar dots).

    Counts child rows rather than summing a column, and excludes warm-ups for
    the same reason ``WorkoutEntry.sets`` does. Days whose entries are all
    warm-ups drop out, which reads the same as a day with nothing logged — the
    endpoint omits empty days either way.
    """
    total = sa.func.count(workout_set.c.id).label("total")
    rows = (
        get_db()
        .execute(
            sa.select(workout_entry.c.entry_date, total)
            .select_from(
                workout_entry.join(
                    workout_set, workout_set.c.entry_id == workout_entry.c.id
                )
            )
            .where(
                workout_entry.c.entry_date.between(start, end),
                workout_set.c.set_type != "warmup",
            )
            .group_by(workout_entry.c.entry_date)
        )
        .all()
    )
    return {row.entry_date.isoformat(): int(row.total) for row in rows}
