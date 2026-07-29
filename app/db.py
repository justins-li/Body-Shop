"""Database engine, request-scoped connections, and schema commands.

The app speaks SQLAlchemy Core, so one query layer serves both SQLite (local
development and the test suite) and Postgres (anywhere hosted). Which one is in
use is decided entirely by ``DATABASE_URL``.

Connections are cached on the request context (``g``) and closed when the request
ends. :func:`get_db` returns a Core ``Connection`` rather than a ``sqlite3``
one — the name is unchanged so that the *all SQL lives in models.py* rule reads
the same as it always did.

Nothing here runs at import or in the application factory. Schema changes happen
only when something calls :func:`upgrade_db` or :func:`init_db`: the factory used
to apply ``schema.sql`` on every boot, which both crashed on a read-only
filesystem and gave fresh deployments an unversioned schema that Alembic had no
revision to stamp.
"""

from __future__ import annotations

from pathlib import Path

import click
import sqlalchemy as sa
from alembic import command
from alembic.config import Config as AlembicConfig
from flask import Flask, current_app, g

from .tables import metadata

#: Key under which the process-wide engine is cached on ``app.extensions``.
ENGINE_KEY = "bodyshop_engine"


def _on_sqlite_connect(dbapi_connection, connection_record) -> None:
    """Enforce foreign keys, which SQLite leaves off per-connection."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


def create_engine(url: str) -> sa.Engine:
    """Build an engine for ``url``, configured for its backend."""
    parsed = sa.make_url(url)
    backend = parsed.get_backend_name()
    kwargs: dict = {}

    if backend == "postgresql":
        # Two settings that only matter behind a connection pooler, which is how
        # both Supabase and Neon serve Postgres:
        #
        # NullPool: the pooler is the pool. Holding a second pool of our own in a
        # serverless function means every concurrent invocation keeps
        # connections open that it is not using, which is how you exhaust a
        # Postgres connection limit at trivial traffic.
        #
        # prepare_threshold=None: disables server-side prepared statements,
        # which a transaction-mode pooler (Supabase's port 6543) cannot carry
        # across the connections it multiplexes. Note that None disables them —
        # 0 means "prepare on first execution", which is the opposite.
        kwargs["poolclass"] = sa.pool.NullPool
        kwargs["connect_args"] = {"prepare_threshold": None}

    engine = sa.create_engine(parsed, **kwargs)

    if backend == "sqlite":
        sa.event.listen(engine, "connect", _on_sqlite_connect)

    return engine


def get_engine(app: Flask | None = None) -> sa.Engine:
    """Return the process-wide engine, building it on first use."""
    app = app or current_app
    engine = app.extensions.get(ENGINE_KEY)
    if engine is None:
        engine = create_engine(app.config["DATABASE_URL"])
        app.extensions[ENGINE_KEY] = engine
    return engine


def get_db() -> sa.Connection:
    """Return the request-scoped database connection, opening it if needed."""
    if "db" not in g:
        g.db = get_engine().connect()
    return g.db


def close_db(exc: BaseException | None = None) -> None:
    """Close the request-scoped connection, if one was opened.

    Closing rolls back any transaction still open, so a request that raised
    part-way through a write leaves nothing behind.
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()


def alembic_config(app: Flask | None = None) -> AlembicConfig:
    """Return an Alembic config pointed at this app's database.

    The URL is passed through ``attributes`` rather than ``sqlalchemy.url``
    because Alembic reads its ini file with a ``configparser`` that performs ``%``
    interpolation — and a percent-encoded character in a Postgres password is
    common enough that setting the option would break on real connection strings.
    """
    app = app or current_app
    root = Path(app.root_path).parent
    config = AlembicConfig(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.attributes["database_url"] = app.config["DATABASE_URL"]
    return config


def upgrade_db(revision: str = "head", app: Flask | None = None) -> None:
    """Run migrations up to ``revision``. Idempotent."""
    command.upgrade(alembic_config(app), revision)


def downgrade_db(revision: str, app: Flask | None = None) -> None:
    """Roll migrations back to ``revision`` (``"base"`` for an empty database).

    No CLI wrapper on purpose: backing a schema out is a deliberate act, and the
    tests are the main consumer — they run the whole chain down to prove each
    revision's ``downgrade`` actually works before it is ever needed.
    """
    command.downgrade(alembic_config(app), revision)


def stamp_db(revision: str = "head", app: Flask | None = None) -> None:
    """Record ``revision`` as applied without running it.

    For a database that predates migrations: ``stamp_db("0001")`` declares that
    its hand-built schema matches the baseline, after which ``upgrade_db()``
    carries it forward.
    """
    command.stamp(alembic_config(app), revision)


def init_db(app: Flask | None = None) -> None:
    """Drop every table, then migrate back up to head. Destroys all data."""
    app = app or current_app
    engine = get_engine(app)
    with engine.begin() as connection:
        metadata.drop_all(connection)
        # Alembic's own bookkeeping table is not in our metadata, and leaving it
        # behind would make the upgrade below a no-op against an empty database.
        connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
    upgrade_db(app=app)


@click.command("init-db")
@click.option("--force", is_flag=True, help="Skip the confirmation prompt.")
def init_db_command(force: bool) -> None:
    """CLI: ``flask --app app init-db`` — reset the database. Development only.

    This is a convenience for a throwaway local database, not a deployment step;
    deployments run ``upgrade-db``.
    """
    app = current_app
    if app.config.get("CONFIG_NAME") == "production":
        raise click.ClickException(
            "init-db drops every table and is disabled under production config. "
            "Run upgrade-db instead."
        )

    url = sa.make_url(app.config["DATABASE_URL"])
    if not force and url.get_backend_name() != "sqlite":
        click.confirm(
            f"This drops every table in {url.render_as_string()}. Continue?",
            abort=True,
        )

    init_db(app)
    click.echo("Initialised the database.")


@click.command("upgrade-db")
@click.argument("revision", default="head")
def upgrade_db_command(revision: str) -> None:
    """CLI: ``flask --app app upgrade-db [revision]`` — apply migrations."""
    upgrade_db(revision)
    click.echo(f"Database migrated to {revision}.")


@click.command("stamp-db")
@click.argument("revision", default="head")
def stamp_db_command(revision: str) -> None:
    """CLI: ``flask --app app stamp-db [revision]`` — mark migrations applied.

    Use ``stamp-db 0001`` on a database created before migrations existed.
    """
    stamp_db(revision)
    click.echo(f"Database stamped as {revision}.")


def init_app(app: Flask) -> None:
    """Register database teardown and CLI commands on ``app``."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(upgrade_db_command)
    app.cli.add_command(stamp_db_command)
