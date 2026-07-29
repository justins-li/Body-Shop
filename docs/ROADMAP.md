# Roadmap

Technical plan for taking Body Shop from a single-user local Flask app to a hosted,
multi-user product. Written as specs rather than tickets: each phase states what
changes, what it depends on, and what it breaks.

**Phases are in execution order.** The ordering is dependency-driven, with one rule
doing most of the work: *anything that will be re-done later should be built later.*
Tailwind is first because every remaining phase adds UI, and UI built before the
migration gets styled twice.

Current state: Flask + Jinja + vanilla ES modules, no build step, no JS dependencies,
one SQLite table, no auth, no migrations, 4 exercises, 7 muscle groups. See
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Three conflicts that shape the ordering

### 1. Vercel cannot host the app as it exists today

Vercel serverless functions have an **ephemeral filesystem** — only `/tmp` is writable,
and it does not survive between invocations. `instance/bodyshop.sqlite3` would be
recreated empty on every cold start, silently losing every workout.

**SQLite must become hosted Postgres before the app goes on the internet.** This is a
hard blocker on auth, the stack decision, and deployment simultaneously, which is why
Phase 3 exists and why Phases 4–5 sit behind it.

### 2. Tailwind reverses a deliberate architectural choice

`CLAUDE.md`, `CONTRIBUTING.md` and `ARCHITECTURE.md` all state the no-build-step,
no-JS-dependencies invariant as intentional. Tailwind requires a build step. That is a
fine trade — it buys DaisyUI and a design system — but it is a reversal, not an
addition, and all three documents need updating in the same change so the next session
isn't working from a stale invariant.

The good news: **DaisyUI is pure CSS.** Its components (`btn`, `card`, `modal`, `stat`,
`drawer`) are class names, not React components. They work directly in Jinja templates
with no JS framework, which is what makes Phase 1 cheap and what keeps Flask viable
through Phase 5.

### 3. Auth is impossible without migrations

`schema.sql` is applied once and `init-db` drops everything. Survivable while the
database is one laptop; data loss the moment there are accounts. Alembic has to land
before the `user` table does.

---

## Dependency graph

```
Phase 1  Tailwind + DaisyUI ──┬──▶ Phase 2  Exercise taxonomy ──┬──▶ Phase 6  AI custom exercises
                              │                                 ├──▶ Phase 7  Images (+ licensing)
                              └──▶ (all later UI)               └──▶ Phase 8  Mobile + app stores

Phase 3  Migrations + Postgres ──▶ Phase 4  Auth ──┬──▶ Phase 5  Vercel deploy ──▶ Phase 8
                                                   └──▶ Phase 6  AI custom exercises

   Phase 8 reaches backwards: it requires token auth (not cookie sessions) and an
   in-app account-deletion endpoint, both of which must be decided in Phase 4.
```

Phases 1–2 and Phase 3 are independent and can run in parallel. The critical path to
being on the internet is **3 → 4 → 5**.

---

## Phase 1 — Tailwind + DaisyUI

**Depends on:** nothing. **First because it is a soft dependency of everything else** —
Phases 2, 4 and 6 each add UI surfaces (exercise picker, login/signup, AI verification
modal), and every one of them would need re-styling if Tailwind landed later. The app is
three pages today; this is the cheapest it will ever be.

### Build setup

Tailwind CLI only — no bundler, no PostCSS pipeline, no npm runtime dependencies:

```
npm install -D tailwindcss daisyui
npx tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --watch
```

Content globs must cover `app/templates/**/*.html` **and** `app/static/js/**/*.js`,
because `summary.js` toggles classes at runtime. Any class that only appears in a JS
string must be written out in full or safelisted — Tailwind's scanner does not evaluate
template literals, so `` `is-${state}` `` would be silently purged.

Commit the compiled `styles.css` (a Python deployment should not depend on npm at build
time) and add `app/static/css/input.css` as the real source.

### Migration order

The existing stylesheet is already sectioned (`1) tokens 2) reset 3) layout
4) components 5) pages 6) media`), which makes this tractable:

1. **Tokens → `theme.extend`.** The `:root` custom properties become theme values; the
   `prefers-color-scheme: light` block becomes a DaisyUI theme pair.
2. **Reset → Preflight.** Delete section 2 outright.
3. **Layout + components → utilities in templates.** Mechanical.
4. **Pages → DaisyUI components.** Mapping below.

### DaisyUI component mapping

| Current | DaisyUI |
| --- | --- |
| `.card` | `card` / `card-body` |
| `.icon-btn`, form buttons | `btn`, `btn-circle`, `btn-primary` |
| `.toast` | `toast` + `alert` |
| `.muscle-bar` | `progress` (custom fill colour still needed) |
| Week switcher | `join` + `btn` |
| `.tag` | `badge` |
| Nav | `navbar` |
| Week totals | `stats` / `stat` |

Define a **custom DaisyUI theme** rather than using a stock one, so
`--train-light`/`--train-dark`/`--over-*` stay first-class design tokens.

### What must not become Tailwind utilities

The volume-scale colour mixing is computed, not enumerable:

```css
fill: color-mix(in srgb, var(--train-dark) calc(var(--level) * 100%), var(--train-light));
```

`--level` is a continuous 0–1 value written by JS. Tailwind cannot express this as a
utility, and quantising it into 10 fixed classes would visibly band the gradient. **Keep
the `.muscle` / `.muscle-row` colour rules as hand-written CSS** in a `@layer components`
block, along with the SVG body-map geometry. Everything else can go.

### Homepage

There is no signed-out surface today — `/` is the calendar. Build the visual redesign of
the three existing pages here; the **landing page lands in Phase 4**, when auth creates
the signed-out/signed-in split that gives it a purpose.

---

## Phase 2 — Exercise catalog and muscle map

**Depends on:** Phase 1 (so the picker is styled once). **Highest product value of the
seven**, independent of all infrastructure work, and it defines the vocabulary the AI
feature in Phase 6 must emit into — which is why it precedes it.

### The scaling problem

The target list is **186 entries across 11 muscle groups**. The current design breaks in
three places at that size:

- `EXERCISES` is a hand-written dict — 186 rows of manual, error-prone data entry.
- `/log` renders every exercise as a radio button. 186 radio buttons is not a UI.
- `MUSCLE_GROUPS` has 7 entries; the list implies **12**.

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
Biceps and Forearms.** Those are duplicate rows describing one movement. With
`primary`/`secondary` muscles each movement is defined once and surfaces wherever it
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

Keep `app/exercises.py` as the single source of truth, but move the ~180 rows into a
data file (`app/data/exercises.yaml`) that the module loads and validates at import.
Hand-editing 180 dataclass constructors is worse than editing structured data, and a
load-time validator can assert every muscle slug exists in `MUSCLE_GROUPS` and every
`id` is unique — errors the current design can only catch by eye.

### Grading change: primary vs secondary

Secondary muscles receive less stimulus; counting them at full weight would inflate every
accessory group:

```python
PRIMARY_WEIGHT = 1.0
SECONDARY_WEIGHT = 0.5
```

This makes `sets` a float, needs display rounding (`12.5 / 20`), changes the "a set counts
once per muscle group it targets" invariant in CLAUDE.md, and churns every integer
assertion in `tests/test_summary.py`. Worth doing, but not a drop-in.

### Muscle map expansion

7 → 12 groups means new SVG regions in `_body_figure.html` and new `MUSCLE_TARGETS`
entries. Suggested split, preserving the disjoint-views rule:

- **Front:** chest, abs, biceps, forearms, quads, shoulders
- **Back:** back, traps, triceps, glutes, hamstrings, calves

Keep `shoulders` as **one** group initially even though the list distinguishes front/side/
rear raises. The facet data preserves the distinction, so splitting into three delt
regions later is a data change plus SVG paths — not a re-model.

### Selection UI

Three access paths, serving different moments:

1. **Recent / frequent** — the default view and **the single biggest efficiency win**.
   Most people cycle through 10–20 movements; this is the 90% path. Works off entry
   history, so it improves again once Phase 4 makes history per-user.
2. **Search** — fuzzy match over name + pattern + equipment. Typing "incl db" should find
   "Dumbbell incline bench press". Client-side filtering over a ~180-entry JSON payload is
   sufficient; no search backend.
3. **Browse** — muscle group → pattern → equipment drill-down for discovery.

`/api/exercises` already returns the whole catalog, so the front end filters locally with
no new endpoints.

---

## Phase 3 — Foundations: migrations and Postgres

**Depends on:** nothing — runs in parallel with Phases 1–2. Placed here because it blocks
Phases 4 and 5 and nothing else. No user-visible change.

| Task | Detail |
| --- | --- |
| Introduce migrations | Alembic. Baseline the current `workout_entry` schema as revision 1, then never hand-edit `schema.sql` again. Reduce `init-db` to a dev-only convenience. |
| Abstract the data layer | `app/models.py` is already the only place SQL lives, so this is contained — but it is raw `sqlite3` with `?` placeholders. Move to SQLAlchemy Core, or `psycopg` with `%s`. **This is the payoff for enforcing the SQL-only-in-models.py invariant.** |
| Provision Postgres | Neon or Supabase (both have usable free tiers and serverless-friendly pooling). Keep SQLite working locally via a `DATABASE_URL` both backends understand. |
| Connection pooling | Serverless + Postgres needs a pooler (PgBouncer, Neon's built-in, Supabase's). Without it, concurrent lambdas exhaust connections. |
| Secret hygiene | `BODYSHOP_SECRET_KEY` defaults to `dev-secret-change-me`. Make `ProductionConfig` raise at startup if it is unset or still the default. |

**Test impact:** keep the per-test SQLite file in `tmp_path` — it is fast and the
isolation is genuinely good. Add a CI job running the suite against a Postgres service
container so dialect differences surface. The `entry_date BETWEEN` lexicographic trick
relies on TEXT dates and should be revisited against a real `DATE` column.

**Data migration note:** if Phase 2 has already renamed exercise ids (`squat` →
`barbell_back_squat_high_bar`), existing rows point at ids that no longer exist. Either
wipe (fine pre-launch — it is your own data) or write the id remap as revision 2.

---

## Phase 4 — Secure user login

**Depends on:** Phase 3 (migrations + Postgres), Phase 1 (login/signup pages styled once).

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
`delete_entry` are all currently global. `delete_entry` is the dangerous one — without an
ownership check it is an IDOR letting any user delete any row by guessing an id. This is
mechanical but must be exhaustive; one missed clause is a data leak.

### Requirements

| Area | Decision |
| --- | --- |
| Don't roll your own | Flask-Login for sessions, or delegate entirely to Clerk / Auth0 / Supabase Auth. Recommended if the goal is "secure" rather than "educational". |
| Password hashing | Argon2id (`argon2-cffi`) or bcrypt. Never SHA/MD5, never unsalted. |
| Session cookies | `HttpOnly`, `Secure`, `SameSite=Lax`, signed with a real `SECRET_KEY`. |
| CSRF | **Currently absent.** `POST`/`DELETE /api/entries` accept form encoding with no token — harmless locally, exploitable the moment there are cookie-authenticated sessions on the internet. Flask-WTF `CSRFProtect`, or move the API to bearer tokens. |
| Rate limiting | Login and password-reset endpoints. Flask-Limiter backed by Redis (Upstash on Vercel). |
| Email flows | Verification + password reset need a transactional sender (Resend, Postmark, SES). |
| Enumeration | Login and reset must return identical responses for unknown vs known emails. |
| Transport | HTTPS only, HSTS. Free with Vercel. |

Existing rows have no owner: either wipe or backfill to a seed account. Decide before
writing the migration — `NOT NULL` without a default fails on a non-empty table.

The **signed-out homepage** lands here, since auth is what creates the split: signed-out
`/` = landing page, signed-in `/` = calendar.

---

## Phase 5 — Stack decision and Vercel deployment

**Depends on:** Phases 3 and 4. Placed before the AI feature deliberately: deployment is
the critical path to your stated goal, and features are cheaper to add to a deployed app
than deployment is to add to a feature-rich app.

### Recommendation: keep Flask, deploy as Vercel Python functions

| | Option A — Flask on Vercel | Option B — rewrite to Next.js |
| --- | --- | --- |
| Rewrite cost | Low: `api/index.py` entrypoint, blueprints intact | High: whole app |
| Tailwind + DaisyUI | ✅ works in Jinja, CSS-only | ✅ native |
| Auth | Flask-Login or a provider | Auth.js, very polished |
| Vercel fit | Good (Python runtime supported, not first-class) | Ideal |
| Cold starts | Noticeable on Python | Lower |

**Take Option A.** The reason is sequencing, not preference: Phase 2 is the highest-value
work and is pure backend/data. Rewriting the frontend before the data model settles means
building the exercise picker twice. Option A gets you deployed, authenticated and
persistent with the app you already have. Revisit Option B only if Python cold starts hurt
in practice.

### Deployment shape

```
vercel.json          → route all traffic to api/index.py
api/index.py         → from app import create_app; app = create_app("production")
requirements.txt     → runtime deps (Vercel installs automatically)
```

Serve `app/static/` from Vercel's CDN, not Flask. Everything is already env-driven
(`BODYSHOP_*` in `config.py`) — add `DATABASE_URL`, set `BODYSHOP_CONFIG=production`, and
set a real `BODYSHOP_SECRET_KEY` in Vercel's dashboard, never in the repo.

Extend `.github/workflows/ci.yml` to run the suite against Postgres as well as SQLite, and
gate production deploys on it passing.

---

## Phase 6 — AI-assisted custom exercises

**Depends on:** Phase 2 (the vocabulary the model classifies *into*), Phase 4 (custom
exercises are per-user by definition), Phase 5 (API key management is deployment config).

Placed last among functional phases for a product reason as well as a technical one: **the
value of this feature is a function of how often the ~180-exercise catalog falls short.**
Ship the catalog, measure the miss rate, then build this. If the catalog covers 99% of
what people log, a search box that says "not found — request it" may be enough.

### Flow

1. User can't find their movement → **Add custom exercise**
2. User types a name (*"Jefferson curl"*, *"Zercher squat"*, *"Copenhagen plank"*)
3. App calls Claude with the app's muscle + facet vocabulary and the user's text
4. Model returns structured JSON: primary/secondary muscles, pattern, equipment, confidence
5. **User verifies and edits a pre-filled form** — never auto-accept
6. Saved as a user-owned exercise, usable exactly like a catalog exercise

Step 5 is the design constraint, not a nicety: the model is a *drafting* aid. A wrong
classification silently corrupts every future weekly summary, and the user is the only one
who can catch it.

### Implementation

Single API call — classification, the simplest tier. No agent loop, no tools.

```python
from typing import Literal
from pydantic import BaseModel, Field
import anthropic

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

MuscleGroup = Literal[
    "chest", "abs", "back", "shoulders", "biceps", "triceps",
    "forearms", "traps", "quads", "hamstrings", "glutes", "calves",
]

class ExerciseSuggestion(BaseModel):
    recognized: bool = Field(description="False if the input is not a real exercise.")
    canonical_name: str
    pattern: str
    equipment: str
    primary: list[MuscleGroup]
    secondary: list[MuscleGroup]
    confidence: float = Field(ge=0.0, le=1.0)
    note: str = Field(description="One sentence on the movement, shown to the user.")

response = client.messages.parse(
    model="claude-opus-5",
    max_tokens=1024,
    output_config={"effort": "low"},          # bounded classification, not deep reasoning
    system=[{
        "type": "text",
        "text": CLASSIFIER_PROMPT,             # vocabulary + ~8 examples from the catalog
        "cache_control": {"type": "ephemeral"},
    }],
    messages=[{"role": "user", "content": user_input}],
    output_format=ExerciseSuggestion,
)
suggestion = response.parsed_output
```

Notes on the shape above, each load-bearing:

- **`Literal` muscle enum.** Structured outputs constrain the response to the schema, so
  the model *cannot* invent `"rotator_cuff"` if it is not a tracked group. This is the
  main reason to use `messages.parse()` rather than parsing prose.
- **Cached system prompt.** The vocabulary and few-shot examples are a stable prefix;
  `cache_control` makes repeat calls cheap (cache reads are ~0.1× input price). Minimum
  cacheable prefix on Opus 5 is 512 tokens — the catalog vocabulary clears that easily.
  Keep the prompt byte-stable: no timestamps, no user ids, deterministic ordering.
- **`effort: "low"`.** The task is a bounded lookup, not multi-step reasoning. Effort is
  the right cost lever here; if accuracy on obscure movements is short, raise it before
  changing anything else.
- **`recognized` flag.** Gives the model an explicit way to reject junk input instead of
  hallucinating a classification for `"asdf"`.

### Server-side validation is not optional

**Re-validate the model's output against `MUSCLE_GROUPS` server-side before persisting.**
The schema constrains the response, but the boundary rule still holds: never write
model-derived values into the database without checking them. Reject empty `primary`,
unknown slugs, and `recognized: false`.

Handle `stop_reason == "refusal"` before reading content — Opus 5 runs safety classifiers,
and while a fitness classifier is unlikely to trip them, code that indexes into `content`
unconditionally breaks if one does. Opting into the server-side `fallbacks` parameter
(beta `server-side-fallback-2026-07-01`, `fallbacks: "default"`) makes that self-healing.

### Data model

```sql
CREATE TABLE custom_exercise (
    id             INTEGER PRIMARY KEY,
    user_id        INTEGER NOT NULL REFERENCES "user"(id),
    name           TEXT NOT NULL,
    pattern        TEXT,
    equipment      TEXT,
    primary_muscles   TEXT NOT NULL,   -- JSON array of slugs
    secondary_muscles TEXT NOT NULL,
    ai_confidence  REAL,
    source         TEXT NOT NULL,      -- 'ai_verified' | 'ai_edited' | 'manual'
    created_at     TEXT NOT NULL
);
```

`workout_entry.exercise_id` stays a single TEXT column; custom exercises get a
`custom:{id}` prefix. `get_exercise()` resolves the catalog first, then the user's custom
table. One column, no schema churn, no id collisions.

**Log the suggestion alongside the user's correction** (`source` distinguishes them). That
is a free labelled dataset: it tells you which movements the catalog is missing, lets you
tune the prompt against real misses, and identifies popular custom exercises worth
promoting into the main catalog.

### Abuse and cost controls

- Rate-limit per user (reuse the Phase 4 Flask-Limiter setup).
- Cap custom exercises per account.
- Treat the input as untrusted text — it reaches a model, so prompt injection is in scope.
  The `Literal` enum plus server-side validation contains the blast radius: the worst case
  is a wrong-but-valid muscle group, not arbitrary data.
- Log token usage per call. At Opus 5 pricing ($5/$25 per MTok) with a cached prompt, a
  classification is fractions of a cent — but it is a per-user-action cost, unlike the rest
  of the app.

---

## Phase 7 — Exercise images

**Depends on:** Phase 2, and an unresolved licensing decision.

Last because it is the largest asset effort, the least structural risk, and blocked
externally rather than technically. **It can start the moment licensing resolves** — it is
purely additive and parallelises with anything.

- **Format/naming:** `{exercise_id}.webp`, one convention, lazy-loaded, with a placeholder
  fallback so a missing image never breaks the grid.
- **Storage:** ~180 images is too much for the git repo. Vercel Blob or any object store,
  referenced by URL.
- **Licensing is the blocker.** Nearly all exercise photography and illustration is
  copyrighted. Options: license a set from an exercise-database vendor, commission or
  generate them, or adopt an openly-licensed source such as
  [free-exercise-db](https://github.com/yuhonas/free-exercise-db) (public domain, ~800
  exercises with images).

> **This decision can move Phase 7 to Phase 2.** If you adopt free-exercise-db, the images
> and the catalog data arrive together — which would eliminate most of Phase 2's data-entry
> work *and* collapse this phase into it. Resolve licensing early even though the phase is
> last; it is the one open question that can change the plan's shape.

---

## Phase 8 — Mobile apps and store distribution

**Depends on:** Phases 2, 4 and 5. Last because it consumes all of them — the catalog is
what makes a mobile logger worth opening, auth is what makes it multi-device, and the
deployed API is what it talks to.

**But two of its constraints have to be honoured in Phase 4, not here.** See *Decisions
this forces earlier* below; retrofitting either is expensive.

### The asset you already have

Pages are server-rendered shells and every dynamic byte comes from `/api` — the same API
the tests exercise. A mobile client is just another consumer of it; no new backend surface
is required. That is the payoff for the shell + fetch design in [ARCHITECTURE.md](ARCHITECTURE.md).

The ISO-local-date rule holds up too: a workout logged at 7am in Tokyo is that day's
workout, not a UTC instant. Keep the backend free of time-zone conversion.

### A wrapped website gets rejected

Apple's **Guideline 4.2 (Minimum Functionality)** rejects apps that are repackaged
websites. That rules out the cheapest version of this phase.

| Option | Both stores? | Cost | Notes |
| --- | --- | --- | --- |
| **A** — PWA + Trusted Web Activity | Play only | Lowest | Apple does not accept PWAs in the App Store. Installable from Safari, but no listing. |
| **B** — Capacitor shell around the web UI | Yes | Low–medium | **Rejection risk under 4.2** unless it does genuinely native things. |
| **C** — React Native / Expo client on `/api` | Yes | High | A real native client; Flask stays the API. |
| **D** — Native Swift + Kotlin | Yes | Highest | Two codebases. |

**Recommendation: B, but only paired with real native capability** — otherwise it is the
textbook 4.2 rejection. The capabilities that both clear the bar and genuinely help a gym
app are the same list:

- Offline logging (below) — the gym-basement problem
- Apple Health / Health Connect write-back
- Local rest-timer notifications
- A home-screen widget showing weekly muscle coverage

If mobile is a first-class surface rather than a checkbox, **C is the honest answer**, and
it moots the Next.js question from Phase 5 — React Native becomes the client and Flask
stays the API it already is.

### Offline-first is the real cost

The gym is where this app gets used and where reception dies. The current design fetches
everything from `/api` on load, which is a blank screen in a basement.

**The append-only single-table model is unusually well suited to sync**: entries are
immutable rows, so a client can queue inserts locally and replay them with no conflict
resolution. Two changes make it work, both Alembic revisions rather than rewrites:

- **Client-generated ids** (UUID instead of autoincrement) so a queued entry has an
  identity before it ever reaches the server.
- **Soft delete / tombstones** — `delete_entry` hard-deletes today, which cannot be
  replayed or ordered against a concurrent insert from another device.

### Decisions this forces earlier

| Decision | Phase | Why mobile changes it |
| --- | --- | --- |
| **Token auth, not cookie sessions** | 4 | Flask-Login cookie sessions are awkward from a native client. Choose bearer tokens (JWT + refresh) or a provider with mobile SDKs (Clerk, Supabase). Converting an API from cookies to tokens later touches every endpoint and the whole CSRF design. |
| **In-app account deletion** | 4 | **Apple Guideline 5.1.1(v) requires** any app offering account creation to offer account deletion *inside the app* — a support email does not satisfy it. Needs `DELETE /api/account` and a cascade to `workout_entry` and `custom_exercise`. |

One more, worth knowing before Phase 1: if you end up on route C, Tailwind/DaisyUI does
not transfer (NativeWind ports Tailwind to React Native; DaisyUI has no RN equivalent).
That is not a reason to change Phase 1 — the web app needs styling either way — but budget
the UI twice if C is the destination.

### Store logistics

- Apple Developer Program $99/yr; Google Play $25 one-time.
- **Privacy labels** (App Store) and **Data Safety** (Play) both require declaring what you
  collect — email and workout data here. Fill them from the actual schema.
- Both stores require a public **privacy policy URL**. There is no privacy policy in the
  repo today; it needs writing before submission.
- Budget for at least one rejection round on 4.2.

---

## Summary

| # | Phase | Blocked by | Why here |
| --- | --- | --- | --- |
| 1 | Tailwind + DaisyUI | — | Soft dependency of every later UI surface; cheapest at three pages |
| 2 | Exercise taxonomy, 12 muscle groups, picker | 1 | Highest product value; defines the vocabulary Phase 6 emits into |
| 3 | Migrations + Postgres | — | Blocks 4 and 5; runs parallel to 1–2 |
| 4 | Auth, `user_id`, CSRF, rate limiting | 3 | Needs migrations and a real database |
| 5 | Vercel deploy, CI gates | 3, 4 | Critical path to being online; don't expose an unauthenticated app |
| 6 | AI custom exercises | 2, 4, 5 | Needs the vocabulary, per-user ownership, and key management — and its value depends on the catalog's measured miss rate |
| 7 | Exercise images | 2 + licensing | Largest asset effort, least structural risk; can start early if licensing resolves |
| 8 | Mobile apps + store distribution | 2, 4, 5 | Consumes everything before it — but dictates Phase 4's auth design, so pick an approach early even though you build it last |

---

## Open decisions

1. **Image licensing** — license, commission, or adopt free-exercise-db? Gates Phase 7 and
   may collapse it into Phase 2. **Answer this first** despite being last in the order.
2. **Mobile approach — PWA, Capacitor shell, or React Native?** Last to build, but
   **answer it before Phase 4**: it decides token auth vs cookie sessions and whether an
   in-app account-deletion endpoint is required. Route C would also make the Phase 5
   Next.js question moot.
3. **Auth: self-hosted or provider?** Flask-Login is more code and more responsibility;
   Clerk/Supabase is faster and safer, adds a vendor, and ships mobile SDKs — which
   matters more once decision 2 is settled.
4. **Secondary-muscle weighting** — is 0.5 right, and is fractional set counting acceptable
   in the UI (`12.5 / 20`)?
5. **Existing data on migration** — wipe, or backfill to a seed account?
6. **Delt granularity** — one `shoulders` group, or split front/side/rear?
7. **AI feature scope** — per-user custom exercises only, or a review queue that promotes
   popular ones into the shared catalog?

Decisions 1 and 2 are the two that can change the plan's *shape* rather than its detail —
worth resolving early even though both belong to late phases.
