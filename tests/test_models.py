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
from app.models import recent_exercise_ids
from conftest import TEST_USER_ID
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
