# Roadmap

Technical plan for taking Body Shop from a single-user local Flask app to a hosted,
multi-user product. Written as specs rather than tickets: each section states what
changes, what it depends on, and what it breaks.

Current state for reference: Flask + Jinja + vanilla ES modules, no build step, no JS
dependencies, one SQLite table, no auth, no migrations, 4 exercises, 7 muscle groups.
See [ARCHITECTURE.md](ARCHITECTURE.md).

---

## Three conflicts to resolve before anything else

These are the load-bearing decisions. Everything below depends on them.

### 1. Vercel cannot host the app as it exists today

Vercel serverless functions have an **ephemeral filesystem** — only `/tmp` is writable,
and it does not survive between invocations. `instance/bodyshop.sqlite3` would be
recreated empty on every cold start, silently losing every workout.

**SQLite must be replaced with a hosted database before the app goes on the internet.**
This is a hard blocker on goals 4, 5 and 6 simultaneously, and it is why Phase 0 below
exists. Postgres on Neon, Supabase, or Vercel Postgres are all standard pairings.

### 2. Tailwind reverses a deliberate architectural choice

`CLAUDE.md`, `CONTRIBUTING.md` and `ARCHITECTURE.md` all state the no-build-step, no-JS-
dependencies invariant as intentional. Tailwind requires a build step (`tailwindcss` CLI
watching templates, emitting a compiled stylesheet). That is a fine trade — it buys
DaisyUI and a design system — but it is a reversal, not an addition, and all three
documents need updating in the same change so the next session isn't working from a
stale invariant.

The good news: **DaisyUI is pure CSS.** Its components (`btn`, `card`, `modal`, `stat`,
`drawer`) are class names, not React components. It works directly in Jinja templates
with no JS framework. Goals 1 and 3 do **not** require a rewrite to React/Next.js.

### 3. Auth is impossible without migrations

`schema.sql` is applied once and `init-db` drops everything. That is survivable while the
database is one person's laptop; it is data loss the moment there are accounts. Alembic
(or equivalent) has to land before the `user` table does.

---

## Phase 0 — Foundations

Unblocks goals 4, 5 and 6. No user-visible change. Do this first.

| Task | Detail |
| --- | --- |
| Introduce migrations | Alembic. Baseline the current `workout_entry` schema as revision 1, then never edit `schema.sql` by hand again. Retire the `init-db` command or reduce it to a dev-only convenience. |
| Abstract the data layer | `app/models.py` is already the only place SQL lives, so this is contained — but it is raw `sqlite3` with `?` placeholders. Move to SQLAlchemy Core or swap to `psycopg` with `%s` placeholders. **This is the single reason the "SQL only in models.py" invariant was worth enforcing.** |
| Provision Postgres | Neon or Supabase (both have usable free tiers and serverless-friendly pooling). Keep SQLite working locally via a `DATABASE_URL` that both backends understand. |
| Connection pooling | Serverless + Postgres needs a pooler (PgBouncer, Neon's built-in, or Supabase's). Without it, concurrent lambdas exhaust connections. |
| Secret hygiene | `BODYSHOP_SECRET_KEY` currently defaults to `dev-secret-change-me`. Make `ProductionConfig` raise on startup if it is unset or still the default. |

**Test impact:** `tests/conftest.py` builds a fresh SQLite file per test in `tmp_path`.
Keep that — it is fast and the isolation is genuinely good. Add a separate CI job that
runs the suite against a real Postgres service container so dialect differences surface.
Note that the `entry_date BETWEEN` lexicographic-ordering trick relies on TEXT dates and
should be revisited against a real `DATE` column.

---

## Goal 1 — Derive all CSS from Tailwind

**Depends on:** nothing. Can run in parallel with Phase 0.

### Build setup

Tailwind CLI only — no bundler, no PostCSS pipeline, no npm runtime dependencies:

```
npm install -D tailwindcss daisyui
npx tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --watch
```

Content globs must cover `app/templates/**/*.html` **and** `app/static/js/**/*.js`,
because `summary.js` toggles classes at runtime. Any class name that only ever appears
in a JS string literal must be written out in full or safelisted — Tailwind's scanner
does not evaluate template literals, so `` `is-${state}` `` would be silently purged.

Commit the compiled `styles.css` (Vercel builds should not depend on npm at deploy time
in a Python project), and add `app/static/css/input.css` as the real source.

### Migration order

The existing stylesheet is already sectioned (`1) tokens 2) reset 3) layout 4) components
5) pages 6) media`), which makes this tractable:

1. **Tokens → `theme.extend`.** The `:root` custom properties become Tailwind theme
   values. The light-mode `@media (prefers-color-scheme: light)` block becomes a DaisyUI
   theme pair.
2. **Reset → Preflight.** Delete section 2 outright.
3. **Layout + components → utilities in templates.** Mechanical.
4. **Pages → mostly DaisyUI components.** See goal 3.

### What must not become Tailwind utilities

The volume-scale colour mixing is computed, not enumerable:

```css
fill: color-mix(in srgb, var(--train-dark) calc(var(--level) * 100%), var(--train-light));
```

`--level` is a continuous 0–1 value written by JS. Tailwind cannot express this as a
utility class, and quantising it into 10 fixed classes would visibly band the gradient.
**Keep the `.muscle` / `.muscle-row` colour rules as hand-written CSS** in a Tailwind
`@layer components` block. Same for the SVG body-map geometry. Everything else can go.

---

## Goal 2 — Exercise catalog with images

**Depends on:** nothing. **Highest product value of the six**, and independent of all
infrastructure work — this is the one to build while Phase 0 is in flight.

### The scaling problem

The provided list is **186 entries across 11 muscle groups**. The current design breaks
in three places at that size:

- `EXERCISES` is a hand-written dict — 186 rows of manual, error-prone data entry.
- `/log` renders every exercise as a radio button. 186 radio buttons is not a UI.
- `MUSCLE_GROUPS` has 7 entries; the list implies **12** (add shoulders, forearms, traps,
  glutes, calves).

### Facet decomposition

Every entry in the list is the same four things in different combinations. This is not
imposed structure — it is already latent in how the list is written:

| Facet | Values observed in the list |
| --- | --- |
| `pattern` | `bench_press`, `overhead_press`, `row`, `pulldown`, `pull_up`, `dip`, `push_up`, `fly`, `lateral_raise`, `front_raise`, `upright_row`, `shrug`, `curl`, `triceps_extension`, `pushdown`, `wrist_curl`, `squat`, `lunge`, `hinge`, `hip_thrust`, `leg_curl`, `leg_extension`, `calf_raise`, `crunch`, `leg_raise`, `twist`, `plank`, `rollout`, `carry` |
| `equipment` | `barbell`, `dumbbell`, `ez_bar`, `trap_bar`, `cable`, `machine`, `smith`, `bodyweight`, `plate`, `kettlebell`, `ab_wheel` |
| `modifiers` | angle (`flat`/`incline`/`decline`), grip (`wide`/`close`/`neutral`/`underhand`/`overhand`/`rope`/`v_bar`), stance (`standing`/`seated`/`lying`/`kneeling`/`bent_over`), `unilateral`, `deficit`, `elevated`, `weighted` |
| `muscles` | `primary` and `secondary`, replacing today's flat tuple |

The list itself proves why facets beat per-group lists: **upright row appears under both
Shoulders and Traps, farmer's walk under both Forearms and Traps, hammer curl under both
Biceps and Forearms.** Those are ~6 duplicate rows describing the same movement. With
`primary`/`secondary` muscles each movement is defined once and appears wherever it
belongs — 186 listed rows collapse to roughly 180 unique exercises.

### Proposed model

```python
@dataclass(frozen=True)
class Exercise:
    id: str                          # "barbell_incline_bench_press"
    name: str                        # "Barbell incline bench press"
    pattern: str                     # "bench_press"
    equipment: str                   # "barbell"
    modifiers: tuple[str, ...]       # ("incline",)
    primary: tuple[str, ...]         # ("chest",)
    secondary: tuple[str, ...]       # ("triceps", "shoulders")
    image: str | None = None         # "barbell_incline_bench_press.webp"
```

Keep `app/exercises.py` as the single source of truth, but move the 180 rows into a data
file (`app/data/exercises.yaml` or `.json`) that the module loads and validates at import.
Hand-editing 180 Python dataclass constructors is worse than editing structured data, and
a load-time validator can assert every `primary`/`secondary` slug exists in
`MUSCLE_GROUPS` and every `id` is unique — errors the current design can only catch by
eye.

### Grading change: primary vs secondary

Secondary muscles genuinely receive less stimulus, and counting them at full weight would
inflate every accessory group. Proposal:

```python
PRIMARY_WEIGHT = 1.0
SECONDARY_WEIGHT = 0.5
```

This changes `summarise_entries` — `sets` becomes a float, and the display needs rounding
(`12.5 / 20`). It also changes the meaning of the existing "a set counts once per muscle
group it targets" invariant in CLAUDE.md, and every test in `tests/test_summary.py` that
asserts integer set counts. **Worth doing, but it is a behavioural change with real test
churn — not a drop-in.**

### Selection UI

Three access paths, because they serve different moments:

1. **Recent / frequent** — default view. Most people cycle through 10–20 movements; this
   is the 90% path and the single biggest efficiency win. Needs a query on the user's
   own entry history, so it lands properly after auth.
2. **Search** — fuzzy match over name + pattern + equipment. Typing "incl db" should find
   "Dumbbell incline bench press". Client-side filtering over a ~180-entry JSON payload is
   entirely sufficient; no search backend needed.
3. **Browse** — muscle group → pattern → equipment drill-down for discovery.

The existing `/api/exercises` endpoint already returns the whole catalog, so the front end
can filter locally with no new endpoints.

### Images

- **Format/naming:** `{exercise_id}.webp`, one convention, lazy-loaded, with a placeholder
  fallback so a missing image never breaks the grid.
- **Storage:** ~180 images is too much for the git repo. Vercel Blob or any object store,
  referenced by URL.
- **Licensing is an unresolved blocker.** Nearly all exercise photography and illustration
  is copyrighted. Realistic options: license a set (e.g. from an exercise-database vendor),
  commission/generate them, or use an openly-licensed source such as the
  [free-exercise-db](https://github.com/yuhonas/free-exercise-db) dataset (public domain,
  ~800 exercises with images) — which could also seed the catalog itself and eliminate
  most of the data-entry work. **This needs a decision before any image work starts.**

### Muscle map expansion

7 → 12 groups means new SVG regions in `_body_figure.html` and new `MUSCLE_TARGETS`
entries. Suggested front/back split preserving the existing disjoint-views rule:

- **Front:** chest, abs, biceps, forearms, quads, shoulders (front delts)
- **Back:** back, traps, triceps, glutes, hamstrings, calves

Recommend keeping `shoulders` as **one** group initially even though the list distinguishes
front/side/rear raises. The facet data preserves the distinction, so splitting into three
delt regions later is a data change plus SVG paths — not a re-model.

---

## Goal 3 — Homepage and UI with DaisyUI

**Depends on:** goal 1 (DaisyUI is a Tailwind plugin).

DaisyUI is CSS-only, so this is a template-level change with no JS framework. Direct
component mappings for what already exists:

| Current | DaisyUI |
| --- | --- |
| `.card` | `card` / `card-body` |
| `.icon-btn`, form buttons | `btn`, `btn-circle`, `btn-primary` |
| `.toast` | `toast` + `alert` |
| `.muscle-bar` | `progress` (custom colour still needed for the volume ramp) |
| Week switcher | `join` + `btn` |
| `.tag` | `badge` |
| Nav | `navbar` |
| Week totals | `stats` / `stat` |

### Theming

DaisyUI themes are the natural home for the existing light/dark token pair. Define a
custom theme rather than using a stock one, so `--train-light`/`--train-dark`/`--over-*`
stay first-class design tokens rather than one-off hex values.

### Homepage

There is currently no marketing/landing surface — `/` is the calendar. A signed-out
homepage becomes necessary once auth exists (goal 4), so these two should be designed
together: signed-out `/` = landing page, signed-in `/` = calendar.

---

## Goal 4 — Secure user login

**Depends on:** Phase 0 (migrations + Postgres).

### Schema

```sql
CREATE TABLE "user" (
    id            INTEGER PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    verified_at   TEXT
);
ALTER TABLE workout_entry ADD COLUMN user_id INTEGER NOT NULL REFERENCES "user"(id);
CREATE INDEX workout_entry_user_date ON workout_entry (user_id, entry_date);
```

### Blast radius

**Every function in `app/models.py` needs a `user_id` parameter and every query a
`WHERE user_id = ?` clause.** `list_entries`, `sets_by_date`, `get_entry` and
`delete_entry` are all currently global. `delete_entry` is the dangerous one — without
ownership checks it becomes an IDOR letting any user delete any row by guessing an id.
This is mechanical but must be exhaustive; a single missed clause is a data leak.

### Requirements

| Area | Decision |
| --- | --- |
| Don't roll your own | Flask-Login for sessions; or delegate entirely to Clerk / Auth0 / Supabase Auth. Recommended if the goal is "secure" rather than "educational". |
| Password hashing | Argon2id (`argon2-cffi`) or bcrypt. Never SHA/MD5, never unsalted. |
| Session cookies | `HttpOnly`, `Secure`, `SameSite=Lax`, signed with a real `SECRET_KEY`. |
| CSRF | **Currently absent.** `POST`/`DELETE /api/entries` accept form encoding with no token — harmless single-user and local, exploitable the moment there are cookie-authenticated sessions on the internet. Flask-WTF `CSRFProtect`, or move the API to bearer tokens. |
| Rate limiting | Login and password-reset endpoints. Flask-Limiter, backed by Redis (Upstash on Vercel). |
| Email flows | Verification + password reset need a transactional sender (Resend, Postmark, SES). |
| Enumeration | Login and reset must return identical responses for unknown vs known emails. |
| Transport | HTTPS only, HSTS. Free with Vercel. |

### Data migration

Existing rows have no owner. Either wipe (acceptable pre-launch — it is your own data) or
backfill to a single seed account. Decide before writing the migration, since
`NOT NULL` without a default fails on a non-empty table.

---

## Goals 5 & 6 — Stack and Vercel deployment

**Depends on:** Phase 0, goal 4.

### Recommendation: keep Flask, deploy as Vercel Python functions

| | Option A — Flask on Vercel | Option B — rewrite to Next.js |
| --- | --- | --- |
| Rewrite cost | Low: `api/index.py` entrypoint, existing blueprints intact | High: whole app |
| Tailwind + DaisyUI | ✅ works in Jinja, CSS-only | ✅ native |
| Auth | Flask-Login or a provider | Auth.js, very polished |
| Vercel fit | Good (Python runtime is supported, not first-class) | Ideal |
| Cold starts | Noticeable on Python | Lower |

**Take Option A.** The reason is sequencing, not preference: goal 2 — the exercise
taxonomy — is the highest-value work and is pure backend/data. Rewriting the frontend
before the data model settles means building the exercise-picker UI twice. Option A gets
you deployed, authenticated and persistent with the app you already have; revisit
Option B only if Python cold starts turn out to hurt in practice.

### Deployment shape

```
vercel.json          → route all traffic to api/index.py
api/index.py         → from app import create_app; app = create_app("production")
requirements.txt     → runtime deps (Vercel installs automatically)
```

Static assets under `app/static/` should be served by Vercel's CDN rather than Flask.

### Environment

Everything is already env-driven (`BODYSHOP_*` in `config.py`), which makes this
straightforward. Add `DATABASE_URL`, set `BODYSHOP_CONFIG=production`, and set a real
`BODYSHOP_SECRET_KEY` in Vercel's dashboard — never in the repo.

### CI

Extend `.github/workflows/ci.yml`: run the suite against Postgres as well as SQLite, and
gate Vercel production deploys on it passing.

---

## Suggested sequencing

| Phase | Work | Blocked by | Why here |
| --- | --- | --- | --- |
| 0 | Migrations, Postgres, secrets | — | Blocks 4, 5, 6. Nothing ships without it. |
| 1 | Exercise taxonomy, 12 muscle groups, picker UI | — | Highest product value; runs parallel to 0. |
| 2 | Tailwind + DaisyUI + homepage | — | Independent; do it before the picker UI is styled twice. |
| 3 | Auth, `user_id`, CSRF, rate limiting | 0 | Needs migrations and a real database. |
| 4 | Vercel deploy, CI gates | 0, 3 | Don't expose an unauthenticated app. |
| 5 | Exercise images | 1, licensing decision | Largest asset/legal effort, least structural risk. |

Phases 0, 1 and 2 are genuinely parallel. The critical path to being on the internet is
**0 → 3 → 4**.

---

## Open decisions

These need answers before the phases they gate can start:

1. **Image licensing** — license, commission, or adopt an open dataset such as
   free-exercise-db? Gates all image work, and may also solve catalog data entry.
2. **Auth: self-hosted or provider?** Flask-Login is more code and more responsibility;
   Clerk/Supabase is faster and safer but adds a vendor.
3. **Secondary-muscle weighting** — is 0.5 right, and is fractional set counting
   acceptable in the UI (`12.5 / 20`)?
4. **Existing data on migration** — wipe, or backfill to a seed account?
5. **Delt granularity** — one `shoulders` group, or split front/side/rear?
