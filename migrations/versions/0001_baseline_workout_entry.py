"""Baseline: workout_entry as schema.sql built it

The starting point for migrations, reproducing the schema the app carried from
its first commit through Phase 2. A database that predates Alembic can be marked
as already at this revision rather than rebuilt::

    flask --app app stamp-db 0001
    flask --app app upgrade-db

The one deliberate difference from the retired ``schema.sql`` is the
``created_at`` default: it used ``datetime('now')``, which no other dialect has.
``CURRENT_TIMESTAMP`` is the portable spelling and produces the identical value
in SQLite, which matters because a fresh Postgres deployment starts here.

Revision ID: 0001
Revises:
Create Date: 2026-07-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "workout_entry",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("entry_date", sa.Text(), nullable=False),
        sa.Column("exercise_id", sa.Text(), nullable=False),
        sa.Column("sets", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.Text(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        # Bare token, not the finished name: Alembic applies the metadata's
        # naming_convention ("ck_%(table_name)s_%(constraint_name)s") to whatever
        # is passed here, so a full name comes out double-prefixed as
        # ck_workout_entry_ck_workout_entry_sets_positive.
        sa.CheckConstraint("sets > 0", name="sets_positive"),
        sa.PrimaryKeyConstraint("id"),
        # Without this SQLite reuses the ids of deleted rows.
        sqlite_autoincrement=True,
    )
    op.create_index("idx_workout_entry_date", "workout_entry", ["entry_date"])


def downgrade() -> None:
    op.drop_index("idx_workout_entry_date", table_name="workout_entry")
    op.drop_table("workout_entry")
