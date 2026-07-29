"""Alembic environment.

Resolves the database from the application's own configuration, so there is one
answer to "which database?" whether migrations are invoked as
``flask --app app upgrade-db``, as ``alembic upgrade head``, or from a test.

Two settings below are load-bearing for later phases:

``render_as_batch``
    SQLite cannot ``ALTER`` most things. Batch mode rebuilds the table instead,
    which is the only portable way to write the ``user_id`` column Phase 5 adds.
``compare_type``
    Autogenerate ignores type changes unless asked. Phase 4 changes column types,
    and a silently skipped diff is worse than a spurious one.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.tables import metadata

config = context.config

target_metadata = metadata


def _database_url() -> str:
    """Return the URL to migrate.

    ``attributes`` is set when the app invokes Alembic programmatically. When the
    ``alembic`` CLI is used directly there is no app yet, so one is built purely
    to read its resolved config — which also means the CLI honours ``.env`` and
    ``instance/config.py`` exactly as the app does.
    """
    url = config.attributes.get("database_url")
    if url:
        return url

    from app import create_app

    return create_app().config["DATABASE_URL"]


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (``alembic upgrade --sql``)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = config.attributes.get("connection")

    if connectable is None:
        connectable = engine_from_config(
            {"sqlalchemy.url": _database_url()},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
