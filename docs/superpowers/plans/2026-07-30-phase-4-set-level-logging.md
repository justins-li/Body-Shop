# Phase 4 — Set-Level Logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `workout_entry.sets` (a flat integer) with a `workout_set` child table carrying weight, reps, RPE and set type per set, and rebuild `/log` around a set grid.

**Architecture:** `workout_entry` stays the parent; `workout_set` is a child with `ON DELETE CASCADE` and a UUID primary key. `WorkoutEntry.sets` becomes a derived **property** counting non-warm-up child rows, which is what leaves `app/services/summary.py` untouched and the weekly summary payload byte-identical. Reads use one batched second query, never N+1.

**Tech Stack:** Flask 3, SQLAlchemy 2.0 Core (no ORM), Alembic, pytest, vanilla ES modules, Tailwind v4 + daisyUI (CSS-only build step).

**Spec:** [docs/superpowers/specs/2026-07-30-phase-4-set-level-logging-design.md](../specs/2026-07-30-phase-4-set-level-logging-design.md) — read it before starting. It records *why* each decision was made and which roadmap open decisions it closes.

## Global Constraints

- **Branch:** all work lands on `phase-4-set-level-logging`. Do not commit to `main`.
- **Never add attribution trailers** to commits — no `Co-Authored-By:`, no "Generated with".
- **Commit messages:** present tense; subject says what changed, body says why.
- **SQL lives only in `app/models.py`.** Services and routes never call `get_db()`.
- **Queries are SQLAlchemy Core expressions, not strings** — that is what serves both dialects.
- **A metadata change needs an Alembic revision in the same commit.** `tests/test_migrations.py::test_migrations_match_the_metadata` compares them with Alembic's own autogenerate diff.
- **CHECK constraint names in migrations are bare tokens** (`reps_in_range`), because the `ck` convention contains `%(constraint_name)s` and prefixes them. **UNIQUE constraints are the opposite** — the `uq` convention has no such token, so leave `UniqueConstraint` **unnamed** and let the convention produce `uq_workout_set_entry_id`. (Verified against SQLAlchemy 2.0.43.)
- **Weight is kilograms at rest, always.** Conversion happens only in `app/static/js/ui.js`.
- **Dates:** ISO-8601 strings at the API boundary, `datetime.date` inside `models.py`. No time-zone conversion anywhere in the backend. In JS parse with `new Date(y, m - 1, d)`, never `new Date(iso)`.
- **JS has zero dependencies and no bundler.** Keep it that way.
- **`app/static/css/styles.css` is build output.** Never hand-edit it; edit `input.css` and rebuild.
- **Every class the JS toggles must be hand-written** in `input.css`'s `@layer components`. Tailwind's scanner reads literal text only, so an interpolated class name is purged silently.
- **Product voice:** never print a range as advice. No "aim for 10–20 sets". Say "balanced"/"covered"/"in range", never "optimal"/"maximal". No medical or injury claims.
- **Run `pytest` before every commit.** CI only runs `pytest -q`, so a green local run is the whole signal.

---

## File Structure

| File | Status | Responsibility |
| --- | --- | --- |
| `app/tables.py` | Modify | Add `workout_set`; drop `workout_entry.sets` and its check |
| `migrations/versions/0004_set_level_logging.py` | Create | Create, backfill, drop — branching by dialect |
| `app/models.py` | Modify | `WorkoutSet`/`WorkoutEntry` shapes, per-set validation, batched reads |
| `app/api.py` | Modify | Array `sets` on POST, `set_count` on GET, new `last-sets` endpoint |
| `app/static/js/api.js` | Modify | `createEntry` sends an array; add `fetchLastSets` |
| `app/static/js/ui.js` | Modify | `toKg`/`fromKg`/`formatWeight`; render sets in `renderEntries` |
| `app/static/js/log.js` | Modify | The set grid replaces the stepper |
| `app/static/js/timer.js` | Create | Rest timer — pure client-side, no API |
| `app/static/js/plates.js` | Create | Plate calculator — a pure function |
| `app/templates/log.html` | Modify | Set-grid markup, units toggle, timer and plate shells |
| `app/static/css/input.css` | Modify | `.set-row`, `.rest-timer`, `.plate-hint` and their state classes |
| `app/static/css/styles.css` | Rebuild | Build output — regenerated, never edited |
| `tests/conftest.py` | Modify | `add` fixture takes a set list |
| `tests/test_models.py` | Modify | Direct-insert helper writes child rows |
| `tests/test_summary.py` | Modify | `entry()` helper builds `set_rows` |
| `tests/test_api.py` | Modify | New payload shape; new endpoint and validation tests |
| `tests/test_migrations.py` | Modify | Pin the 0003 test; add 0004 coverage |
| `tests/test_pages.py` | Modify | Set-grid markers replace the stepper's |
| `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `CLAUDE.md` | Modify | Same-commit doc updates |

---

## Task 1: Schema, migration and data layer

Schema and data layer move together on purpose: `app/models.py` reads `workout_entry.c.sets` in four places, so changing the metadata alone leaves the suite red. **The suite is red in the middle of this task and green at its end.** That is expected; do not stop early.

**Files:**
- Modify: `app/tables.py:40-67`
- Create: `migrations/versions/0004_set_level_logging.py`
- Modify: `app/models.py` (whole file)
- Modify: `tests/conftest.py:52-56,74-85`
- Modify: `tests/test_models.py:21-29`
- Modify: `tests/test_summary.py:29`
- Modify: `tests/test_migrations.py:66-76,138-186`

**Interfaces:**
- Consumes: nothing (first task).
- Produces:
  - `app.tables.workout_set` — the `sa.Table`.
  - `app.models.WorkoutSet(id: str, set_index: int, weight: float | None, reps: int | None, rpe: float | None, set_type: str)` with `.to_dict() -> dict`.
  - `app.models.WorkoutEntry(id: int, entry_date: date, exercise_id: str, set_rows: tuple[WorkoutSet, ...])` with `.sets -> int` (property, warm-ups excluded), `.exercise_name`, `.muscles`, `.to_dict()`.
  - `app.models.add_entry(entry_date, exercise_id: str, sets: list[dict]) -> WorkoutEntry`
  - `app.models.validate_entry(entry_date, exercise_id) -> tuple[date, str]` — **note the changed arity**, it no longer takes or returns sets.
  - `app.models.validate_sets(raw_sets) -> list[dict]`
  - `app.models.last_sets_for_exercise(exercise_id: str) -> tuple[date | None, list[WorkoutSet]]`
  - `app.models.SET_TYPES: tuple[str, ...]`, `MAX_SETS_PER_ENTRY: int`, `MAX_REPS: int`
  - Unchanged signatures: `get_entry`, `list_entries`, `delete_entry`, `sets_by_date`, `recent_exercise_usage`, `recent_exercise_ids`, `parse_date`.

- [ ] **Step 1: Add `workout_set` to the metadata and drop the `sets` column**

In `app/tables.py`, delete the `sets` column and the `sets_positive` check from `workout_entry`, then append the new table. Note the docstring on `weight` — the kilogram rule has to be discoverable from the schema, not only from the spec.

```python
#: The sets that make up one entry — the unit weight, reps and RPE attach to.
#:
#: ``workout_entry.sets`` used to be an integer column here. It is now derived:
#: ``WorkoutEntry.sets`` counts these rows, excluding warm-ups. A denormalised
#: cache was considered and rejected — a cache that can disagree with its source
#: is the bug this app's single-source-of-truth design exists to avoid.
#:
#: The primary key is a UUID rather than an autoincrement integer so Phase 10's
#: offline queue can mint ids on the client without a migration. It is generated
#: server-side today; accepting a client-supplied one later is an API change.
workout_set = sa.Table(
    "workout_set",
    metadata,
    sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column(
        "entry_id",
        sa.Integer,
        sa.ForeignKey("workout_entry.id", ondelete="CASCADE"),
        nullable=False,
    ),
    #: 1-based position within the entry. Assigned by the server from submission
    #: order, so it can never arrive with a gap.
    sa.Column("set_index", sa.Integer, nullable=False),
    #: **Kilograms, always.** NULL means the weight was not recorded — which is
    #: what revision 0004 backfills, and what a blank grid row saves as.
    sa.Column("weight", sa.Float),
    sa.Column("reps", sa.Integer),
    sa.Column("rpe", sa.Float),
    #: warmup is excluded from volume; the other three all count.
    sa.Column("set_type", sa.Text, nullable=False, server_default=sa.text("'normal'")),
    sa.CheckConstraint("set_index > 0", name="set_index_positive"),
    sa.CheckConstraint("weight IS NULL OR weight >= 0", name="weight_non_negative"),
    sa.CheckConstraint("reps IS NULL OR (reps > 0 AND reps <= 1000)", name="reps_in_range"),
    sa.CheckConstraint("rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="rpe_in_range"),
    sa.CheckConstraint(
        "set_type IN ('normal', 'warmup', 'drop', 'failure')", name="set_type_known"
    ),
    # Unnamed on purpose: the `uq` convention has no %(constraint_name)s token,
    # so an explicit name would be used verbatim instead of being prefixed.
    sa.UniqueConstraint("entry_id", "set_index"),
    sa.Index("idx_workout_set_entry", "entry_id"),
)
```

Also update the `workout_entry` docstring: it currently says "N sets of an exercise on a given day". Change to "One logged movement on a given day; its sets live in ``workout_set``."

- [ ] **Step 2: Write revision 0004**

Create `migrations/versions/0004_set_level_logging.py`. The DDL below is **verified output** from `metadata.create_all` on both dialects — do not retype it from memory.

```python
"""Replace workout_entry.sets with per-set rows

Phase 4. ``workout_entry.sets`` was a flat count: three sets at 60kg and three
at 140kg were the same row. Sets become child rows carrying weight, reps, RPE
and a type, and the parent's count becomes derived.

**The dialects need a different order of operations, and this is not
cosmetic.** Postgres drops a column in place, so the safe order holds: create
the child table, backfill it, drop the column. SQLite cannot drop a column
without rebuilding the table, and ``app/db.py`` turns foreign keys on for every
connection — so ``DROP TABLE workout_entry`` with child rows already pointing at
it is a foreign-key violation. On SQLite the parent is therefore rebuilt
*first*, while no child rows exist yet.

The rebuild is hand-written rather than ``batch_alter_table`` for the reason
revision 0003 documents: ``SQLiteImpl.cast_for_batch_migrate`` inserts a CAST
when type affinity changes, and ``CAST('2026-07-28' AS DATE)`` prefix-parses to
the integer 2026. ``workout_entry`` still carries the DATE and DATETIME columns
that trap applies to.

The backfill runs in Python because it has to mint UUIDs, which no portable SQL
expression can do. It writes NULL weight and reps: an existing row knows a set
count and nothing else, and inventing weights would make the history lie.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-30

"""

from __future__ import annotations

from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | None = None
depends_on: str | None = None

#: A frozen local handle, not an import from app/tables.py. A migration must not
#: import a definition a later commit can change, or it does different things
#: depending on when it runs — the same rule revision 0002 follows for the
#: retired-id mapping.
_workout_set = sa.table(
    "workout_set",
    sa.column("id"),
    sa.column("entry_id"),
    sa.column("set_index"),
    sa.column("weight"),
    sa.column("reps"),
    sa.column("rpe"),
    sa.column("set_type"),
)

#: Spelled out to match what metadata.create_all() emits, so the migrated schema
#: and app/tables.py stay byte-comparable. The plain SELECT is the point — no
#: CAST, so the date and timestamp bytes survive untouched.
_SQLITE_ENTRY_TABLE = """
    CREATE TABLE workout_entry_migrated (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        entry_date DATE NOT NULL,
        exercise_id TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
    )
"""


def _create_workout_set() -> None:
    """Create the child table. Identical DDL on both dialects."""
    op.create_table(
        "workout_set",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("entry_id", sa.Integer(), nullable=False),
        sa.Column("set_index", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("reps", sa.Integer(), nullable=True),
        sa.Column("rpe", sa.Float(), nullable=True),
        sa.Column(
            "set_type", sa.Text(), server_default=sa.text("'normal'"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["entry_id"], ["workout_entry.id"], ondelete="CASCADE"),
        sa.CheckConstraint("set_index > 0", name="set_index_positive"),
        sa.CheckConstraint("weight IS NULL OR weight >= 0", name="weight_non_negative"),
        sa.CheckConstraint(
            "reps IS NULL OR (reps > 0 AND reps <= 1000)", name="reps_in_range"
        ),
        sa.CheckConstraint("rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="rpe_in_range"),
        sa.CheckConstraint(
            "set_type IN ('normal', 'warmup', 'drop', 'failure')", name="set_type_known"
        ),
        sa.UniqueConstraint("entry_id", "set_index"),
    )
    op.create_index("idx_workout_set_entry", "workout_set", ["entry_id"])


def _backfill(counts: list[tuple[int, int]]) -> None:
    """Write one set row per counted set, with nothing but its position known.

    ``uuid4().hex`` goes in unhyphenated, which is exactly the stored form on
    SQLite (CHAR(32)) and a form Postgres accepts for a ``uuid`` literal. The
    frozen table carries no types, so nothing rewrites it on the way in — do
    not "fix" this by giving ``_workout_set`` a ``sa.Uuid`` column, which would
    reintroduce the import-a-changeable-definition problem for no gain.
    """
    rows = [
        {
            "id": uuid4().hex,
            "entry_id": entry_id,
            "set_index": index,
            "weight": None,
            "reps": None,
            "rpe": None,
            "set_type": "normal",
        }
        for entry_id, count in counts
        for index in range(1, count + 1)
    ]
    if rows:
        op.get_bind().execute(sa.insert(_workout_set), rows)


def _read_counts() -> list[tuple[int, int]]:
    rows = op.get_bind().execute(sa.text("SELECT id, sets FROM workout_entry")).all()
    return [(int(row.id), int(row.sets)) for row in rows]


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        # Read first, rebuild second, create third: the parent cannot be dropped
        # once workout_set holds rows referencing it.
        counts = _read_counts()
        op.execute(_SQLITE_ENTRY_TABLE)
        op.execute(
            "INSERT INTO workout_entry_migrated "
            "(id, entry_date, exercise_id, created_at) "
            "SELECT id, entry_date, exercise_id, created_at FROM workout_entry"
        )
        op.execute("DROP TABLE workout_entry")
        op.execute("ALTER TABLE workout_entry_migrated RENAME TO workout_entry")
        op.execute("CREATE INDEX idx_workout_entry_date ON workout_entry (entry_date)")
        _create_workout_set()
        _backfill(counts)
        return

    _create_workout_set()
    _backfill(_read_counts())
    # Postgres drops a CHECK that depends solely on the dropped column, so
    # ck_workout_entry_sets_positive needs no separate drop_constraint.
    op.drop_column("workout_entry", "sets")


def downgrade() -> None:
    """Restore the flat count.

    **Lossy, unavoidably**: weight, reps, RPE and set type have nowhere to go in
    a single integer, and are discarded. The count restored is the non-warm-up
    count, which is what the column meant.
    """
    counts = dict(
        op.get_bind()
        .execute(
            sa.text(
                "SELECT entry_id, COUNT(*) AS total FROM workout_set "
                "WHERE set_type <> 'warmup' GROUP BY entry_id"
            )
        )
        .all()
    )

    if op.get_bind().dialect.name == "sqlite":
        op.execute("DROP TABLE workout_set")
        op.execute(
            """
            CREATE TABLE workout_entry_restored (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                entry_date DATE NOT NULL,
                exercise_id TEXT NOT NULL,
                sets INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
                CONSTRAINT ck_workout_entry_sets_positive CHECK (sets > 0)
            )
            """
        )
        op.execute(
            "INSERT INTO workout_entry_restored "
            "(id, entry_date, exercise_id, sets, created_at) "
            "SELECT id, entry_date, exercise_id, 1, created_at FROM workout_entry"
        )
        op.execute("DROP TABLE workout_entry")
        op.execute("ALTER TABLE workout_entry_restored RENAME TO workout_entry")
        op.execute("CREATE INDEX idx_workout_entry_date ON workout_entry (entry_date)")
    else:
        op.add_column(
            "workout_entry",
            sa.Column("sets", sa.Integer(), nullable=False, server_default="1"),
        )
        op.create_check_constraint("sets_positive", "workout_entry", "sets > 0")
        op.alter_column("workout_entry", "sets", server_default=None)
        op.drop_index("idx_workout_set_entry", table_name="workout_set")
        op.drop_table("workout_set")

    bind = op.get_bind()
    for entry_id, total in counts.items():
        # The check forbids 0, so an all-warm-up entry restores as 1 set. There
        # is no honest integer for "some sets, none of them counting".
        bind.execute(
            sa.text("UPDATE workout_entry SET sets = :total WHERE id = :id"),
            {"total": max(1, int(total)), "id": int(entry_id)},
        )
```

- [ ] **Step 3: Run the metadata/migration agreement test — it must pass**

Run: `pytest tests/test_migrations.py::test_migrations_match_the_metadata -v`
Expected: **PASS**. A failure prints exactly what Alembic still wants to apply; fix the revision until the diff is empty. Do not proceed past this step with a non-empty diff — everything downstream assumes the two agree.

- [ ] **Step 4: Rewrite `app/models.py`**

Replace the file's dataclasses, validation and queries. Keep the module docstring's existing paragraphs about dialects and dates, and add a paragraph about the parent/child split.

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

import sqlalchemy as sa

from .db import get_db
from .exercises import get_exercise
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

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": self.entry_date.isoformat(),
            "exercise_id": self.exercise_id,
            "exercise_name": self.exercise_name,
            "muscles": list(self.muscles),
            # Named so no client reads it as len(sets): warm-ups are in `sets`
            # but not in this count.
            "set_count": self.sets,
            "sets": [row.to_dict() for row in self.set_rows],
        }
```

Then validation. `validate_entry` **loses its sets argument**:

```python
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
```

Then the queries:

```python
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


def add_entry(entry_date, exercise_id: str, sets) -> WorkoutEntry:
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
```

`delete_entry`, `recent_exercise_usage` and `recent_exercise_ids` are **unchanged** — copy them across verbatim. `delete_entry` needs no cascade handling: the FK does it, and `app/db.py:35-39` already sets `PRAGMA foreign_keys = ON` per SQLite connection.

- [ ] **Step 5: Update the test fixtures and helpers**

`tests/conftest.py` — the `add` fixture takes a set list, with an integer accepted **in the fixture only**:

```python
@pytest.fixture
def add(client):
    """POST an entry and return the raw response.

    ``sets`` may be a list of set dicts, or an integer as shorthand for that
    many sets with nothing recorded. The shorthand is **test scaffolding only**
    — the API itself takes the array and nothing else — and it exists so the
    many tests that only care about a count stay readable.
    """

    def _add(date: str, exercise_id: str, sets):
        if isinstance(sets, int):
            sets = [{} for _ in range(sets)]
        return client.post(
            "/api/entries",
            json={"date": date, "exercise_id": exercise_id, "sets": sets},
        )

    return _add
```

And the Postgres truncation must name both tables:

```python
connection.execute(
    sa.text(
        "TRUNCATE TABLE workout_set, workout_entry RESTART IDENTITY CASCADE"
    )
)
```

`tests/test_models.py` — the direct-insert helper writes child rows:

```python
from uuid import uuid4

from app.tables import workout_entry, workout_set


def log_entry(exercise_id: str, sets: int = 3, day: str = "2026-07-28") -> None:
    """Insert directly, bypassing the API and its validation."""
    db = get_db()
    result = db.execute(
        sa.insert(workout_entry).values(
            entry_date=date.fromisoformat(day), exercise_id=exercise_id
        )
    )
    entry_id = int(result.inserted_primary_key[0])
    db.execute(
        sa.insert(workout_set),
        [
            {
                "id": uuid4().hex,
                "entry_id": entry_id,
                "set_index": index,
                "weight": None,
                "reps": None,
                "rpe": None,
                "set_type": "normal",
            }
            for index in range(1, sets + 1)
        ],
    )
    db.commit()
```

`tests/test_summary.py:29` — the `entry()` helper builds `set_rows`, because `sets` is now a property and cannot be passed to the constructor:

```python
from app.models import WorkoutEntry, WorkoutSet


def entry(exercise_id: str, sets: int, day: str = "2026-07-28") -> WorkoutEntry:
    """A detached entry with `sets` plain working sets — no database involved."""
    return WorkoutEntry(
        id=1,
        entry_date=date.fromisoformat(day),
        exercise_id=exercise_id,
        set_rows=tuple(
            WorkoutSet(
                id=f"set-{index}", set_index=index, weight=None, reps=None,
                rpe=None, set_type="normal",
            )
            for index in range(1, sets + 1)
        ),
    )
```

- [ ] **Step 6: Fix the two migration tests the new revision invalidates**

In `tests/test_migrations.py`:

`test_revision_0003_keeps_the_sets_check_constraint` migrates to `head` and asserts `sets=0` is rejected. At head the column is gone, so **pin it to 0003** and insert with raw SQL rather than the metadata (which no longer has the column):

```python
def test_revision_0003_keeps_the_sets_check_constraint(migrated):
    """SQLite cannot reflect CHECK constraints, so a batch rebuild can drop one.

    Pinned to 0003 rather than head: revision 0004 removes the column, and the
    point of this test is that 0003 did not silently lose the constraint on its
    way past.
    """
    application, to = migrated
    engine = to("0003")

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                    "VALUES ('2026-07-28', 'Barbell_Squat', 0)"
                )
            )
```

`test_the_chain_downgrades_to_base` inserts with `sets=3` through the metadata. At head that column is gone; insert the parent alone:

```python
def test_the_chain_downgrades_to_base(migrated):
    """Every revision's downgrade runs, so a bad deploy can be backed out."""
    application, to = migrated
    engine = to("head")
    with engine.begin() as connection:
        connection.execute(
            sa.insert(workout_entry).values(
                entry_date=date(2026, 7, 28), exercise_id="Barbell_Squat"
            )
        )

    downgrade_db("base", app=application)

    inspector = sa.inspect(engine)
    assert not inspector.has_table("workout_entry")
    assert not inspector.has_table("workout_set")
```

- [ ] **Step 7: Write the new migration tests**

Append to `tests/test_migrations.py`:

```python
def test_revision_0004_backfills_one_set_per_counted_set(migrated):
    """Existing history keeps its count and gains no invented weights."""
    application, to = migrated
    engine = to("0003")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-28', 'Barbell_Squat', 4)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-27', 'Pullups', 2)"
            )
        )

    to("0004")

    with engine.connect() as connection:
        rows = connection.execute(
            sa.select(workout_set).order_by(
                workout_set.c.entry_id, workout_set.c.set_index
            )
        ).all()

    assert len(rows) == 6
    by_entry: dict[int, list] = {}
    for row in rows:
        by_entry.setdefault(row.entry_id, []).append(row)
    assert sorted(len(v) for v in by_entry.values()) == [2, 4]

    for sets in by_entry.values():
        # 1-based and contiguous.
        assert [r.set_index for r in sets] == list(range(1, len(sets) + 1))
        # Do not invent weights: an old row knew a count and nothing else.
        assert all(r.weight is None and r.reps is None and r.rpe is None for r in sets)
        assert all(r.set_type == "normal" for r in sets)


def test_revision_0004_gives_every_set_a_distinct_uuid(migrated):
    """Ids are UUIDs so Phase 10's offline queue can mint them client-side."""
    from uuid import UUID

    application, to = migrated
    engine = to("0003")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-28', 'Barbell_Squat', 3)"
            )
        )

    to("0004")

    with engine.connect() as connection:
        ids = connection.execute(sa.select(workout_set.c.id)).scalars().all()

    assert len(set(ids)) == 3
    # Parse rather than compare strings: the type stores 32-char hex and reads
    # back the hyphenated 36-char form.
    assert all(UUID(str(value)) for value in ids)


def test_revision_0004_survives_a_round_trip(migrated):
    """Down and back up again, with the count intact both ways."""
    application, to = migrated
    engine = to("0003")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-28', 'Barbell_Squat', 5)"
            )
        )

    to("0004")
    downgrade_db("0003", app=application)

    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT sets FROM workout_entry")
        ).scalar() == 5

    to("0004")

    with engine.connect() as connection:
        assert connection.execute(
            sa.select(sa.func.count()).select_from(workout_set)
        ).scalar() == 5


def test_revision_0004_preserves_dates_through_the_sqlite_rebuild(migrated):
    """The parent is rebuilt on SQLite, so 0003's CAST trap is back in range."""
    application, to = migrated
    engine = to("0003")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-28', 'Barbell_Squat', 3)"
            )
        )

    to("0004")

    with engine.connect() as connection:
        row = connection.execute(sa.select(workout_entry)).one()
    assert row.entry_date == date(2026, 7, 28)
```

Add `workout_set` to the imports at the top of the file:

```python
from app.tables import metadata, workout_entry, workout_set
```

- [ ] **Step 8: Run the whole suite**

Run: `pytest -q`
Expected: **PASS**, except `tests/test_api.py` failures caused by the API still sending an integer `sets`. Those are Task 2's job. Everything in `test_models.py`, `test_summary.py`, `test_migrations.py`, `test_exercises.py`, `test_weeks.py`, `test_config.py` and `test_pages.py` must pass now.

If `test_summary.py` fails, the derived-property approach has not worked and something in `services/summary.py` needs changing — **stop and re-read the spec** rather than editing `summary.py`, because keeping it untouched is the design's central claim.

- [ ] **Step 9: Commit**

```bash
git add app/tables.py migrations/versions/0004_set_level_logging.py app/models.py \
        tests/conftest.py tests/test_models.py tests/test_summary.py tests/test_migrations.py
git commit -m "Store sets as rows, not a count

workout_entry.sets could not tell three sets at 60kg from three at
140kg, which blocks every feature in Phase 7. Sets become child rows
carrying weight, reps, RPE and a type.

The parent's count is derived rather than cached: WorkoutEntry.sets
counts non-warm-up child rows, so services/summary.py and the weekly
payload are unchanged. Excluding warm-ups is why the count could not
stay a column — it is a property of the rows, not of the entry.

Revision 0004 branches by dialect. Postgres drops the column in place;
SQLite has to rebuild the table, and doing that after the child table
exists would violate the foreign key app/db.py enables, so the parent is
rebuilt before workout_set is created. The rebuild is hand-written for
the reason 0003 documents: batch mode inserts a CAST that destroys
dates.

The backfill writes NULL weights. An existing row knows a set count and
nothing else, and inventing numbers would make the history lie."
```

---

## Task 2: API layer

**Files:**
- Modify: `app/api.py:14-22,93-125`
- Modify: `tests/test_api.py`
- Modify: `docs/API.md`

**Interfaces:**
- Consumes: `add_entry`, `last_sets_for_exercise`, `WorkoutEntry.to_dict`, `ValidationError` from Task 1.
- Produces:
  - `POST /api/entries` accepting `{"date", "exercise_id", "sets": [...]}`
  - `GET /api/entries` returning `set_count` and a `sets` array
  - `GET /api/exercises/<id>/last-sets` returning `{"date": str | null, "sets": [...]}`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`:

```python
def test_entries_carry_their_sets_and_a_count(client, add):
    add("2026-07-28", SQUAT, [
        {"weight": 100, "reps": 5},
        {"weight": 100, "reps": 5},
        {"weight": 105, "reps": 3, "rpe": 8.5, "set_type": "failure"},
    ])

    entry = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]
    assert entry["set_count"] == 3
    assert [s["set_index"] for s in entry["sets"]] == [1, 2, 3]
    assert entry["sets"][0]["weight"] == 100.0
    assert entry["sets"][2]["rpe"] == 8.5
    assert entry["sets"][2]["set_type"] == "failure"


def test_blank_sets_are_stored_as_nulls(client, add):
    """Logging bare sets stays possible — the backfill produces the same shape."""
    add("2026-07-28", SQUAT, [{}, {}])
    entry = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]

    assert entry["set_count"] == 2
    assert all(s["weight"] is None and s["reps"] is None for s in entry["sets"])
    assert all(s["set_type"] == "normal" for s in entry["sets"])


def test_warmup_sets_are_stored_but_excluded_from_the_count(client, add):
    add("2026-07-28", SQUAT, [
        {"weight": 40, "reps": 5, "set_type": "warmup"},
        {"weight": 100, "reps": 5},
        {"weight": 100, "reps": 5},
    ])

    entry = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]
    assert len(entry["sets"]) == 3
    assert entry["set_count"] == 2


def test_warmup_sets_do_not_inflate_the_muscle_map(client, add):
    """The correctness requirement: a warm-up must not shade the body map."""
    add("2026-07-28", BENCH, [{"set_type": "warmup"}] * 4 + [{}] * 2)

    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert summary["muscles"]["chest"]["sets"] == 2.0
    assert summary["total_sets"] == 2


def test_warmup_sets_do_not_inflate_the_calendar(client, add):
    add("2026-07-28", SQUAT, [{"set_type": "warmup"}, {}, {}])
    days = client.get("/api/calendar?year=2026&month=7").get_json()["days"]
    assert days == {"2026-07-28": 2}


def test_an_entry_of_only_warmups_contributes_no_volume(client, add):
    add("2026-07-28", BENCH, [{"set_type": "warmup"}] * 3)

    entry = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]
    assert entry["set_count"] == 0

    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert summary["muscles"]["chest"]["worked"] is False
    assert summary["total_sets"] == 0


def test_set_ids_are_distinct_uuids(client, add):
    from uuid import UUID

    add("2026-07-28", SQUAT, [{}, {}, {}])
    sets = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]["sets"]

    ids = [s["id"] for s in sets]
    assert len(set(ids)) == 3
    # Parse rather than compare: the stored form is hex, the read form hyphenated.
    assert all(UUID(value) for value in ids)


def test_weights_round_trip_in_kilograms(client, add):
    add("2026-07-28", SQUAT, [{"weight": 102.5, "reps": 5}])
    sets = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]["sets"]
    assert sets[0]["weight"] == 102.5


def test_deleting_an_entry_cascades_to_its_sets(client, add, app):
    import sqlalchemy as sa

    from app.db import get_db
    from app.tables import workout_set

    entry_id = add("2026-07-28", SQUAT, [{}, {}, {}]).get_json()["entry"]["id"]
    client.delete(f"/api/entries/{entry_id}")

    with app.app_context():
        remaining = get_db().execute(
            sa.select(sa.func.count()).select_from(workout_set)
        ).scalar()
    assert remaining == 0


@pytest.mark.parametrize(
    "sets",
    [
        3,                                        # the old integer shape
        [],                                       # empty
        "three",                                  # not a list
        [{}] * 101,                               # over the cap
        [{"weight": -1}],                         # negative weight
        [{"reps": 0}],                            # reps below range
        [{"reps": 1001}],                         # reps above range
        [{"rpe": 0.9}],                           # rpe below range
        [{"rpe": 10.5}],                          # rpe above range
        [{"rpe": 8.3}],                           # not a 0.5 step
        [{"set_type": "backoff"}],                # unknown type
        ["not-an-object"],                        # not a dict
    ],
)
def test_invalid_set_payloads_are_rejected(client, sets):
    response = client.post(
        "/api/entries",
        json={"date": "2026-07-28", "exercise_id": SQUAT, "sets": sets},
    )
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_last_sets_returns_the_most_recent_session(client, add):
    add("2026-07-20", SQUAT, [{"weight": 95, "reps": 5}])
    add("2026-07-27", SQUAT, [{"weight": 100, "reps": 5}, {"weight": 100, "reps": 4}])
    add("2026-07-27", BENCH, [{"weight": 60, "reps": 8}])

    data = client.get(f"/api/exercises/{SQUAT}/last-sets").get_json()
    assert data["date"] == "2026-07-27"
    assert [s["weight"] for s in data["sets"]] == [100.0, 100.0]
    assert [s["reps"] for s in data["sets"]] == [5, 4]


def test_last_sets_is_empty_for_an_unlogged_movement(client):
    data = client.get(f"/api/exercises/{PULLUP}/last-sets").get_json()
    assert data == {"date": None, "sets": []}


def test_last_sets_404s_for_an_unknown_exercise(client):
    assert client.get("/api/exercises/not_a_movement/last-sets").status_code == 404
```

Update the two existing tests the new shape breaks:

```python
def test_create_and_list_entry(client, add):
    response = add("2026-07-28", SQUAT, 4)
    assert response.status_code == 201
    entry = response.get_json()["entry"]
    assert entry["set_count"] == 4
    assert entry["exercise_name"] == "Barbell Squat"
    assert entry["muscles"] == ["quads", "back", "calves", "glutes", "hamstrings"]

    listed = client.get("/api/entries?date=2026-07-28").get_json()["entries"]
    assert len(listed) == 1
    assert listed[0]["id"] == entry["id"]
```

And in `test_invalid_entries_are_rejected`, change the three `"sets": 3` values to `"sets": [{}, {}, {}]` so each case still tests the field it means to, and drop the now-duplicated `"sets": 0` and `"sets": "many"` cases (covered by `test_invalid_set_payloads_are_rejected`):

```python
@pytest.mark.parametrize(
    "payload",
    [
        {"date": "not-a-date", "exercise_id": SQUAT, "sets": [{}]},
        {"date": "2026-07-28", "exercise_id": "squat", "sets": [{}]},  # retired id
        {"date": "", "exercise_id": SQUAT, "sets": [{}]},
    ],
)
def test_invalid_entries_are_rejected(client, payload):
    response = client.post("/api/entries", json=payload)
    assert response.status_code == 400
    assert "error" in response.get_json()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_api.py -q`
Expected: FAIL. `last-sets` returns 404 from the catch-all `/exercises/<id>` route (or 405), and `set_count` is missing from entry payloads.

- [ ] **Step 3: Implement the API changes**

In `app/api.py`, extend the import and rewrite `create_entry`:

```python
from .models import (
    ValidationError,
    add_entry,
    delete_entry,
    last_sets_for_exercise,
    list_entries,
    parse_date,
    recent_exercise_usage,
    sets_by_date,
)
```

```python
@bp.post("/entries")
def create_entry():
    """Create a workout entry and its sets from a JSON body.

    ``sets`` is an **array of set objects**, not a count. Three bare sets are
    ``[{}, {}, {}]``. The integer form Phase 3 accepted is gone: there were no
    external consumers before Phase 6 deploys, and this was the last cheap
    moment to make the break.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError("A JSON body is required.")

    entry = add_entry(
        payload.get("date"),
        payload.get("exercise_id"),
        payload.get("sets"),
    )
    return jsonify({"entry": entry.to_dict()}), 201
```

**Note the dropped form-encoding fallback.** `request.form` cannot carry a nested array, so accepting it would mean silently rejecting every form post with a confusing error. JSON is now the only shape, and `log.js` already sends JSON.

Add the new endpoint. It must be declared **before** `/exercises/<exercise_id>` is not a concern — Flask matches on the full rule, so `/exercises/<id>/last-sets` is unambiguous — but keep it next to its sibling for readability:

```python
@bp.get("/exercises/<exercise_id>/last-sets")
def get_last_sets(exercise_id: str):
    """The sets from the most recent session of this movement.

    Backs the ``/log`` grid's prefill. Returns ``{"date": null, "sets": []}``
    when the movement has never been logged, which the page renders as empty
    placeholders rather than an error.
    """
    if get_exercise(exercise_id) is None:
        return jsonify({"error": f"Unknown exercise: {exercise_id!r}."}), 404

    day, sets = last_sets_for_exercise(exercise_id)
    return jsonify(
        {
            "date": day.isoformat() if day else None,
            "sets": [row.to_dict() for row in sets],
        }
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest -q`
Expected: **PASS**, whole suite.

- [ ] **Step 5: Update `docs/API.md`**

Payload examples in this file are **exhaustive, not illustrative** — every field must appear. Make these edits:

1. `GET /api/entries` — replace the example with the `set_count` + `sets` shape from the spec, and add a table row per set field. State that `weight` is kilograms and may be `null`.
2. `POST /api/entries` — replace `{"sets": 4}` with the array example. Update the field table: `sets` is "Required, array of 1–100 set objects". Add a per-set field table: `weight` (optional, kg, ≥ 0), `reps` (optional, 1–1000), `rpe` (optional, 1–10 in 0.5 steps), `set_type` (optional, one of `normal`/`warmup`/`drop`/`failure`, default `normal`). Update the `curl` example. Add a line: **the integer form is no longer accepted**; three bare sets are `[{}, {}, {}]`.
3. Add a `GET /api/exercises/<id>/last-sets` section between `/exercises/<id>` and `/entries`.
4. Under `GET /api/calendar` and `GET /api/summary/week`, note that warm-up sets are excluded from every count.
5. Add a short **Units** note near the top, beside the existing date note: weight is kilograms everywhere in the API; the kg/lb choice is a display preference and never crosses the wire.

- [ ] **Step 6: Commit**

```bash
git add app/api.py tests/test_api.py docs/API.md
git commit -m "Take sets as an array over the API

POST /api/entries took an integer count; it now takes an array of set
objects, and entries come back with their sets plus a set_count that
excludes warm-ups. This is a breaking change made deliberately while
there are no external consumers.

Form encoding is no longer accepted on this endpoint. It cannot carry a
nested array, so keeping it would mean failing every form post with a
confusing message rather than an honest 400.

GET /api/exercises/<id>/last-sets backs the log grid's prefill. It joins
back through workout_entry rather than reading workout_set directly:
once Phase 5 adds user_id, a set query that skips that join is an IDOR."
```

---

## Task 3: Client API and unit conversion

**Files:**
- Modify: `app/static/js/api.js:81-92`
- Modify: `app/static/js/ui.js:39-47,104-137`

**Interfaces:**
- Consumes: the endpoints from Task 2.
- Produces:
  - `api.js`: `createEntry({date, exercise_id, sets})` where `sets` is an array; `fetchLastSets(id) -> Promise<{date, sets}>`
  - `ui.js`: `WEIGHT_UNITS`, `loadUnit() -> "kg"|"lb"`, `saveUnit(unit)`, `toKg(value, unit)`, `fromKg(value, unit)`, `formatWeight(kg, unit) -> string`, `describeSet(set, unit) -> string`

- [ ] **Step 1: Add the client API functions**

In `app/static/js/api.js`, update `createEntry`'s JSDoc and add the new fetch:

```js
/**
 * Create an entry.
 * @param {{date: string, exercise_id: string, sets: Array<object>}} entry
 *   `sets` is an array of `{weight?, reps?, rpe?, set_type?}` — weight in
 *   **kilograms**, which is the only unit that crosses the wire. Three bare
 *   sets are `[{}, {}, {}]`.
 */
export async function createEntry(entry) {
  const data = await request("/entries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  return data.entry;
}

/**
 * The sets from the last session of a movement — what the grid prefills from.
 * @returns {Promise<{date: string|null, sets: Array<object>}>}
 */
export async function fetchLastSets(id) {
  return request(`/exercises/${encodeURIComponent(id)}/last-sets`);
}
```

- [ ] **Step 2: Add the unit helpers to `ui.js`**

Append beside `formatSets`, whose formatting convention these follow:

```js
/**
 * Weight is stored in kilograms and displayed in whichever unit the reader
 * picked. Conversion happens only here, at the UI boundary — the column, the
 * API and every Phase 7 aggregate are kilograms throughout.
 */
export const WEIGHT_UNITS = ["kg", "lb"];

const LB_PER_KG = 2.2046226218;
const UNIT_KEY = "bodyshop:weight-unit";

/** The reader's chosen unit, defaulting to kg. */
export function loadUnit() {
  const stored = localStorage.getItem(UNIT_KEY);
  return WEIGHT_UNITS.includes(stored) ? stored : "kg";
}

export function saveUnit(unit) {
  if (WEIGHT_UNITS.includes(unit)) localStorage.setItem(UNIT_KEY, unit);
}

/** A displayed value in `unit` → kilograms, for sending to the API. */
export function toKg(value, unit) {
  return unit === "lb" ? value / LB_PER_KG : value;
}

/** Kilograms → a value in `unit`, for display. */
export function fromKg(value, unit) {
  return unit === "lb" ? value * LB_PER_KG : value;
}

/**
 * Render a weight for reading: `60`, `62.5`, and `""` when it was not recorded.
 *
 * Rounds to one decimal like `formatSets`, which is also what makes the lb
 * round trip read cleanly — 135 lb stored as 61.23kg comes back as `135`, not
 * `134.99998`.
 */
export function formatWeight(kg, unit = loadUnit()) {
  if (kg === null || kg === undefined) return "";
  const value = Math.round(fromKg(kg, unit) * 10) / 10;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/**
 * One set as a short line: `100kg × 5 @8.5`, degrading as fields are missing.
 * Returns `""` for a set that recorded nothing, so callers can skip it.
 */
export function describeSet(set, unit = loadUnit()) {
  const parts = [];
  if (set.weight !== null && set.weight !== undefined) {
    parts.push(`${formatWeight(set.weight, unit)}${unit}`);
  }
  if (set.reps !== null && set.reps !== undefined) {
    parts.push(parts.length ? `× ${set.reps}` : `${set.reps} reps`);
  }
  if (set.rpe !== null && set.rpe !== undefined) parts.push(`@${set.rpe}`);
  return parts.join(" ");
}
```

- [ ] **Step 3: Show the sets in `renderEntries`**

`renderEntries` at `app/static/js/ui.js:92` currently prints `entry.sets` as a number, which is now an array. Change the count line to read `set_count`, and add a detail line under the muscles when any set recorded something:

```js
    const sets = document.createElement("span");
    sets.className = "entry-sets";
    sets.textContent = `${entry.set_count} ${entry.set_count === 1 ? "set" : "sets"}`;
```

```js
    // A line of "100kg × 5" per set, when there is anything to say. Entries
    // logged as a bare count stay a single line, exactly as before.
    const detail = entry.sets.map((set) => describeSet(set)).filter(Boolean);
    if (detail.length) {
      const performed = document.createElement("div");
      performed.className = "entry-performed";
      performed.textContent = detail.join(" · ");
      main.append(performed);
    }
```

and the delete button's label:

```js
      remove.setAttribute("aria-label", `Delete ${entry.set_count} sets of ${entry.exercise_name}`);
```

- [ ] **Step 4: Verify the pages still load**

Run: `pytest -q`
Expected: PASS (these are JS changes; the page tests assert markup, not behaviour).

Then boot the app and load `/calendar`, which uses `renderEntries`:

```bash
python run.py
```

Open `http://127.0.0.1:5000/calendar`, click a day with entries, and confirm the entry rows render with their set counts and no console errors. Stop the server.

- [ ] **Step 5: Commit**

```bash
git add app/static/js/api.js app/static/js/ui.js
git commit -m "Convert weight at the UI boundary only

Kilograms are canonical in the column and over the wire; the kg/lb
choice is a display preference in localStorage, so switching it re-reads
all history correctly rather than relabelling it.

Rounding to one decimal on display is what makes the pound round trip
readable: 135lb stored as 61.23kg comes back as 135, not 134.99998.

renderEntries reads set_count rather than sets, which is now an array,
and prints what was actually lifted when any set recorded it."
```

---

## Task 4: The set grid on `/log`

**Files:**
- Modify: `app/templates/log.html:93-103`
- Modify: `app/static/js/log.js:451-517`
- Modify: `tests/test_pages.py`

**Interfaces:**
- Consumes: `createEntry`, `fetchLastSets` (Task 3); `loadUnit`, `saveUnit`, `toKg`, `formatWeight` (Task 3).
- Produces: DOM contract for Task 5 — `#set-grid` (the rows' container), `#add-set` (the button), and a `setGridValues()` reading the grid.

- [ ] **Step 1: Write the failing page test**

In `tests/test_pages.py`, replace the stepper assertions with the grid's shell markers:

```python
def test_log_page_renders_a_set_grid_shell(client):
    """Rows are built by log.js; the page ships the container and the controls."""
    body = client.get("/log").data.decode()
    for marker in ('id="set-grid"', 'id="add-set"', 'id="weight-unit"'):
        assert marker in body

    # The old flat-count stepper is gone, not hidden.
    assert 'id="entry-sets"' not in body
    assert 'data-step="-1"' not in body
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_pages.py::test_log_page_renders_a_set_grid_shell -v`
Expected: FAIL — `id="set-grid"` is not in the page.

- [ ] **Step 3: Replace the stepper markup in `log.html`**

Swap the whole `<div>` at lines 93–103 for:

```html
        <div>
          <div class="flex items-baseline justify-between mb-2.5 gap-3">
            <span class="type-label text-secondary">Sets</span>
            <div class="flex items-center gap-1.5">
              <label class="sr-only" for="weight-unit">Weight unit</label>
              <select id="weight-unit" class="select select-sm bg-base-200 border hairline">
                <option value="kg">kg</option>
                <option value="lb">lb</option>
              </select>
            </div>
          </div>

          {#
            One row per set, built by log.js. The header is here rather than in
            JS so the column names survive with no script, and because Tailwind
            only sees classes it can read as literal text in a template.
          #}
          <div class="set-grid-head type-label text-secondary" aria-hidden="true">
            <span>#</span><span>Weight</span><span>Reps</span><span>RPE</span><span>Type</span><span></span>
          </div>
          <div id="set-grid" class="grid gap-1.5"></div>

          <div class="flex flex-wrap items-center gap-2.5 mt-2.5">
            <button type="button" id="add-set"
                    class="btn btn-sm btn-outline rounded-full hairline">Add set</button>
            <p class="picker-note m-0" id="prefill-note" hidden></p>
          </div>
        </div>
```

- [ ] **Step 4: Build the grid in `log.js`**

Extend the imports:

```js
import {
  createEntry, deleteEntry, fetchEntriesForDate, fetchExerciseDetail,
  fetchExercises, fetchLastSets, fetchRecentExercises,
} from "./api.js";
import {
  $, formatDate, formatWeight, loadUnit, renderEntries, retargetLinks,
  saveUnit, syncUrlDate, toKg, toast,
} from "./ui.js";
```

Add module state beside the existing declarations:

```js
/** The reader's display unit. Weight is kilograms everywhere else. */
let unit = loadUnit();

/** Last session's sets for the chosen movement — placeholders, never values. */
let previousSets = [];

const SET_TYPES = ["normal", "warmup", "drop", "failure"];
const SET_TYPE_LABELS = {
  normal: "Working", warmup: "Warm-up", drop: "Drop", failure: "To failure",
};
const MAX_SETS = 100;
```

Replace `initStepper` with the grid:

```js
// ---- The set grid ---------------------------------------------------------

/**
 * Build one row of the grid.
 *
 * `previous` is last session's set at this position, if there was one. It is
 * rendered as a **placeholder, not a value** — visible enough to aim at, absent
 * enough that an untouched row saves as NULL rather than silently re-logging
 * weights nobody lifted today.
 */
function setRow(index, previous) {
  const row = document.createElement("div");
  row.className = "set-row";
  row.dataset.index = String(index);

  const number = document.createElement("span");
  number.className = "set-row-index";
  number.textContent = String(index);

  const weight = document.createElement("input");
  weight.type = "number";
  weight.step = "any";
  weight.min = "0";
  weight.className = "input input-sm bg-base-200 border hairline set-weight tabular-nums";
  weight.setAttribute("aria-label", `Set ${index} weight in ${unit}`);
  if (previous && previous.weight !== null && previous.weight !== undefined) {
    weight.placeholder = formatWeight(previous.weight, unit);
  }

  const reps = document.createElement("input");
  reps.type = "number";
  reps.min = "1";
  reps.max = "1000";
  reps.className = "input input-sm bg-base-200 border hairline set-reps tabular-nums";
  reps.setAttribute("aria-label", `Set ${index} reps`);
  if (previous && previous.reps !== null && previous.reps !== undefined) {
    reps.placeholder = String(previous.reps);
  }

  const rpe = document.createElement("input");
  rpe.type = "number";
  rpe.min = "1";
  rpe.max = "10";
  rpe.step = "0.5";
  rpe.className = "input input-sm bg-base-200 border hairline set-rpe tabular-nums";
  rpe.setAttribute("aria-label", `Set ${index} RPE`);

  const type = document.createElement("select");
  type.className = "select select-sm bg-base-200 border hairline set-type";
  type.setAttribute("aria-label", `Set ${index} type`);
  SET_TYPES.forEach((value) => type.append(new Option(SET_TYPE_LABELS[value], value)));
  if (previous && previous.set_type) type.value = previous.set_type;
  type.addEventListener("change", () => {
    row.classList.toggle("is-warmup", type.value === "warmup");
  });
  row.classList.toggle("is-warmup", type.value === "warmup");

  const remove = document.createElement("button");
  remove.type = "button";
  remove.className = "set-row-remove";
  remove.textContent = "×";
  remove.setAttribute("aria-label", `Remove set ${index}`);
  remove.addEventListener("click", () => {
    row.remove();
    renumberRows();
  });

  row.append(number, weight, reps, rpe, type, remove);
  return row;
}

/** Keep the visible numbering contiguous after a removal. */
function renumberRows() {
  const rows = [...document.querySelectorAll("#set-grid .set-row")];
  rows.forEach((row, position) => {
    const index = position + 1;
    row.dataset.index = String(index);
    row.querySelector(".set-row-index").textContent = String(index);
    row.querySelector(".set-row-remove")
      .setAttribute("aria-label", `Remove set ${index}`);
  });
  // Never leave the grid empty: an entry needs at least one set.
  if (!rows.length) addSetRow();
}

/** Append a row, seeded from last session's set at that position. */
function addSetRow() {
  const grid = $("#set-grid");
  const index = grid.children.length + 1;
  if (index > MAX_SETS) {
    showError(`An entry can hold at most ${MAX_SETS} sets.`);
    return;
  }
  grid.append(setRow(index, previousSets[index - 1]));
}

/** Rebuild the grid from scratch, one row per remembered set (min 1). */
function renderSetGrid() {
  const grid = $("#set-grid");
  grid.textContent = "";
  const count = Math.max(1, Math.min(previousSets.length, MAX_SETS));
  for (let index = 1; index <= count; index += 1) {
    grid.append(setRow(index, previousSets[index - 1]));
  }
}

/**
 * Read the grid into the API's shape.
 *
 * A blank field becomes `null`, not `0` — "not recorded" and "zero" are
 * different facts, and the schema keeps them apart. Weight is converted to
 * kilograms here, which is the only unit the API accepts.
 */
function setGridValues() {
  return [...document.querySelectorAll("#set-grid .set-row")].map((row) => {
    const rawWeight = row.querySelector(".set-weight").value.trim();
    const rawReps = row.querySelector(".set-reps").value.trim();
    const rawRpe = row.querySelector(".set-rpe").value.trim();
    return {
      weight: rawWeight === "" ? null : toKg(Number(rawWeight), unit),
      reps: rawReps === "" ? null : Number(rawReps),
      rpe: rawRpe === "" ? null : Number(rawRpe),
      set_type: row.querySelector(".set-type").value,
    };
  });
}
```

- [ ] **Step 5: Load the prefill on selection and rewrite submit**

Extend `selectExercise` so choosing a movement fetches its last session:

```js
async function selectExercise(id) {
  selectedId = id;
  $("#exercise-id").value = id;
  showError("");

  document.querySelectorAll(".picker-result").forEach((row) => {
    row.setAttribute("aria-pressed", String(row.dataset.id === id));
  });

  await Promise.all([renderChosenFor(id), loadPreviousSets(id)]);
}

/** Render the chosen movement's card, falling back to the light shape. */
async function renderChosenFor(id) {
  try {
    renderChosen(await fetchExerciseDetail(id));
  } catch (err) {
    // The pick still stands; only its illustration failed.
    const exercise = byId.get(id);
    if (exercise) renderChosen({ ...exercise, images: [], instructions: [] });
    toast(err.message, "error");
  }
}

/**
 * Prefill the grid from the last time this movement was logged.
 *
 * A failure here is not worth a toast — the grid still works, it just starts
 * empty — so it degrades to no placeholders rather than an error.
 */
async function loadPreviousSets(id) {
  const note = $("#prefill-note");
  try {
    const data = await fetchLastSets(id);
    previousSets = data.sets || [];
    note.hidden = !data.date;
    if (data.date) {
      note.textContent = `Greyed values are what you did on ${formatDate(data.date, {
        month: "short", day: "numeric",
      })}.`;
    }
  } catch {
    previousSets = [];
    note.hidden = true;
  }
  renderSetGrid();
}
```

Rewrite `onSubmit`:

```js
async function onSubmit(event) {
  event.preventDefault();
  showError("");

  const form = event.currentTarget;
  const data = new FormData(form);
  const sets = setGridValues();

  if (!data.get("date")) return showError("Pick a date first.");
  if (!data.get("exercise_id")) return showError("Choose an exercise.");
  if (!sets.length) return showError("Add at least one set.");

  try {
    const entry = await createEntry({
      date: data.get("date"),
      exercise_id: data.get("exercise_id"),
      sets,
    });
    toast(`Logged ${entry.set_count} × ${entry.exercise_name}.`);
    startRestTimer();
    await Promise.all([refreshDay(), loadRecent(), loadPreviousSets(entry.exercise_id)]);
  } catch (err) {
    showError(err.message);
  }
}
```

`startRestTimer` arrives in Task 5. For now define a no-op beside it so this task stands alone:

```js
/** Replaced by the real timer in the next task. */
function startRestTimer() {}
```

- [ ] **Step 6: Wire the unit toggle and boot the grid**

In `initLog`, replace `initStepper();` with:

```js
  const unitSelect = $("#weight-unit");
  unitSelect.value = unit;
  unitSelect.addEventListener("change", () => {
    unit = unitSelect.value;
    saveUnit(unit);
    // Rebuild so placeholders and aria-labels re-read in the new unit. Typed
    // values are deliberately left alone: they are what the user just entered,
    // and silently converting them under the cursor is worse than a mixed grid.
    renderSetGrid();
  });
  $("#add-set").addEventListener("click", addSetRow);
  renderSetGrid();
```

- [ ] **Step 7: Run the tests**

Run: `pytest -q`
Expected: **PASS**.

- [ ] **Step 8: Verify in the browser**

```bash
python run.py
```

At `http://127.0.0.1:5000/log`: pick a movement, confirm one empty row appears; add rows; enter weight and reps; submit; confirm the toast and the day panel. Log the same movement again and confirm the previous values appear as grey placeholders and that submitting without touching them stores `null` (the day panel shows the count only). Switch kg→lb and confirm placeholders re-read. Stop the server.

- [ ] **Step 9: Commit**

```bash
git add app/templates/log.html app/static/js/log.js tests/test_pages.py
git commit -m "Log sets in a grid, not a stepper

A row per set with weight, reps, RPE and type replaces the flat count.
Blank fields save as NULL rather than 0 — not recorded and zero are
different facts, and the schema keeps them apart — so logging bare sets
is still a two-click path.

Previous values render as placeholders rather than values. Prefilling
real values would mean an untouched row silently re-logs weights nobody
lifted today, which is worse than no prefill at all.

Switching kg/lb rebuilds placeholders but leaves typed values alone.
Converting a number under the cursor is more surprising than a grid that
is briefly mixed."
```

---

## Task 5: Rest timer and plate calculator

Both are pure client-side, need no schema and no endpoint, and are small enough to review together.

**Files:**
- Create: `app/static/js/timer.js`
- Create: `app/static/js/plates.js`
- Modify: `app/templates/log.html`
- Modify: `app/static/js/log.js`

**Interfaces:**
- Consumes: `#set-grid`, `startRestTimer()` stub (Task 4).
- Produces: `initRestTimer(root)`, `startRestTimer()` from `timer.js`; `platesFor(target, bar, unit)` from `plates.js`.

- [ ] **Step 1: Write `plates.js`**

```js
/**
 * Plate calculator — what to load per side to reach a target weight.
 *
 * A pure function of the target, the bar and the unit. No storage, no API, and
 * no opinion about what you should be lifting: it reports what makes the number
 * you already typed.
 */

/** Plates a normal gym actually stocks, heaviest first, per unit. */
const PLATES = {
  kg: [25, 20, 15, 10, 5, 2.5, 1.25],
  lb: [45, 35, 25, 10, 5, 2.5],
};

/** The bar most racks have, in each unit. */
export const DEFAULT_BAR = { kg: 20, lb: 45 };

/**
 * Plates for **one side** of the bar.
 *
 * @param {number} target - Total weight, in `unit`.
 * @param {number} bar - Bar weight, in `unit`.
 * @param {"kg"|"lb"} unit
 * @returns {{plates: number[], remainder: number}} `remainder` is what the
 *   stocked plates cannot make — non-zero for, say, 61kg on a 20kg bar. It is
 *   reported rather than rounded away, because rounding would quietly claim a
 *   loadout that does not exist.
 */
export function platesFor(target, bar, unit) {
  const perSide = (target - bar) / 2;
  if (!Number.isFinite(perSide) || perSide <= 0) return { plates: [], remainder: 0 };

  const plates = [];
  let left = perSide;
  for (const plate of PLATES[unit] || PLATES.kg) {
    while (left >= plate - 1e-9) {
      plates.push(plate);
      left -= plate;
    }
  }
  // Two decimal places: float subtraction leaves 1e-15 dust otherwise.
  return { plates, remainder: Math.round(left * 100) / 100 };
}

/**
 * The same thing as a line to read: `20 + 25/20/1.25 per side`.
 * Returns `""` when the bar alone is the answer or the target is unreachable.
 */
export function describePlates(target, bar, unit) {
  const { plates, remainder } = platesFor(target, bar, unit);
  if (!plates.length) return "";
  const line = `${bar}${unit} bar + ${plates.join(" / ")} per side`;
  return remainder > 0 ? `${line} (${remainder}${unit} short)` : line;
}
```

- [ ] **Step 2: Write `timer.js`**

```js
/**
 * Rest timer — counts down after a set is saved.
 *
 * Entirely client-side: no schema, no endpoint, and no notification. Phase 10
 * moves the alert to a watch, where you can see it without unlocking a phone;
 * this is the logic that phase will reuse.
 *
 * The timer is a convenience, never a prescription. It counts the rest you
 * chose — it does not tell you how long to rest.
 */

const DURATIONS = [60, 90, 120, 180];
const DEFAULT_SECONDS = 120;
const KEY = "bodyshop:rest-seconds";

let handle = null;
let remaining = 0;
let elements = null;

function chosenSeconds() {
  const stored = Number(localStorage.getItem(KEY));
  return DURATIONS.includes(stored) ? stored : DEFAULT_SECONDS;
}

function format(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function paint() {
  elements.readout.textContent = format(Math.max(0, remaining));
  elements.root.classList.toggle("is-running", handle !== null);
}

function stop() {
  if (handle !== null) clearInterval(handle);
  handle = null;
  paint();
}

function tick() {
  remaining -= 1;
  if (remaining <= 0) {
    remaining = 0;
    stop();
  }
  paint();
}

/** Start (or restart) the countdown from the chosen duration. */
export function startRestTimer() {
  if (!elements) return;
  if (handle !== null) clearInterval(handle);
  remaining = chosenSeconds();
  handle = setInterval(tick, 1000);
  paint();
}

/**
 * Wire the timer's controls.
 * @param {HTMLElement} root - The `.rest-timer` container.
 */
export function initRestTimer(root) {
  if (!root) return;
  elements = {
    root,
    readout: root.querySelector("[data-timer-readout]"),
    select: root.querySelector("[data-timer-duration]"),
    toggle: root.querySelector("[data-timer-toggle]"),
  };

  elements.select.value = String(chosenSeconds());
  elements.select.addEventListener("change", () => {
    localStorage.setItem(KEY, elements.select.value);
    if (handle === null) {
      remaining = chosenSeconds();
      paint();
    }
  });
  elements.toggle.addEventListener("click", () => {
    if (handle !== null) stop();
    else startRestTimer();
  });

  remaining = chosenSeconds();
  paint();
}
```

- [ ] **Step 3: Add the markup**

In `log.html`, insert after the `#add-set` block's closing `</div>` and before the `#form-error` paragraph:

```html
        <div class="rest-timer flex flex-wrap items-center gap-2.5" id="rest-timer">
          <span class="type-label text-secondary">Rest</span>
          <span class="rest-timer-readout tabular-nums" data-timer-readout>2:00</span>
          <label class="sr-only" for="rest-duration">Rest length</label>
          <select id="rest-duration" data-timer-duration
                  class="select select-sm bg-base-200 border hairline">
            <option value="60">1:00</option>
            <option value="90">1:30</option>
            <option value="120">2:00</option>
            <option value="180">3:00</option>
          </select>
          <button type="button" data-timer-toggle
                  class="btn btn-sm btn-outline rounded-full hairline">Start / stop</button>
        </div>
```

- [ ] **Step 4: Wire both into `log.js`**

Replace the `startRestTimer` stub with the real import, and add the plate hint. Extend the imports:

```js
import { describePlates, DEFAULT_BAR } from "./plates.js";
import { initRestTimer, startRestTimer } from "./timer.js";
```

Delete the stub function. In `setRow`, after `weight` is created, add the hint wiring:

```js
  const hint = document.createElement("span");
  hint.className = "plate-hint";
  const updateHint = () => {
    const value = Number(weight.value);
    hint.textContent = weight.value.trim() === ""
      ? ""
      : describePlates(value, DEFAULT_BAR[unit], unit);
  };
  weight.addEventListener("input", updateHint);
```

and append it to the row (it spans the full width beneath the inputs — see the CSS in Task 6):

```js
  row.append(number, weight, reps, rpe, type, remove, hint);
```

In `initLog`, add beside the other wiring:

```js
  initRestTimer($("#rest-timer"));
```

- [ ] **Step 5: Add a page test for both shells**

In `tests/test_pages.py`:

```python
def test_log_page_ships_the_rest_timer_shell(client):
    """The timer is client-side; the page only provides its controls."""
    body = client.get("/log").data.decode()
    for marker in ('id="rest-timer"', "data-timer-readout", "data-timer-toggle"):
        assert marker in body
```

- [ ] **Step 6: Run the tests**

Run: `pytest -q`
Expected: **PASS**.

- [ ] **Step 7: Verify in the browser**

```bash
python run.py
```

At `/log`: type `100` into a weight field with kg selected and confirm the hint reads `20kg bar + 25 / 15 per side`. Type `61` and confirm it reports being short. Submit an entry and confirm the timer starts counting down; press Start / stop and confirm it halts. Stop the server.

- [ ] **Step 8: Commit**

```bash
git add app/static/js/timer.js app/static/js/plates.js \
        app/templates/log.html app/static/js/log.js tests/test_pages.py
git commit -m "Add the rest timer and plate calculator

Both are pure client-side and cost nothing now the set data exists: the
timer starts on save and counts the rest you chose, and the plate hint
is a function of the weight already typed.

The plate calculator reports what it cannot make rather than rounding.
Claiming a loadout the gym does not stock is worse than saying 1kg
short.

Neither prescribes anything. The timer counts a chosen rest, it does not
recommend one."
```

---

## Task 6: Stylesheet

**Files:**
- Modify: `app/static/css/input.css` (inside `@layer components`, which starts at line 224)
- Rebuild: `app/static/css/styles.css`

- [ ] **Step 1: Fetch the toolchain**

```bash
python tools/fetch_css_toolchain.py
```

This downloads the pinned Tailwind CLI binary and the daisyUI tarball into gitignored `tools/`. **It needs network access.** If it fails, stop and report it — do not hand-edit `styles.css`, which is build output and is overwritten by the next build.

- [ ] **Step 2: Add the component styles**

Append inside `@layer components` in `app/static/css/input.css`. Use theme colours only — never a raw hex — so both themes stay correct.

```css
  /* ---- The set grid on /log ------------------------------------------- */

  /* Six columns: index, weight, reps, RPE, type, remove. The plate hint is a
     seventh child that spans the row beneath them. */
  .set-grid-head,
  .set-row {
    display: grid;
    grid-template-columns: 1.75rem minmax(0, 1.3fr) minmax(0, 1fr) minmax(0, 1fr) minmax(0, 1.2fr) 1.75rem;
    gap: 0.375rem;
    align-items: center;
  }

  .set-grid-head {
    padding-inline: 0.125rem;
    margin-bottom: 0.375rem;
  }

  .set-row {
    /* The hint wraps onto its own line without disturbing the columns. */
    grid-auto-flow: row;
  }

  .set-row-index {
    font-variant-numeric: tabular-nums;
    color: var(--color-base-content);
    opacity: 0.55;
    text-align: center;
    font-size: 0.8125rem;
  }

  /* A warm-up is logged but does not count toward the week, so it reads as
     quieter rather than as an error. */
  .set-row.is-warmup .set-weight,
  .set-row.is-warmup .set-reps,
  .set-row.is-warmup .set-rpe {
    opacity: 0.6;
  }

  .set-row-remove {
    border: 0;
    background: none;
    cursor: pointer;
    line-height: 1;
    font-size: 1.125rem;
    color: var(--color-base-content);
    opacity: 0.4;
    transition: opacity 0.15s ease;
  }

  .set-row-remove:hover,
  .set-row-remove:focus-visible {
    opacity: 1;
  }

  .plate-hint {
    grid-column: 2 / -1;
    font-size: 0.75rem;
    color: var(--color-base-content);
    opacity: 0.6;
    font-variant-numeric: tabular-nums;
  }

  .plate-hint:empty {
    display: none;
  }

  /* ---- Rest timer ------------------------------------------------------ */

  .rest-timer-readout {
    font-size: 1.25rem;
    font-weight: 600;
    color: var(--color-base-content);
    opacity: 0.45;
    transition: opacity 0.2s ease;
  }

  /* `.is-running` is toggled from timer.js, so it is hand-written here —
     Tailwind's scanner reads literal text only and would purge a class it
     never sees in a template. */
  .rest-timer.is-running .rest-timer-readout {
    opacity: 1;
  }

  /* ---- Sets on an entry row -------------------------------------------- */

  .entry-performed {
    font-size: 0.75rem;
    color: var(--color-base-content);
    opacity: 0.6;
    font-variant-numeric: tabular-nums;
    margin-top: 0.125rem;
  }
```

- [ ] **Step 3: Rebuild the stylesheet**

```bash
tools/tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --minify
```

- [ ] **Step 4: Confirm the new classes survived the build**

```bash
grep -c "set-row-index\|plate-hint\|rest-timer-readout\|entry-performed" app/static/css/styles.css
```

Expected: a non-zero count. A zero means a class was purged — check it appears as literal text in a template or in `input.css` itself.

- [ ] **Step 5: Verify visually, in both themes**

```bash
python run.py
```

Load `/log` and check the grid aligns, a warm-up row dims, the plate hint sits under the inputs, and the timer readout brightens while running. Then switch your OS to dark mode and confirm the same. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add app/static/css/input.css app/static/css/styles.css
git commit -m "Style the set grid, timer and plate hint

Every class the JS toggles is hand-written here rather than composed
from utilities: Tailwind's scanner reads literal text, so is-running and
is-warmup would be purged silently if they were built in JS.

Colours come from the theme tokens, so the achromatic palette holds and
the volume ramp stays the only saturated thing in the app.

A warm-up row reads as quieter rather than as an error. It is logged and
valid; it just does not count toward the week."
```

---

## Task 7: Documentation

The read-before-edit protocol makes these part of the change, not a follow-up.

**Files:**
- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/ROADMAP.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update `docs/ARCHITECTURE.md`**

Read it first, then:

1. **Layer-ownership table** — add `app/static/js/timer.js` and `app/static/js/plates.js` as page-level modules with no API access.
2. **Data model section** — replace the single-table description with the parent/child split. State that `sets` is derived and excludes warm-ups, that weight is kilograms, and that set ids are UUIDs (with the Phase 10 reason).
3. **Volume-scale section** — note that a set's contribution is unchanged, but the count feeding it now comes from child rows.
4. Anywhere the doc says the app has "one append-only table", correct it to two.

- [ ] **Step 2: Update `docs/ROADMAP.md`**

1. Change the "Current state" paragraph (lines 12–16) to include Phase 4.
2. Mark Phase 4's heading **✅ *done*** and add a "What shipped, and where it diverged from this plan" section in the style Phases 1–3 use. Record the four divergences honestly:
   - The `weight` column needed a **unit decision the plan never made**; kilograms canonical, with a display preference.
   - **`POST /api/entries` also dropped form encoding**, which the plan did not mention. A nested array cannot be form-encoded.
   - The **migration's operation order inverts on SQLite**, because the FK the plan's own Phase 10 section relies on makes dropping the parent illegal once children exist.
   - **UUIDs do not round-trip as strings** — SQLAlchemy stores 32-char hex and returns the hyphenated 36-char form.
3. Update the dependency graph: Phase 4 is done, so Phase 7 is unblocked.
4. **Open decisions:** mark 8 answered (parent/child survives, with the reasoning). Mark the `workout_set` half of decision 2 answered (UUIDs), leaving the mobile-route question open. Add a new open decision for the kg/lb preference's home once Phase 5 has a user table.
5. Summary table (line 1045): mark row 4 ✅.

- [ ] **Step 3: Update `CLAUDE.md`**

**Replace stale invariants, do not append to them** — the file's own rule is that a stale CLAUDE.md is worse than a short one.

1. **Delete** the sentence "The schema is unaffected — `sets` is still an integer column; only the aggregate is fractional" from the weighted-sets bullet, and replace with a note that the count comes from child rows.
2. **Replace** "**One append-only table** (`workout_entry`), no `user_id`, no auth" with a bullet describing the two tables and the cascade.
3. **Add** these invariants:
   - `WorkoutEntry.sets` is derived, not stored, and **excludes warm-ups** — a warm-up is logged but must never reach the muscle map.
   - **Weight is kilograms at rest and over the wire.** kg/lb is a display preference in `localStorage`; conversion happens only in `ui.js`.
   - **Set ids are UUIDs**, server-generated, so Phase 10's offline queue is an API change rather than a migration. They do **not** round-trip as strings: stored as 32-char hex, returned hyphenated.
   - **CHECK constraint names are bare tokens; UNIQUE constraints are left unnamed.** The `ck` convention contains `%(constraint_name)s` and prefixes what it is given; the `uq` convention does not, so an explicit name is used verbatim.
   - **`POST /api/entries` takes a `sets` array and JSON only.** Form encoding cannot carry it.
4. In the **Read-before-edit protocol** table, the roadmap row lists Phase 4 as upcoming work — update the examples so they still make sense.
5. Update the Architecture paragraph's phase list: Phases 1, 2, 3 and 4 are done.

- [ ] **Step 4: Verify the docs match the code**

Run: `pytest -q`
Expected: **PASS** — docs do not affect tests, but this is the last gate before the branch is done.

Then re-read `docs/API.md` against `app/api.py` one endpoint at a time. A doc that contradicts the code is a bug.

- [ ] **Step 5: Commit**

```bash
git add docs/ARCHITECTURE.md docs/ROADMAP.md CLAUDE.md
git commit -m "Record what Phase 4 changed and what it invalidated

Four invariants in CLAUDE.md were true before this phase and are false
now, so they are replaced rather than appended to: sets is no longer a
column, the app no longer has one table, weight has a unit, and set ids
are not integers.

The roadmap keeps the divergences rather than the plan. The unit
decision was missing from the spec entirely, form encoding had to go,
the migration's order inverts on SQLite, and UUIDs do not round-trip as
strings — all four are things the next session would otherwise
rediscover."
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
| --- | --- |
| Decision 8 — parent/child | 1 |
| Decision 2 — UUID set ids | 1 (schema), 2 (test) |
| Weight units — kg canonical | 1 (column doc), 3 (conversion), 4 (toggle) |
| `workout_set` schema, all five checks | 1 |
| `workout_entry` loses `sets` | 1 |
| Migration 0004, dialect branch, Python backfill, lossy downgrade | 1 |
| Read path A — batched second query | 1 |
| `WorkoutEntry.sets` as a property | 1 |
| `validate_sets` bounds | 1 (impl), 2 (tests) |
| `sets_by_date` joins and excludes warm-ups | 1 (impl), 2 (test) |
| `last_sets_for_exercise` joins through the parent | 1 |
| `POST /api/entries` array-only | 2 |
| `GET /api/entries` `sets` + `set_count` | 2 |
| `GET /api/exercises/<id>/last-sets` | 2 |
| Set grid, placeholders not values | 4 |
| Units toggle | 4 |
| Rest timer | 5 |
| Plate calculator | 5 |
| Hand-written state classes | 6 |
| `add` fixture, all new test cases | 1, 2 |
| Existing test fixes (0003 pin, `entry()` helper) | 1 |
| API.md, ARCHITECTURE.md, ROADMAP.md, CLAUDE.md | 2, 7 |
| VOLUME_SCIENCE.md unchanged | — (correctly no task) |

**Placeholder scan:** no "TBD", no "add appropriate error handling", no "similar to Task N". Every code step carries real code. Task 7's steps are prose because they are prose edits, and each names the specific line or section to change.

**Type consistency:** `WorkoutSet` fields are identical in `models.py` (Task 1), `to_dict` (Task 1), the API examples (Task 2) and `describeSet` (Task 3). `set_count` is used consistently in `to_dict`, `renderEntries`, `onSubmit`'s toast and every test. `startRestTimer()` is stubbed in Task 4 and replaced by the real import in Task 5 — deliberate, and called out in both places. `platesFor`/`describePlates`/`DEFAULT_BAR` are defined in Task 5 and used only there. `validate_entry`'s **arity change** (no longer takes `sets`) is flagged in Task 1's Interfaces block, and its only caller is `add_entry` in the same file.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-30-phase-4-set-level-logging.md`.
