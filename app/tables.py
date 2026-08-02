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

#: The account. **A mirror row, not the source of truth.**
#:
#: Supabase owns credentials; this table exists because ``user_id`` has to be a
#: real foreign key on both dialects and SQLite has no ``auth.users`` to point
#: at. It therefore carries no ``password_hash`` (a credential we chose not to
#: own) and no ``verified_at`` (Supabase's ``email_confirmed_at`` is the truth,
#: and a mirrored copy drifts invisibly until someone is wrongly let in or
#: wrongly kept out).
#:
#: Rows appear just-in-time, on the first authenticated request carrying a
#: ``sub`` we have not seen — there is no signup webhook. See
#: ``models.ensure_user``.
#:
#: ``user`` is a reserved word in Postgres. SQLAlchemy quotes identifiers
#: automatically in both dialects, so this is safe — but it is why the name must
#: never be interpolated into a string query.
user = sa.Table(
    "user",
    metadata,
    # The Supabase auth.users id, which is the JWT's `sub`. Not minted here.
    # as_uuid=False stores 32-char hex and returns the hyphenated 36-char form,
    # exactly as workout_set.id does — compare with uuid.UUID(...), never with
    # string equality against a `.hex`.
    sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column("email", sa.Text, nullable=False, unique=True),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
)

#: One logged movement on a given day; its sets live in ``workout_set``.
#:
#: Append-only, and there is no per-day "workout" parent row, which keeps logging
#: a single insert and range queries trivial. Every row belongs to exactly one
#: user as of Phase 5.
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
    #: The owning account. ``ON DELETE CASCADE`` all the way down, so deleting a
    #: user is one DELETE and needs no cascade handling in Python — the same
    #: property delete_entry has relied on since Phase 4.
    sa.Column(
        "user_id",
        sa.Uuid(as_uuid=False),
        sa.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    ),
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
    sa.Index("idx_workout_entry_date", "entry_date"),
    # Every query in models.py now filters on user_id first and ranges on
    # entry_date second, which is the order this index is built in.
    sa.Index("idx_workout_entry_user_date", "user_id", "entry_date"),
    # Preserves the AUTOINCREMENT the hand-written schema had: without it SQLite
    # reuses the ids of deleted rows. Ignored by every other dialect.
    sqlite_autoincrement=True,
)

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
