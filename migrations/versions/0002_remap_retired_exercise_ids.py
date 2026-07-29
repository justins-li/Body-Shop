"""Move pre-Phase-2 exercise ids onto the vendored catalog

Phase 2 replaced four hand-written exercise ids with free-exercise-db's, and
shipped ``flask --app app remap-exercises`` to carry existing rows across. That
left two mechanisms for changing exercise ids; this is the surviving one, and the
command is gone.

The mapping is written out here rather than imported from
``app.exercises.RETIRED_EXERCISE_IDS``. A migration is a historical record: if it
imported a constant that a later commit could edit, what this revision did to a
database would depend on when it was run.

Safe on a database that never held the old ids — it matches nothing.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-29

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | None = None
depends_on: str | None = None

#: Frozen copy of app.exercises.RETIRED_EXERCISE_IDS as of Phase 3.
RETIRED_EXERCISE_IDS: dict[str, str] = {
    "bench_press": "Barbell_Bench_Press_-_Medium_Grip",
    "pull_ups": "Pullups",
    "squat": "Barbell_Squat",
    "sit_ups": "Sit-Up",
}

_UPDATE = sa.text(
    "UPDATE workout_entry SET exercise_id = :new_id WHERE exercise_id = :old_id"
)


def upgrade() -> None:
    connection = op.get_bind()
    for old_id, new_id in RETIRED_EXERCISE_IDS.items():
        connection.execute(_UPDATE, {"old_id": old_id, "new_id": new_id})


def downgrade() -> None:
    """Restore the retired ids.

    Lossy in one narrow case: an entry logged against ``Barbell_Squat`` *after*
    the upgrade becomes ``squat`` here, which is indistinguishable from one that
    was always ``squat``. Reversing a data migration cannot do better without a
    column to record where each row came from, which is not worth a table change
    for a downgrade that only exists for symmetry.
    """
    connection = op.get_bind()
    for old_id, new_id in RETIRED_EXERCISE_IDS.items():
        connection.execute(_UPDATE, {"old_id": new_id, "new_id": old_id})
