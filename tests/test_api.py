"""End-to-end tests for the JSON API."""

import pytest


def test_exercise_catalog(client):
    data = client.get("/api/exercises").get_json()
    ids = {e["id"] for e in data["exercises"]}
    assert ids == {"bench_press", "pull_ups", "squat", "sit_ups"}

    bench = next(e for e in data["exercises"] if e["id"] == "bench_press")
    assert bench["muscles"] == ["triceps", "chest"]


def test_create_and_list_entry(client, add):
    response = add("2026-07-28", "squat", 4)
    assert response.status_code == 201
    entry = response.get_json()["entry"]
    assert entry["sets"] == 4
    assert entry["exercise_name"] == "Squat"
    assert entry["muscles"] == ["quads", "hamstrings"]

    listed = client.get("/api/entries?date=2026-07-28").get_json()["entries"]
    assert len(listed) == 1
    assert listed[0]["id"] == entry["id"]


def test_entries_can_be_filtered_by_range(client, add):
    add("2026-07-27", "squat", 2)
    add("2026-07-30", "pull_ups", 3)
    add("2026-08-05", "bench_press", 1)

    entries = client.get("/api/entries?start=2026-07-27&end=2026-07-31").get_json()["entries"]
    assert {e["date"] for e in entries} == {"2026-07-27", "2026-07-30"}


@pytest.mark.parametrize(
    "payload",
    [
        {"date": "not-a-date", "exercise_id": "squat", "sets": 3},
        {"date": "2026-07-28", "exercise_id": "deadlift", "sets": 3},
        {"date": "2026-07-28", "exercise_id": "squat", "sets": 0},
        {"date": "2026-07-28", "exercise_id": "squat", "sets": "many"},
        {"date": "", "exercise_id": "squat", "sets": 3},
    ],
)
def test_invalid_entries_are_rejected(client, payload):
    response = client.post("/api/entries", json=payload)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_delete_entry(client, add):
    entry_id = add("2026-07-28", "squat", 3).get_json()["entry"]["id"]

    assert client.delete(f"/api/entries/{entry_id}").status_code == 200
    assert client.get("/api/entries?date=2026-07-28").get_json()["entries"] == []
    assert client.delete(f"/api/entries/{entry_id}").status_code == 404


def test_calendar_totals_are_grouped_by_day(client, add):
    add("2026-07-28", "squat", 3)
    add("2026-07-28", "bench_press", 2)
    add("2026-07-29", "pull_ups", 4)

    data = client.get("/api/calendar?year=2026&month=7").get_json()
    assert data["days"] == {"2026-07-28": 5, "2026-07-29": 4}


def test_calendar_rejects_bad_month(client):
    assert client.get("/api/calendar?year=2026&month=13").status_code == 400


def test_weekly_summary_endpoint(client, add):
    add("2026-07-28", "bench_press", 3)

    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert summary["week_start"] == "2026-07-27"
    assert summary["muscles"]["chest"]["worked"] is True
    assert summary["muscles"]["quads"]["worked"] is False
    assert summary["muscles"]["abs"]["worked"] is False
    assert summary["total_sets"] == 3


def test_weekly_summary_grades_volume_against_each_target(client, add):
    add("2026-07-28", "bench_press", 12)

    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    chest, triceps = summary["muscles"]["chest"], summary["muscles"]["triceps"]

    assert (chest["target"], chest["state"], chest["intensity"]) == (20, "trained", 0.6)
    assert (triceps["target"], triceps["state"], triceps["over"]) == (10, "over", 2)
    assert summary["muscles_over"] == ["triceps"]


def test_week_bounds_endpoint(client):
    data = client.get("/api/summary/week/bounds?date=2026-07-28").get_json()
    assert data == {"week_start": "2026-07-27", "week_end": "2026-08-02"}
