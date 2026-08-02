"""Add user accounts and give every entry an owner

Phase 5. Two append-only tables become two append-only tables plus an account,
and every ``workout_entry`` row gains a ``user_id``.

**This revision is destructive and irreversible.** It deletes every existing
``workout_set`` and ``workout_entry`` row before adding the column. That is a
decision, not a shortcut: a backfill onto a seed account would carry
single-user development history into the multi-user world as one account's
workouts and leave a permanent "who is user 1" question behind it.
``downgrade()`` puts the column and the table back. It cannot put the rows back.

**``batch_alter_table`` unconditionally, not branched by dialect.** SQLite
refuses to ``ADD COLUMN`` when the column is ``NOT NULL`` with no default, and
refuses again when it carries a ``REFERENCES`` clause. Both rules apply to an
empty table, so wiping first does not rescue a plain ``ALTER``. Batch mode
rebuilds under SQLite and emits a plain ``ALTER`` under Postgres, which is one
code path where revisions 0003 and 0004 each needed two.

Revision 0003's CAST trap does not bite here: ``cast_for_batch_migrate`` only
fires when a column's type *changes*, and nothing here changes type.

``copy_from`` is passed rather than letting batch mode reflect the table.
Reflection would lose ``sqlite_autoincrement``, and SQLite would start reusing
the ids of deleted rows.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-31

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None

#: A frozen copy, not an import from app/tables.py — the rule revision 0002
#: established. Batch mode needs the convention passed explicitly or SQLite's
#: rebuilt constraints come out unnamed.
_NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _entry_table(*, with_user: bool) -> sa.Table:
    """A frozen handle on ``workout_entry``, for ``batch_alter_table(copy_from=)``.

    Spelled out rather than reflected so ``sqlite_autoincrement`` survives the
    rebuild. Each call gets its own MetaData because a Table name can only be
    registered once per MetaData.
    """
    metadata = sa.MetaData(naming_convention=_NAMING_CONVENTION)
    columns = [
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("exercise_id", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]
    if with_user:
        # The referenced table has to exist in the same MetaData for the
        # ForeignKey to resolve during a batch rebuild.
        sa.Table(
            "user",
            metadata,
            sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
        )
        columns.append(
            sa.Column(
                "user_id",
                sa.Uuid(as_uuid=False),
                sa.ForeignKey("user.id", ondelete="CASCADE"),
                nullable=False,
            )
        )
    return sa.Table(
        "workout_entry",
        metadata,
        *columns,
        sa.Index("idx_workout_entry_date", "entry_date"),
        sqlite_autoincrement=True,
    )


def upgrade() -> None:
    # The wipe. Children first — app/db.py turns SQLite foreign keys on for
    # every connection, so the order is enforced rather than merely tidy.
    op.execute("DELETE FROM workout_set")
    op.execute("DELETE FROM workout_entry")

    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user"),
        # Spelled in full, not as a bare token: the `uq` convention carries no
        # %(constraint_name)s, so a name given here is used verbatim rather than
        # prefixed. `ck` is the opposite, which is why 0004's checks are bare.
        sa.UniqueConstraint("email", name="uq_user_email"),
    )

    with op.batch_alter_table(
        "workout_entry",
        copy_from=_entry_table(with_user=False),
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.add_column(
            sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False)
        )
        batch.create_foreign_key(
            "fk_workout_entry_user_id_user",
            "user",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.create_index(
        "idx_workout_entry_user_date", "workout_entry", ["user_id", "entry_date"]
    )


def downgrade() -> None:
    """Remove accounts.

    **Does not restore the rows ``upgrade()`` deleted.** Nothing can — they were
    not copied anywhere. This returns the schema to its Phase 4 shape and leaves
    it empty.
    """
    op.drop_index("idx_workout_entry_user_date", table_name="workout_entry")

    with op.batch_alter_table(
        "workout_entry",
        copy_from=_entry_table(with_user=True),
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.drop_constraint("fk_workout_entry_user_id_user", type_="foreignkey")
        batch.drop_column("user_id")

    op.drop_table("user")
