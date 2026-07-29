"""SQLite connection handling and schema management.

The database lives in Flask's ``instance/`` folder by default so it never gets
committed to git.  Connections are cached on the request context (``g``) and
closed automatically when the request ends.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import click
from flask import Flask, current_app, g


def get_db() -> sqlite3.Connection:
    """Return the request-scoped SQLite connection, opening it if needed."""
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exc: BaseException | None = None) -> None:
    """Close the request-scoped connection, if one was opened."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db() -> None:
    """(Re)create all tables from ``schema.sql``. Destroys existing data."""
    db = get_db()
    schema = Path(current_app.root_path, "schema.sql").read_text(encoding="utf-8")
    db.executescript(schema)
    db.commit()


def ensure_db() -> None:
    """Create the schema if the database file has not been initialised yet."""
    db = get_db()
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'workout_entry'"
    ).fetchone()
    if row is None:
        init_db()


@click.command("init-db")
def init_db_command() -> None:
    """CLI: ``flask --app app init-db`` — reset the database."""
    init_db()
    click.echo("Initialised the database.")


@click.command("remap-exercises")
def remap_exercises_command() -> None:
    """CLI: ``flask --app app remap-exercises`` — carry history onto the catalog.

    Phase 2 replaced four hand-written exercise ids with free-exercise-db's.
    This rewrites entries logged against the old ones so they keep counting.
    Idempotent.
    """
    # Imported here: models.py imports this module for get_db().
    from .exercises import RETIRED_EXERCISE_IDS
    from .models import remap_exercise_ids

    moved = remap_exercise_ids(RETIRED_EXERCISE_IDS)
    if not moved:
        click.echo("No entries to remap.")
        return
    for old_id, count in moved.items():
        click.echo(f"  {old_id} -> {RETIRED_EXERCISE_IDS[old_id]} ({count} entries)")
    click.echo(f"Remapped {sum(moved.values())} entries.")


def init_app(app: Flask) -> None:
    """Register database teardown and CLI commands on ``app``."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(remap_exercises_command)
