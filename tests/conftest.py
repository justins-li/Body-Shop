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
import time

import jwt
import pytest
import sqlalchemy as sa
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers

from app import create_app
from app.db import get_engine, init_db
from app.models import ensure_user
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
                    # `user` is a reserved word in Postgres, and this is the one
                    # place in the project that writes raw SQL — so it is the one
                    # place the quoting has to be done by hand.
                    sa.text(
                        'TRUNCATE TABLE workout_set, workout_entry, "user" '
                        "RESTART IDENTITY CASCADE"
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


#: The user every test is signed in as, unless it says otherwise.
TEST_USER_ID = "11111111-1111-4111-8111-111111111111"
TEST_USER_EMAIL = "tester@example.com"

#: A second account, for tests/test_ownership.py.
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
OTHER_USER_EMAIL = "other@example.com"


def make_token(app, user_id=TEST_USER_ID, email=TEST_USER_EMAIL, **overrides) -> str:
    """Mint an HS256 token the app will accept.

    Signed with the testing config's pinned ``SUPABASE_JWT_SECRET``, which is
    what keeps the suite offline: no test resolves a JWKS document, and no test
    reaches Supabase. ``overrides`` replaces any claim, which is how
    tests/test_auth.py builds its rejected tokens.
    """
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "iss": f"{app.config['SUPABASE_URL']}/auth/v1",
        "exp": int(time.time()) + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, app.config["SUPABASE_JWT_SECRET"], algorithm="HS256")


class AuthedClient(FlaskClient):
    """A test client that signs every request as :data:`token`'s user.

    Injecting the header here rather than at each call site is what let the
    whole pre-Phase-5 suite survive the sweep unedited. A request that sets its
    own ``Authorization`` wins, so a test can still be anonymous by using
    ``app.test_client()`` directly.
    """

    token: str | None = None

    def open(self, *args, **kwargs):
        headers = Headers(kwargs.get("headers") or {})
        if self.token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {self.token}"
        kwargs["headers"] = headers
        return super().open(*args, **kwargs)


def _signed_in_client(app, user_id, email) -> AuthedClient:
    app.test_client_class = AuthedClient
    client = app.test_client()
    client.token = make_token(app, user_id=user_id, email=email)
    # Seeded rather than left to just-in-time provisioning, because tests that
    # call models.add_entry directly never go through require_user and would
    # otherwise trip the foreign key.
    with app.app_context():
        ensure_user(user_id, email)
    return client


@pytest.fixture
def client(app):
    """A Flask test client signed in as :data:`TEST_USER_ID`."""
    return _signed_in_client(app, TEST_USER_ID, TEST_USER_EMAIL)


@pytest.fixture
def other_client(app):
    """A second signed-in client, for the ownership tests."""
    return _signed_in_client(app, OTHER_USER_ID, OTHER_USER_EMAIL)


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
