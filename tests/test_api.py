"""End-to-end tests for the JSON API."""

import pytest

BENCH = "Barbell_Bench_Press_-_Medium_Grip"
PULLUP = "Pullups"
SQUAT = "Barbell_Squat"
SITUP = "Sit-Up"


def test_exercise_catalog(client):
    data = client.get("/api/exercises").get_json()
    exercises = data["exercises"]
    assert len(exercises) == 873

    bench = next(e for e in exercises if e["id"] == BENCH)
    assert bench["name"] == "Barbell Bench Press - Medium Grip"
    assert bench["primary"] == ["chest"]
    assert bench["secondary"] == ["shoulders", "triceps"]
    assert bench["equipment"] == "barbell"
    assert bench["counts_toward_volume"] is True


def test_catalog_payload_omits_instructions_and_images(client):
    """The picker fetches the whole catalog, so it gets the light shape."""
    exercises = client.get("/api/exercises").get_json()["exercises"]
    assert all("instructions" not in e and "images" not in e for e in exercises)


def test_exercise_detail_includes_instructions_and_absolute_images(client):
    exercise = client.get(f"/api/exercises/{SQUAT}").get_json()["exercise"]
    assert exercise["name"] == "Barbell Squat"
    assert exercise["instructions"]
    # Exactly two frames, which is what the /log animation assumes.
    assert len(exercise["images"]) == 2
    assert all(url.startswith("https://") for url in exercise["images"])
    assert exercise["images"][0].endswith(f"{SQUAT}/0.jpg")


def test_unknown_exercise_detail_is_404(client):
    assert client.get("/api/exercises/not_a_movement").status_code == 404


def test_recent_exercises_are_most_recently_used_first(client, add):
    add("2026-07-26", SITUP, 2)
    add("2026-07-28", SQUAT, 3)
    add("2026-07-27", PULLUP, 4)

    recent = client.get("/api/exercises/recent").get_json()["exercises"]
    assert [e["id"] for e in recent] == [SQUAT, PULLUP, SITUP]


def test_recent_exercises_are_empty_before_anything_is_logged(client):
    assert client.get("/api/exercises/recent").get_json()["exercises"] == []


def test_create_and_list_entry(client, add):
    response = add("2026-07-28", SQUAT, 4)
    assert response.status_code == 201
    entry = response.get_json()["entry"]
    assert entry["sets"] == 4
    assert entry["exercise_name"] == "Barbell Squat"
    assert entry["muscles"] == ["quads", "back", "calves", "glutes", "hamstrings"]

    listed = client.get("/api/entries?date=2026-07-28").get_json()["entries"]
    assert len(listed) == 1
    assert listed[0]["id"] == entry["id"]


def test_entries_can_be_filtered_by_range(client, add):
    add("2026-07-27", SQUAT, 2)
    add("2026-07-30", PULLUP, 3)
    add("2026-08-05", BENCH, 1)

    entries = client.get("/api/entries?start=2026-07-27&end=2026-07-31").get_json()["entries"]
    assert {e["date"] for e in entries} == {"2026-07-27", "2026-07-30"}


@pytest.mark.parametrize(
    "payload",
    [
        {"date": "not-a-date", "exercise_id": SQUAT, "sets": 3},
        {"date": "2026-07-28", "exercise_id": "squat", "sets": 3},  # retired id
        {"date": "2026-07-28", "exercise_id": SQUAT, "sets": 0},
        {"date": "2026-07-28", "exercise_id": SQUAT, "sets": "many"},
        {"date": "", "exercise_id": SQUAT, "sets": 3},
    ],
)
def test_invalid_entries_are_rejected(client, payload):
    response = client.post("/api/entries", json=payload)
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_delete_entry(client, add):
    entry_id = add("2026-07-28", SQUAT, 3).get_json()["entry"]["id"]

    assert client.delete(f"/api/entries/{entry_id}").status_code == 200
    assert client.get("/api/entries?date=2026-07-28").get_json()["entries"] == []
    assert client.delete(f"/api/entries/{entry_id}").status_code == 404


def test_calendar_totals_are_grouped_by_day(client, add):
    add("2026-07-28", SQUAT, 3)
    add("2026-07-28", BENCH, 2)
    add("2026-07-29", PULLUP, 4)

    data = client.get("/api/calendar?year=2026&month=7").get_json()
    assert data["days"] == {"2026-07-28": 5, "2026-07-29": 4}


def test_calendar_rejects_bad_month(client):
    assert client.get("/api/calendar?year=2026&month=13").status_code == 400


def test_weekly_summary_endpoint(client, add):
    add("2026-07-28", BENCH, 3)

    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert summary["week_start"] == "2026-07-27"
    assert summary["muscles"]["chest"]["worked"] is True
    assert summary["muscles"]["quads"]["worked"] is False
    assert summary["muscles"]["abs"]["worked"] is False
    assert summary["total_sets"] == 3


def test_weekly_summary_grades_volume_against_each_target(client, add):
    add("2026-07-28", BENCH, 12)

    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    chest, triceps = summary["muscles"]["chest"], summary["muscles"]["triceps"]

    assert (chest["target"], chest["state"], chest["intensity"]) == (20, "trained", 0.6)
    # Triceps are secondary here: 12 sets of bench press count as 6.
    assert (triceps["sets"], triceps["target"], triceps["state"]) == (6, 10, "trained")
    assert summary["muscles_over"] == []


def test_weekly_summary_reports_all_twelve_groups(client):
    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert set(summary["muscles"]) == {
        "chest", "abs", "shoulders", "biceps", "forearms", "quads",
        "back", "traps", "triceps", "glutes", "hamstrings", "calves",
    }


def test_week_bounds_endpoint(client):
    data = client.get("/api/summary/week/bounds?date=2026-07-28").get_json()
    assert data == {"week_start": "2026-07-27", "week_end": "2026-08-02"}
