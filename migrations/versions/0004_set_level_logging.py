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
