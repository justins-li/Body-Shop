# Phase 7 — Deployment on Render, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Body Shop to a real URL on Render, with the launch floor the roadmap names — backups with a tested restore, error monitoring, a privacy policy, and CSV export.

**Architecture:** Render runs a gunicorn web service; Postgres stays in the Supabase project that already holds auth. Migrations run from the operator's machine against Supabase's session pooler (port 5432), because Render's `preDeployCommand` is a paid-tier feature. Three new surfaces: `GET /healthz` (deliberately touching no database), `GET /api/entries/export.csv`, and a bare `/privacy` page.

**Tech Stack:** Flask 3, SQLAlchemy Core, Alembic, gunicorn, `sentry-sdk[flask]`, Render blueprint (`render.yaml`), Supabase Postgres + GoTrue.

**Design doc:** [docs/superpowers/specs/2026-08-03-phase-7-deployment-design.md](../specs/2026-08-03-phase-7-deployment-design.md)

## Global Constraints

Every task's requirements implicitly include all of these.

- **Read the doc before the code.** `CLAUDE.md`'s read-before-edit table is binding. Adding or changing an endpoint means reading and updating [docs/API.md](../../API.md) in the **same commit**; payload examples there are exhaustive, not illustrative. Moving logic between layers means [docs/ARCHITECTURE.md](../../ARCHITECTURE.md)'s layer-ownership table.
- **SQL only in `app/models.py`.** Services and routes never call `get_db()`. This phase adds no SQL at all — the export reads through the existing `list_entries`.
- **`user_id` is the first positional parameter** of every `models.py` function touching `workout_entry`. The export endpoint passes `g.user_id` and nothing else identifies the user.
- **Weight is kilograms at rest and over the wire.** `kg`/`lb` is a display preference and conversion happens **only** in `app/static/js/ui.js`. A CSV file is not a display surface: it exports kilograms and its header says so.
- **`weight`, `reps` and `rpe` are nullable, and `0` is a legitimate value.** Guard with `is None` in Python and `=== null` in JS, never a falsy check. In the CSV, `None` is an empty cell and `0` is `0`.
- **JS is ES modules with zero dependencies.** No bundler; JS is served as written. `app/static/js/api.js` is the only place our own API is called; `auth.js` is the only place Supabase is.
- **The stylesheet is compiled.** `app/static/css/input.css` is the source; `styles.css` is build output. This phase adds no new CSS classes — the privacy page reuses `.auth-shell`, `.auth-title`, `.auth-note`, `.auth-field`, `.auth-submit`, `.type-label` and `.type-data`, which already exist. **Do not edit `styles.css`.**
- **Python conventions:** `from __future__ import annotations` at module top, type hints on signatures, docstrings on public functions.
- **Run the full suite before every commit:** `pytest`. CI only runs `pytest -q`, so a green local run is the whole signal.
- **Commit messages:** present tense, one logical change per commit. **Never add attribution trailers** — no `Co-Authored-By:`, no "Generated with" footers.
- **Branch:** work continues on `phase-7-deployment`, which is already checked out.
- **`gh` is not installed.** Do not attempt to open PRs or issues.
- **Never hand-edit `app/data/exercises.json`.** Nothing in this phase touches the catalog.
- **No secret is ever committed.** Every secret in `render.yaml` is declared `sync: false`, which means "enter it in the Render dashboard". The service-role key and the Sentry DSN must never reach a template or the browser.

## File Structure

| File | Status | Responsibility |
| --- | --- | --- |
| `app/views.py` | Modify | Adds `GET /healthz` and `GET /privacy`. |
| `app/templates/privacy.html` | Create | The privacy policy, `bare=True`. |
| `app/services/export.py` | Create | Pure: `list[WorkoutEntry]` → CSV text. No SQL, no Flask. |
| `app/api.py` | Modify | Adds `GET /entries/export.csv`. |
| `app/static/js/api.js` | Modify | Adds `downloadExport()`; refactors the 401-retry out of `request`. |
| `app/templates/account.html` | Modify | Export button; privacy link. |
| `app/templates/login.html`, `signup.html` | Modify | Privacy link. |
| `app/config.py` | Modify | `CONTACT_EMAIL`, `SENTRY_DSN`; production requires the former. |
| `app/observability.py` | Create | `init_sentry(app)`. Called by `create_app` only when a DSN is set. |
| `app/__init__.py` | Modify | Calls `init_sentry`. |
| `render.yaml` | Create | Render blueprint. |
| `.python-version` | Create | `3.13`. |
| `requirements.txt` | Modify | Adds `gunicorn` and `sentry-sdk[flask]`. |
| `docs/OPERATIONS.md` | Create | Deploy, rollback, restore drill, incident checklist. |
| `tests/test_export.py` | Create | The CSV writer and the endpoint. |
| `tests/test_pages.py`, `test_config.py`, `test_ownership.py`, `test_api.py` | Modify | Health check, privacy page, contact-email check, two-user export walk. |

---

### Task 1: The health check

Render restarts a service whose health check fails. A health check that queries Postgres turns a thirty-second Supabase blip into a restart loop — so this one answers only "is this process serving HTTP".

**Files:**
- Modify: `app/views.py` (add route after `home_page`, around line 109)
- Modify: `docs/API.md` (new section)
- Modify: `docs/ARCHITECTURE.md` (layer-ownership table)
- Test: `tests/test_pages.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `GET /healthz` → `{"status": "ok", "version": str}`, 200. Endpoint name `views.healthz`. Task 2's `render.yaml` sets `healthCheckPath: /healthz`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pages.py`:

```python
class TestHealthCheck:
    """Render restarts a service whose health check fails."""

    def test_it_reports_ok_and_the_version(self, client):
        response = client.get("/healthz")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["status"] == "ok"
        assert payload["version"] == __version__

    def test_it_needs_no_bearer_token(self, app):
        """A platform health check cannot carry one."""
        assert app.test_client().get("/healthz").status_code == 200

    def test_it_answers_with_the_database_unreachable(self):
        """The load-bearing property, proved from outside.

        A health check that queries Postgres converts a brief database outage
        into a platform restart loop, which is strictly worse than the outage.
        So: point an app at a database that cannot be reached and assert the
        check still answers.

        Black-box on purpose. Monkeypatching `app.db.get_db` would prove
        nothing — `models.py` binds that name at import, so the patch would not
        reach the call — whereas a dead URL breaks every path to the database
        regardless of how anything imports anything.
        """
        from app import create_app

        unreachable = create_app(
            "testing",
            DATABASE_URL="postgresql+psycopg://nobody:nobody@127.0.0.1:1/nothing",
        )
        response = unreachable.test_client().get("/healthz")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"
```

Note this relies on `create_app` opening no connection, which is itself an
invariant the repo holds — so if this test fails at *construction* rather than
at the request, something has put a side effect back into the factory.

Add the import at the top of `tests/test_pages.py`, beside the existing ones:

```python
from app import __version__
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pages.py -k HealthCheck -v`
Expected: FAIL — all three 404.

- [ ] **Step 3: Add the route**

In `app/views.py`, add `jsonify` to the `flask` import on line 27:

```python
from flask import (
    Blueprint,
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
```

Add near the top of the module, after the `bp = Blueprint(...)` line on line 54:

```python
from . import __version__
```

Then add the route immediately after `home_page` (after line 108):

```python
@bp.get("/healthz")
def healthz():
    """Liveness probe for the platform. **Touches no database, deliberately.**

    Render restarts a service whose health check fails, so a check that queried
    Postgres would convert a thirty-second database blip into a restart loop —
    strictly worse than the blip. The only question the platform is asking is
    whether this process is serving HTTP, and that is the only one answered
    here. Database health is a Supabase dashboard concern and a Sentry alert.

    Unauthenticated, because a platform health check cannot carry a bearer
    token, and outside ``/api`` because it is not part of the product's API.
    """
    return jsonify({"status": "ok", "version": __version__})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_pages.py -k HealthCheck -v`
Expected: 3 passed.

- [ ] **Step 5: Document it**

In `docs/API.md`, add a section immediately after the `## Authentication` section (which ends around line 69), before `## GET /api/exercises`:

```markdown
## `GET /healthz`

Liveness probe. **Outside `/api`, unauthenticated, and it opens no database
connection** — a health check that queried Postgres would turn a brief database
outage into a platform restart loop. `render.yaml` points `healthCheckPath` at
it.

```json
{ "status": "ok", "version": "0.1.0" }
```

Always 200 while the process is serving. There is no failure body: a process
that cannot answer this does not answer at all.
```

In `docs/ARCHITECTURE.md`, find the layer-ownership table and add a row for `/healthz` under `app/views.py`, noting that it is the one view that renders no template.

- [ ] **Step 6: Run the full suite**

Run: `pytest`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add app/views.py tests/test_pages.py docs/API.md docs/ARCHITECTURE.md
git commit -m "Answer a health check without touching the database

Render restarts a service whose health check fails. A check that queried
Postgres would convert a thirty-second Supabase blip into a restart loop,
which is worse than the blip — so /healthz reports only that this process is
serving HTTP. Database health belongs to the Supabase dashboard and Sentry."
```

---

### Task 2: The Render blueprint

**Files:**
- Create: `render.yaml`
- Create: `.python-version`
- Modify: `requirements.txt`
- Modify: `CLAUDE.md` (the gunicorn line in the Commands block)

**Interfaces:**
- Consumes: `GET /healthz` from Task 1; `wsgi:application`, which already exists.
- Produces: a blueprint Render can import. Task 9's `docs/OPERATIONS.md` walks the operator through it.

- [ ] **Step 1: Add gunicorn to the runtime dependencies**

In `requirements.txt`, append:

```
# Production WSGI server. In the repository rather than "install it separately"
# because there is a deployment now: render.yaml's build command installs this
# file and its start command is `gunicorn wsgi:application`, so a build that
# did not include gunicorn would succeed and then fail to boot.
gunicorn>=22.0,<24.0
```

- [ ] **Step 2: Pin the interpreter**

Create `.python-version`:

```
3.13
```

Render reads this file. CI's Postgres job — the one that proves the migration chain round-trips on the dialect production actually uses — already pins 3.13, so this keeps the deployed interpreter from drifting away from the one that gets proved.

- [ ] **Step 3: Write the blueprint**

Create `render.yaml`:

```yaml
# Render blueprint. Import this from the Render dashboard: New → Blueprint,
# point it at this repository, and fill in the values marked `sync: false`.
#
# What is NOT here, deliberately:
#
#   database:  Postgres lives in the Supabase project that already holds auth.
#              One vendor, one dashboard, one backup story — and app/db.py is
#              already tuned for a connection pooler (NullPool,
#              prepare_threshold=None), which is what Supabase puts in front.
#
#   migrations: `preDeployCommand` is a paid-tier feature, and so is Shell. On
#              the free plan migrations run from the operator's machine against
#              Supabase's SESSION pooler (port 5432, not the transaction pooler
#              on 6543 — DDL through a transaction-mode pooler is not something
#              to rely on):
#
#                  DATABASE_URL=<session-pooler-url> flask --app app upgrade-db
#
#              See docs/OPERATIONS.md. On Starter, uncomment preDeployCommand
#              below and point DATABASE_URL at the session pooler.

services:
  - type: web
    name: body-shop
    runtime: python
    region: oregon
    plan: free
    # `plan: starter` ($7/mo) is the one-line upgrade. The free instance sleeps
    # after 15 minutes idle and the next request pays roughly a 50-second cold
    # start — bad for a workout log, which is opened mid-set. See
    # docs/OPERATIONS.md § Upgrading off the free tier.
    branch: main
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn wsgi:application
    # preDeployCommand: flask --app app upgrade-db   # Starter and above only.
    healthCheckPath: /healthz
    envVars:
      - key: BODYSHOP_CONFIG
        value: production

      # Render mints this once and keeps it, which beats a human pasting one.
      - key: BODYSHOP_SECRET_KEY
        generateValue: true

      # Supabase → Project Settings → Database → Connection string.
      # Use the TRANSACTION pooler (port 6543) here: this is the app, and every
      # web process holds connections. Migrations use the session pooler (5432).
      - key: DATABASE_URL
        sync: false

      # Supabase → Project Settings → API.
      - key: BODYSHOP_SUPABASE_URL
        sync: false
      - key: BODYSHOP_SUPABASE_ANON_KEY
        sync: false
      # SECRET. Used by DELETE /api/account and nowhere else.
      - key: BODYSHOP_SUPABASE_SERVICE_ROLE_KEY
        sync: false
      # Optional: set only for older projects signing with the shared HS256
      # secret. Unset means "verify against the published JWKS", which is a
      # valid configuration rather than a missing one.
      - key: BODYSHOP_SUPABASE_JWT_SECRET
        sync: false

      # Rendered into /privacy. Production refuses to boot without it: a
      # privacy policy naming no way to reach anyone is the launch floor
      # failing silently.
      - key: BODYSHOP_CONTACT_EMAIL
        sync: false

      # Optional. Unset → Sentry is never initialised and nothing is reported.
      - key: BODYSHOP_SENTRY_DSN
        sync: false
```

- [ ] **Step 4: Correct the CLAUDE.md line that this reverses**

`CLAUDE.md`'s Commands block currently reads:

```
gunicorn "wsgi:application"           # production entry point — NB: gunicorn is not in requirements.txt, install it separately
```

Replace that line with:

```
gunicorn "wsgi:application"           # production entry point (Render's start command)
```

That claim is now false, and CLAUDE.md's own header says a stale file is worse than a short one.

- [ ] **Step 5: Verify the app actually boots under gunicorn**

```bash
pip install -r requirements.txt
BODYSHOP_CONFIG=development gunicorn --bind 127.0.0.1:8000 --workers 1 "wsgi:application" &
sleep 3
curl -sf http://127.0.0.1:8000/healthz
kill %1
```

Expected: `{"status":"ok","version":"0.1.0"}`.

Note `BODYSHOP_CONFIG=development` — `wsgi.py` hard-codes `create_app("production")`, so without the override this fails the production config checks locally, which is the checks working. If you want to prove the production path too, set `BODYSHOP_SECRET_KEY`, `DATABASE_URL` (a Postgres URL) and the three Supabase variables first.

- [ ] **Step 6: Run the full suite**

Run: `pytest`
Expected: all pass. Nothing here changes application behaviour, but `requirements.txt` changed and the suite is the check that the new pins install cleanly together.

- [ ] **Step 7: Commit**

```bash
git add render.yaml .python-version requirements.txt CLAUDE.md
git commit -m "Describe the Render service as a blueprint

Flask stays and Render hosts it; Postgres remains in the Supabase project that
already holds auth, so there is one vendor and one backup story. Every secret
is `sync: false` — entered in the dashboard, never committed — and the secret
key is generated by Render rather than pasted by a human.

Migrations are deliberately not a deploy hook: preDeployCommand is paid-tier,
and DDL through a transaction-mode pooler is not something to rely on. They run
from the operator's machine against the session pooler, which is what run.py
has told people to do since Phase 3.

gunicorn moves into requirements.txt. 'Install it separately' was defensible
with no deployment; with a build command it means a build that succeeds and
then fails to boot."
```

---

### Task 3: The CSV writer

Pure and layer-clean: it takes entries and returns text. No SQL, no Flask, no request context — which is what makes the interesting cases (nulls, warm-ups, escaping) testable without a client.

**Files:**
- Create: `app/services/export.py`
- Test: `tests/test_export.py`

**Interfaces:**
- Consumes: `app.models.WorkoutEntry` and `WorkoutSet` (frozen dataclasses; `WorkoutSet.set_index` is **1-based**, assigned from submission order in `validate_sets`).
- Produces:
  - `EXPORT_COLUMNS: tuple[str, ...]` — the header row, in order.
  - `entries_to_csv(entries: Iterable[WorkoutEntry]) -> str`
  - `export_filename(day: date) -> str` → `"bodyshop-export-2026-08-03.csv"`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_export.py`:

```python
"""The CSV export — the 'get your data out' half of the privacy obligation.

The writer is pure, so everything interesting about it is tested here without a
client: nulls, warm-ups, ordering and escaping. The endpoint's own tests live
at the foot of the file, and the two-user leak check lives in
tests/test_ownership.py, where a failure is read as a data leak.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from app.models import WorkoutEntry, WorkoutSet
from app.services.export import EXPORT_COLUMNS, entries_to_csv, export_filename


def _set(index, **kwargs):
    """A WorkoutSet with everything unrecorded unless named."""
    fields = {"weight": None, "reps": None, "rpe": None, "set_type": "normal"}
    fields.update(kwargs)
    return WorkoutSet(id=f"id{index}", set_index=index, **fields)


def _rows(text):
    """Parse CSV text back into a list of dict rows."""
    return list(csv.DictReader(io.StringIO(text)))


class TestTheWriter:
    def test_the_header_names_every_column_in_order(self):
        text = entries_to_csv([])
        assert text.splitlines()[0] == ",".join(EXPORT_COLUMNS)

    def test_an_empty_log_is_a_header_and_nothing_else(self):
        """Not an error, and not an empty file: the columns are the answer."""
        assert entries_to_csv([]).strip().count("\n") == 0

    def test_one_row_per_set(self):
        entry = WorkoutEntry(
            id=41,
            entry_date=date(2026, 8, 1),
            exercise_id="Barbell_Squat",
            set_rows=(_set(1, weight=100.0, reps=5), _set(2, weight=100.0, reps=5)),
        )
        rows = _rows(entries_to_csv([entry]))
        assert len(rows) == 2
        assert [r["set_number"] for r in rows] == ["1", "2"]
        assert {r["entry_id"] for r in rows} == {"41"}

    def test_warmups_are_exported_and_named(self):
        """This is the raw record, not the graded week.

        Excluding warm-ups is a *grading* rule — it keeps them off the muscle
        map. An export that dropped them would be lying about what happened.
        """
        entry = WorkoutEntry(
            id=41,
            entry_date=date(2026, 8, 1),
            exercise_id="Barbell_Squat",
            set_rows=(_set(1, set_type="warmup"), _set(2)),
        )
        rows = _rows(entries_to_csv([entry]))
        assert [r["set_type"] for r in rows] == ["warmup", "normal"]

    def test_unrecorded_values_are_empty_cells(self):
        entry = WorkoutEntry(
            id=1, entry_date=date(2026, 8, 1), exercise_id="Sit-Up",
            set_rows=(_set(1, reps=15),),
        )
        row = _rows(entries_to_csv([entry]))[0]
        assert row["weight_kg"] == ""
        assert row["rpe"] == ""
        assert row["reps"] == "15"

    def test_zero_is_not_blank(self):
        """`0` and 'not recorded' are different facts.

        A bodyweight movement legitimately logs 0 kg added. Rendering that as an
        empty cell would erase the difference between 'I added nothing' and 'I
        did not write it down'.
        """
        entry = WorkoutEntry(
            id=1, entry_date=date(2026, 8, 1), exercise_id="Pullups",
            set_rows=(_set(1, weight=0.0, reps=0, rpe=0.0),),
        )
        row = _rows(entries_to_csv([entry]))[0]
        assert row["weight_kg"] == "0.0"
        assert row["reps"] == "0"
        assert row["rpe"] == "0.0"

    def test_the_exercise_name_is_resolved_from_the_catalog(self):
        entry = WorkoutEntry(
            id=1, entry_date=date(2026, 8, 1), exercise_id="Barbell_Squat",
            set_rows=(_set(1),),
        )
        row = _rows(entries_to_csv([entry]))[0]
        assert row["exercise_id"] == "Barbell_Squat"
        assert row["exercise"] == "Barbell Squat"

    def test_it_reads_in_log_order_oldest_first(self):
        """list_entries returns newest first; a file people keep reads forwards."""
        older = WorkoutEntry(id=1, entry_date=date(2026, 7, 1),
                             exercise_id="Sit-Up", set_rows=(_set(1),))
        newer = WorkoutEntry(id=2, entry_date=date(2026, 8, 1),
                             exercise_id="Sit-Up", set_rows=(_set(1),))
        rows = _rows(entries_to_csv([newer, older]))
        assert [r["date"] for r in rows] == ["2026-07-01", "2026-08-01"]

    def test_sets_are_ordered_within_an_entry(self):
        entry = WorkoutEntry(
            id=1, entry_date=date(2026, 8, 1), exercise_id="Sit-Up",
            set_rows=(_set(3), _set(1), _set(2)),
        )
        rows = _rows(entries_to_csv([entry]))
        assert [r["set_number"] for r in rows] == ["1", "2", "3"]

    def test_a_comma_in_a_name_does_not_break_the_file(self):
        """csv.writer quotes; this asserts we did not hand-roll a join."""
        entry = WorkoutEntry(
            id=1, entry_date=date(2026, 8, 1),
            exercise_id="Pushups_With_Feet_Elevated", set_rows=(_set(1),),
        )
        text = entries_to_csv([entry])
        assert len(_rows(text)) == 1

    def test_dates_are_iso_strings(self):
        entry = WorkoutEntry(id=1, entry_date=date(2026, 8, 1),
                             exercise_id="Sit-Up", set_rows=(_set(1),))
        assert _rows(entries_to_csv([entry]))[0]["date"] == "2026-08-01"

    def test_an_entry_with_no_sets_contributes_no_rows(self):
        entry = WorkoutEntry(id=1, entry_date=date(2026, 8, 1),
                             exercise_id="Sit-Up", set_rows=())
        assert _rows(entries_to_csv([entry])) == []


class TestTheFilename:
    def test_it_carries_the_date(self):
        assert export_filename(date(2026, 8, 3)) == "bodyshop-export-2026-08-03.csv"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_export.py -v`
Expected: collection error — `No module named 'app.services.export'`.

- [ ] **Step 3: Write the writer**

Create `app/services/export.py`:

```python
"""Turn a user's log into CSV.

Pure: it takes entries and returns text. No SQL, no Flask, no request context —
so the cases that matter (nulls, warm-ups, ordering, escaping) are testable
without a client, and the layering rule holds without an exception.

**One row per set, warm-ups included.** Excluding warm-ups is a *grading* rule:
it keeps them off the muscle map, where counting them would inflate the week.
An export is the raw record of what happened, and dropping a set from it would
be lying about the session.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date

from ..models import WorkoutEntry

#: The header row, in order.
#:
#: ``weight_kg`` names its unit on purpose. Kilograms are what is stored and
#: what is exported; ``kg``/``lb`` is a display preference that lives only in
#: ``app/static/js/ui.js``, and a file someone keeps for years must not be
#: ambiguous about which one it holds.
EXPORT_COLUMNS: tuple[str, ...] = (
    "entry_id",
    "date",
    "exercise_id",
    "exercise",
    "set_number",
    "set_type",
    "weight_kg",
    "reps",
    "rpe",
)


def _cell(value: object) -> str:
    """Render one value.

    ``None`` is an empty cell and ``0`` is ``0``. The two are different facts —
    "I added no weight" against "I did not write it down" — and a falsy check
    would collapse them, which is the same bug the ``is None`` guards elsewhere
    in the app exist to prevent.
    """
    return "" if value is None else str(value)


def entries_to_csv(entries: Iterable[WorkoutEntry]) -> str:
    """Render ``entries`` and their sets as CSV text.

    Sorted oldest first, then by entry, then by set number. ``list_entries``
    returns newest first because that is what a day panel wants; a file someone
    opens in a spreadsheet reads forwards.
    """
    buffer = io.StringIO()
    # Explicit terminator: csv.writer defaults to CRLF, and a file that reads
    # cleanly on every platform is worth more here than strict RFC 4180.
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)

    for entry in sorted(entries, key=lambda item: (item.entry_date, item.id)):
        for row in sorted(entry.set_rows, key=lambda item: item.set_index):
            writer.writerow(
                [
                    entry.id,
                    entry.entry_date.isoformat(),
                    entry.exercise_id,
                    entry.exercise_name,
                    row.set_index,
                    row.set_type,
                    _cell(row.weight),
                    _cell(row.reps),
                    _cell(row.rpe),
                ]
            )

    return buffer.getvalue()


def export_filename(day: date) -> str:
    """Filename for a download taken on ``day``."""
    return f"bodyshop-export-{day.isoformat()}.csv"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_export.py -v`
Expected: all pass.

If `test_the_exercise_name_is_resolved_from_the_catalog` fails on the expected name, check the catalog for the real one rather than changing the assertion:
`python -c "from app.exercises import get_exercise; print(get_exercise('Barbell_Squat').name)"`

- [ ] **Step 5: Run the full suite**

Run: `pytest`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add app/services/export.py tests/test_export.py
git commit -m "Render a log as CSV

Pure — entries in, text out — so nulls, warm-ups, ordering and escaping are
testable without a client and the SQL-only-in-models rule needs no exception.

Two decisions worth stating. Warm-ups are exported: excluding them is a
grading rule that keeps them off the muscle map, and a raw record that dropped
a set would be lying about the session. And an unrecorded value is an empty
cell while zero is zero, because 0 kg added on a pull-up is a fact and a blank
is the absence of one."
```

---

### Task 4: The export endpoint

**Files:**
- Modify: `app/api.py`
- Modify: `docs/API.md`
- Test: `tests/test_export.py` (append), `tests/test_ownership.py` (append)

**Interfaces:**
- Consumes: `entries_to_csv`, `export_filename`, `EXPORT_COLUMNS` from Task 3; `models.list_entries(user_id, start, end)`, which already exists and already filters by user.
- Produces: `GET /api/entries/export.csv` → `text/csv; charset=utf-8` with a `Content-Disposition: attachment` header. Task 5's `api.js` consumes it.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_export.py`:

```python
class TestTheEndpoint:
    def test_it_returns_csv_as_an_attachment(self, client, add):
        assert add("2026-08-01", "Barbell_Squat", 3).status_code == 201

        response = client.get("/api/entries/export.csv")
        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert "attachment" in response.headers["Content-Disposition"]
        assert "bodyshop-export-" in response.headers["Content-Disposition"]

    def test_it_exports_the_whole_log_not_one_week(self, client, add):
        """No date filtering: this is the 'get my data out' obligation."""
        assert add("2025-01-05", "Sit-Up", 1).status_code == 201
        assert add("2026-08-01", "Barbell_Squat", 1).status_code == 201

        rows = _rows(client.get("/api/entries/export.csv").data.decode())
        assert [r["date"] for r in rows] == ["2025-01-05", "2026-08-01"]

    def test_an_empty_log_still_downloads(self, client):
        response = client.get("/api/entries/export.csv")
        assert response.status_code == 200
        assert response.data.decode().strip() == ",".join(EXPORT_COLUMNS)

    def test_it_carries_the_recorded_numbers(self, client):
        response = client.post(
            "/api/entries",
            json={
                "date": "2026-08-01",
                "exercise_id": "Barbell_Squat",
                "sets": [
                    {"weight": 60, "reps": 5, "set_type": "warmup"},
                    {"weight": 100, "reps": 5, "rpe": 8},
                ],
            },
        )
        assert response.status_code == 201

        rows = _rows(client.get("/api/entries/export.csv").data.decode())
        assert [r["set_type"] for r in rows] == ["warmup", "normal"]
        assert rows[0]["rpe"] == ""
        assert rows[1]["rpe"] == "8.0"

    def test_it_needs_a_bearer_token(self, app):
        assert app.test_client().get("/api/entries/export.csv").status_code == 401
```

Append to `tests/test_ownership.py`, inside `class TestReadsAreScoped`:

```python
    def test_the_csv_export(self, client, other_client, two_users):
        """An export is a file someone keeps. A leak here is permanent."""
        mine = client.get("/api/entries/export.csv").data.decode()
        theirs = other_client.get("/api/entries/export.csv").data.decode()
        assert MINE in mine and THEIRS not in mine
        assert THEIRS in theirs and MINE not in theirs
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_export.py::TestTheEndpoint tests/test_ownership.py -k export -v`
Expected: FAIL — 404 on every request.

- [ ] **Step 3: Add the endpoint**

In `app/api.py`, extend the `flask` import on line 12:

```python
from flask import Blueprint, Response, current_app, g, jsonify, request
```

Add to the imports, after the `.services.auth` line:

```python
from .services.export import entries_to_csv, export_filename
```

Add the route in `app/api.py` immediately after `get_entries` and **before** `create_entry` (Flask matches `/entries/export.csv` against the static rule regardless of order, but reading order should follow the reads):

```python
@bp.get("/entries/export.csv")
@require_user
def export_entries():
    """Every set this account has ever logged, as CSV.

    No date filtering, deliberately. This is the "get your data out" half of
    what ``/privacy`` promises — the other half being ``DELETE /api/account`` —
    and an export that made you ask for a range would be a report rather than
    your data. A spreadsheet filters dates by itself.

    Bearer-authed like everything else. The browser cannot put an
    ``Authorization`` header on a link it follows, so ``api.js`` fetches this
    and triggers the download from a Blob rather than the app growing a signed
    URL or a cookie for one endpoint.
    """
    body = entries_to_csv(list_entries(g.user_id))
    return Response(
        body,
        mimetype="text/csv",
        headers={
            "Content-Type": "text/csv; charset=utf-8",
            "Content-Disposition": (
                f'attachment; filename="{export_filename(date.today())}"'
            ),
        },
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_export.py tests/test_ownership.py -v`
Expected: all pass.

- [ ] **Step 5: Document it**

In `docs/API.md`, add a section after `## DELETE /api/entries/<id>` (which ends around line 488), before `## GET /api/calendar`:

````markdown
## `GET /api/entries/export.csv`

Every set this account has ever logged. **Not JSON** — `text/csv; charset=utf-8`,
served as an attachment named `bodyshop-export-<today>.csv`.

No query parameters and no date filtering. This is the "get your data out" half
of what `/privacy` promises, and an export that made you ask for a range would
be a report rather than your data.

One row per set, **warm-ups included** — excluding them is a grading rule that
keeps them off the muscle map, and a raw record that dropped a set would
misstate the session. Ordered oldest first, then by entry, then by set number.

```
entry_id,date,exercise_id,exercise,set_number,set_type,weight_kg,reps,rpe
41,2026-08-01,Barbell_Squat,Barbell Squat,1,warmup,60.0,5,
41,2026-08-01,Barbell_Squat,Barbell Squat,2,normal,100.0,5,8.0
42,2026-08-01,Sit-Up,Sit-Up,1,normal,,15,
```

| Column | Notes |
| --- | --- |
| `entry_id` | The `workout_entry` id — regroup sets by it. |
| `date` | ISO-8601, as everywhere else at the API boundary. |
| `exercise_id` | free-exercise-db's id, the join key back into the catalog. |
| `exercise` | The display name, so the file reads without the catalog. |
| `set_number` | 1-based, assigned from submission order. |
| `set_type` | `normal` \| `warmup` \| `drop` \| `failure`. |
| `weight_kg` | **Kilograms**, always. `kg`/`lb` is a display preference that lives only in `ui.js` and never reaches this file. |
| `reps`, `rpe` | |

**An empty cell means "not recorded"; `0` means zero.** `weight`, `reps` and
`rpe` are all nullable and `0` is a legitimate bodyweight entry, so the two are
never collapsed.

An account with no entries gets the header row and nothing else — 200, not 404.

Requires a bearer token like every other endpoint; the browser cannot set one
on a link it follows, so `api.js` fetches this and downloads it from a Blob.
````

- [ ] **Step 6: Run the full suite**

Run: `pytest`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add app/api.py tests/test_export.py tests/test_ownership.py docs/API.md
git commit -m "Serve the whole log as a CSV download

The 'get your data out' half of what the privacy policy promises; DELETE
/api/account is the other half. No date filtering — an export that made you ask
for a range would be a report rather than your data, and a spreadsheet filters
dates itself.

Added to the two-user ownership walk. An export is a file someone keeps, so a
missing WHERE user_id here leaks permanently rather than until a refresh."
```

---

### Task 5: The download button

**Files:**
- Modify: `app/static/js/api.js`
- Modify: `app/templates/account.html`
- Test: `tests/test_pages.py` (append)

**Interfaces:**
- Consumes: `GET /api/entries/export.csv` from Task 4.
- Produces: `downloadExport(): Promise<void>` exported from `api.js` — fetches the CSV, triggers a browser download, resolves when the download has started.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pages.py`:

```python
def test_account_page_offers_an_export(client):
    """Export and deletion are the same obligation from opposite ends."""
    body = client.get("/account").data.decode()
    assert 'id="export-data"' in body
```

- [ ] **Step 2: Run it to verify it fails**

Run: `pytest tests/test_pages.py::test_account_page_offers_an_export -v`
Expected: FAIL — `assert 'id="export-data"' in body`.

- [ ] **Step 3: Refactor the 401 retry so a non-JSON response can share it**

In `app/static/js/api.js`, replace the body of `request` (lines 41–72) with a shared core plus two thin readers. The 401-retry behaviour must not change: **one** silent refresh-and-retry, then a redirect to `/login`, never a loop.

```javascript
/**
 * Send a request, refreshing once behind a 401.
 *
 * Split out of `request` so a response that is not JSON — the CSV export — can
 * inherit the bearer header and the retry rather than reimplementing them.
 * Returns the raw `Response`; the caller decides how to read it.
 */
async function fetchWithRefresh(path, options = {}) {
  let response = await send(path, options, accessToken());

  if (response.status === 401) {
    // One retry, never a loop: a refresh token that is genuinely dead must not
    // spin, and the honest end of that road is the login page.
    try {
      const session = await refresh();
      response = await send(path, options, session.access_token);
    } catch {
      clearSession();
      toLogin();
      throw new Error("Sign in to continue.");
    }
    if (response.status === 401) {
      clearSession();
      toLogin();
      throw new Error("Sign in to continue.");
    }
  }

  return response;
}

/**
 * Perform a request against the API.
 * @param {string} path - Path below `/api`, e.g. `/entries`.
 * @param {RequestInit} [options]
 * @returns {Promise<any>} Parsed JSON body.
 */
async function request(path, options = {}) {
  const response = await fetchWithRefresh(path, options);

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    throw new Error((payload && payload.error) || `Request failed (${response.status})`);
  }
  return payload;
}
```

- [ ] **Step 4: Add the download**

Append to `app/static/js/api.js`, next to `deleteAccount`:

```javascript
/**
 * Download every set this account has logged, as CSV.
 *
 * The browser cannot put an `Authorization` header on a link it follows, so
 * this fetches the file and hands it to a synthetic anchor instead. That keeps
 * the API bearer-only: no signed URL, no cookie, no second way in for the sake
 * of one endpoint.
 *
 * The filename comes from the server's `Content-Disposition`, so the date in it
 * is the server's rather than a guess made in a browser sitting in some other
 * time zone.
 */
export async function downloadExport() {
  const response = await fetchWithRefresh("/entries/export.csv", {
    headers: { Accept: "text/csv" },
  });

  if (!response.ok) {
    throw new Error(`Export failed (${response.status})`);
  }

  const disposition = response.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  const url = URL.createObjectURL(await response.blob());

  const link = document.createElement("a");
  link.href = url;
  link.download = match ? match[1] : "bodyshop-export.csv";
  document.body.append(link);
  link.click();
  link.remove();
  // Revoking immediately can race the download in Safari; a tick is enough.
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
```

- [ ] **Step 5: Add the button**

In `app/templates/account.html`, insert this block **between** the `Sign out` button and the `Delete account` block:

```html
  <div class="flex flex-col gap-3 border-t border-base-content/15 pt-6">
    <span class="type-label">Your data</span>
    <p class="auth-note">
      Every set you have logged, as a CSV file you can open in a spreadsheet.
    </p>
    <button id="export-data" type="button" class="auth-submit type-label">
      Download my data
    </button>
  </div>
```

In the same file's `{% block scripts %}`, extend the `api.js` import and add the handler after the `sign-out` listener:

```javascript
  import { deleteAccount, downloadExport, fetchMe }
    from "{{ url_for('static', filename='js/api.js') }}";
```

```javascript
  const exportButton = document.getElementById("export-data");

  exportButton.addEventListener("click", async () => {
    exportButton.disabled = true;
    status.textContent = "";
    try {
      await downloadExport();
    } catch (err) {
      status.textContent = err.message;
    } finally {
      exportButton.disabled = false;
    }
  });
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `pytest tests/test_pages.py::test_account_page_offers_an_export -v`
Expected: PASS.

- [ ] **Step 7: Check the JS by hand**

There is no JS test runner in this repo — the front end is verified through the pages it renders. So check it in a browser:

```bash
python run.py
```

Sign in, log an entry if the account has none, open `/account`, click **Download my data**, and confirm a `bodyshop-export-<date>.csv` lands with your sets in it. Then confirm nothing else broke — `/log`, `/summary` and `/progress` all go through `request`, which this task refactored.

- [ ] **Step 8: Run the full suite**

Run: `pytest`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add app/static/js/api.js app/templates/account.html tests/test_pages.py
git commit -m "Offer the export from the account page

The browser cannot put an Authorization header on a link it follows, so the
file is fetched and handed to a synthetic anchor. That keeps the API
bearer-only: no signed URL and no cookie for the sake of one endpoint.

The 401 refresh-and-retry moves into fetchWithRefresh so a non-JSON response
can inherit it rather than reimplement it. Still one retry, never a loop.

Export sits beside deletion because they are the same obligation from opposite
ends."
```

---

### Task 6: A reachable contact address

**Files:**
- Modify: `app/config.py`
- Modify: `app/views.py` (`inject_globals`)
- Modify: `.env.example`
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: `app.config["CONTACT_EMAIL"]`, and `contact_email` in every template's context. Task 7's `privacy.html` renders it.

- [ ] **Step 1: Write the failing tests**

In `tests/test_config.py`, add `CONTACT_EMAIL` to the `SUPABASE` dict so the existing successful-boot tests keep passing (rename it in place — it is now "everything production insists on"):

```python
#: The settings production also insists on, so the tests that assert a
#: *successful* boot are not testing those checks by accident. Spread into
#: create_app with ``**REQUIRED``.
REQUIRED = {
    "SUPABASE_URL": "https://p.supabase.co",
    "SUPABASE_ANON_KEY": "anon",
    "SUPABASE_SERVICE_ROLE_KEY": "service",
    "CONTACT_EMAIL": "hello@example.com",
}
```

Replace every `**SUPABASE` in the file with `**REQUIRED`, and every explicit
`SUPABASE_URL=`/`SUPABASE_ANON_KEY=`/`SUPABASE_SERVICE_ROLE_KEY=` keyword in the
four rejection tests with the same keyword plus `CONTACT_EMAIL="hello@example.com"`,
so those tests still fail for the reason they name. For example:

```python
    def test_a_missing_supabase_url_is_rejected(self):
        with pytest.raises(ConfigError, match="SUPABASE_URL"):
            create_app("production", SECRET_KEY="real", DATABASE_URL=POSTGRES,
                       CONTACT_EMAIL="hello@example.com", SUPABASE_URL=None)
```

Then append to `class TestProductionRefusesUnsafeConfig`:

```python
    def test_a_missing_contact_email_is_rejected(self):
        """A privacy policy naming no way to reach anyone fails silently.

        The other four checks catch a deployment that would lose data or leak
        one. This one catches a deployment that is *unreachable* — which nobody
        notices until someone needed to reach you and could not, and which
        Phase 10's store requirements inherit.
        """
        with pytest.raises(ConfigError, match="CONTACT_EMAIL"):
            create_app("production", SECRET_KEY="real", DATABASE_URL=POSTGRES,
                       SUPABASE_URL="https://p.supabase.co",
                       SUPABASE_ANON_KEY="anon",
                       SUPABASE_SERVICE_ROLE_KEY="service",
                       CONTACT_EMAIL=None)
```

- [ ] **Step 2: Run the tests to verify the new one fails**

Run: `pytest tests/test_config.py -v`
Expected: `test_a_missing_contact_email_is_rejected` FAILS (no `ConfigError` raised); everything else passes.

- [ ] **Step 3: Add the setting and the check**

In `app/config.py`, add to `BaseConfig` after `EXERCISE_IMAGE_BASE`:

```python
    #: Where someone reaches a human. Rendered into ``/privacy`` and nowhere
    #: else. **Production refuses to boot without it** — a privacy policy that
    #: names no contact route is the launch floor failing silently, and it is
    #: also a store requirement Phase 10 inherits.
    CONTACT_EMAIL = os.environ.get("BODYSHOP_CONTACT_EMAIL")
```

In `TestingConfig`, pin it so the suite never depends on the environment:

```python
    CONTACT_EMAIL = "test@example.com"
```

In `validate()`, after the service-role-key check:

```python
    if not config.get("CONTACT_EMAIL"):
        raise ConfigError(
            "BODYSHOP_CONTACT_EMAIL is unset. The privacy policy renders it, "
            "and a policy naming no way to reach anyone is not one. See "
            ".env.example."
        )
```

- [ ] **Step 4: Expose it to templates**

In `app/views.py`'s `inject_globals`, add beside the `supabase` key:

```python
        "contact_email": current_app.config.get("CONTACT_EMAIL") or "",
```

- [ ] **Step 5: Document the variable**

In `.env.example`, add under the `# --- App ---` section:

```
# Where someone reaches a human. Rendered into /privacy and nowhere else.
# Production refuses to boot without it: a privacy policy naming no contact
# route is not a privacy policy.
# BODYSHOP_CONTACT_EMAIL=
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: all pass.

- [ ] **Step 7: Run the full suite**

Run: `pytest`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add app/config.py app/views.py .env.example tests/test_config.py
git commit -m "Refuse to boot production with no contact address

The four existing checks catch a deployment that would lose data or leak one.
This catches one that is unreachable — which nobody notices until somebody
needed to reach you and could not.

It joins them rather than degrading the page, because a privacy policy naming
no contact route is not a privacy policy, and Phase 10's store requirements
inherit the same obligation."
```

---

### Task 7: The privacy policy

**Files:**
- Create: `app/templates/privacy.html`
- Modify: `app/views.py`
- Modify: `app/templates/account.html`, `login.html`, `signup.html`
- Test: `tests/test_pages.py` (append)

**Interfaces:**
- Consumes: `contact_email` from Task 6; the export from Tasks 4–5.
- Produces: `GET /privacy`, endpoint `views.privacy_page`, rendered with `bare=True`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pages.py`:

```python
class TestPrivacyPage:
    def test_it_renders(self, client):
        response = client.get("/privacy")
        assert response.status_code == 200
        assert b"Privacy" in response.data

    def test_it_is_bare_and_not_a_chapter(self, client):
        """Like the five auth pages: outside the book.

        `sections` in base.html must never learn about it, or the chapter
        numbering and the shelf-splitting tests start describing a book with a
        privacy policy in it.
        """
        body = client.get("/privacy").data.decode()
        assert "shelf-stack" not in body
        assert "tab-bar" not in body
        assert "01 Chp." not in body

    def test_it_names_the_contact_address(self, client, app):
        assert app.config["CONTACT_EMAIL"] in client.get("/privacy").data.decode()

    def test_it_names_every_third_party_that_sees_you(self, client):
        """Including jsDelivr, which most apps do not disclose.

        An exercise photograph is a request to someone else's CDN, which means
        that CDN sees your IP address. EXERCISE_IMAGE_BASE exists so this can be
        ended by configuration; until it is, it gets said out loud.
        """
        body = client.get("/privacy").data.decode()
        for party in ("Supabase", "Render", "Sentry", "jsDelivr"):
            assert party in body

    def test_it_links_to_export_and_deletion(self, client):
        body = client.get("/privacy").data.decode()
        assert "/account" in body

    @pytest.mark.parametrize("path", ["/login", "/signup", "/account"])
    def test_the_bare_pages_link_to_it(self, client, path):
        assert "/privacy" in client.get(path).data.decode()

    def test_the_home_page_does_not_link_to_it(self, client):
        """`/` is exactly one screen, and a privacy link does not earn height."""
        assert "/privacy" not in client.get("/").data.decode()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pages.py -k Privacy -v`
Expected: FAIL — 404 on `/privacy`, and the link assertions fail.

- [ ] **Step 3: Add the route**

In `app/views.py`, add after `account_page`:

```python
@bp.get("/privacy")
def privacy_page():
    """What is collected, who else sees it, and how to leave.

    Bare, like the auth pages: it is not a chapter of the product, so
    ``sections`` in ``base.html`` never learns about it and the chapter
    numbering is untouched. Linked from the three bare pages and deliberately
    **not** from ``/``, which is pinned to one screen — anything new there has
    to earn its height, and a privacy link does not.
    """
    return render_template(
        "privacy.html", page="privacy", bare=True, selected_date=_requested_date()
    )
```

Update the module docstring's list of pages outside the book — the comment above `login_page` says "All five are public shells". Change it to six and name the privacy policy.

- [ ] **Step 4: Write the page**

Create `app/templates/privacy.html`. It reuses the existing `.auth-*` classes — **no new CSS**, because the stylesheet is compiled and this phase does not run the toolchain.

```html
{% extends "base.html" %}
{% block title %}Privacy — Body Shop{% endblock %}

{% block content %}
<div class="auth-shell">
  <h1 class="auth-title">Privacy</h1>

  <p class="auth-note">
    Body Shop is a workout log. It holds the sets you write down and the email
    address you signed up with, and it is built so that there is very little
    else to hold.
  </p>

  <div class="flex flex-col gap-3 border-t border-base-content/15 pt-6">
    <span class="type-label">What is stored</span>
    <p class="auth-note">
      Your email address, and every set you log — the movement, the date, the
      weight in kilograms, the reps and the RPE if you record one. That is the
      whole of it.
    </p>
  </div>

  <div class="flex flex-col gap-3 border-t border-base-content/15 pt-6">
    <span class="type-label">What is not stored</span>
    <p class="auth-note">
      No bodyweight, no measurements, no photographs of you. No analytics, no
      advertising, no tracking pixels, and no third-party scripts on any page.
      Your password is held by Supabase and never reaches this app.
    </p>
    <p class="auth-note">
      Nobody is compared to anybody. The estimated one-rep max on the progress
      page is worked out from your own sets; the app holds no strength standards
      and no population data to rank you against.
    </p>
  </div>

  <div class="flex flex-col gap-3 border-t border-base-content/15 pt-6">
    <span class="type-label">Who else sees it</span>
    <p class="auth-note">
      <strong>Supabase</strong> holds your email address, your password and the
      database your workouts live in.
      <strong>Render</strong> runs the app, so its logs record the requests your
      browser makes, including your IP address.
      <strong>Sentry</strong> receives an error report when something breaks;
      it is configured not to send personal data with one.
    </p>
    <p class="auth-note">
      <strong>jsDelivr</strong> serves the exercise photographs. That means your
      browser fetches images from their servers directly, and they see your IP
      address when it does. The images can be moved to our own origin by
      configuration, and this line will change when they are.
    </p>
  </div>

  <div class="flex flex-col gap-3 border-t border-base-content/15 pt-6">
    <span class="type-label">Your data is yours</span>
    <p class="auth-note">
      Download everything you have logged as a CSV file, any time, from
      <a href="{{ url_for('views.account_page') }}">your account</a>.
    </p>
    <p class="auth-note">
      Delete your account from the same page. It removes the account and every
      workout in it, including the sign-in record held by Supabase. It cannot be
      undone, and nothing is kept back.
    </p>
  </div>

  <div class="flex flex-col gap-3 border-t border-base-content/15 pt-6">
    <span class="type-label">Contact</span>
    <p class="auth-note">
      Questions about any of this:
      <a href="mailto:{{ contact_email }}" class="type-data">{{ contact_email }}</a>
    </p>
  </div>

  <p class="auth-note"><a href="{{ url_for('views.home_page') }}">Back to Body Shop</a></p>
</div>
{% endblock %}
```

- [ ] **Step 5: Link it from the three bare pages**

In `app/templates/account.html`, add above the existing "Back to Body Shop" line:

```html
  <p class="auth-note"><a href="{{ url_for('views.privacy_page') }}">Privacy</a></p>
```

In `app/templates/login.html` and `app/templates/signup.html`, add the same line beside whatever footer note each already carries. On `signup.html` it belongs directly under the submit button — that is the moment someone is deciding whether to hand over an address.

Do **not** add it to `home.html`. `.home-masthead` is `height: 100vh; overflow: hidden` from `lg:` and only the specimen flexes; a new link in the follow row costs height nothing gives back.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pytest tests/test_pages.py -k Privacy -v`
Expected: all pass.

- [ ] **Step 7: Look at it**

```bash
python run.py
```

Open `/privacy` in both themes (the toggle is bottom-left) and at a narrow width. It should read as one continuous ground with hairline-ruled bands, like the account page — no cards, no shadows.

- [ ] **Step 8: Run the full suite**

Run: `pytest`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add app/templates/privacy.html app/templates/account.html \
        app/templates/login.html app/templates/signup.html \
        app/views.py tests/test_pages.py
git commit -m "Say what the app holds and who else sees it

Bare like the auth pages, so `sections` never learns about it and the chapter
numbering is untouched. Linked from login, signup and the account page, and
deliberately not from / — that page is one screen and a privacy link does not
earn its height.

It names jsDelivr, which most apps do not: an exercise photograph is a request
to someone else's CDN and they see your IP when it loads. Saying so is the
point of writing one of these."
```

---

### Task 8: Error monitoring

**Files:**
- Create: `app/observability.py`
- Modify: `app/__init__.py`, `app/config.py`, `requirements.txt`, `.env.example`
- Modify: `CLAUDE.md` (the `create_app` side-effect invariant)
- Test: `tests/test_config.py` (append a small class)

**Interfaces:**
- Consumes: `app.config["SENTRY_DSN"]`.
- Produces: `init_sentry(app: Flask) -> bool` — returns whether Sentry was initialised. Called from `create_app` after `validate_config`.

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, append:

```
# Error reporting. Initialised only when BODYSHOP_SENTRY_DSN is set, so
# development and the test suite never load it and the suite stays offline.
sentry-sdk[flask]>=2.0,<3.0
```

Then: `pip install -r requirements.txt`

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_config.py`:

```python
class TestSentryIsOptional:
    """Unset DSN must mean *nothing happens* — that is what keeps the suite
    offline and the factory free of side effects in development."""

    def test_no_dsn_means_no_initialisation(self):
        from app.observability import init_sentry

        app = create_app("testing", DATABASE_URL="sqlite:///x.db")
        assert app.config.get("SENTRY_DSN") is None
        assert init_sentry(app) is False

    def test_the_testing_config_never_carries_a_dsn(self, monkeypatch):
        """Even with one in the environment. A test run must never report."""
        monkeypatch.setenv("BODYSHOP_SENTRY_DSN", "https://x@example.test/1")
        app = create_app("testing", DATABASE_URL="sqlite:///x.db")
        assert app.config.get("SENTRY_DSN") is None
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_config.py -k Sentry -v`
Expected: FAIL — `No module named 'app.observability'`.

- [ ] **Step 4: Add the setting**

In `app/config.py`, add to `BaseConfig` after `CONTACT_EMAIL`:

```python
    #: Optional. Set → errors are reported to Sentry. Unset → nothing is
    #: initialised and nothing is sent, which is the development and test case.
    SENTRY_DSN = os.environ.get("BODYSHOP_SENTRY_DSN")
```

In `TestingConfig`, pin it off — an environment variable must never make a test run report:

```python
    # Pinned to None so a developer with a DSN in their environment cannot make
    # the suite report a deliberately-raised test exception to production Sentry.
    SENTRY_DSN = None
```

- [ ] **Step 5: Write the module**

Create `app/observability.py`:

```python
"""Error reporting.

Sentry is initialised from :func:`app.create_app`, but **only when a DSN is
configured** — which development and the test suite never do. That is what keeps
the suite offline and keeps the factory free of side effects everywhere it is
called in a loop.

This is the one thing the factory does that reaches outside the process, and it
is permitted because it is not the thing the no-side-effects rule is about: that
rule exists because ``ensure_db()`` used to open a connection and apply DDL on
every boot, which crashed on a read-only filesystem and left fresh deploys with
an unversioned schema. Sentry's ``init`` opens no connection and touches no
disk; it registers hooks and starts a background transport that sends nothing
until something is captured.
"""

from __future__ import annotations

from flask import Flask

#: Set once a process has initialised, so a factory called twice — which the
#: test suite does constantly and a WSGI server can do — does not stack
#: integrations.
_initialised = False


def init_sentry(app: Flask) -> bool:
    """Start error reporting for ``app``. Returns whether it did.

    A missing DSN is a valid configuration meaning "do not report", not an
    error: this must be a no-op in development, in the suite, and in any
    deployment that has not set one up.
    """
    global _initialised

    dsn = app.config.get("SENTRY_DSN")
    if not dsn or _initialised:
        return False

    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    from . import __version__

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        environment=app.config.get("CONFIG_NAME", "production"),
        release=f"body-shop@{__version__}",
        # The privacy policy says error reports carry no personal data. This is
        # the line that makes that true: with it on, the SDK attaches request
        # headers, cookies and the user's address to every event.
        send_default_pii=False,
        # Errors, not performance. A workout log has no latency problem worth a
        # trace budget, and traces are the expensive half of the free tier.
        traces_sample_rate=0.0,
    )

    _initialised = True
    return True
```

- [ ] **Step 6: Call it from the factory**

In `app/__init__.py`, after `validate_config(app.config)` and before `from . import db`:

```python
    # After validation, so a misconfigured production deploy fails on its own
    # terms rather than reporting the failure to a service it may not have.
    # A no-op unless SENTRY_DSN is set — see app/observability.py for why this
    # is the one permitted exception to the factory's no-side-effects rule.
    from .observability import init_sentry

    init_sentry(app)
```

Also extend the factory's module docstring: it currently says the factory "opens no connection, runs no DDL, and touches the filesystem only to create `instance/`". Add a sentence naming Sentry as the one outward-facing thing it does, and why that is not the same class of side effect.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/test_config.py -k Sentry -v`
Expected: 2 passed.

- [ ] **Step 8: Narrow the invariant in CLAUDE.md**

Find the bullet beginning **"Nothing in `create_app` opens a connection or runs DDL."** and add to the end of it:

```
  The one outward-facing thing the factory does is `init_sentry`, and only when
  `SENTRY_DSN` is set — it opens no connection and touches no disk, which is
  what this rule is actually about.
```

- [ ] **Step 9: Document the variable**

In `.env.example`, add a section:

```
# --- Error monitoring ------------------------------------------------------
# Optional. Set and errors are reported to Sentry; unset and the SDK is never
# initialised, which is what keeps development and the test suite offline.
# Personal data is deliberately not attached (send_default_pii=False), because
# /privacy says so.
# BODYSHOP_SENTRY_DSN=
```

- [ ] **Step 10: Run the full suite**

Run: `pytest`
Expected: all pass.

- [ ] **Step 11: Commit**

```bash
git add app/observability.py app/__init__.py app/config.py \
        requirements.txt .env.example CLAUDE.md tests/test_config.py
git commit -m "Report production errors, and only production errors

Sentry initialises only when a DSN is configured, which development and the
suite never do — so the suite stays offline and the factory stays a no-op
outside a real deployment. The testing config pins the DSN to None so a DSN in
someone's environment cannot make a test run report to production.

send_default_pii is off because /privacy claims error reports carry no personal
data, and that claim has to be made true here rather than asserted there.

CLAUDE.md's no-side-effects invariant is narrowed rather than quietly broken:
the rule exists because ensure_db() opened a connection and applied DDL on
every boot. Sentry's init does neither."
```

---

### Task 9: The operations runbook, and closing the phase

**Files:**
- Create: `docs/OPERATIONS.md`
- Modify: `README.md`, `docs/ROADMAP.md`, `docs/ARCHITECTURE.md`, `CHANGELOG.md`, `CLAUDE.md`

**Interfaces:**
- Consumes: everything above.
- Produces: nothing code depends on.

- [ ] **Step 1: Write the runbook**

Create `docs/OPERATIONS.md` covering, in this order:

**1. What runs where.** A table: web service on Render (free plan, `render.yaml`), Postgres and auth in Supabase, images on jsDelivr, errors in Sentry. State that Render holds no data — every persistent thing is in Supabase — which is what makes the web service disposable.

**2. First deploy.** Numbered, in this order, because two of them are ordering traps:

1. In Supabase, note the **transaction** pooler URL (6543) for the app and the **session** pooler URL (5432) for migrations.
2. Run the migrations **before** the first deploy, from your machine:
   `DATABASE_URL=<session-pooler-url> flask --app app upgrade-db`
   A web service that boots against an unmigrated database serves 500s from every authenticated route.
3. Render → New → Blueprint → this repository. Fill in every `sync: false` value.
4. After Render assigns the URL, go to Supabase → Authentication → URL Configuration and add `https://<name>.onrender.com` as the Site URL, plus `https://<name>.onrender.com/verify` and `https://<name>.onrender.com/reset-password` as redirect URLs. **Confirmation and recovery emails point at whatever is configured here**, so until this is done a new signup gets an email whose link goes to localhost.
5. Check `https://<name>.onrender.com/healthz`.

**3. Deploying a change.** Push to `main`; Render builds. **Wait for CI green first** — specifically the Postgres job, because the SQLite job cannot catch a dialect difference by construction. If the change includes a migration, run `upgrade-db` against the session pooler **before** pushing, since a rolling deploy runs new code against the old schema otherwise.

**4. Rolling back.** Render's dashboard → Rollback to a previous deploy. Note the asymmetry plainly: **code rolls back, migrations do not.** If a deploy included a migration, rolling back the code leaves the new schema in place, which is fine for an additive revision and is not for a destructive one. `downgrade_db` exists and has no CLI wrapper on purpose — backing a schema out is a deliberate act.

**5. The restore drill.** The numbered procedure from the spec, verbatim:

1. `pg_dump` production through the session pooler.
2. `pg_restore` into a **scratch** database. Never over production.
3. `alembic current` against the restored copy equals `head`.
4. Row counts for `user`, `workout_entry` and `workout_set` match the source.
5. Optionally `BODYSHOP_TEST_DATABASE_URL=<scratch> pytest`, **last**, because the suite truncates.

Include the actual commands. End the section with a dated line:

```markdown
**Last successful drill:** _never run_
```

Say that an untested backup is a belief rather than a backup, and that this line is here so a stale one is visible.

**6. Upgrading off the free tier.** The free instance sleeps after 15 minutes idle and the next request pays roughly a 50-second cold start — bad for an app opened mid-set. The change is `plan: starter` in `render.yaml` (and then `preDeployCommand: flask --app app upgrade-db` becomes available, pointed at the session pooler).

**7. When something breaks.** Short checklist: is `/healthz` answering (process) → is Supabase up (data) → what does Sentry say → Render's logs. Note that `/healthz` answering while the app 500s means the database, which is the whole reason the health check does not touch it.

- [ ] **Step 2: Point the README at it**

In `README.md`, replace the production paragraph around line 153 with a short **Deployment** section: Render + Supabase in two sentences, and a link to `docs/OPERATIONS.md`. Update line 248's "Vercel hosting" in the roadmap summary — that plan is now decided against.

- [ ] **Step 3: Close the phase in the roadmap**

In `docs/ROADMAP.md`:

- Change the "Current state" paragraph (lines 9–17) to include Phase 7.
- Replace the `### 1. Phase 7` section with a shipped writeup: Flask stayed; **Vercel was declined on record** — this is a long-lived WSGI process with a migration step, and every serverless accommodation in the repo (`NullPool`, `prepare_threshold=None`, the side-effect-free factory) survives only because it is also correct behind a connection pooler. Migrations are not a deploy hook because `preDeployCommand` is paid-tier and DDL through a transaction pooler is not something to rely on. Name the free tier's cold start as a known, documented limitation rather than a silent one.
- Renumber the prioritized list so Phase 8.4 is `### 1.`
- In the mermaid graph, change `P7[Phase 7: Stack decision and deployment]` to `P7[Phase 7: Deployment ✓]`.
- Update the closing paragraph — "Phase 7 gates launch" becomes past tense.
- Add Phase 7 to the "Already shipped" list.

- [ ] **Step 4: Update the architecture doc**

In `docs/ARCHITECTURE.md`:

- Add a **Deployment** section: the service shape table, why migrations run from the operator's machine, and why `/healthz` touches no database.
- Add `app/services/export.py` and `app/observability.py` to the layer-ownership table.
- Add to **Deliberate limitations**: the free tier's spin-down, and that error monitoring is opt-in by DSN.
- The existing bullet on `NullPool` says it is deliberate for serverless. Extend it: the deployment is not serverless, and the setting survives because a pooler is what Supabase puts in front regardless.

- [ ] **Step 5: Update CLAUDE.md's Architecture paragraph**

Two facts changed: `app/views.py` renders **twelve** shells, not eleven — six chapters and **six** bare pages, the sixth being `/privacy`. And the "Planned direction" sentence lists deployment first; that is done now, so the list starts at 8.4.

- [ ] **Step 6: Update the changelog**

Add a Phase 7 entry to `CHANGELOG.md` following the file's existing format.

- [ ] **Step 7: Run the full suite**

Run: `pytest`
Expected: all pass.

- [ ] **Step 8: Verify the docs are not lying**

Re-read `docs/OPERATIONS.md` against what was actually built. Specifically check: the endpoint names match `app/api.py`, the CLI commands match `app/db.py`, and the environment variable names match `app/config.py` exactly. A doc that contradicts the code is a bug in this repo.

- [ ] **Step 9: Commit**

```bash
git add docs/OPERATIONS.md README.md docs/ROADMAP.md docs/ARCHITECTURE.md \
        CHANGELOG.md CLAUDE.md
git commit -m "Write down how this thing is operated

The runbook covers the two ordering traps that only bite once: migrations run
before the first deploy, and Supabase's redirect URLs have to be updated after
Render assigns a hostname, or every confirmation email points at localhost.

The restore drill carries a dated line recording when it was last run, because
an untested backup is a belief rather than a backup and a stale one should be
visible.

Phase 7 closes in the roadmap with the Vercel decision recorded: this is a
long-lived WSGI process with a migration step, and the serverless
accommodations in the repo survive only because they are also correct behind a
connection pooler."
```

---

### Task 10: Deploy

This task needs the account holder — it cannot be done by an agent. Everything above is the preparation for it.

- [ ] **Step 1: Merge to `main`**

The blueprint's `branch: main` means Render builds from `main`.

```bash
git checkout main
git merge --no-ff phase-7-deployment
git push origin main
```

- [ ] **Step 2: Wait for CI green**

Both jobs, including the Postgres one. Production is gated on it because the SQLite job cannot catch a dialect difference.

- [ ] **Step 3: Follow `docs/OPERATIONS.md` § First deploy**

Migrations first, then the blueprint, then Supabase's redirect URLs, then `/healthz`.

- [ ] **Step 4: Walk the app end to end on the deployed URL**

Sign up with a real address and confirm the email link lands on `/verify` on the Render host rather than localhost. Then: log a session, check `/summary` grades it, check `/progress` draws, download the CSV, read `/privacy`, and delete the account.

- [ ] **Step 5: Run the restore drill once and date it**

`docs/OPERATIONS.md` § The restore drill. Then replace `**Last successful drill:** _never run_` with the date, and commit that one line. A drill that has never been run is not a tested restore, and the roadmap asked for a tested one.

---

## Self-review

**Spec coverage.** Every section of the design maps to a task: service shape → 2; migrations-not-a-hook → 2 and 9; `/healthz` → 1; gunicorn → 2; export → 3, 4, 5; contact email → 6; privacy policy → 7; Sentry → 8; backups with tested restore → 9 and 10; "production stays gated on the Postgres CI job" → 9's runbook and 10's step 2; docs → folded into each task, with the cross-cutting ones in 9.

**One deliberate departure from the spec.** The spec's test table put the `/privacy` and `/healthz` tests in `tests/test_pages.py` and the export's in `tests/test_export.py`; this plan also adds `TestSentryIsOptional` to `tests/test_config.py`, which the spec did not name. It belongs there — it is a configuration-resolution test, and `test_config.py` is where the "unset means X" cases already live.

**Ordering.** Task 6 precedes Task 7 because the privacy page renders `contact_email`. Task 3 precedes 4 precedes 5. Task 1 precedes 2 because `render.yaml` references `/healthz`. Everything else is independent.
