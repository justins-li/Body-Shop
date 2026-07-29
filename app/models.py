"""Data access layer for workout entries.

Every SQL statement in the project lives here so routes and services stay free
of database details.  Dates are stored and returned as ISO-8601 strings
(``YYYY-MM-DD``) to keep the JSON API and the SQLite column format identical.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .db import get_db
from .exercises import get_exercise


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
        id=row["id"],
        entry_date=date.fromisoformat(row["entry_date"]),
        exercise_id=row["exercise_id"],
        sets=row["sets"],
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
    cursor = db.execute(
        "INSERT INTO workout_entry (entry_date, exercise_id, sets) VALUES (?, ?, ?)",
        (parsed_date.isoformat(), parsed_exercise, parsed_sets),
    )
    db.commit()
    return WorkoutEntry(
        id=int(cursor.lastrowid),
        entry_date=parsed_date,
        exercise_id=parsed_exercise,
        sets=parsed_sets,
    )


def get_entry(entry_id: int) -> WorkoutEntry | None:
    """Return a single entry by id, or ``None``."""
    row = get_db().execute(
        "SELECT * FROM workout_entry WHERE id = ?", (entry_id,)
    ).fetchone()
    return _row_to_entry(row) if row else None


def list_entries(start: date | None = None, end: date | None = None) -> list[WorkoutEntry]:
    """Return entries within the inclusive ``start``–``end`` range."""
    sql = "SELECT * FROM workout_entry"
    params: list[str] = []
    clauses: list[str] = []
    if start is not None:
        clauses.append("entry_date >= ?")
        params.append(start.isoformat())
    if end is not None:
        clauses.append("entry_date <= ?")
        params.append(end.isoformat())
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY entry_date DESC, id DESC"

    rows = get_db().execute(sql, params).fetchall()
    return [_row_to_entry(row) for row in rows]


def delete_entry(entry_id: int) -> bool:
    """Delete an entry. Returns ``True`` if a row was removed."""
    db = get_db()
    cursor = db.execute("DELETE FROM workout_entry WHERE id = ?", (entry_id,))
    db.commit()
    return cursor.rowcount > 0


def recent_exercise_ids(limit: int = 12) -> list[str]:
    """Return recently-logged exercise ids, most recently used first.

    Backs the picker's default view on ``/log``. Ordering is recency of last
    use, with total uses breaking ties, which is what makes the 10–20 movements
    someone actually cycles through surface without a search.
    """
    rows = get_db().execute(
        """
        SELECT exercise_id, MAX(entry_date) AS last_used, COUNT(*) AS uses
        FROM workout_entry
        GROUP BY exercise_id
        ORDER BY last_used DESC, uses DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row["exercise_id"] for row in rows]


def remap_exercise_ids(mapping: dict[str, str]) -> dict[str, int]:
    """Rewrite ``old_id -> new_id`` across every entry. Returns rows moved.

    Used once, by ``flask --app app remap-exercises``, to carry history across
    the Phase 2 catalog swap. Safe to run twice: ids already migrated simply
    match nothing.
    """
    db = get_db()
    moved: dict[str, int] = {}
    for old_id, new_id in mapping.items():
        cursor = db.execute(
            "UPDATE workout_entry SET exercise_id = ? WHERE exercise_id = ?",
            (new_id, old_id),
        )
        if cursor.rowcount:
            moved[old_id] = cursor.rowcount
    db.commit()
    return moved


def sets_by_date(start: date, end: date) -> dict[str, int]:
    """Return ``{iso_date: total_sets}`` for the inclusive range (calendar dots)."""
    rows = get_db().execute(
        """
        SELECT entry_date, SUM(sets) AS total
        FROM workout_entry
        WHERE entry_date BETWEEN ? AND ?
        GROUP BY entry_date
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    return {row["entry_date"]: int(row["total"]) for row in rows}
