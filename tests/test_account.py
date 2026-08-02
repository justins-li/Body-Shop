"""In-app account deletion.

Apple's Guideline 5.1.1(v) is what eventually *requires* this, but an app
holding email addresses and training history needs it as ordinary privacy
hygiene, which is why it is here rather than deferred to Phase 10.

**Local rows go first, the auth record second.** If the Supabase call fails the
account survives with no data — recoverable, retryable, and the response says so.
Supabase-first would risk the opposite: the auth record gone, the rows orphaned
behind an account that can never sign in again to delete them.

Nothing here reaches the network. ``delete_auth_user`` is patched at its use
site in ``app.api``.
"""

from __future__ import annotations

import pytest

from app.models import get_user
from app.services.auth import AuthError
from conftest import OTHER_USER_ID, TEST_USER_ID

DAY = "2026-07-28"


@pytest.fixture
def no_supabase_call(monkeypatch):
    """Record the call instead of making it."""
    calls = []

    def _fake(user_id, *, supabase_url, service_role_key, timeout=10.0):
        calls.append((user_id, supabase_url, service_role_key))

    monkeypatch.setattr("app.api.delete_auth_user", _fake)
    return calls


class TestDeleteAccount:
    def test_it_removes_the_user_their_entries_and_their_sets(
        self, app, client, add, no_supabase_call
    ):
        assert add(DAY, "Barbell_Squat", 3).status_code == 201

        response = client.delete("/api/account")
        assert response.status_code == 200
        assert response.get_json() == {"deleted": True, "auth_record_removed": True}

        with app.app_context():
            assert get_user(TEST_USER_ID) is None
        # The entries are gone with the user, by cascade — no cascade handling
        # in Python anywhere in this path.
        assert client.get(f"/api/entries?date={DAY}").get_json()["entries"] == []

    def test_it_calls_supabase_with_the_service_role_key(
        self, client, no_supabase_call
    ):
        client.delete("/api/account")
        assert no_supabase_call == [
            (TEST_USER_ID, "https://test.supabase.co", "test-service-role-key")
        ]

    def test_another_users_data_survives(
        self, app, client, other_client, add, no_supabase_call
    ):
        assert add(DAY, "Barbell_Squat", 3).status_code == 201
        assert other_client.post(
            "/api/entries",
            json={"date": DAY, "exercise_id": "Pullups", "sets": [{}, {}]},
        ).status_code == 201

        client.delete("/api/account")

        with app.app_context():
            assert get_user(OTHER_USER_ID) is not None
        theirs = other_client.get(f"/api/entries?date={DAY}").get_json()["entries"]
        assert [e["exercise_id"] for e in theirs] == ["Pullups"]

    def test_it_reports_honestly_when_supabase_refuses(self, app, client, monkeypatch):
        """Local-first ordering: the rows are gone, the auth record is not."""

        def _boom(user_id, **kwargs):
            raise AuthError("Supabase would not delete the auth record: 503")

        monkeypatch.setattr("app.api.delete_auth_user", _boom)

        response = client.delete("/api/account")
        assert response.status_code == 200
        assert response.get_json() == {"deleted": True, "auth_record_removed": False}
        with app.app_context():
            assert get_user(TEST_USER_ID) is None

    def test_it_refuses_before_touching_anything_without_a_service_key(self, tmp_path):
        from app import create_app
        from app.db import get_engine
        from app.tables import metadata
        from conftest import TEST_USER_EMAIL, _signed_in_client

        application = create_app(
            "testing",
            DATABASE_URL=f"sqlite:///{tmp_path / 'nokey.sqlite3'}",
            SUPABASE_SERVICE_ROLE_KEY=None,
        )
        with application.app_context():
            metadata.create_all(get_engine(application))
            local = _signed_in_client(application, TEST_USER_ID, TEST_USER_EMAIL)

            local.post(
                "/api/entries",
                json={"date": DAY, "exercise_id": "Barbell_Squat", "sets": [{}]},
            )
            response = local.delete("/api/account")
            assert response.status_code == 503

            # Nothing was touched.
            assert get_user(TEST_USER_ID) is not None
            entries = local.get(f"/api/entries?date={DAY}").get_json()["entries"]
            assert len(entries) == 1

            get_engine(application).dispose()

    def test_it_needs_a_token(self, app):
        assert app.test_client().delete("/api/account").status_code == 401
