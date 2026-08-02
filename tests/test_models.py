"""Tests for data-layer behaviour not reached through the API.

The Phase 2 id remap used to be tested here. It is a migration now, so its tests
live in ``test_migrations.py`` — this file is what is left: the recent-exercise
query behind the ``/log`` picker's default tab.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import sqlalchemy as sa

from app.db import get_db
from app.models import (
    get_trainer_setup,
    loaded_sets,
    recent_exercise_ids,
    set_trainer_setup,
)
from conftest import OTHER_USER_ID, TEST_USER_ID
from app.tables import workout_entry, workout_set

SQUAT = "Barbell_Squat"


def log_entry(exercise_id: str, sets: int = 3, day: str = "2026-07-28") -> None:
    """Insert directly, bypassing the API and its validation."""
    db = get_db()
    result = db.execute(
        sa.insert(workout_entry).values(
            user_id=TEST_USER_ID,
            entry_date=date.fromisoformat(day),
            exercise_id=exercise_id,
        )
    )
    entry_id = int(result.inserted_primary_key[0])
    db.execute(
        sa.insert(workout_set),
        [
            {
                "id": uuid4().hex,
                "entry_id": entry_id,
                "set_index": index,
                "weight": None,
                "reps": None,
                "rpe": None,
                "set_type": "normal",
            }
            for index in range(1, sets + 1)
        ],
    )
    db.commit()


def test_recent_ids_are_capped_by_limit(app, client):
    with app.app_context():
        for day, exercise in [
            ("2026-07-26", "Sit-Up"),
            ("2026-07-27", "Pullups"),
            ("2026-07-28", SQUAT),
        ]:
            log_entry(exercise, 3, day=day)

        assert recent_exercise_ids(TEST_USER_ID, 2) == [SQUAT, "Pullups"]


def test_recent_ids_deduplicate_by_exercise(app, client):
    with app.app_context():
        log_entry(SQUAT, 3, day="2026-07-27")
        log_entry(SQUAT, 4, day="2026-07-28")

        assert recent_exercise_ids(TEST_USER_ID) == [SQUAT]


# ---- loaded_sets: the personal-best query (Phase 6.7) ----------------------


def test_loaded_sets_returns_only_rows_that_carry_both_numbers(app, add):
    """The filter here is about NULL columns, not about training: a set missing
    either number cannot support a one-rep-max estimate at all."""
    add("2026-07-28", "Barbell_Squat", [
        {"weight": 100, "reps": 5},
        {"weight": 100},           # no reps
        {"reps": 5},               # no weight
        {},                        # a bare count
    ])

    with app.app_context():
        rows = loaded_sets(TEST_USER_ID, date(2026, 7, 1), date(2026, 7, 31))

    assert rows == [("Barbell_Squat", 100.0, 5, date(2026, 7, 28))]


def test_loaded_sets_excludes_warm_ups(app, add):
    add("2026-07-28", "Barbell_Squat", [
        {"weight": 200, "reps": 1, "set_type": "warmup"},
        {"weight": 100, "reps": 5},
    ])

    with app.app_context():
        rows = loaded_sets(TEST_USER_ID, date(2026, 7, 1), date(2026, 7, 31))

    assert [row[1] for row in rows] == [100.0]


def test_loaded_sets_respects_the_range(app, add):
    add("2026-06-01", "Barbell_Squat", [{"weight": 90, "reps": 5}])
    add("2026-07-28", "Barbell_Squat", [{"weight": 100, "reps": 5}])

    with app.app_context():
        rows = loaded_sets(TEST_USER_ID, date(2026, 7, 1), date(2026, 7, 31))

    assert [row[1] for row in rows] == [100.0]


# ---- The trainer setup on the user row (Phase 5 carryover) ------------------


def test_trainer_setup_is_unset_for_a_fresh_account(app, client):
    """None, not a dict of Nones: "never chosen" is one check at the call site."""
    with app.app_context():
        assert get_trainer_setup(TEST_USER_ID) is None


def test_trainer_setup_round_trips(app, client):
    with app.app_context():
        set_trainer_setup(TEST_USER_ID, "beginner", 3, 45)
        assert get_trainer_setup(TEST_USER_ID) == {
            "experience": "beginner",
            "sessions_per_week": 3,
            "minutes_per_session": 45,
        }


def test_setting_the_trainer_setup_twice_overwrites(app, client):
    with app.app_context():
        set_trainer_setup(TEST_USER_ID, "beginner", 3, 45)
        set_trainer_setup(TEST_USER_ID, "advanced", 6, 90)
        assert get_trainer_setup(TEST_USER_ID)["experience"] == "advanced"
        assert get_trainer_setup(TEST_USER_ID)["sessions_per_week"] == 6


def test_the_trainer_setup_is_scoped_to_its_account(app, client, other_client):
    """Two accounts, two setups. A missing WHERE shows up here."""
    with app.app_context():
        set_trainer_setup(TEST_USER_ID, "beginner", 3, 45)
        set_trainer_setup(OTHER_USER_ID, "advanced", 6, 90)
        assert get_trainer_setup(TEST_USER_ID)["experience"] == "beginner"
        assert get_trainer_setup(OTHER_USER_ID)["experience"] == "advanced"
