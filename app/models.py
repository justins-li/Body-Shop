"""Data access layer for workout entries.

Every SQL statement in the project lives here so routes and services stay free
of database details.  Queries are SQLAlchemy Core, which is what lets the same
code run on SQLite and Postgres: the dialect decides ``lastrowid`` versus
``RETURNING``, and ``entry_date`` is a real ``DATE`` column rather than a string
the caller has to format.

Dates cross this boundary as :class:`datetime.date` objects and leave it as
ISO-8601 strings, in :meth:`WorkoutEntry.to_dict` and :func:`sets_by_date`. The
backend performs no time-zone conversion anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import sqlalchemy as sa

from .db import get_db
from .exercises import get_exercise
from .tables import workout_entry


class ValidationError(ValueError):
    """Raised when user supplied entry data is not acceptable."""


@dataclass(frozen=True)
class WorkoutEntry:
    """One logged movement: N sets of an exercise on a given day."""

    id: int
    entry_date: date
    exercise_id: str
    sets: int

    @property
    def exercise_name(self) -> str:
        exercise = get_exercise(self.exercise_id)
        return exercise.name if exercise else self.exercise_id

    @property
    def muscles(self) -> tuple[str, ...]:
        exercise = get_exercise(self.exercise_id)
        return exercise.muscles if exercise else ()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.entry_date.isoformat(),
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise_name,
            "muscles": list(self.muscles),
            "sets": self.sets,
        }


def _row_to_entry(row) -> WorkoutEntry:
    return WorkoutEntry(
        id=row.id,
        entry_date=row.entry_date,
        exercise_id=row.exercise_id,
        sets=row.sets,
    )


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


def validate_entry(entry_date, exercise_id, sets) -> tuple[date, str, int]:
    """Validate raw user input and return normalised values."""
    parsed_date = parse_date(entry_date)

    if not exercise_id or get_exercise(str(exercise_id)) is None:
        raise ValidationError(f"Unknown exercise: {exercise_id!r}.")

    try:
        parsed_sets = int(sets)
    except (TypeError, ValueError) as exc:
        raise ValidationError("'sets' must be a whole number.") from exc
    if parsed_sets < 1:
        raise ValidationError("'sets' must be at least 1.")
    if parsed_sets > 100:
        raise ValidationError("'sets' must be 100 or fewer.")

    return parsed_date, str(exercise_id), parsed_sets


def add_entry(entry_date, exercise_id: str, sets: int) -> WorkoutEntry:
    """Insert a workout entry after validating it. Returns the stored row."""
    parsed_date, parsed_exercise, parsed_sets = validate_entry(
        entry_date, exercise_id, sets
    )
    db = get_db()
    result = db.execute(
        sa.insert(workout_entry).values(
            entry_date=parsed_date,
            exercise_id=parsed_exercise,
            sets=parsed_sets,
        )
    )
    db.commit()
    return WorkoutEntry(
        # The dialect supplies this from lastrowid on SQLite and RETURNING on
        # Postgres; Core papers over the difference.
        id=int(result.inserted_primary_key[0]),
        entry_date=parsed_date,
        exercise_id=parsed_exercise,
        sets=parsed_sets,
    )


def get_entry(entry_id: int) -> WorkoutEntry | None:
    """Return a single entry by id, or ``None``."""
    row = (
        get_db()
        .execute(sa.select(workout_entry).where(workout_entry.c.id == entry_id))
        .first()
    )
    return _row_to_entry(row) if row else None


def list_entries(start: date | None = None, end: date | None = None) -> list[WorkoutEntry]:
    """Return entries within the inclusive ``start``–``end`` range."""
    query = sa.select(workout_entry)
    if start is not None:
        query = query.where(workout_entry.c.entry_date >= start)
    if end is not None:
        query = query.where(workout_entry.c.entry_date <= end)
    query = query.order_by(
        workout_entry.c.entry_date.desc(), workout_entry.c.id.desc()
    )

    rows = get_db().execute(query).all()
    return [_row_to_entry(row) for row in rows]


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


def sets_by_date(start: date, end: date) -> dict[str, int]:
    """Return ``{iso_date: total_sets}`` for the inclusive range (calendar dots)."""
    total = sa.func.sum(workout_entry.c.sets).label("total")
    rows = (
        get_db()
        .execute(
            sa.select(workout_entry.c.entry_date, total)
            .where(workout_entry.c.entry_date.between(start, end))
            .group_by(workout_entry.c.entry_date)
        )
        .all()
    )
    return {row.entry_date.isoformat(): int(row.total) for row in rows}
