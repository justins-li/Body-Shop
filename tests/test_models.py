"""Tests for data-layer behaviour not reached through the API.

The Phase 2 id remap used to be tested here. It is a migration now, so its tests
live in ``test_migrations.py`` — this file is what is left: the recent-exercise
query behind the ``/log`` picker's default tab.
"""

from __future__ import annotations

from datetime import date

import sqlalchemy as sa

from app.db import get_db
from app.models import recent_exercise_ids
from app.tables import workout_entry

SQUAT = "Barbell_Squat"


def log_entry(exercise_id: str, sets: int = 3, day: str = "2026-07-28") -> None:
    """Insert directly, bypassing the API and its validation."""
    db = get_db()
    db.execute(
        sa.insert(workout_entry).values(
            entry_date=date.fromisoformat(day), exercise_id=exercise_id, sets=sets
        )
    )
    db.commit()


def test_recent_ids_are_capped_by_limit(app):
    with app.app_context():
        for day, exercise in [
            ("2026-07-26", "Sit-Up"),
            ("2026-07-27", "Pullups"),
            ("2026-07-28", SQUAT),
        ]:
            log_entry(exercise, 3, day=day)

        assert recent_exercise_ids(2) == [SQUAT, "Pullups"]


def test_recent_ids_deduplicate_by_exercise(app):
    with app.app_context():
        log_entry(SQUAT, 3, day="2026-07-27")
        log_entry(SQUAT, 4, day="2026-07-28")

        assert recent_exercise_ids() == [SQUAT]
