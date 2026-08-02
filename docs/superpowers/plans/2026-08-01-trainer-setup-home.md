# Trainer Setup's Home — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the Phase 6 trainer setup off `localStorage` and onto the `user` row, so an account's weekly targets follow it to any device.

**Architecture:** Three nullable columns on `user` (all NULL = never chosen), read by a new `_user_profile()` in `app/api.py` and written by a new `PUT /api/profile`. The `experience`/`sessions`/`minutes` query parameters disappear from `/api/summary/week` and `/api/progress/graph`. On the client, `localStorage` is demoted from store to read-through cache, so `loadProfile()` stays synchronous and `setgrid.js`'s RPE gate needs no rework.

**Tech Stack:** Flask, SQLAlchemy Core, Alembic, pytest, vanilla ES modules. No new dependencies — this adds none and must not.

Full design: [docs/superpowers/specs/2026-08-01-trainer-setup-home-design.md](../specs/2026-08-01-trainer-setup-home-design.md).

## Global Constraints

- **SQL only in `app/models.py`.** Services and routes never call `get_db()`. Queries are SQLAlchemy Core expressions, never strings.
- **`user_id` is the first positional parameter** of every `models.py` function that touches user-owned data. Positional-and-first is the safety property: a stale call site must fail as a `TypeError`, not query across users.
- **A metadata change needs an Alembic revision in the same commit.** `tests/test_migrations.py` compares the two with Alembic's own autogenerate diff.
- **Nothing downstream may hard-code 20 or 10.** Consumers read `target` off the group or `profile.targets`.
- **The client never computes a target.** It renders `profile.targets` from the response.
- **JS has zero dependencies and no bundler.** ES modules, served as written.
- **Python style:** `from __future__ import annotations` at module top, type hints on signatures, docstrings on public functions.
- **CHECK constraint names in migrations are bare tokens** (`sets_positive`); UNIQUE constraints are left unnamed so the convention names them. This plan adds neither.
- **Run `python -m pytest -q` before every commit.** CI runs only `pytest -q`, so a green local run is the whole signal.
- **Commit messages:** present tense subject saying what changed; body saying why. **Never add attribution trailers** — no `Co-Authored-By`, no "Generated with".
- **Work directly on `main`.** No feature branch, no PR.

---

### Task 1: The columns and the migration

**Files:**
- Modify: `app/tables.py` (the `user` table definition, around line 52)
- Create: `migrations/versions/0006_trainer_setup_on_user.py`
- Test: `tests/test_migrations.py` (existing tests cover this; one new test added)

**Interfaces:**
- Consumes: nothing.
- Produces: three nullable columns on the `user` table — `experience` (`sa.Text`), `sessions_per_week` (`sa.Integer`), `minutes_per_session` (`sa.Integer`). Alembic revision id `"0006"`, `down_revision = "0005"`.

- [ ] **Step 1: Add the columns to the metadata**

In `app/tables.py`, inside the `user = sa.Table(...)` call, after the `created_at` column and before the closing paren:

```python
    # The Phase 6 trainer setup, moved off localStorage in the Phase 5
    # carryover. **All three NULL means "never chosen"**, which is a different
    # fact from "chose the defaults": it is what the first-run dialog reads to
    # decide whether this account has already answered, and it is what keeps
    # DEFAULT_EXPERIENCE / REFERENCE_PLAN meaning *today's* default rather than
    # being frozen into every row.
    #
    # No CHECK constraints. `training.resolve_profile` clamps every value on the
    # way in, so the column can only receive something in range; a check
    # duplicating MIN_SESSIONS/MAX_MINUTES would add a migration to every future
    # tuning of what are documented as conventions, and a check on `experience`
    # would need rewriting to add a fourth level.
    sa.Column("experience", sa.Text, nullable=True),
    sa.Column("sessions_per_week", sa.Integer, nullable=True),
    sa.Column("minutes_per_session", sa.Integer, nullable=True),
```

- [ ] **Step 2: Run the migration test to verify it now fails**

Run: `python -m pytest tests/test_migrations.py::test_migrations_match_the_metadata -q`

Expected: FAIL. The autogenerate diff reports three `add_column` operations the migration chain does not perform — the metadata and `upgrade head` no longer agree.

- [ ] **Step 3: Write the revision**

Create `migrations/versions/0006_trainer_setup_on_user.py`:

```python
"""Give the trainer setup a home on the user row

The Phase 5 carryover. Phase 6 shipped ahead of Phase 5 and had no user row to
hang the trainer setup off, so it became a ``localStorage`` preference sent with
every request. This is the column it should always have had.

**Nullable, and not backfilled.** Three NULLs means "this account has never
chosen", which is deliberately distinct from "chose the defaults" — the first-run
dialog reads it, and backfilling today's defaults would freeze them into every
existing row. ``app.training.resolve_profile`` already falls back per absent
input, so a row of NULLs resolves to exactly the grading the app did before this
revision.

**No ``batch_alter_table``.** Adding a nullable column with no constraint and no
default is the one ``ALTER`` SQLite supports natively, so batch mode would rebuild
the table for nothing — and a rebuild is what revisions 0003 and 0005 had to
reason carefully about. Nothing here changes a type, so 0003's CAST trap is out
of range too.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-01

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("user", sa.Column("experience", sa.Text(), nullable=True))
    op.add_column("user", sa.Column("sessions_per_week", sa.Integer(), nullable=True))
    op.add_column(
        "user", sa.Column("minutes_per_session", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    """Forget every account's trainer setup.

    Lossy, but only of a preference: a downgraded database grades every user
    against the baseline targets again, which is what the app did before Phase 6.
    """
    op.drop_column("user", "minutes_per_session")
    op.drop_column("user", "sessions_per_week")
    op.drop_column("user", "experience")
```

- [ ] **Step 4: Run the migration test to verify it passes**

Run: `python -m pytest tests/test_migrations.py -q`

Expected: PASS, all tests — including `test_the_chain_downgrades_to_base`, which now runs `0006`'s `downgrade()` on the way down.

- [ ] **Step 5: Write the new revision test**

Append to `tests/test_migrations.py`:

```python
def test_revision_0006_leaves_existing_accounts_unset(migrated):
    """A row that predates the trainer setup must read as "never chosen".

    Not backfilled with the defaults: the first-run dialog reads NULL to decide
    whether this account has answered, and a backfill would tell it everyone had.
    """
    app = migrated("0005")
    with app.app_context():
        with get_engine(app).begin() as connection:
            connection.execute(
                sa.text(
                    'INSERT INTO "user" (id, email) VALUES (:id, :email)'
                ),
                {"id": "33333333-3333-4333-8333-333333333333",
                 "email": "before@example.com"},
            )

    app = migrated("0006")
    with app.app_context():
        with get_engine(app).begin() as connection:
            row = connection.execute(
                sa.text(
                    'SELECT experience, sessions_per_week, minutes_per_session '
                    'FROM "user"'
                )
            ).one()
    assert row == (None, None, None)
```

If `get_engine` or `sa` is not already imported at the top of `tests/test_migrations.py`, add the imports the other tests in that file use — check the existing header before adding anything, and reuse the `migrated` fixture's own idioms for opening a connection rather than inventing a second style.

- [ ] **Step 6: Run the new test**

Run: `python -m pytest tests/test_migrations.py::test_revision_0006_leaves_existing_accounts_unset -q`

Expected: PASS.

- [ ] **Step 7: Run the whole suite**

Run: `python -m pytest -q`

Expected: PASS. Nothing reads the new columns yet, so no other test can be affected.

- [ ] **Step 8: Commit**

```bash
git add app/tables.py migrations/versions/0006_trainer_setup_on_user.py tests/test_migrations.py
git commit -m "Give the trainer setup a column on the user row

Three nullable columns, and deliberately not backfilled: all three NULL
means this account has never chosen a setup, which the first-run dialog
needs to tell apart from having chosen the defaults. Nothing reads them
yet."
```

---

### Task 2: Reading and writing the setup in the data layer

**Files:**
- Modify: `app/models.py` (add two functions near `get_user`, around line 170)
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: the columns from Task 1.
- Produces:
  - `get_trainer_setup(user_id: str) -> dict | None` — `None` when all three columns are NULL, otherwise `{"experience": str | None, "sessions_per_week": int | None, "minutes_per_session": int | None}`.
  - `set_trainer_setup(user_id: str, experience: str, sessions_per_week: int, minutes_per_session: int) -> None`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_models.py`:

```python
# ---- The trainer setup on the user row (Phase 5 carryover) ------------------


def test_trainer_setup_is_unset_for_a_fresh_account():
    """None, not a dict of Nones: "never chosen" is one check at the call site."""
    assert get_trainer_setup(TEST_USER_ID) is None


def test_trainer_setup_round_trips():
    set_trainer_setup(TEST_USER_ID, "beginner", 3, 45)
    assert get_trainer_setup(TEST_USER_ID) == {
        "experience": "beginner",
        "sessions_per_week": 3,
        "minutes_per_session": 45,
    }


def test_setting_the_trainer_setup_twice_overwrites():
    set_trainer_setup(TEST_USER_ID, "beginner", 3, 45)
    set_trainer_setup(TEST_USER_ID, "advanced", 6, 90)
    assert get_trainer_setup(TEST_USER_ID)["experience"] == "advanced"
    assert get_trainer_setup(TEST_USER_ID)["sessions_per_week"] == 6


def test_the_trainer_setup_is_scoped_to_its_account():
    """Two accounts, two setups. A missing WHERE shows up here."""
    ensure_user(OTHER_USER_ID, "other@example.com")
    set_trainer_setup(TEST_USER_ID, "beginner", 3, 45)
    set_trainer_setup(OTHER_USER_ID, "advanced", 6, 90)
    assert get_trainer_setup(TEST_USER_ID)["experience"] == "beginner"
    assert get_trainer_setup(OTHER_USER_ID)["experience"] == "advanced"
```

These need `get_trainer_setup`, `set_trainer_setup` and `ensure_user` added to the `from app.models import ...` line at the top of the file, and `OTHER_USER_ID` added to the `from conftest import TEST_USER_ID` line.

Every test in this file runs inside an app context — check how the existing tests in `tests/test_models.py` obtain one (they use the `app`/`client` fixtures) and follow the same pattern exactly. If the existing tests take a fixture argument to get their context, these four take it too.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_models.py -q`

Expected: FAIL at collection with `ImportError: cannot import name 'get_trainer_setup' from 'app.models'`.

- [ ] **Step 3: Implement both functions**

In `app/models.py`, immediately after `get_user` and before `delete_user`:

```python
def get_trainer_setup(user_id: str) -> dict | None:
    """The account's stored trainer setup, or ``None`` if it has never chosen one.

    ``None`` rather than a dict of ``None``s so "never chosen" is a single check
    at the call site instead of three — the first-run dialog turns on exactly
    this distinction, and it is why the columns are nullable and unbackfilled.

    The values are returned raw, exactly as stored.
    :func:`app.training.resolve_profile` is what clamps and falls back, and it
    does so identically for a missing value and a nonsense one.
    """
    row = get_db().execute(
        sa.select(
            user.c.experience, user.c.sessions_per_week, user.c.minutes_per_session
        ).where(user.c.id == user_id)
    ).first()
    if row is None or (
        row.experience is None
        and row.sessions_per_week is None
        and row.minutes_per_session is None
    ):
        return None
    return {
        "experience": row.experience,
        "sessions_per_week": row.sessions_per_week,
        "minutes_per_session": row.minutes_per_session,
    }


def set_trainer_setup(
    user_id: str,
    experience: str,
    sessions_per_week: int,
    minutes_per_session: int,
) -> None:
    """Store the account's trainer setup, replacing whatever was there.

    The row is guaranteed to exist: every authenticated request runs
    ``ensure_user`` first. Callers are expected to pass values that have already
    been through :func:`app.training.resolve_profile`, so the column never holds
    a setup the app would refuse to use.
    """
    db = get_db()
    db.execute(
        sa.update(user)
        .where(user.c.id == user_id)
        .values(
            experience=experience,
            sessions_per_week=sessions_per_week,
            minutes_per_session=minutes_per_session,
        )
    )
    db.commit()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python -m pytest tests/test_models.py -q`

Expected: PASS.

- [ ] **Step 5: Run the whole suite**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/models.py tests/test_models.py
git commit -m "Read and write the trainer setup in the data layer

get_trainer_setup returns None for an account that has never chosen,
rather than a dict of Nones, so the first-run gate is one check. Both
take user_id first positionally, so a stale call site fails loudly."
```

---

### Task 3: The API — `GET`/`PUT /api/profile`, and the query parameters go

**Files:**
- Modify: `app/api.py` (`_query_profile` at lines 58–70; `get_weekly_summary` and `get_progress_graph` at lines 294–325; new routes near `get_me`)
- Modify: `app/training.py` (module docstring only — the closing "No ownership yet" paragraph)
- Test: `tests/test_api.py` (lines ~370–445 are rewritten), `tests/test_ownership.py`

**Interfaces:**
- Consumes: `get_trainer_setup` / `set_trainer_setup` from Task 2; `resolve_profile(experience, sessions, minutes)` and `TrainerProfile.to_dict()`, both unchanged.
- Produces:
  - `GET /api/profile` → `{"profile": {…TrainerProfile.to_dict()…}, "configured": bool}`
  - `PUT /api/profile` with body `{"experience": str, "sessions_per_week": int, "minutes_per_session": int}` → the same shape, `"configured": true`.
  - `_user_profile() -> TrainerProfile` replacing `_query_profile()`.

- [ ] **Step 1: Write the failing tests**

Replace the six trainer-setup tests in `tests/test_api.py` (from `test_weekly_summary_defaults_to_the_baseline_targets` through `test_the_graph_colours_against_the_same_setup`, roughly lines 370–445) with:

```python
# ---- The trainer setup, on the user row (Phase 5 carryover) ----------------


def test_the_profile_starts_unconfigured_at_the_baseline(client):
    """An account that has never chosen grades exactly as it did before Phase 6."""
    payload = client.get("/api/profile").get_json()
    assert payload["configured"] is False
    assert payload["profile"]["experience"] == "experienced"
    assert payload["profile"]["volume_scale"] == 1.0
    assert payload["profile"]["targets"]["chest"] == 20


def test_putting_a_profile_stores_it_and_echoes_it(client):
    payload = client.put(
        "/api/profile",
        json={"experience": "beginner", "sessions_per_week": 6,
              "minutes_per_session": 90},
    ).get_json()
    assert payload["configured"] is True
    assert payload["profile"]["experience"] == "beginner"
    # The week is roomy, so the beginner level is what binds: 0.6 of baseline.
    assert payload["profile"]["limited_by"] == "experience"
    assert payload["profile"]["targets"]["chest"] == 12

    # And it survives the request that wrote it.
    assert client.get("/api/profile").get_json() == payload


def test_a_bad_profile_is_clamped_rather_than_400ing(client):
    """It arrives from a settings control, so the honest answer to an
    out-of-range number is the nearest one that works — and the *resolved*
    values are what get stored, so the column can never hold a setup the app
    would refuse to use."""
    response = client.put(
        "/api/profile",
        json={"experience": "wizard", "sessions_per_week": 400,
              "minutes_per_session": -9},
    )
    assert response.status_code == 200
    stored = response.get_json()["profile"]
    assert stored["experience"] == "experienced"
    assert stored["sessions_per_week"] == 14
    assert stored["minutes_per_session"] == 15
    assert client.get("/api/profile").get_json()["profile"] == stored


def test_the_weekly_summary_defaults_to_the_baseline_targets(client):
    payload = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert payload["muscles"]["chest"]["target"] == 20
    assert payload["muscles"]["abs"]["target"] == 10
    assert payload["profile"]["experience"] == "experienced"


def test_the_weekly_summary_grades_against_the_stored_setup(client):
    client.put(
        "/api/profile",
        json={"experience": "beginner", "sessions_per_week": 6,
              "minutes_per_session": 90},
    )
    payload = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert payload["profile"]["limited_by"] == "experience"
    assert payload["muscles"]["chest"]["target"] == 12
    assert payload["muscles"]["abs"]["target"] == 6


def test_a_short_week_lowers_the_targets(client):
    client.put(
        "/api/profile",
        json={"experience": "advanced", "sessions_per_week": 2,
              "minutes_per_session": 30},
    )
    payload = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert payload["profile"]["limited_by"] == "plan"
    assert payload["muscles"]["chest"]["target"] < 20


def test_the_profile_echoes_the_targets_it_graded_against(client):
    """The page renders these rather than re-deriving them, so the two halves of
    the payload must agree."""
    client.put("/api/profile", json={"experience": "beginner",
                                     "sessions_per_week": 5,
                                     "minutes_per_session": 75})
    payload = client.get("/api/summary/week?date=2026-07-28").get_json()
    targets = payload["profile"]["targets"]
    for muscle, info in payload["muscles"].items():
        assert info["target"] == targets[muscle], muscle


def test_the_query_string_can_no_longer_set_the_targets(client):
    """One source of truth. A stale client sending the old parameters must be
    graded against the account's setup, not its own idea of one."""
    payload = client.get(
        "/api/summary/week?date=2026-07-28"
        "&experience=beginner&sessions=2&minutes=30"
    ).get_json()
    assert payload["profile"]["experience"] == "experienced"
    assert payload["muscles"]["chest"]["target"] == 20


def test_grading_scales_so_a_week_can_cross_its_target(client, add):
    """The point of the whole feature: the same sets read differently against a
    smaller target."""
    add("2026-07-28", BENCH, sets=14)

    baseline = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert baseline["muscles"]["chest"]["state"] == "trained"

    client.put(
        "/api/profile",
        json={"experience": "beginner", "sessions_per_week": 6,
              "minutes_per_session": 90},
    )
    scaled = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert scaled["muscles"]["chest"]["state"] == "over"


def test_the_graph_colours_against_the_same_setup(client, add):
    """Node colour *is* the body map's grading, so the two pages must not
    disagree about the same week — and now they cannot, because neither is
    told the setup by its caller."""
    add("2026-07-28", BENCH, sets=14)
    client.put(
        "/api/profile",
        json={"experience": "beginner", "sessions_per_week": 6,
              "minutes_per_session": 90},
    )

    graph = client.get("/api/progress/graph?date=2026-07-28").get_json()
    summary = client.get("/api/summary/week?date=2026-07-28").get_json()
    assert graph["coverage"]["chest"]["state"] == summary["muscles"]["chest"]["state"]
    assert graph["coverage"]["chest"]["state"] == "over"
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python -m pytest tests/test_api.py -q -k "profile or trainer or setup or targets or graph_colours"`

Expected: FAIL. `GET /api/profile` returns 404, and `test_the_query_string_can_no_longer_set_the_targets` fails because the query string still wins.

- [ ] **Step 3: Replace `_query_profile` with `_user_profile`**

In `app/api.py`, replace the whole `_query_profile` function (lines 58–70) with:

```python
def _user_profile() -> TrainerProfile:
    """The signed-in account's trainer setup.

    The Phase 5 carryover: this used to read three query parameters, because
    Phase 6 shipped before there was a user row to hang the setup off. There is
    one now, and it is the only source — a client cannot override the targets it
    is graded against, so the summary and the graph cannot be made to disagree
    about one week.

    An account that has never chosen resolves to the default profile, which is
    the pre-Phase-6 grading exactly. ``resolve_profile`` clamps and falls back
    rather than raising, so a value stored before a bound was tuned shows the
    usual targets rather than blanking the page.
    """
    stored = get_trainer_setup(g.user_id) or {}
    return resolve_profile(
        stored.get("experience"),
        stored.get("sessions_per_week"),
        stored.get("minutes_per_session"),
    )
```

Add `get_trainer_setup` and `set_trainer_setup` to the `from .models import (...)` block at the top of the file, keeping its existing ordering style.

- [ ] **Step 4: Point the two graded endpoints at it**

In `get_weekly_summary`, replace `_query_profile()` with `_user_profile()` and replace the docstring's second paragraph:

```python
    """Weekly muscle-coverage summary for the week containing ``date``.

    Targets come from the account's stored trainer setup — see
    ``GET /api/profile``. The resolved profile comes back in the payload, so the
    page renders the targets it was graded against rather than deriving its own.
    """
```

In `get_progress_graph`, replace `_query_profile()` with `_user_profile()`. Leave its docstring's `window` paragraph alone; it is still true.

- [ ] **Step 5: Add the two routes**

In `app/api.py`, immediately after `get_me` and before `remove_account`:

```python
@bp.get("/profile")
@require_user
def get_profile():
    """The account's trainer setup, resolved, with its targets.

    ``configured`` says whether the account has ever chosen one. It is a fact
    about storage rather than about training, which is why it rides beside the
    profile instead of inside it — ``TrainerProfile`` describes a week's targets
    and has no business knowing where its inputs came from. The first-run dialog
    is the one reader: an account that has answered is never asked again, on any
    device.
    """
    configured = get_trainer_setup(g.user_id) is not None
    return jsonify({"profile": _user_profile().to_dict(), "configured": configured})


@bp.put("/profile")
@require_user
def put_profile():
    """Store the account's trainer setup.

    **Clamps rather than 400s**, for the reason the query string did: these
    arrive from a settings control, and the honest response to an out-of-range
    number is the nearest one that works. The *resolved* values are what get
    stored, so the column can never hold a setup the app would refuse to use,
    and the echoed profile is what the controls settle on — a value corrected on
    the way in corrects itself on screen rather than sitting there disagreeing
    with the bars it produced.
    """
    body = request.get_json(silent=True) or {}
    profile = resolve_profile(
        body.get("experience"),
        body.get("sessions_per_week"),
        body.get("minutes_per_session"),
    )
    set_trainer_setup(
        g.user_id,
        profile.experience.key,
        profile.plan.sessions_per_week,
        profile.plan.minutes_per_session,
    )
    return jsonify({"profile": profile.to_dict(), "configured": True})
```

- [ ] **Step 6: Run the API tests**

Run: `python -m pytest tests/test_api.py -q`

Expected: PASS.

- [ ] **Step 7: Add the ownership test**

In `tests/test_ownership.py`, inside `class TestReadsAreScoped`, after `test_the_weekly_summary`:

```python
    def test_the_trainer_setup(self, client, other_client):
        """One account's setup must never grade another's week."""
        client.put(
            "/api/profile",
            json={"experience": "beginner", "sessions_per_week": 3,
                  "minutes_per_session": 45},
        )
        mine = client.get("/api/profile").get_json()
        theirs = other_client.get("/api/profile").get_json()

        assert mine["configured"] is True
        assert theirs["configured"] is False
        assert theirs["profile"]["experience"] == "experienced"
        assert theirs["profile"]["targets"]["chest"] == 20

        # And the grading follows the account, not the request.
        their_week = other_client.get(f"/api/summary/week?date={DAY}").get_json()
        assert their_week["muscles"]["chest"]["target"] == 20
```

- [ ] **Step 8: Run the ownership tests**

Run: `python -m pytest tests/test_ownership.py -q`

Expected: PASS. A failure here is a data leak — fix the query, never the test.

- [ ] **Step 9: Correct `app/training.py`'s docstring**

The module docstring's final paragraph currently reads:

> **No ownership yet.** Phase 5 adds ``user_id`` and this becomes a column on the
> user row; until then the choice is a client preference sent with the request, so
> :func:`resolve_profile` treats every input as untrusted and falls back rather
> than raising — the same discipline ``window`` follows in
> :mod:`app.services.graph`.

Replace it with:

```
**Where the setup lives.** On the user row, as of the Phase 5 carryover — three
nullable columns, all NULL meaning the account has never chosen. It reaches this
module through ``api._user_profile``, and :func:`resolve_profile` still treats
every input as untrusted: a stored value predates any tuning of the bounds above,
and a settings control can send anything. It falls back rather than raising, the
same discipline ``window`` follows in :mod:`app.services.graph`.
```

No code in this module changes.

- [ ] **Step 10: Run the whole suite**

Run: `python -m pytest -q`

Expected: PASS. `tests/test_training.py`, `test_summary.py` and `test_graph.py` construct profiles directly and never went through the query string, so none of them move.

- [ ] **Step 11: Commit**

```bash
git add app/api.py app/training.py tests/test_api.py tests/test_ownership.py
git commit -m "Grade every week against the account's stored trainer setup

GET/PUT /api/profile own the setup, and /api/summary/week and
/api/progress/graph stop reading experience/sessions/minutes off the
query string. Two sources of truth meant a stale client could grade a
week against something other than the account's setup, and both answers
render correctly — the disagreement would have been invisible.

PUT clamps rather than 400ing, and stores the resolved values, so the
column can never hold a setup the app would refuse to use."
```

---

### Task 4: The client's read path — cache, not store

**Files:**
- Modify: `app/static/js/ui.js` (the trainer-setup block, lines ~70–133)
- Modify: `app/static/js/api.js` (the `profileQuery` import at line 15; `fetchWeeklySummary` and `fetchTrainingGraph` at lines ~172–195; two new functions)
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: `GET`/`PUT /api/profile` from Task 3.
- Produces, from `ui.js`: `loadProfile()` (unchanged signature, still synchronous) and `cacheProfile(profile)` replacing `saveProfile`. `profileQuery` is **deleted**.
- Produces, from `api.js`: `fetchProfile()` → `{profile, configured}` and `saveProfile(profile)` → `{profile, configured}`. Note the name `saveProfile` now belongs to `api.js`; `ui.js` no longer exports it.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pages.py`:

```python
def test_no_module_sends_the_trainer_setup_on_a_query_string():
    """The setup lives on the user row. A client that still sent it would be
    asking to be graded against something other than its own account's setup,
    and the server would ignore it — silently."""
    from pathlib import Path

    js = Path(__file__).resolve().parent.parent / "app" / "static" / "js"
    offenders = [
        path.name
        for path in js.glob("*.js")
        if "profileQuery" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []
```

Match the import style of the file's existing tests — if `Path` is already imported at module level there, use that rather than importing inside the function.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_pages.py::test_no_module_sends_the_trainer_setup_on_a_query_string -q`

Expected: FAIL — `assert ['api.js', 'ui.js'] == []`.

- [ ] **Step 3: Demote the cache in `ui.js`**

Replace the block comment above `const PROFILE_KEY` with:

```js
/**
 * The trainer setup — Phase 6, given a home on the user row in the Phase 5
 * carryover.
 *
 * **The server owns this. What is stored here is a cache of its answer**, so
 * that `loadProfile()` can stay synchronous: `setgrid.js` decides whether to
 * draw the RPE column while it is building markup, and making that await a
 * fetch means the column flickers in after the grid has already painted.
 *
 * Nothing writes this cache except `api.js`, from a payload that carried a
 * resolved profile. Treating it as a store is what this change ended — a second
 * device would go on grading you against whatever that browser last chose.
 *
 * **The client never computes a target from it.** The server sends back the
 * targets it graded against (`profile.targets` on the weekly summary), and
 * deriving them here as well would be two implementations of one rule.
 */
```

Rename `saveProfile` to `cacheProfile` and give it this docstring, leaving the body as it is:

```js
/**
 * Remember the server's resolved profile. Silently does nothing if storage is
 * blocked — the setup is on the account either way, and the next response
 * carries it again.
 */
export function cacheProfile(profile) {
```

Delete `profileQuery` entirely, along with its doc comment. Leave `loadProfile`, `PROFILE_KEY` and `DEFAULT_PROFILE` otherwise untouched: a browser that has not yet heard from the server must render what the server would resolve for an unconfigured account, so the pre-fetch paint is never wrong in a way the fetch then corrects.

- [ ] **Step 4: Rewrite the profile plumbing in `api.js`**

Change the import at line 15 from `import { profileQuery } from "./ui.js";` to:

```js
import { cacheProfile } from "./ui.js";
```

Replace `fetchWeeklySummary` and `fetchTrainingGraph` with:

```js
/**
 * Weekly muscle-coverage summary for the week containing `isoDate`.
 *
 * Targets come from the account's stored trainer setup, so nothing about it is
 * sent. The response echoes the profile the server graded against, and that is
 * what refreshes the local cache — see `cacheProfile`.
 */
export async function fetchWeeklySummary(isoDate) {
  const payload = await request(`/summary/week?date=${encodeURIComponent(isoDate)}`);
  if (payload && payload.profile) cacheProfile(payload.profile);
  return payload;
}

/**
 * The training graph: movements as nodes, same-day pairings as edges.
 *
 * @param {"8w"|"6m"|"all"} window
 * @param {string} isoDate - Anchors both the window and the colouring week.
 */
export async function fetchTrainingGraph(window, isoDate) {
  const query = `window=${encodeURIComponent(window)}&date=${encodeURIComponent(isoDate)}`;
  return request(`/progress/graph?${query}`);
}
```

Then add the two profile functions immediately after `fetchMe`:

```js
/**
 * The account's trainer setup, and whether it has ever chosen one.
 *
 * Caching here rather than in each page module is what makes the cache
 * impossible to forget: this file is the only place our own API is called, so
 * every payload carrying a profile passes through exactly one function that
 * stores it.
 *
 * @returns {Promise<{profile: Object, configured: boolean}>}
 */
export async function fetchProfile() {
  const payload = await request("/profile");
  if (payload && payload.profile) cacheProfile(payload.profile);
  return payload;
}

/**
 * Store the account's trainer setup.
 *
 * Values are sent unvalidated on purpose — the server clamps to the same bounds
 * the inputs carry and echoes what it stored, so a corrected value corrects
 * itself on screen instead of being validated twice.
 *
 * @param {{experience: string, sessions_per_week: number,
 *          minutes_per_session: number}} profile
 * @returns {Promise<{profile: Object, configured: boolean}>}
 */
export async function saveProfile(profile) {
  const payload = await request("/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(profile),
  });
  if (payload && payload.profile) cacheProfile(payload.profile);
  return payload;
}
```

Check how `postEntry` (or whichever existing function sends a JSON body) sets its headers, and match it exactly rather than introducing a second idiom.

- [ ] **Step 5: Run the test to verify it passes**

Run: `python -m pytest tests/test_pages.py -q`

Expected: PASS.

- [ ] **Step 6: Check for stale importers before committing**

Run: `grep -rn "saveProfile\|profileQuery\|cacheProfile" app/static/js/`

Expected: `summary.js` still imports `saveProfile` from `./ui.js` and `onboarding.js` still imports `saveProfile` from `./ui.js` — **both are broken right now and Task 5 fixes them**. Confirm that is the complete list of breakage, and that nothing else references `profileQuery`.

- [ ] **Step 7: Commit**

```bash
git add app/static/js/ui.js app/static/js/api.js tests/test_pages.py
git commit -m "Make the stored trainer setup a cache of the server's answer

localStorage stops being where the setup lives and becomes a read-through
cache written only from API payloads, which keeps loadProfile synchronous
so setgrid.js's RPE gate does not have to await a fetch and flicker.

summary.js and onboarding.js still import the old ui.js saveProfile and
are wired up in the next commit."
```

---

### Task 5: The three page modules

**Files:**
- Modify: `app/static/js/summary.js` (imports at lines ~20–22; `onSetupChange` at ~348)
- Modify: `app/static/js/log.js` (`initLog` at ~553)
- Modify: `app/static/js/onboarding.js` (whole gate, lines ~27–110)
- Modify: `app/templates/base.html` (the `initOnboarding` call at line 366)
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: `fetchProfile()` and `saveProfile()` from `api.js`, `loadProfile()` and `cacheProfile()` from `ui.js` — all from Task 4.
- Produces: `initOnboarding(dialog, page)` becomes `async` and returns a `Promise`. Nothing awaits it; `base.html` calls it as it does today.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pages.py`:

```python
def test_no_module_imports_saveProfile_from_ui():
    """`saveProfile` writes to the account and lives in api.js. The ui.js
    function is `cacheProfile`, and it is api.js's to call."""
    from pathlib import Path

    js = Path(__file__).resolve().parent.parent / "app" / "static" / "js"
    for path in js.glob("*.js"):
        source = path.read_text(encoding="utf-8")
        if "saveProfile" in source and path.name != "api.js":
            assert 'from "./api.js"' in source, path.name
            assert "saveProfile" not in source.split('from "./ui.js"')[0][-400:], (
                f"{path.name} imports saveProfile from ui.js"
            )
```

If that second assertion reads as fragile once you see the real import blocks, replace it with the simpler and stricter check: assert that no file other than `ui.js` contains the exact string `cacheProfile` unless it is `api.js`, and that no file's `./ui.js` import list contains `saveProfile`. Write whichever version you can state plainly; do not ship both.

- [ ] **Step 2: Run it to verify it fails**

Run: `python -m pytest tests/test_pages.py::test_no_module_imports_saveProfile_from_ui -q`

Expected: FAIL, naming `summary.js` and `onboarding.js`.

- [ ] **Step 3: Wire up `summary.js`**

Change the `./ui.js` import block so it no longer takes `saveProfile`, and add `saveProfile` to the existing `./api.js` import (which already brings in `fetchWeeklySummary`). Then replace `onSetupChange`:

```js
async function onSetupChange() {
  try {
    // The setup is on the account, so changing it is a write. `load()` then
    // re-fetches: targets are graded server-side, so a new setup has always
    // meant a new request rather than a re-render — the states, the ramp
    // positions and the readouts all move with it.
    await saveProfile(readSetup());
  } catch (err) {
    // The controls stay where the user put them; the week below is still the
    // one that was graded against the old setup, which is what is on screen.
    toast(err.message, "error");
    return;
  }
  renderBlurb();
  await load();
}
```

Leave `initSummary`'s `fillSetup(loadProfile())` exactly as it is — it paints the cached setup before the first fetch, and the echo corrects it if the cache was stale.

- [ ] **Step 4: Warm the cache in `log.js`**

Add `fetchProfile` to the existing `./api.js` import block. Then in `initLog`, in the `try` that fetches the catalog, fetch the profile alongside it:

```js
  try {
    // The profile before the catalog: `setgrid.js` reads the cached setup to
    // decide whether to draw the RPE column, and on a browser with a cold cache
    // that would otherwise resolve to the default and draw the wrong columns
    // for an advanced lifter.
    await fetchProfile();
    catalog = await fetchExercises();
```

The grid is mounted earlier in `initLog` and re-reads the profile when it renders rows — check `setgrid.js`'s `showRpe` handling at lines 55 and 407 and confirm the first row render happens after this await. If it does not, move the `createSetGrid` call below the fetch and say so in a comment.

- [ ] **Step 5: Rewrite the gate in `onboarding.js`**

Change the import line to:

```js
import { $, loadProfile } from "./ui.js";
import { fetchProfile, saveProfile } from "./api.js";
```

Replace the `ASKED_KEY` doc comment with:

```js
/**
 * Whether the question has been put to *this browser*.
 *
 * There are now two gates, and they answer different questions. The account's
 * stored setup says whether anyone has answered — so a user who set up on their
 * phone is never interviewed again on their laptop. This flag says whether this
 * browser has been asked, which is what makes skipping stick: skipping writes
 * nothing to the server, deliberately, because nobody has answered yet.
 *
 * It is also separate from the cached profile. If it were the same key, a user
 * who skipped would be asked again on every visit, and one who cleared only
 * their preferences would never be asked again — both backwards.
 */
```

Replace `initOnboarding` with:

```js
/**
 * Boot the first-run dialog.
 *
 * @param {HTMLDialogElement|null} dialog - The shell from `base.html`.
 * @param {string} page - The current page's `data-page` value.
 */
export async function initOnboarding(dialog, page) {
  if (!dialog || !APP_PAGES.has(page) || hasBeenAsked()) return;

  // Only now is a request worth making. A browser that has already been asked
  // must not pay for a fetch on every navigation.
  let profile = loadProfile();
  try {
    const payload = await fetchProfile();
    if (payload.configured) {
      // The account has answered, on some other device. This browser now knows,
      // and the cache `fetchProfile` just wrote is what the page will render.
      markAsked();
      return;
    }
    profile = payload.profile;
  } catch {
    // Offline, or signed out — `api.js` is already handling a 401 by redirecting.
    // Treat it as unanswered and fall through to the local flag alone: a dialog
    // is not worth an error, and asking twice is better than never asking.
  }

  const sessions = $("#first-run-sessions", dialog);
  const minutes = $("#first-run-minutes", dialog);

  // Start on whatever the app would have used anyway, so skipping and
  // submitting-untouched land in the same place.
  selectLevel(dialog, profile.experience);
  sessions.value = profile.sessions_per_week;
  minutes.value = profile.minutes_per_session;

  dialog.querySelectorAll(".first-run-level").forEach((button) => {
    button.addEventListener("click", () => selectLevel(dialog, button.dataset.level));
  });

  // Both exits mark the question asked; only this one records an answer, and
  // only this one reaches the account.
  $("#first-run-start", dialog).addEventListener("click", async () => {
    try {
      await saveProfile({
        experience: dialog.dataset.level,
        sessions_per_week: Number(sessions.value),
        minutes_per_session: Number(minutes.value),
      });
    } catch {
      // The answer did not reach the account. Leave the flag unset so the
      // question survives to the next visit rather than being silently lost.
      dialog.close();
      return;
    }
    markAsked();
    dialog.close();
    // The page fetched its data before this was answered, so anything graded
    // against a target is now stale. A reload is the honest fix and costs one
    // request on a page that has just opened.
    window.location.reload();
  });

  $("#first-run-skip", dialog).addEventListener("click", () => {
    markAsked();
    dialog.close();
  });

  // Escape closes a modal dialog natively; catch it so it counts as skipping
  // rather than leaving the question to reappear on the next navigation.
  dialog.addEventListener("close", markAsked);

  dialog.showModal();
}
```

Note the `close` listener is registered before `showModal`, exactly as it is today, so the early `return` paths above never attach it.

- [ ] **Step 6: Check `base.html` needs no change**

`initOnboarding` is called inside a `<script type="module">` that already uses top-level `await` (for the sign-out import), so an unawaited promise is fine and the call site does not change. Read lines 355–370 of `app/templates/base.html` and confirm. If the surrounding comment claims the four boots are synchronous, correct that sentence — nothing else.

- [ ] **Step 7: Run the page tests and the whole suite**

Run: `python -m pytest -q`

Expected: PASS.

- [ ] **Step 8: Verify in the running app**

Run: `python run.py`, then in the browser, signed in:

1. `/summary` — change Experience to Beginner. The targets drop, the sentence under the controls changes, and the body map re-grades.
2. Reload `/summary` in a **private window**, signed in as the same account. The controls come up on Beginner: the setup followed the account, not the browser. This is the whole feature.
3. `/log` with an Advanced setup — the RPE column is present on first paint, not added a moment later.
4. `localStorage.clear()` then reload `/summary` — the first-run dialog does **not** open, because the account is configured.

Expected: all four. If (2) fails, the `PUT` is not reaching the server; if (3) flickers, `log.js`'s `fetchProfile` is landing after the grid's first row render.

- [ ] **Step 9: Commit**

```bash
git add app/static/js/summary.js app/static/js/log.js app/static/js/onboarding.js tests/test_pages.py
git commit -m "Read and write the trainer setup through the account

The summary's controls now PUT and re-fetch; /log warms the cache before
the grid's first render so an advanced lifter's RPE column does not
flicker in; and first run asks only when the account has no setup *and*
this browser has not been asked. Skipping still writes nothing to the
server, because nobody has answered yet."
```

---

### Task 6: The documentation

**Files:**
- Modify: `docs/API.md` (endpoint table ~line 47; `GET /api/summary/week` query params ~line 513; the graph's trainer-setup paragraph ~line 758; a new section before `DELETE /api/account`)
- Modify: `docs/ARCHITECTURE.md` (line 446, and the "per-browser, not per-account" limitation at ~line 864)
- Modify: `docs/ROADMAP.md` (the "Current state" paragraph ~line 9, and item 1)
- Modify: `CLAUDE.md` (the Architecture paragraph, and the trainer-setup invariant)

**Interfaces:**
- Consumes: everything above. Produces: nothing code depends on.

- [ ] **Step 1: `docs/API.md` — the endpoint table**

Add two rows to the auth table, after `GET /api/me`:

```markdown
| `GET /api/profile` | bearer |
| `PUT /api/profile` | bearer |
```

- [ ] **Step 2: `docs/API.md` — the summary's query parameters**

Replace the four-row query-param table under `## GET /api/summary/week` and the paragraph beginning "The last three are the **trainer setup**" with:

```markdown
| Query param | Default | Notes |
| --- | --- | --- |
| `date` | Today | Any day inside the week wanted. |

Targets come from the account's stored **trainer setup** — see
[`GET /api/profile`](#get-apiprofile). It used to travel on this query string as
`experience`/`sessions`/`minutes`; those parameters are gone, and a client still
sending them is ignored rather than 400ed. Two sources of truth meant a stale
client could be graded against something other than its own account's setup, and
because both answers render correctly the disagreement was invisible.
```

Leave the `profile` block in the example payload and the whole `### Trainer setup` subsection as they are — the shape did not change.

- [ ] **Step 3: `docs/API.md` — the graph's paragraph**

Replace:

> That is also why the trainer setup has to be sent here too. Node colour *is* the body
> map's grading, so a graph fetched without the profile the summary page is using would
> be graded against different targets and the two pages would disagree about one week.

with:

```markdown
Node colour *is* the body map's grading, so this endpoint resolves the account's
trainer setup exactly as `GET /api/summary/week` does. Neither is told the setup by
its caller any more, which is what makes it impossible for the two pages to disagree
about one week.
```

- [ ] **Step 4: `docs/API.md` — the new section**

Insert before `## DELETE /api/account`:

```markdown
---

## `GET /api/profile`

The account's trainer setup, resolved, with the targets it produces.

```json
{
  "profile": {
    "experience": "beginner",
    "label": "Beginner",
    "shows_rpe": false,
    "volume_scale": 0.6,
    "limited_by": "experience",
    "sessions_per_week": 6,
    "minutes_per_session": 90,
    "targets": { "chest": 12, "abs": 6, "...": 0 }
  },
  "configured": true
}
```

`profile` is the same shape `GET /api/summary/week` echoes, specified under
[Trainer setup](#trainer-setup).

`configured` is `false` when the account has never chosen a setup — the three
columns are NULL and `profile` is the app's default, which is the pre-Phase-6
grading exactly. It is a fact about storage rather than about training, which is
why it sits beside the profile rather than inside it. **The first-run dialog is
its one reader:** an account that has answered is never asked again, on any
device.

---

## `PUT /api/profile`

Stores the account's trainer setup.

```json
{"experience": "beginner", "sessions_per_week": 6, "minutes_per_session": 90}
```

Responds with the same shape `GET /api/profile` returns, and `configured: true`.

**Nothing here 400s.** An unknown experience level falls back to `experienced`
and out-of-range numbers are clamped to 1–14 sessions and 15–240 minutes — the
same rule `window` follows on the graph endpoint, and for the same reason: these
arrive from a settings control, and the honest response to an out-of-range number
is the nearest one that works.

**The stored values are the resolved ones**, not what was submitted, so the column
can never hold a setup the app would refuse to use. The echo is therefore what the
client's controls should settle on: a value corrected on the way in corrects itself
on screen rather than sitting there disagreeing with the grading it produced.
```

- [ ] **Step 5: `docs/ARCHITECTURE.md`**

At line ~446, replace the clause "but the setup is a `localStorage` preference sent with each request" with a sentence saying the setup is three nullable columns on `user`, read through `api._user_profile` and written by `PUT /api/profile`, with `localStorage` holding only a cache of the server's answer so `loadProfile()` can stay synchronous for `setgrid.js`'s RPE gate. Read the surrounding paragraph first and match its voice.

Then delete the limitation bullet at ~line 864 — "**The trainer setup is per-browser, not per-account.**" — since it has stopped being true. Check the `user` table's description in the data-model section names the three new columns; add them if it enumerates columns.

- [ ] **Step 6: `docs/ROADMAP.md`**

In the "Current state" paragraph, add the carryover to the list of what is done and delete the paragraph beginning "Phase 6 shipped **ahead of** Phase 5". Replace the whole `### 1. Phase 5 carryover` section with a short shipped note in the style `8.1`/`8.2`/`8.3` use — what moved, and the one thing worth knowing (the columns are nullable and unbackfilled, so "never chosen" stays distinguishable). Renumber the remaining items so Phase 7 is `### 1.`

- [ ] **Step 7: `CLAUDE.md`**

Two edits, both replacing text that is now false:

In the Architecture section, delete the sentence beginning "**Phase 6 shipped ahead of Phase 5, and Phase 5 did not finish moving it**" through the end of that paragraph, and add the carryover to the list of completed phases in the preceding sentence.

Replace the invariant beginning "**The trainer setup has no user row yet, so it travels on the query string**" with:

```markdown
- **The trainer setup lives on the user row** — three nullable columns on `user`, where all three NULL means *never chosen* (which is not the same as chose-the-defaults: the first-run dialog reads exactly that distinction, and it is why they are not backfilled). `GET`/`PUT /api/profile` own it; `/api/summary/week` and `/api/progress/graph` resolve it from the row and **no longer read `experience`/`sessions`/`minutes` off the query string** — two sources of truth let a stale client be graded against something other than its account's setup, invisibly, since both answers render correctly. `PUT` clamps rather than 400ing and stores the *resolved* values, so the column can never hold a setup the app would refuse to use. `resolve_profile` still falls back rather than raising, like the graph's `window`: a value stored before a bound was tuned should show the usual targets, not blank the page. **`localStorage` still holds the setup, but only as a cache of the server's answer**, written solely by `api.js` — that is what keeps `loadProfile()` synchronous, which `setgrid.js` needs to decide the RPE column while it is building markup rather than after it has painted. **The client never computes a target** — it renders `profile.targets` from the response.
```

- [ ] **Step 8: Verify the docs against the code**

Run: `grep -rn "experience=\|sessions=\|minutes=" docs/ app/ tests/ --include=*.md --include=*.py --include=*.js`

Expected: no hit describing a *query parameter*. Hits inside `tests/test_api.py::test_the_query_string_can_no_longer_set_the_targets` and keyword arguments in Python calls are correct and stay.

- [ ] **Step 9: Run the whole suite**

Run: `python -m pytest -q`

Expected: PASS. `tests/test_pages.py` asserts markup against these docs' claims in places, so a docs-only commit still runs it.

- [ ] **Step 10: Commit**

```bash
git add docs/API.md docs/ARCHITECTURE.md docs/ROADMAP.md CLAUDE.md
git commit -m "Document the trainer setup's new home

A doc that contradicts the code is a bug: three files said the setup was
a per-browser preference on the query string. API.md gains the two
endpoints and loses the three parameters, and the roadmap's last Phase 5
carryover is closed."
```

---

## Self-Review

**Spec coverage.** Every section of the design maps to a task: columns and migration → Task 1; `get_trainer_setup`/`set_trainer_setup` → Task 2; `_user_profile`, the two endpoints, the removed parameters and `training.py`'s docstring → Task 3; `ui.js`/`api.js` → Task 4; `summary.js`/`log.js`/`onboarding.js` → Task 5; all four documents → Task 6. The spec's testing section is distributed across the tasks that create each behaviour, which is where TDD wants it. The spec's "out of scope" list is not implemented anywhere, which is correct.

**Types and names, checked across tasks.** `get_trainer_setup(user_id) -> dict | None` is defined in Task 2 and consumed in Task 3 with `or {}` plus `.get()`, which is exactly its `None` case. `resolve_profile` is called with three positional arguments in both `_user_profile` and `put_profile`, matching its signature. `profile.experience.key`, `profile.plan.sessions_per_week` and `profile.plan.minutes_per_session` are the real attribute paths on `TrainerProfile` — `to_dict()` flattens them, but `set_trainer_setup` takes the objects' own values. `ui.js` exports `cacheProfile` (Task 4) and `api.js` exports `saveProfile` (Task 4); Task 5's `summary.js` and `onboarding.js` import `saveProfile` from `./api.js`, never from `./ui.js`, which is what Task 5's test enforces. `initOnboarding` becomes `async` in Task 5 and Task 5 Step 6 confirms the one call site tolerates it.

**Known sharp edge, flagged rather than hidden.** Task 5 Step 4 depends on when `setgrid.js` first reads `loadProfile()`. The step says to check lines 55 and 407 and move the mount if the read happens before the fetch lands — that is a real branch in the work, and the browser check in Step 8 catches it either way.
