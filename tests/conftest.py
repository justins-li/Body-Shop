"""Shared pytest fixtures: a throwaway app and client backed by a temp SQLite file."""

from __future__ import annotations

import pytest

from app import create_app
from app.db import init_db


@pytest.fixture
def app(tmp_path):
    """A testing app with an isolated, freshly initialised database."""
    application = create_app("testing", DATABASE=str(tmp_path / "test.sqlite3"))
    with application.app_context():
        init_db()
    yield application


@pytest.fixture
def client(app):
    """A Flask test client for the app fixture."""
    return app.test_client()


@pytest.fixture
def add(client):
    """Helper that POSTs an entry and returns the parsed JSON response."""

    def _add(date: str, exercise_id: str, sets: int):
        response = client.post(
            "/api/entries",
            json={"date": date, "exercise_id": exercise_id, "sets": sets},
        )
        return response

    return _add
