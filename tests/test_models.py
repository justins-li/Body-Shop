"""Tests for data-layer behaviour not reached through the API.

Chiefly the Phase 2 id migration: the catalog swap retired four hand-written
exercise ids, and entries logged against them have to survive it.
"""

from app.exercises import RETIRED_EXERCISE_IDS
from app.models import list_entries, recent_exercise_ids, remap_exercise_ids

SQUAT = "Barbell_Squat"


def log_legacy_entry(app, exercise_id: str, sets: int = 3, day: str = "2026-07-28") -> None:
    """Insert directly, bypassing validation — these ids no longer validate."""
    from app.db import get_db

    db = get_db()
    db.execute(
        "INSERT INTO workout_entry (entry_date, exercise_id, sets) VALUES (?, ?, ?)",
        (day, exercise_id, sets),
    )
    db.commit()


def test_remap_rewrites_retired_ids(app):
    with app.app_context():
        log_legacy_entry(app, "squat", 5)
        log_legacy_entry(app, "bench_press", 3)

        moved = remap_exercise_ids(RETIRED_EXERCISE_IDS)
        assert moved == {"squat": 1, "bench_press": 1}

        entries = list_entries()
        assert {e.exercise_id for e in entries} == {
            SQUAT,
            "Barbell_Bench_Press_-_Medium_Grip",
        }
        # The names resolve again, which is the point of remapping.
        assert all(e.exercise_name != e.exercise_id for e in entries)


def test_remap_is_idempotent(app):
    with app.app_context():
        log_legacy_entry(app, "sit_ups", 2)

        assert remap_exercise_ids(RETIRED_EXERCISE_IDS) == {"sit_ups": 1}
        assert remap_exercise_ids(RETIRED_EXERCISE_IDS) == {}
        assert [e.exercise_id for e in list_entries()] == ["Sit-Up"]


def test_remap_leaves_untouched_ids_alone(app):
    with app.app_context():
        log_legacy_entry(app, SQUAT, 4)

        assert remap_exercise_ids(RETIRED_EXERCISE_IDS) == {}
        assert [e.exercise_id for e in list_entries()] == [SQUAT]


def test_remap_moves_every_row_for_an_id(app):
    with app.app_context():
        log_legacy_entry(app, "pull_ups", 3, day="2026-07-27")
        log_legacy_entry(app, "pull_ups", 4, day="2026-07-28")

        assert remap_exercise_ids(RETIRED_EXERCISE_IDS) == {"pull_ups": 2}
        assert [e.exercise_id for e in list_entries()] == ["Pullups", "Pullups"]


def test_recent_ids_are_capped_by_limit(app):
    with app.app_context():
        for day, exercise in [("2026-07-26", "Sit-Up"), ("2026-07-27", "Pullups"),
                              ("2026-07-28", SQUAT)]:
            log_legacy_entry(app, exercise, 3, day=day)

        assert recent_exercise_ids(2) == [SQUAT, "Pullups"]


def test_recent_ids_deduplicate_by_exercise(app):
    with app.app_context():
        log_legacy_entry(app, SQUAT, 3, day="2026-07-27")
        log_legacy_entry(app, SQUAT, 4, day="2026-07-28")

        assert recent_exercise_ids() == [SQUAT]
