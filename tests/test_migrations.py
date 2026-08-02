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
from app.tables import metadata, user, workout_entry, workout_set

from conftest import TEST_DATABASE_URL

#: An owner id for the tests that need one. Any UUID does.
OWNER = "11111111-1111-4111-8111-111111111111"

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
    """Pinned to 0004, not head: revision 0005 wipes every row on its way past.

    What this test is about is 0002 leaving an un-retired id alone, which is a
    statement about 0002 — running it through the Phase 5 wipe would assert
    nothing except that the wipe works, which its own test covers.
    """
    application, to = migrated
    engine = to("0001")
    insert_legacy(engine, "Barbell_Squat")

    to("0004")

    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT exercise_id FROM workout_entry")
        ).scalars().all() == ["Barbell_Squat"]


def test_revision_0005_wipes_existing_history(migrated):
    """The destructive step, asserted rather than left implicit.

    A backfill onto a seed account would have carried single-user development
    history into the multi-user world and left a permanent "who is user 1"
    question. The wipe is the decision; this is the test that says so out loud,
    so nobody later "fixes" it as a bug.
    """
    application, to = migrated
    engine = to("0004")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id) "
                "VALUES ('2026-07-28', 'Barbell_Squat')"
            )
        )

    to("0005")

    with engine.connect() as connection:
        assert connection.execute(
            sa.select(sa.func.count()).select_from(workout_entry)
        ).scalar() == 0
        assert connection.execute(
            sa.select(sa.func.count()).select_from(workout_set)
        ).scalar() == 0


def test_revision_0005_requires_an_owner_for_every_entry(migrated):
    """The column is NOT NULL and the foreign key is real on both dialects."""
    application, to = migrated
    engine = to("head")

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.insert(workout_entry).values(
                    user_id="99999999-9999-4999-8999-999999999999",
                    entry_date=date(2026, 7, 28),
                    exercise_id="Barbell_Squat",
                )
            )


def test_revision_0005_cascades_from_the_user(migrated):
    """Deleting an account is one DELETE; the cascade does the rest."""
    application, to = migrated
    engine = to("head")

    with engine.begin() as connection:
        connection.execute(sa.insert(user).values(id=OWNER, email="o@example.com"))
        result = connection.execute(
            sa.insert(workout_entry).values(
                user_id=OWNER,
                entry_date=date(2026, 7, 28),
                exercise_id="Barbell_Squat",
            )
        )
        connection.execute(
            sa.insert(workout_set).values(
                id="0" * 32,
                entry_id=int(result.inserted_primary_key[0]),
                set_index=1,
                set_type="normal",
            )
        )

    with engine.begin() as connection:
        connection.execute(sa.delete(user).where(user.c.id == OWNER))

    with engine.connect() as connection:
        assert connection.execute(
            sa.select(sa.func.count()).select_from(workout_entry)
        ).scalar() == 0
        assert connection.execute(
            sa.select(sa.func.count()).select_from(workout_set)
        ).scalar() == 0


def test_revision_0003_preserves_dates_across_the_type_change(migrated):
    """The whole point of the conversion: no history is lost or shifted."""
    application, to = migrated
    engine = to("0002")
    insert_legacy(engine, "Barbell_Squat", day="2026-07-28", sets=5)

    to("0003")

    # Pinned to 0003, where `sets` still exists as a column — app/tables.py's
    # workout_entry no longer declares it, so a local typed handle is used
    # instead of the metadata's, purely to keep DATE coercion on the read.
    entry_at_0003 = sa.table(
        "workout_entry",
        sa.column("entry_date", sa.Date),
        sa.column("sets", sa.Integer),
    )
    with engine.connect() as connection:
        row = connection.execute(sa.select(entry_at_0003)).one()

    assert row.entry_date == date(2026, 7, 28)
    assert row.sets == 5


def test_revision_0003_keeps_the_sets_check_constraint(migrated):
    """SQLite cannot reflect CHECK constraints, so a batch rebuild can drop one.

    Pinned to 0003 rather than head: revision 0004 removes the column, and the
    point of this test is that 0003 did not silently lose the constraint on its
    way past.
    """
    application, to = migrated
    engine = to("0003")

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                    "VALUES ('2026-07-28', 'Barbell_Squat', 0)"
                )
            )


def test_the_chain_downgrades_to_base(migrated):
    """Every revision's downgrade runs, so a bad deploy can be backed out."""
    application, to = migrated
    engine = to("head")
    with engine.begin() as connection:
        # An entry needs an owner from 0005 on, and the foreign key is enforced
        # on SQLite too — app/db.py turns it on per connection.
        connection.execute(
            sa.insert(user).values(id=OWNER, email="owner@example.com")
        )
        connection.execute(
            sa.insert(workout_entry).values(
                user_id=OWNER,
                entry_date=date(2026, 7, 28),
                exercise_id="Barbell_Squat",
            )
        )

    downgrade_db("base", app=application)

    inspector = sa.inspect(engine)
    assert not inspector.has_table("workout_entry")
    assert not inspector.has_table("workout_set")
    assert not inspector.has_table("user")


def test_revision_0004_backfills_one_set_per_counted_set(migrated):
    """Existing history keeps its count and gains no invented weights."""
    application, to = migrated
    engine = to("0003")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-28', 'Barbell_Squat', 4)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-27', 'Pullups', 2)"
            )
        )

    to("0004")

    with engine.connect() as connection:
        rows = connection.execute(
            sa.select(workout_set).order_by(
                workout_set.c.entry_id, workout_set.c.set_index
            )
        ).all()

    assert len(rows) == 6
    by_entry: dict[int, list] = {}
    for row in rows:
        by_entry.setdefault(row.entry_id, []).append(row)
    assert sorted(len(v) for v in by_entry.values()) == [2, 4]

    for sets in by_entry.values():
        # 1-based and contiguous.
        assert [r.set_index for r in sets] == list(range(1, len(sets) + 1))
        # Do not invent weights: an old row knew a count and nothing else.
        assert all(r.weight is None and r.reps is None and r.rpe is None for r in sets)
        assert all(r.set_type == "normal" for r in sets)


def test_revision_0004_gives_every_set_a_distinct_uuid(migrated):
    """Ids are UUIDs so Phase 10's offline queue can mint them client-side."""
    from uuid import UUID

    application, to = migrated
    engine = to("0003")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-28', 'Barbell_Squat', 3)"
            )
        )

    to("0004")

    with engine.connect() as connection:
        ids = connection.execute(sa.select(workout_set.c.id)).scalars().all()

    assert len(set(ids)) == 3
    # Parse rather than compare strings: the type stores 32-char hex and reads
    # back the hyphenated 36-char form.
    assert all(UUID(str(value)) for value in ids)


def test_revision_0004_survives_a_round_trip(migrated):
    """Down and back up again, with the count intact both ways."""
    application, to = migrated
    engine = to("0003")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-28', 'Barbell_Squat', 5)"
            )
        )

    to("0004")
    downgrade_db("0003", app=application)

    with engine.connect() as connection:
        assert connection.execute(
            sa.text("SELECT sets FROM workout_entry")
        ).scalar() == 5

    to("0004")

    with engine.connect() as connection:
        assert connection.execute(
            sa.select(sa.func.count()).select_from(workout_set)
        ).scalar() == 5


def test_revision_0004_preserves_dates_through_the_sqlite_rebuild(migrated):
    """The parent is rebuilt on SQLite, so 0003's CAST trap is back in range."""
    application, to = migrated
    engine = to("0003")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO workout_entry (entry_date, exercise_id, sets) "
                "VALUES ('2026-07-28', 'Barbell_Squat', 3)"
            )
        )

    to("0004")

    # Pinned to 0004, so a local typed handle rather than the metadata's — which
    # now carries the user_id column revision 0005 adds. Same reason the 0003
    # test declares its own handle.
    entry_at_0004 = sa.table(
        "workout_entry",
        sa.column("entry_date", sa.Date),
        sa.column("exercise_id"),
    )
    with engine.connect() as connection:
        row = connection.execute(sa.select(entry_at_0004)).one()
    assert row.entry_date == date(2026, 7, 28)


def test_revision_0006_leaves_existing_accounts_unset(migrated):
    """A row that predates the trainer setup must read as "never chosen".

    Not backfilled with the defaults: the first-run dialog reads NULL to decide
    whether this account has answered, and a backfill would tell it everyone had.
    """
    application, to = migrated
    engine = to("0005")

    with engine.begin() as connection:
        connection.execute(
            sa.insert(sa.table("user", sa.column("id"), sa.column("email"))).values(
                id="33333333-3333-4333-8333-333333333333",
                email="before@example.com",
            )
        )

    to("0006")

    with engine.connect() as connection:
        row = connection.execute(
            sa.select(
                user.c.experience, user.c.sessions_per_week, user.c.minutes_per_session
            )
        ).one()

    assert row == (None, None, None)
