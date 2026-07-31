"""Shared pytest fixtures.

Two modes, chosen by whether ``BODYSHOP_TEST_DATABASE_URL`` is set:

**SQLite (default).** Each test gets its own file in pytest's ``tmp_path``, built
directly from ``app.tables.metadata``. Fast, and the isolation is absolute — no
test can see another's rows, in any order.

**Postgres.** Every test runs against the one database named by the environment
variable. The schema is built once per session **by running the migrations**, so
a Postgres run also verifies the migration chain against a real dialect rather
than only the queries. Between tests the table is truncated, which is one round
trip where a drop-and-recreate would be a schema rebuild — the difference is
minutes against a hosted database.

    BODYSHOP_TEST_DATABASE_URL=postgresql://... pytest

That database is truncated between tests, so point it at a scratch one.
"""

from __future__ import annotations

import os

import pytest
import sqlalchemy as sa

from app import create_app
from app.db import get_engine, init_db
from app.tables import metadata

TEST_DATABASE_URL = os.environ.get("BODYSHOP_TEST_DATABASE_URL")


@pytest.fixture(scope="session")
def postgres_app():
    """Session-wide app whose schema is built once, by the migrations."""
    application = create_app("testing", DATABASE_URL=TEST_DATABASE_URL)
    with application.app_context():
        init_db(application)
        yield application
        get_engine(application).dispose()


@pytest.fixture
def app(tmp_path, request):
    """A testing app with an isolated, freshly initialised database."""
    if TEST_DATABASE_URL:
        application = request.getfixturevalue("postgres_app")
        with application.app_context():
            engine = get_engine(application)
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "TRUNCATE TABLE workout_set, workout_entry RESTART IDENTITY CASCADE"
                    )
                )
            yield application
        return

    application = create_app(
        "testing", DATABASE_URL=f"sqlite:///{tmp_path / 'test.sqlite3'}"
    )
    with application.app_context():
        metadata.create_all(get_engine(application))
        yield application
        get_engine(application).dispose()


@pytest.fixture
def client(app):
    """A Flask test client for the app fixture."""
    return app.test_client()


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
