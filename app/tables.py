"""The database schema, as SQLAlchemy Core metadata.

This module is the schema's source of truth. It replaced ``schema.sql`` in
Phase 3, when the app gained Alembic and a second dialect: Core describes the
schema once and renders it as SQLite or Postgres DDL, which a hand-written
``.sql`` file cannot do.

**Editing a table here does not change any existing database.** Alembic reads
``metadata`` as its ``target_metadata``, so a change needs a revision in
``migrations/versions/`` in the same commit — ``tests/test_migrations.py`` fails
when the two disagree.
"""

from __future__ import annotations

import sqlalchemy as sa

#: Deterministic constraint names, in every dialect.
#:
#: This is not cosmetic. SQLite cannot ``ALTER`` most things, so Alembic's
#: ``batch_alter_table`` rebuilds the table and recreates its constraints — which
#: it can only do if they have names it can discover. Phase 5 adds ``user_id``
#: with a ``REFERENCES`` clause to ``workout_entry``, which is exactly that
#: operation, and retrofitting a convention afterwards means renaming
#: constraints in a migration.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)

#: One logged movement: N sets of an exercise on a given day.
#:
#: Append-only, and there is no per-day "workout" parent row, which keeps logging
#: a single insert and range queries trivial. No ``user_id`` yet — see Phase 5.
workout_entry = sa.Table(
    "workout_entry",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    # A real DATE, not the TEXT column this started as. On SQLite the stored
    # representation is still 'YYYY-MM-DD', so the lexicographic BETWEEN that
    # range queries rely on remains chronologically correct; Postgres gets real
    # date semantics. The API still speaks ISO-8601 strings in both directions.
    sa.Column("entry_date", sa.Date, nullable=False),
    #: Catalog id from app/exercises.py, e.g. ``Barbell_Squat``.
    sa.Column("exercise_id", sa.Text, nullable=False),
    sa.Column("sets", sa.Integer, nullable=False),
    # CURRENT_TIMESTAMP rather than sa.func.now(), which renders as now() on
    # Postgres and CURRENT_TIMESTAMP on SQLite. Spelling it literally means the
    # metadata and the migrations produce the same default on both dialects,
    # which is what lets tests/test_migrations.py compare them.
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
    sa.CheckConstraint("sets > 0", name="sets_positive"),
    sa.Index("idx_workout_entry_date", "entry_date"),
    # Preserves the AUTOINCREMENT the hand-written schema had: without it SQLite
    # reuses the ids of deleted rows. Ignored by every other dialect.
    sqlite_autoincrement=True,
)
