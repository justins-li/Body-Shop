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


def test_recent_exercises_carry_their_use_count(client, add):
    """The picker ranks browse and search by this, not just the recent list."""
    add("2026-07-26", SQUAT, 3)
    add("2026-07-27", SQUAT, 3)
    add("2026-07-28", PULLUP, 4)

    recent = client.get("/api/exercises/recent").get_json()["exercises"]
    assert {e["id"]: e["uses"] for e in recent} == {SQUAT: 2, PULLUP: 1}


def test_catalog_payload_carries_a_rank_with_the_staples_first(client):
    """"Common lifts first" has to survive the wire; the picker sorts on it."""
    exercises = client.get("/api/exercises").get_json()["exercises"]
    ranked = sorted(exercises, key=lambda e: e["rank"])
    assert ranked[0]["id"] == BENCH
    assert [e["id"] for e in ranked[:3]] == [BENCH, SQUAT, "Barbell_Deadlift"]


def test_weekly_summary_carries_regions_without_grading_them(client, add):
    add("2026-07-28", BENCH, 10)
    summary = client.get("/api/summary/week?date=2026-07-28").get_json()

    shoulders = summary["muscles"]["shoulders"]
    assert shoulders["region_sets"] == 5.0
    front = next(r for r in shoulders["regions"] if r["region"] == "delt_front")
    assert front["share"] == 1.0
    # No target, state or intensity on a region: nothing to grade it against.
    assert set(front) == {"region", "label", "sets", "share", "neglected"}

    # Groups with no evidence for subdivision say so with an empty list.
    assert summary["muscles"]["biceps"]["regions"] == []

    flagged = {r["region"] for r in summary["regions_neglected"]}
    assert {"delt_side", "delt_rear"} <= flagged


def test_create_and_list_entry(client, add):
    response = add("2026-07-28", SQUAT, 4)
    assert response.status_code == 201
    entry = response.get_json()["entry"]
    assert entry["set_count"] == 4
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


def test_entries_carry_their_sets_and_a_count(client, add):
    add("2026-07-28", SQUAT, [
        {"weight": 100, "reps": 5},
        {"weight": 100, "reps": 5},
        {"weight": 105, "reps": 3, "rpe": 8.5, "set_type": "failure"},
    ])

    entry = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]
    assert entry["set_count"] == 3
    assert [s["set_index"] for s in entry["sets"]] == [1, 2, 3]
    assert entry["sets"][0]["weight"] == 100.0
    assert entry["sets"][2]["rpe"] == 8.5
    assert entry["sets"][2]["set_type"] == "failure"


def test_blank_sets_are_stored_as_nulls(client, add):
    """Logging bare sets stays possible — the backfill produces the same shape."""
    add("2026-07-28", SQUAT, [{}, {}])
    entry = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]

    assert entry["set_count"] == 2
    assert all(s["weight"] is None and s["reps"] is None for s in entry["sets"])
    assert all(s["set_type"] == "normal" for s in entry["sets"])


def test_warmup_sets_are_stored_but_excluded_from_the_count(client, add):
    add("2026-07-28", SQUAT, [
        {"weight": 40, "reps": 5, "set_type": "warmup"},
        {"weight": 100, "reps": 5},
        {"weight": 100, "reps": 5},
    ])

    entry = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]
    assert len(entry["sets"]) == 3
    assert entry["set_count"] == 2


def test_warmup_sets_do_not_inflate_the_muscle_map(client, add):
    """The correctness requirement: a warm-up must not shade the body map."""
    add("2026-07-28", BENCH, [{"set_type": "warmup"}] * 4 + [{}] * 2)

    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert summary["muscles"]["chest"]["sets"] == 2.0
    assert summary["total_sets"] == 2


def test_warmup_sets_do_not_inflate_the_calendar(client, add):
    add("2026-07-28", SQUAT, [{"set_type": "warmup"}, {}, {}])
    days = client.get("/api/calendar?year=2026&month=7").get_json()["days"]
    assert days == {"2026-07-28": 2}


def test_an_entry_of_only_warmups_contributes_no_volume(client, add):
    add("2026-07-28", BENCH, [{"set_type": "warmup"}] * 3)

    entry = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]
    assert entry["set_count"] == 0

    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert summary["muscles"]["chest"]["worked"] is False
    assert summary["total_sets"] == 0


def test_set_ids_are_distinct_uuids(client, add):
    from uuid import UUID

    add("2026-07-28", SQUAT, [{}, {}, {}])
    sets = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]["sets"]

    ids = [s["id"] for s in sets]
    assert len(set(ids)) == 3
    # Parse rather than compare: the stored form is hex, the read form hyphenated.
    assert all(UUID(value) for value in ids)


def test_weights_round_trip_in_kilograms(client, add):
    add("2026-07-28", SQUAT, [{"weight": 102.5, "reps": 5}])
    sets = client.get("/api/entries?date=2026-07-28").get_json()["entries"][0]["sets"]
    assert sets[0]["weight"] == 102.5


def test_deleting_an_entry_cascades_to_its_sets(client, add, app):
    import sqlalchemy as sa

    from app.db import get_db
    from app.tables import workout_set

    entry_id = add("2026-07-28", SQUAT, [{}, {}, {}]).get_json()["entry"]["id"]
    client.delete(f"/api/entries/{entry_id}")

    with app.app_context():
        remaining = get_db().execute(
            sa.select(sa.func.count()).select_from(workout_set)
        ).scalar()
    assert remaining == 0


@pytest.mark.parametrize(
    "sets",
    [
        3,                                        # the old integer shape
        [],                                       # empty
        "three",                                  # not a list
        [{}] * 101,                               # over the cap
        [{"weight": -1}],                         # negative weight
        [{"reps": 0}],                            # reps below range
        [{"reps": 1001}],                         # reps above range
        [{"rpe": 0.9}],                           # rpe below range
        [{"rpe": 10.5}],                          # rpe above range
        [{"rpe": 8.3}],                           # not a 0.5 step
        [{"set_type": "backoff"}],                # unknown type
        ["not-an-object"],                        # not a dict
    ],
)
def test_invalid_set_payloads_are_rejected(client, sets):
    response = client.post(
        "/api/entries",
        json={"date": "2026-07-28", "exercise_id": SQUAT, "sets": sets},
    )
    assert response.status_code == 400
    assert "error" in response.get_json()


def test_last_sets_returns_the_most_recent_session(client, add):
    add("2026-07-20", SQUAT, [{"weight": 95, "reps": 5}])
    add("2026-07-27", SQUAT, [{"weight": 100, "reps": 5}, {"weight": 100, "reps": 4}])
    add("2026-07-27", BENCH, [{"weight": 60, "reps": 8}])

    data = client.get(f"/api/exercises/{SQUAT}/last-sets").get_json()
    assert data["date"] == "2026-07-27"
    assert [s["weight"] for s in data["sets"]] == [100.0, 100.0]
    assert [s["reps"] for s in data["sets"]] == [5, 4]


def test_last_sets_is_empty_for_an_unlogged_movement(client):
    data = client.get(f"/api/exercises/{PULLUP}/last-sets").get_json()
    assert data == {"date": None, "sets": []}


def test_last_sets_404s_for_an_unknown_exercise(client):
    assert client.get("/api/exercises/not_a_movement/last-sets").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"date": "not-a-date", "exercise_id": SQUAT, "sets": [{}]},
        {"date": "2026-07-28", "exercise_id": "squat", "sets": [{}]},  # retired id
        {"date": "", "exercise_id": SQUAT, "sets": [{}]},
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
