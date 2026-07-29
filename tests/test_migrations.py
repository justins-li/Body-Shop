"""Tests for the migration chain itself.

Phase 3 introduced a failure mode the app did not have before: ``app/tables.py``
and ``migrations/versions/`` can disagree. Editing a column without writing a
revision leaves the tests passing — the suite builds SQLite from the metadata —
and the schema wrong everywhere the migrations are what ran.
:func:`test_migrations_match_the_metadata` is the guard against that.

These tests run whichever dialect the suite is pointed at, so on a Postgres run
they also check that the migrations execute against real Postgres, which is where
``postgresql_using`` and batch-mode rebuilds actually get exercised.
"""

from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext

from app import create_app
from app.db import downgrade_db, get_engine, init_db, upgrade_db
from app.tables import metadata, workout_entry

from conftest import TEST_DATABASE_URL

RETIRED = {
    "bench_press": "Barbell_Bench_Press_-_Medium_Grip",
    "pull_ups": "Pullups",
    "squat": "Barbell_Squat",
    "sit_ups": "Sit-Up",
}


@pytest.fixture
def migrated(tmp_path):
    """An app on an empty database, plus a helper to migrate it to a revision.

    On a Postgres run this shares the suite's database, so teardown puts it back
    at head — otherwise a test that stopped at ``0001`` would leave the schema
    wrong for everything that ran afterwards.
    """
    url = TEST_DATABASE_URL or f"sqlite:///{tmp_path / 'migrated.sqlite3'}"
    application = create_app("testing", DATABASE_URL=url)

    with application.app_context():
        engine = get_engine(application)
        with engine.begin() as connection:
            metadata.drop_all(connection)
            connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))

        def to(revision: str = "head"):
            upgrade_db(revision, app=application)
            return engine

        yield application, to

        if TEST_DATABASE_URL:
            init_db(application)
        else:
            engine.dispose()


def insert_legacy(engine, exercise_id: str, day: str = "2026-07-28", sets: int = 3):
    """Insert against the pre-0003 schema, where entry_date is still TEXT."""
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES (:day, :exercise_id, :sets)"
            ),
            {"day": day, "exercise_id": exercise_id, "sets": sets},
        )


def test_migrations_match_the_metadata(migrated):
    """`upgrade head` must produce exactly what app/tables.py describes.

    Compares via Alembic's own autogenerate diff, which is the same machinery
    that would write the revision — so an empty diff means there is no revision
    left to write.
    """
    application, to = migrated
    engine = to("head")

    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"compare_type": True, "target_metadata": metadata}
        )
        diff = compare_metadata(context, metadata)

    assert diff == [], (
        "app/tables.py and migrations/versions/ disagree. Alembic wants to "
        f"apply: {diff!r}. Write a revision in the same commit as the metadata "
        "change."
    )


def test_revision_0002_remaps_every_retired_id(migrated):
    application, to = migrated
    engine = to("0001")

    for old_id in RETIRED:
        insert_legacy(engine, old_id)
    # Two rows for one id, to prove the update is not a LIMIT 1.
    insert_legacy(engine, "pull_ups", day="2026-07-27")
    # An id that was never retired must come through untouched.
    insert_legacy(engine, "Barbell_Squat", day="2026-07-26")

    to("0002")

    with engine.connect() as connection:
        ids = connection.execute(
            sa.text("SELECT exercise_id FROM workout_entry")
        ).scalars().all()

    assert sorted(ids) == sorted(
        [*RETIRED.values(), "Pullups", "Barbell_Squat"]
    )
    assert not set(ids) & set(RETIRED), "a retired id survived the remap"


def test_revision_0002_is_safe_on_a_database_that_never_held_old_ids(migrated):
    application, to = migrated
    engine = to("0001")
    insert_legacy(engine, "Barbell_Squat")

    to("head")

    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT exercise_id FROM workout_entry")
        ).scalars().all() == ["Barbell_Squat"]


def test_revision_0003_preserves_dates_across_the_type_change(migrated):
    """The whole point of the conversion: no history is lost or shifted."""
    application, to = migrated
    engine = to("0002")
    insert_legacy(engine, "Barbell_Squat", day="2026-07-28", sets=5)

    to("0003")

    with engine.connect() as connection:
        row = connection.execute(sa.select(workout_entry)).one()

    assert row.entry_date == date(2026, 7, 28)
    assert row.sets == 5


def test_revision_0003_keeps_the_sets_check_constraint(migrated):
    """SQLite cannot reflect CHECK constraints, so a batch rebuild can drop one.

    0003 passes it through ``table_args`` for exactly this reason. Asserting on
    behaviour rather than reflection is deliberate — a dropped constraint is
    invisible to the inspector on SQLite and only shows up when bad data lands.
    """
    application, to = migrated
    engine = to("head")

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.insert(workout_entry).values(
                    entry_date=date(2026, 7, 28), exercise_id="Barbell_Squat", sets=0
                )
            )


def test_the_chain_downgrades_to_base(migrated):
    """Every revision's downgrade runs, so a bad deploy can be backed out."""
    application, to = migrated
    engine = to("head")
    with engine.begin() as connection:
        connection.execute(
            sa.insert(workout_entry).values(
                entry_date=date(2026, 7, 28), exercise_id="Barbell_Squat", sets=3
            )
        )

    downgrade_db("base", app=application)

    inspector = sa.inspect(engine)
    assert not inspector.has_table("workout_entry")
