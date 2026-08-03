# Phase 7 — Stack decision and deployment

Design, 2026-08-03. Implements [ROADMAP.md](../../ROADMAP.md) §1.

## The decision

**Flask stays. Render hosts it. Supabase holds the database.**

The roadmap said "prefer Flask unless a measured constraint forces a rewrite"
and "choose Vercel only if it wins on record". Nothing measured forces a
rewrite, and Vercel does not win: this app is a long-lived WSGI process with a
migration step, and every accommodation the repo already carries for
serverless — `NullPool`, `prepare_threshold=None`, a side-effect-free
`create_app` — was written for a deployment shape we are now declining. Those
accommodations stay, because they cost nothing and are correct behind a
connection pooler regardless.

Postgres lives in the Supabase project that already holds auth. One vendor, one
dashboard, one backup story, and `.env.example` is already written for it: the
transaction pooler (6543) for the app, the session pooler (5432) for
migrations.

## Service shape

| Piece | Where | Why |
| --- | --- | --- |
| Web service | Render, `plan: free` | Blueprint in `render.yaml`. |
| Postgres | Supabase | Already there for auth. |
| Auth | Supabase | Unchanged from Phase 5. |
| Exercise images | jsDelivr, pinned | Unchanged. Disclosed in the privacy policy. |
| Errors | Sentry | Only when a DSN is configured. |

**Free tier, and the upgrade written down.** The service sleeps after 15
minutes idle and the next request pays roughly a 50-second cold start. That is
genuinely bad for a workout log — the app is opened mid-set — so
`docs/OPERATIONS.md` carries the exact change to Starter (`plan: starter`, one
line) and says plainly what the free tier costs. Shipping on free proves the
deploy end to end without spending anything; it is not a claim that the
limitation does not matter.

### Migrations are not a Render hook

Render's `preDeployCommand` and Shell are both paid-tier features. Migrations
therefore run **from the operator's machine against the session pooler
(5432)**:

```bash
DATABASE_URL=<session-pooler-url> flask --app app upgrade-db
```

This matches what `run.py`'s docstring already says — *migrate deliberately, as
a deploy step* — and sidesteps a real hazard: DDL through a transaction-mode
pooler is not something to rely on. `docs/OPERATIONS.md` carries the
`preDeployCommand` line to enable on Starter, and the note that it must point
at the session pooler even then.

## New files

### `render.yaml`

```yaml
services:
  - type: web
    name: body-shop
    runtime: python
    plan: free
    buildCommand: pip install -r requirements.txt
    startCommand: gunicorn wsgi:application
    healthCheckPath: /healthz
    envVars:
      - key: BODYSHOP_CONFIG
        value: production
      - key: BODYSHOP_SECRET_KEY
        generateValue: true
      - key: DATABASE_URL
        sync: false
      # ... the Supabase keys, the contact address and the Sentry DSN, all
      # `sync: false` so they are entered in the dashboard and never committed.
```

Every secret is `sync: false`. `BODYSHOP_SECRET_KEY` uses `generateValue: true`
— Render mints it once and keeps it, which is strictly better than a human
pasting one.

### `.python-version` → `3.13`

CI's Postgres job already pins 3.13. Render reads this file, so the deployed
interpreter cannot silently drift from the one the migration round-trip is
proved against.

### `app/observability.py`

One function, `init_sentry(app)`, called from `create_app` **only when
`SENTRY_DSN` is set**. Development and the test suite never have it set, so the
suite stays offline and the factory stays side-effect-free in every context
that matters.

- `send_default_pii=False` — the privacy policy claims errors are reported
  without personal data, so the SDK must be configured to make that true.
- `release` from `app.__version__`, `environment` from `CONFIG_NAME`.
- Guarded against double-init, because `create_app` is called many times in a
  process during tests and could be twice in a WSGI server.

This is a side effect in the factory, which the repo otherwise forbids. The
forbidden thing is specifically *opening a connection or running DDL* — Sentry
does neither at init. The invariant in CLAUDE.md is narrowed to say so rather
than left to look violated.

### `app/services/export.py`

Pure: takes `list[WorkoutEntry]`, returns CSV text. No SQL, no Flask, no
request context — so it is testable on its own and the layering rule holds.

### `app/templates/privacy.html` + `GET /privacy`

`bare=True`, like the five auth pages. Not a chapter: `sections` in `base.html`
never learns about it, so the chapter-ordering tests stay untouched.

### `docs/OPERATIONS.md`

Deploy, rollback, restore drill, incident checklist. See "The launch floor"
below.

## Changes to existing files

### `gunicorn` moves into `requirements.txt`

CLAUDE.md currently records that gunicorn is deliberately *not* a dependency
and must be installed separately. That was defensible with no deployment; with
a build command it is not — it means either a second install line or a start
command that fails on a clean build. The dependency is added and that line in
CLAUDE.md is edited in the same commit.

### `GET /healthz`

```json
{ "status": "ok", "version": "0.1.0" }
```

**It does not touch the database, and that is the whole design.** Render
restarts a service whose health check fails; a health check that queries
Postgres converts a thirty-second Supabase blip into a restart loop, which
turns a recoverable outage into a longer one. It answers "is this process
serving HTTP", which is the only question Render is asking. Database health is
a Supabase dashboard concern and a Sentry alert.

Registered on the views blueprint, outside `/api`, and unauthenticated — a
health check cannot carry a bearer token.

### `GET /api/entries/export.csv`

Bearer-authed like every other endpoint, via `@require_user`. The browser
cannot put an `Authorization` header on a link it follows, so `api.js` fetches
it, wraps the body in a `Blob` and triggers the download — no signed URL, no
second auth mechanism, no cookie.

Whole log, no date filtering. This is the "get my data out" obligation the
privacy policy promises; a spreadsheet filters dates by itself.

```
entry_id,date,exercise_id,exercise,set_number,set_type,weight_kg,reps,rpe
41,2026-08-01,Barbell_Squat,Barbell Squat,1,warmup,60,5,
41,2026-08-01,Barbell_Squat,Barbell Squat,2,working,100,5,8
42,2026-08-01,Sit-Up,Sit-Up,1,working,,15,
```

- **One row per set**, including warm-ups, with `set_type` naming them. This is
  the raw record, not the graded summary — the summary's warm-up exclusion is a
  grading rule and has no business in an export.
- **Weight is kilograms and the header says so.** `weight_kg`, never a display
  unit; conversion lives only in `ui.js` and an export does not go through it.
- **Missing is an empty cell, never `0`.** `weight`, `reps` and `rpe` are
  nullable and `0` is a legitimate bodyweight entry, so the writer guards with
  `is None`.
- Ordered by date then entry then set number, so the file reads like the log.
- `Content-Type: text/csv; charset=utf-8`, `Content-Disposition: attachment;
  filename="bodyshop-export-<today>.csv"`.

A download button on `/account`, next to the deletion block — export and
deletion are the same obligation from opposite ends.

### `BODYSHOP_CONTACT_EMAIL`, required in production

Joins the four checks in `config.validate()`. **Production refuses to boot
without it.** A privacy policy naming no way to reach anyone is the launch
floor failing silently, and Phase 10's store requirements inherit the same
obligation. Failing at deploy is how you find out; a user who could not reach
you is how you otherwise would.

Rendered into the privacy page and nowhere else.

### The privacy policy's content

It says what is true, including the parts nobody discloses:

- **Collected:** email address (held by Supabase, not by us — there is no
  `password_hash` and no `verified_at` in our `user` table), and the workout log
  you write.
- **Not collected:** no bodyweight, no analytics, no advertising, no tracking
  pixels, no third-party scripts on any page. Nobody is compared to anybody —
  the estimated 1RM on `/progress` is computed from your own sets and no
  population data exists in the app.
- **Third parties, named:** Supabase (email, auth, database), Render (request
  logs, IP address), Sentry (error reports, personal data off), **jsDelivr
  (sees your IP when an exercise photograph loads)**. That last one is the
  disclosure most apps skip; `EXERCISE_IMAGE_BASE` exists precisely so it can be
  ended by configuration.
- **Your data:** export it (link), delete it (link to `/account` —
  irreversible, cascades through every row, and removes the Supabase auth
  record too).
- **Contact:** `BODYSHOP_CONTACT_EMAIL`.

Linked from `/signup`, `/login` and `/account`. **Not from `/`** — that page is
`height: 100vh; overflow: hidden` from `lg:` and anything new there has to earn
its height or replace something. A privacy link does not.

## The launch floor

The roadmap names four items. All four ship.

### 1. Backups with tested restore

Supabase owns the backups (daily on free, PITR on paid). The repo owns the
**drill**, because an untested backup is a belief rather than a backup.
`docs/OPERATIONS.md` documents it as a procedure someone can follow:

1. `pg_dump` production through the session pooler.
2. `pg_restore` into a scratch database — never over production, never over
   anything holding real workouts.
3. `alembic current` against the restored copy equals `head`.
4. Row counts for `user`, `workout_entry` and `workout_set` match the source.
5. Optionally `BODYSHOP_TEST_DATABASE_URL=<scratch> pytest` for schema sanity.
   This **truncates** the restored data, which is why it is last and why the
   copy is scratch.

The doc carries a dated line recording the last successful drill, so a stale
one is visible rather than assumed. No bespoke tooling: `pg_dump`, `alembic`
and the suite already exist.

### 2. Error monitoring

Sentry, as above. `sentry-sdk[flask]` is the one runtime dependency this phase
adds.

### 3. Privacy policy

As above.

### 4. CSV export

As above.

### 5. Production stays gated on the Postgres CI job

Already true and unchanged: `.github/workflows/ci.yml` runs the suite against a
`postgres:16` service container and round-trips the migration chain both ways.
`docs/OPERATIONS.md` states that a deploy follows a green run on `main`,
because the SQLite job cannot catch a dialect difference by construction.

## Testing

| Test | Asserts |
| --- | --- |
| `tests/test_pages.py` | `/healthz` returns 200 and JSON; **it opens no database connection**; `/privacy` renders, is bare (no shelf, no tab bar, no chapter number), and is absent from `sections`; `/signup`, `/login` and `/account` link to it; `/` does not. |
| `tests/test_export.py` | Header row and column order; one row per set including warm-ups; weight in kg; `None` renders as an empty cell and `0` renders as `0`; ordering by date/entry/set; the `Content-Disposition` filename; an empty log gives a header and no rows; commas and quotes in an exercise name are escaped. |
| `tests/test_ownership.py` | The export endpoint added to the two-user walk. A row of user A's in user B's export is a data leak, so this belongs in the file whose failures are read as leaks. |
| `tests/test_config.py` | Production refuses to boot with `BODYSHOP_CONTACT_EMAIL` unset; the message names the variable. |
| `tests/test_api.py` | The export endpoint 401s without a bearer token. |

Sentry is not tested beyond "no DSN means `init_sentry` does nothing" — testing
a vendor SDK's transport is testing the vendor.

## Documentation updated in the same commits

- **ROADMAP.md** — Phase 7 marked shipped, with the Vercel decision recorded
  and the free-tier limitation named. The dependency graph's `P7` ticks.
- **ARCHITECTURE.md** — a deployment section, `/healthz` and the export in the
  layer table, and the free-tier cold start added to "Deliberate limitations".
- **API.md** — `GET /api/entries/export.csv` and `GET /healthz`, with the
  exhaustive payload the file's convention requires.
- **CLAUDE.md** — gunicorn is now a dependency; eleven server-side shells become
  twelve; the `create_app` side-effect invariant narrowed to name Sentry as the
  one permitted exception; the new production config check; the export's
  kg/null rules.
- **README.md** — a deployment section pointing at `docs/OPERATIONS.md`.
- **.env.example** — `BODYSHOP_SENTRY_DSN`, `BODYSHOP_CONTACT_EMAIL`, and the
  note that Supabase's redirect URLs must gain the Render origin.
- **CHANGELOG.md** — the phase.

## Out of scope

- **Creating the Render service.** That needs the account holder. This phase
  delivers everything up to and including "click Deploy", plus the runbook that
  walks it.
- **A custom domain.** `.onrender.com` until there is a reason.
- **Rate limiting, CDN, staging environment.** Phase 5 already argued rate
  limiting is Supabase's; the other two are traffic this app does not have.
- **Self-hosting the exercise images.** `EXERCISE_IMAGE_BASE` makes it a config
  change whenever jsDelivr stops being acceptable. The privacy policy discloses
  it in the meantime.
