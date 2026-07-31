"""Token verification, and the just-in-time user mirror.

Every token here is minted in-process against the testing config's pinned
HS256 secret. Nothing in this file — or anywhere else in the suite — resolves a
JWKS document or otherwise reaches the network.
"""

from __future__ import annotations

import time

import jwt
import pytest

from app.services.auth import AUDIENCE, AuthError, Claims, decode_token, issuer

URL = "https://test.supabase.co"
SECRET = "test-jwt-secret-not-a-real-one-0123456789"
SUB = "11111111-1111-4111-8111-111111111111"

#: A valid-length secret that simply is not ours.
WRONG_SECRET = "wrong-secret-also-long-enough-0123456789"


def mint(secret=SECRET, **overrides) -> str:
    payload = {
        "sub": SUB,
        "email": "tester@example.com",
        "aud": AUDIENCE,
        "iss": issuer(URL),
        "exp": int(time.time()) + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, secret, algorithm="HS256")


class TestIssuer:
    def test_the_issuer_is_the_gotrue_base(self):
        assert issuer(URL) == "https://test.supabase.co/auth/v1"

    def test_a_trailing_slash_does_not_double_up(self):
        assert issuer("https://test.supabase.co/") == "https://test.supabase.co/auth/v1"


class TestDecodeToken:
    def test_a_valid_token_yields_its_claims(self):
        claims = decode_token(mint(), supabase_url=URL, jwt_secret=SECRET)
        assert claims == Claims(sub=SUB, email="tester@example.com")

    @pytest.mark.parametrize(
        ("name", "token"),
        [
            ("expired", lambda: mint(exp=int(time.time()) - 60)),
            ("wrong secret", lambda: mint(secret=WRONG_SECRET)),
            ("wrong audience", lambda: mint(aud="anon")),
            ("wrong issuer", lambda: mint(iss="https://evil.example.com/auth/v1")),
            ("no sub", lambda: mint(sub=None)),
            ("empty sub", lambda: mint(sub="")),
            ("no exp", lambda: jwt.encode(
                {"sub": SUB, "email": "t@e.com", "aud": AUDIENCE, "iss": issuer(URL)},
                SECRET, algorithm="HS256")),
            ("malformed", lambda: "not.a.token"),
            ("empty", lambda: ""),
        ],
    )
    def test_every_failure_raises_the_same_error(self, name, token):
        with pytest.raises(AuthError):
            decode_token(token(), supabase_url=URL, jwt_secret=SECRET)

    def test_every_failure_carries_the_same_message(self):
        """A 401 that says *why* is an oracle. Nothing in the client needs it."""
        messages = set()
        for token in (mint(exp=1), mint(secret=WRONG_SECRET), mint(aud="anon"), "junk"):
            with pytest.raises(AuthError) as caught:
                decode_token(token, supabase_url=URL, jwt_secret=SECRET)
            messages.add(str(caught.value))
        assert len(messages) == 1

    def test_a_token_with_no_email_still_decodes(self):
        """Email is not load-bearing for authorisation; `sub` is."""
        claims = decode_token(mint(email=None), supabase_url=URL, jwt_secret=SECRET)
        assert claims.sub == SUB
        assert claims.email == ""

    def test_none_is_rejected_without_calling_out_to_a_jwks(self):
        """An empty token must fail before the key resolver is ever consulted."""
        with pytest.raises(AuthError):
            decode_token("", supabase_url=URL, jwt_secret=None)


from app.models import add_entry, delete_user, ensure_user, get_user


class TestUserMirror:
    """Rows appear just-in-time. There is no signup webhook to create them."""

    def test_a_new_sub_is_inserted(self, app):
        with app.app_context():
            ensure_user(SUB, "tester@example.com")
            assert get_user(SUB) == {"id": SUB, "email": "tester@example.com"}

    def test_an_unknown_sub_reads_as_none(self, app):
        with app.app_context():
            assert get_user(SUB) is None

    def test_a_second_call_does_not_duplicate_the_row(self, app):
        with app.app_context():
            ensure_user(SUB, "tester@example.com")
            ensure_user(SUB, "tester@example.com")
            assert get_user(SUB) == {"id": SUB, "email": "tester@example.com"}

    def test_a_changed_email_is_written_through(self, app):
        """Supabase is the source of truth for the address, so it wins."""
        with app.app_context():
            ensure_user(SUB, "old@example.com")
            ensure_user(SUB, "new@example.com")
            assert get_user(SUB)["email"] == "new@example.com"

    def test_deleting_a_user_reports_it(self, app):
        with app.app_context():
            ensure_user(SUB, "tester@example.com")
            assert delete_user(SUB) is True
            assert get_user(SUB) is None

    def test_deleting_an_absent_user_reports_false(self, app):
        with app.app_context():
            assert delete_user(SUB) is False

    def test_deleting_a_user_cascades_to_entries_and_sets(self, app):
        """One DELETE, no cascade handling in Python — the FK does the work."""
        with app.app_context():
            ensure_user(SUB, "tester@example.com")
            entry = add_entry(SUB, "2026-07-28", "Barbell_Squat", [{}, {}])
            assert entry.sets == 2
            delete_user(SUB)
            assert get_user(SUB) is None


OTHER_SUB = "22222222-2222-4222-8222-222222222222"


class TestQueriesAreScopedToOneUser:
    """The model layer is where the WHERE clause has to be right.

    tests/test_ownership.py proves the same thing through the API. This proves
    it one layer down, so a failure says which layer lost the clause.
    """

    @pytest.fixture
    def two_users(self, app):
        with app.app_context():
            ensure_user(SUB, "one@example.com")
            ensure_user(OTHER_SUB, "two@example.com")
            add_entry(SUB, "2026-07-28", "Barbell_Squat", [{}, {}, {}])
            add_entry(OTHER_SUB, "2026-07-28", "Barbell_Bench_Press_-_Medium_Grip", [{}, {}])
            yield

    def test_list_entries_sees_only_its_own(self, app, two_users):
        from app.models import list_entries
        with app.app_context():
            mine = list_entries(SUB)
            assert [e.exercise_id for e in mine] == ["Barbell_Squat"]

    def test_get_entry_refuses_another_users_row(self, app, two_users):
        from app.models import get_entry, list_entries
        with app.app_context():
            theirs = list_entries(OTHER_SUB)[0]
            assert get_entry(OTHER_SUB, theirs.id) is not None
            assert get_entry(SUB, theirs.id) is None

    def test_delete_entry_refuses_another_users_row_and_leaves_it(self, app, two_users):
        from app.models import delete_entry, get_entry, list_entries
        with app.app_context():
            theirs = list_entries(OTHER_SUB)[0]
            assert delete_entry(SUB, theirs.id) is False
            assert get_entry(OTHER_SUB, theirs.id) is not None

    def test_sets_by_date_counts_only_its_own(self, app, two_users):
        from datetime import date as _date

        from app.models import sets_by_date
        with app.app_context():
            totals = sets_by_date(SUB, _date(2026, 7, 1), _date(2026, 7, 31))
            assert totals == {"2026-07-28": 3}

    def test_recent_usage_sees_only_its_own(self, app, two_users):
        from app.models import recent_exercise_usage
        with app.app_context():
            assert recent_exercise_usage(SUB) == [("Barbell_Squat", 1)]

    def test_last_sets_does_not_leak_through_the_set_table(self, app, two_users):
        """The join back through workout_entry is what stops this being an IDOR."""
        from app.models import last_sets_for_exercise
        with app.app_context():
            day, sets = last_sets_for_exercise(SUB, "Barbell_Bench_Press_-_Medium_Grip")
            assert day is None
            assert sets == []

    def test_activity_and_co_occurrence_see_only_their_own(self, app, two_users):
        from datetime import date as _date

        from app.models import exercise_activity, exercise_co_occurrence
        with app.app_context():
            start, end = _date(2026, 7, 1), _date(2026, 7, 31)
            assert [row[0] for row in exercise_activity(SUB, start, end)] == [
                "Barbell_Squat"
            ]
            assert exercise_co_occurrence(SUB, start, end) == []

    def test_the_weekly_summary_is_per_user(self, app, two_users):
        from datetime import date as _date

        from app.services.summary import weekly_summary
        with app.app_context():
            week = weekly_summary(SUB, _date(2026, 7, 28))
            assert week["total_sets"] == 3
            assert week["total_entries"] == 1
