"""Two users, exhaustively.

Phase 5's whole risk is one endpoint that forgot its ``WHERE user_id``. This
file walks every read and every write, with two accounts logging different
movements on the same day, and asserts each sees only its own. A missed clause
shows up here as a specific named failure rather than as a leak nobody notices.

The same-day, same-week overlap is deliberate: it makes a missing filter *fail*,
where two users training in different weeks would hide it behind a date range.
"""

from __future__ import annotations

import pytest

from conftest import OTHER_USER_ID, TEST_USER_ID

DAY = "2026-07-28"          # a Tuesday
MINE = "Barbell_Squat"
THEIRS = "Barbell_Bench_Press_-_Medium_Grip"


@pytest.fixture
def two_users(add, other_client):
    """Both accounts log on the same day, in the same week."""
    assert add(DAY, MINE, 3).status_code == 201
    response = other_client.post(
        "/api/entries",
        json={"date": DAY, "exercise_id": THEIRS, "sets": [{}, {}]},
    )
    assert response.status_code == 201
    return response.get_json()["entry"]


class TestReadsAreScoped:
    def test_entries_for_a_day(self, client, other_client, two_users):
        mine = client.get(f"/api/entries?date={DAY}").get_json()["entries"]
        theirs = other_client.get(f"/api/entries?date={DAY}").get_json()["entries"]
        assert [e["exercise_id"] for e in mine] == [MINE]
        assert [e["exercise_id"] for e in theirs] == [THEIRS]

    def test_entries_over_a_range(self, client, two_users):
        entries = client.get(
            "/api/entries?start=2026-07-01&end=2026-07-31"
        ).get_json()["entries"]
        assert [e["exercise_id"] for e in entries] == [MINE]

    def test_the_calendar(self, client, other_client, two_users):
        mine = client.get("/api/calendar?year=2026&month=7").get_json()["days"]
        theirs = other_client.get("/api/calendar?year=2026&month=7").get_json()["days"]
        assert mine == {DAY: 3}
        assert theirs == {DAY: 2}

    def test_the_weekly_summary(self, client, other_client, two_users):
        mine = client.get(f"/api/summary/week?date={DAY}").get_json()
        theirs = other_client.get(f"/api/summary/week?date={DAY}").get_json()
        assert mine["total_sets"] == 3
        assert theirs["total_sets"] == 2
        # Squat is a quad movement; bench is a chest movement. Neither week may
        # show any trace of the other's.
        assert mine["muscles"]["chest"]["sets"] == 0.0
        assert theirs["muscles"]["quads"]["sets"] == 0.0

    def test_the_trainer_setup(self, client, other_client):
        """One account's setup must never grade another's week."""
        client.put(
            "/api/profile",
            json={"experience": "beginner", "sessions_per_week": 3,
                  "minutes_per_session": 45},
        )
        mine = client.get("/api/profile").get_json()
        theirs = other_client.get("/api/profile").get_json()

        assert mine["configured"] is True
        assert theirs["configured"] is False
        assert theirs["profile"]["experience"] == "experienced"
        assert theirs["profile"]["targets"]["chest"] == 20

        # And the grading follows the account, not the request.
        their_week = other_client.get(f"/api/summary/week?date={DAY}").get_json()
        assert their_week["muscles"]["chest"]["target"] == 20

    def test_the_training_graph(self, client, other_client, two_users):
        mine = client.get("/api/progress/graph?window=all").get_json()
        theirs = other_client.get("/api/progress/graph?window=all").get_json()
        assert [n["exercise_id"] for n in mine["nodes"]] == [MINE]
        assert [n["exercise_id"] for n in theirs["nodes"]] == [THEIRS]

    def test_recent_exercises(self, client, other_client, two_users):
        mine = client.get("/api/exercises/recent").get_json()["exercises"]
        theirs = other_client.get("/api/exercises/recent").get_json()["exercises"]
        assert [e["id"] for e in mine] == [MINE]
        assert [e["id"] for e in theirs] == [THEIRS]

    def test_last_sets_does_not_reach_through_the_set_table(self, client, two_users):
        """The prefill joins back through workout_entry. This is why."""
        payload = client.get(f"/api/exercises/{THEIRS}/last-sets").get_json()
        assert payload == {"date": None, "sets": []}

    def test_last_sets_still_finds_your_own(self, client, two_users):
        payload = client.get(f"/api/exercises/{MINE}/last-sets").get_json()
        assert payload["date"] == DAY
        assert len(payload["sets"]) == 3


class TestWritesAreScoped:
    def test_deleting_another_users_entry_is_404(self, client, two_users):
        """404, not 403 — a 403 would confirm the id is real."""
        response = client.delete(f"/api/entries/{two_users['id']}")
        assert response.status_code == 404
        assert response.get_json()["error"] == "Entry not found."

    def test_the_refused_delete_leaves_the_row_intact(
        self, client, other_client, two_users
    ):
        """The half that matters. A 404 that still deleted would pass the test above."""
        client.delete(f"/api/entries/{two_users['id']}")
        still_there = other_client.get(f"/api/entries?date={DAY}").get_json()["entries"]
        assert [e["id"] for e in still_there] == [two_users["id"]]

    def test_deleting_your_own_entry_works(self, client, two_users):
        mine = client.get(f"/api/entries?date={DAY}").get_json()["entries"][0]
        assert client.delete(f"/api/entries/{mine['id']}").status_code == 200
        assert client.get(f"/api/entries?date={DAY}").get_json()["entries"] == []

    def test_a_new_entry_is_owned_by_its_poster(self, client, other_client, add):
        assert add(DAY, MINE, 1).status_code == 201
        assert other_client.get(f"/api/entries?date={DAY}").get_json()["entries"] == []


class TestIdentity:
    def test_each_client_is_a_different_user(self, client, other_client):
        assert client.get("/api/me").get_json()["user"]["id"] == TEST_USER_ID
        assert other_client.get("/api/me").get_json()["user"]["id"] == OTHER_USER_ID
