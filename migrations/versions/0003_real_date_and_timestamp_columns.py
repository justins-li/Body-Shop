"""Give entry_date and created_at real date types

Both started as TEXT, which was defensible while SQLite was the only backend:
ISO-8601 sorts lexicographically, so ``BETWEEN`` on a string was already a correct
chronological comparison. On Postgres it is just a string, with no date semantics
and no way for the planner to know better.

Nothing about the app's date handling changes. SQLite still stores
``'YYYY-MM-DD'``, so range queries behave exactly as before, and the API still
speaks ISO-8601 strings in both directions.

**The two dialects need genuinely different work here, so this revision branches
rather than using batch mode.** That is not a stylistic choice:

``Postgres`` has real types and will not implicitly cast text to date, so the
conversion must be spelled out with ``USING``. Its default has to come off first —
``CURRENT_TIMESTAMP`` was stored on a TEXT column as an ``::text`` expression, and
Postgres refuses a type change it cannot re-cast the default through.

``SQLite`` has no date types at all. ``DATE`` and ``DATETIME`` are declarations
with NUMERIC affinity, and the values already sit in exactly the form SQLAlchemy
reads a date back from, so the correct conversion is *no conversion* — change the
declaration, keep the bytes.

Alembic's ``batch_alter_table`` cannot express that. ``SQLiteImpl.cast_for_batch_migrate``
adds ``CAST(entry_date AS DATE)`` to its copy whenever the type affinity changes,
and in SQLite that cast is ``CAST(... AS NUMERIC)``, which prefix-parses:

    sqlite> SELECT CAST('2026-07-28' AS DATE);
    2026

Every date and timestamp in the table would silently become the integer 2026.
``tests/test_migrations.py`` asserts the real values survive, on both dialects.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | None = None
depends_on: str | None = None

#: Spelled out to match what ``metadata.create_all()`` emits, so that the
#: migrated schema and app/tables.py are byte-comparable.
_SQLITE_TABLE = """
    CREATE TABLE workout_entry_migrated (
        id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
        entry_date {entry_date} NOT NULL,
        exercise_id TEXT NOT NULL,
        sets INTEGER NOT NULL,
        created_at {created_at} DEFAULT CURRENT_TIMESTAMP NOT NULL,
        CONSTRAINT ck_workout_entry_sets_positive CHECK (sets > 0)
    )
"""


def _rebuild_sqlite(entry_date: str, created_at: str) -> None:
    """Re-declare the columns, copying values verbatim.

    The plain ``SELECT`` is the entire point — no ``CAST``, so text stays text.
    Dropping the old table takes its index with it; the new one is created after
    the rename so it lands on the right name.
    """
    op.execute(_SQLITE_TABLE.format(entry_date=entry_date, created_at=created_at))
    op.execute(
        "INSERT INTO workout_entry_migrated "
        "(id, entry_date, exercise_id, sets, created_at) "
        "SELECT id, entry_date, exercise_id, sets, created_at FROM workout_entry"
    )
    op.execute("DROP TABLE workout_entry")
    op.execute("ALTER TABLE workout_entry_migrated RENAME TO workout_entry")
    op.execute("CREATE INDEX idx_workout_entry_date ON workout_entry (entry_date)")


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _rebuild_sqlite(entry_date="DATE", created_at="DATETIME")
        return

    op.alter_column(
        "workout_entry",
        "entry_date",
        existing_type=sa.Text(),
        type_=sa.Date(),
        existing_nullable=False,
        postgresql_using="entry_date::date",
    )
    op.execute("ALTER TABLE workout_entry ALTER COLUMN created_at DROP DEFAULT")
    op.alter_column(
        "workout_entry",
        "created_at",
        existing_type=sa.Text(),
        type_=sa.DateTime(timezone=True),
        existing_nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="created_at::timestamptz",
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        _rebuild_sqlite(entry_date="TEXT", created_at="TEXT")
        return

    op.alter_column(
        "workout_entry",
        "entry_date",
        existing_type=sa.Date(),
        type_=sa.Text(),
        existing_nullable=False,
        postgresql_using="entry_date::text",
    )
    op.execute("ALTER TABLE workout_entry ALTER COLUMN created_at DROP DEFAULT")
    op.alter_column(
        "workout_entry",
        "created_at",
        existing_type=sa.DateTime(timezone=True),
        type_=sa.Text(),
        existing_nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
        postgresql_using="created_at::text",
    )
