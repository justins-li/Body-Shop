# Roadmap

Technical plan for taking Body Shop from a single-user local Flask app to a hosted,
multi-user product. Written as specs rather than tickets: each phase states what
changes, what it depends on, and what it breaks.

**Phases are in execution order.** The ordering is dependency-driven, with one rule
doing most of the work: *anything that will be re-done later should be built later.*
Tailwind is first because every remaining phase adds UI, and UI built before the
migration gets styled twice.

Current state: **Phases 1, 2 and 3 are done, and Phase 9 landed with Phase 2.** Flask
+ Jinja + vanilla ES modules, styled with Tailwind v4 + daisyUI (CSS build step, still
no JS dependencies), one append-only table on **SQLite or Postgres with Alembic
migrations**, no auth, **873 exercises with images across 12 muscle groups**. See
[ARCHITECTURE.md](ARCHITECTURE.md).

---

## Four conflicts that shape the ordering

### 1. The data model cannot express a set

`workout_entry` stores `(entry_date, exercise_id, sets)`. There is **no weight, no reps,
no per-set row** — "3 sets of bench press" is the entire record, and 3 sets at 60kg is
indistinguishable from 3 sets at 140kg.

This is the single largest gap against every competitor in the category, and it is
load-bearing for most of the table-stakes feature set: previous-values-inline, 1RM
estimates, PR detection, per-exercise progress graphs, plate calculators, volume-load
charts, warm-up calculators and RPE all read weight and reps per set. None of them can be
prototyped against the current schema.

It was filed as a README to-do ("Per-set weight and reps") alongside genuinely small items
like CSV export. It is not a small item — it is a foundation, and **Phase 4 exists to fix
this before anything is built on top of the flat count.** The weekly muscle-coverage map
this app is built around keeps working unchanged; sets-per-muscle is derived from the
child rows instead of a column.

### 2. Vercel could not host the app as it existed — *resolved in Phase 3*

Vercel serverless functions have an **ephemeral filesystem** — only `/tmp` is writable,
and it does not survive between invocations. `instance/bodyshop.sqlite3` would be
recreated empty on every cold start, silently losing every workout.

It was worse than silent data loss: `create_app` would **crash on import**. Two lines in
[`app/__init__.py`](../app/__init__.py) touched the filesystem at factory time — an
unconditional `mkdir` of the instance folder, and a `db.ensure_db()` inside an app context
that opened a connection and ran `schema.sql` if `workout_entry` was missing.

Both are gone. The factory now runs no DDL and reaches the `mkdir` only when falling back
to the SQLite development default, which production refuses to do at all. `ensure_db()`
was deleted rather than made conditional, because it conflicted with Alembic as well: it
gave a fresh deployment an unversioned schema that no revision could stamp.

**SQLite had to become hosted Postgres before the app went on the internet**, which is why
Phase 3 came first and why Phases 5–6 sat behind it.

### 3. Tailwind reverses a deliberate architectural choice

`CLAUDE.md`, `CONTRIBUTING.md` and `ARCHITECTURE.md` all stated the no-build-step,
no-JS-dependencies invariant as intentional. Tailwind requires a build step. That is a
fine trade — it buys DaisyUI and a design system — but it is a reversal, not an
addition, and all three documents were updated in the same change so a later session
isn't working from a stale invariant.

The good news: **DaisyUI is pure CSS.** Its components (`btn`, `card`, `modal`, `stat`,
`drawer`) are class names, not React components. They work directly in Jinja templates
with no JS framework, which is what makes Phase 1 cheap and what keeps Flask viable
through Phase 6.

The reversal turned out narrower than feared: the build step is **CSS-only and
npm-free**, and JS is still served exactly as written. See Phase 1 below.

### 4. Auth and the set model were both impossible without migrations — *resolved in Phase 3*

`schema.sql` was applied once and `init-db` dropped everything. Survivable while the
database is one laptop; data loss the moment there are accounts. Alembic had to land
before the `user` table did — and before the `workout_set` table, which is the more
invasive of the two changes.

Both are now revisions rather than rewrites. Phase 3 also set the metadata's constraint
`naming_convention` for this specific reason: SQLite cannot `ALTER` most things, and
Alembic's batch mode can only recreate constraints it can name.

---

## Dependency graph

```
Phase 1  Tailwind + DaisyUI ──┬──▶ Phase 2  Exercise taxonomy ──┬──▶ Phase 8  AI custom exercises
   ✅ done                    │       ✅ done (absorbed 9)      ├──▶ Phase 9  Images ✅ shipped in 2
                              └──▶ (all later UI)               └──▶ Phase 10 Mobile + watch + stores

Phase 3  Migrations + Postgres ──┬──▶ Phase 4  Set-level logging ──▶ Phase 7  Training essentials
   ✅ done                       │                                        │
                                 └──▶ Phase 5  Auth ──┬──▶ Phase 6  Vercel deploy ──▶ Phase 10
                                                      └──▶ Phase 8  AI custom exercises

   Phase 4 is the other hard gate: Phase 7 and most of the competitive feature set read
   weight and reps per set, so nothing in that list can be built before it lands.

   Phase 10 reaches backwards: it requires token auth (not cookie sessions) and an
   in-app account-deletion endpoint, both of which must be decided in Phase 5.
```

Phases 1–2 and Phase 3 were independent and ran in parallel. With Phase 3 landed, both
critical paths now start at their next link: **5 → 6** to be on the internet, and
**4 → 7** to be competitive. They converge at Phase 10.

---

## The launch line, and a warning about parity

Three findings from the 2026-07-30 planning review that sit above any single phase.

**Launch is Phase 6 plus a named slice of Phase 7 — and the slice is smaller than
Phase 7.** The stated goal ("hosted, multi-user product") is technically met the moment
Phase 6 deploys, but shipping without a parity floor reads as a prototype. The floor:
previous-values-inline already ships with Phase 4, so the launch-blocking remainder is
**routines and entry editing**. Everything else in Phase 7 — 1RM, PRs, charts,
measurements — improves a launched app and should not delay one.

**Parity is a floor, not a strategy.** Every phase after 2 chases feature parity with
free, mature incumbents, while the thing they cannot copy — the volume-coverage model
and the body map — receives no deepening work anywhere in this plan: per-exercise
secondary weights, region expansion, the tap-a-muscle body-map picker and the coverage
widget are all parked in "left for later" notes. A solo project does not out-feature
Hevy. After launch, alternate parity work with work that widens that gap, starting from
the parked items.

**Add a user-contact checkpoint after Phase 6.** Phase 8's "measure the miss rate
before building" is currently the only place real usage feeds a decision. Make it the
rule rather than the exception: get a handful of people logging for a month before
finalising Phase 7's internal order — what they stumble on should reorder it.

---

## Phase 1 — Tailwind + DaisyUI ✅ *done*

**Depends on:** nothing. **First because it is a soft dependency of everything else** —
Phases 2, 4, 5, 7 and 8 each add UI surfaces (exercise picker, the set grid, login/signup,
routines and charts, AI verification modal), and every one of them would need re-styling if
Tailwind landed later. The app is three pages today; this is the cheapest it will ever be.

### What shipped, and where it diverged from this plan

Three deviations, each deliberate:

**1. No npm.** The plan called for `npm install -D tailwindcss daisyui`. Node was not
installed on the dev machine, and adding a `package.json` to a Python project to compile
one stylesheet is a poor trade. Instead:

```
python tools/fetch_css_toolchain.py    # pinned Tailwind CLI binary + daisyUI tarball → tools/
tools/tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --minify
```

Tailwind publishes a self-contained CLI binary per platform, and daisyUI is a plain
tarball of CSS plus a plugin entry point, so `@plugin "../../../tools/daisyui"` resolves
off disk with no package manager involved. `tools/` is gitignored; the fetch script pins
both versions so a rebuild elsewhere is byte-identical. As planned, the compiled
`styles.css` **is** committed, so nothing at runtime or in CI needs the toolchain.

**2. Tailwind v4, so config is CSS-first.** There is no `tailwind.config.js` and no
`theme.extend`. Tokens live in `@theme`, the theme pair in two `@plugin "daisyui/theme"`
blocks, and content globs are `@source` directives inside `input.css`, with `source(none)`
disabling auto-detection so the globs are the whole story. Cover both
`app/templates/**/*.html` and `app/static/js/**/*.js`; those JS modules construct whole UI
surfaces and toggle literal state classes, so the scanner needs to see them.

**3. A real home page landed now, not in Phase 4.** The plan deferred it on the grounds
that auth creates the signed-out/signed-in split. But `/` being the calendar meant the
app had no front door at all, and a landing page is the natural showcase for the body
map. So `/` is now a static landing page and the calendar moved to `/calendar`. Phase 4
gets *easier* for it: the split becomes a branch inside an existing template rather than
a new route plus a URL migration.

### The theme

Two hand-written daisyUI themes, `bodyshop` (default, light) and `bodyshop-dark`
(`prefersdark`); all 35 stock themes are disabled. As planned, a custom theme rather
than a stock one keeps `--color-train-*`/`--color-over-*` first-class tokens.

The palette is **achromatic on purpose** — cream `#fff8ed`, warm ink `#312726`, warm grey
`#7a716e`, adapted from [jeskojets.com](https://jeskojets.com). There is no accent hue,
which makes the volume ramp the only saturated colour in the app: the heatmap wins the
eye by default. Separation is hairline borders at 10–20% ink, never shadows (`--depth`
and `--noise` are 0). Type is one variable family, Archivo, whose width axis supplies the
wide display voice via `font-stretch`.

### DaisyUI component mapping, as built

| Was | Now |
| --- | --- |
| `.card` | `card` / `card-body` |
| `.icon-btn`, form buttons | `btn`, `btn-circle`, `btn-outline`, `btn-primary` |
| `.toast` | `.toast-bar` (hand-written — daisyUI's `toast` is a corner *stack*, not a centred bar) |
| `.muscle-bar` | hand-written (see below) |
| Week switcher | `card` + `btn btn-circle` (`join` implies a segmented control; these are steppers) |
| `.tag` | `badge` |
| Nav | plain flex header (`navbar` adds a min-height and padding the design doesn't want) |
| Week totals | `#week-meta` inline summary line (a `stats` block outweighed three numbers) |
| Form fields | `input`, `radio`, `alert` |

### What stayed hand-written

The volume-scale colour mixing is computed, not enumerable:

```css
fill: color-mix(in srgb, var(--color-train-dark) calc(var(--level) * 100%), var(--color-train-light));
```

`--level` is a continuous 0–1 value written by JS. Tailwind cannot express this as a
utility, and quantising it into 10 fixed classes would visibly band the gradient. So the
`.muscle` / `.muscle-row` colour rules and the SVG body-map geometry stay hand-written in
`@layer components`.

That block grew one more job than planned. **Every class the JS toggles lives there too**
— `.day-cell.is-selected`, `.toast-bar.is-visible`, `.entry`, `.empty`. Tailwind's
scanner reads literal text only, so `` `is-${state}` `` would be purged silently; the
plan's answer was "write it out in full or safelist it", but a named component class is
more readable than swapping utility lists from JS and keeps the state vocabulary visible
in one place. The rule now is: **static structure is utilities in templates, JS-driven
state is a named class in `input.css`.**

One trap worth knowing: daisyUI sets `.card figure { display: flex }` with no
`flex-direction`, so a `<figcaption>` inside a card lands *beside* its figure. The
body-map macro passes `flex flex-col` to counter it.

---

## Phase 2 — Exercise catalog and muscle map ✅ *done*

**Depended on:** Phase 1 (so the picker was styled once). The highest-value phase
independent of all infrastructure work, and it defines the vocabulary the AI feature in
Phase 8 emits into — which is why it preceded it.

### What shipped, and where it diverged from this plan

The plan assumed a hand-authored catalog of ~180 curated movements. **It was replaced
wholesale by [free-exercise-db](https://github.com/yuhonas/free-exercise-db)** — 873
movements, Unlicense (public domain), every entry carrying two photographs. That single
decision resolved open decision 1, collapsed Phase 9 into this phase, and made most of
what follows moot.

**1. 873 exercises, not 180.** All categories were imported, including 123 stretches, 61
plyometrics and 14 cardio entries. Muscle mapping collapses the source's 17 slugs onto
our 12 (`lats`/`middle back`/`lower back` → `back`, `abductors` → `glutes`, `adductors`
→ `quads`, `neck` → `traps`); verified across the whole set, no exercise loses its
muscles. Where a secondary collapsed onto its own primary — 107 of them — primary wins,
so no group is ever counted at both weights.

**2. The facets are the dataset's, not the plan's.** There is no `pattern` and no
`modifiers`. free-exercise-db carries `equipment`, `category`, `level`, `force` and
`mechanic` instead, and deriving 29 patterns across 873 rows by hand is exactly the
error-prone data entry adopting a dataset was meant to avoid. Browse drills down muscle →
equipment rather than muscle → pattern; Phase 8 classifies into these facets just as
well.

**3. JSON, not YAML.** `app/data/exercises.json` is generated by
`tools/build_exercise_catalog.py` from a pinned commit, so it is never hand-edited and
YAML's readability advantage does not apply — while PyYAML would have been the first new
runtime dependency in a repo that pins only Flask. The generator follows the CSS
toolchain's contract: pinned fetch, committed output, no network at runtime or in CI.

**4. Non-strength categories grade as zero.** Not in the plan, but forced by importing
everything: a hamstring stretch that shades the hamstrings green is a lie about the week.
`VOLUME_CATEGORIES` gates it, and `/log` labels the excluded movements on selection
rather than letting the omission be silent.

**5. Two endpoints were added.** The plan said "no new endpoints", which held at 180
entries but not at 873. `GET /api/exercises` is now a *light* shape (no instructions, no
images — 186 KB rather than 846 KB), `GET /api/exercises/<id>` serves the full record for
the one selected movement, and `GET /api/exercises/recent` backs the picker's default tab
because history is a database query and cannot be filtered client-side.

**6. Search gained an alias map.** The plan's example — "incl db" finding "Dumbbell
Incline Bench Press" — does not work on substring matching alone, since no field contains
"db". A small gym-shorthand map (`db`, `bb`, `kb`, `ez`, `bw`, `ohp`, `rdl`) makes it
work, and it is the kind of thing worth extending as real misses show up.

### Grading: primary vs secondary

Shipped as specified:

```python
PRIMARY_WEIGHT = 1.0
SECONDARY_WEIGHT = 0.5
```

`sets` is now a float, rendered by `format_sets()` in Python and `formatSets()` in
`ui.js`. `schema.sql` did not change — `sets INTEGER NOT NULL CHECK (sets > 0)` still
stores what the user did, and only the per-muscle aggregate is fractional.

Open decision 4 stands answered *provisionally*: 0.5 is defensible and uniform, but it is
one number standing in for a spectrum. Revisit if the map starts reading wrong.

### Muscle map expansion

7 → 12, split as planned. Front: chest, abs, shoulders, biceps, forearms, quads. Back:
back, traps, triceps, glutes, hamstrings, calves. All three predicted complications were
real:

- **`traps` moved out of `back`** — historical `back` counts are not comparable across
  the change.
- **`glutes`, `calves` and `forearms` were documented as deliberate gaps** in
  `_body_figure.html` and ARCHITECTURE.md. Both were corrected in the same change.
- **`shoulders` needed new `.body-base` deltoid caps** before there was anything to
  overlay.

One complication the plan missed: **regions within a view must not overlap.** The first
attempt had glutes spanning y=198–238 and hamstrings y=216–298, so one painted over the
other and the map misreported volume. They are now separated at the crease, and the rule
is written into the partial's header comment.

`shoulders` stayed **one** group (open decision 6 answered: one, for now). The facet data
preserves front/side/rear, so splitting later is a data change plus SVG paths.

### Selection UI

All three access paths shipped: **Recent** (default, from entry history), **Search**
(substring over name, equipment, muscles and category, with the alias map above) and
**Browse** (muscle → equipment). The selected movement shows its two frames cross-fading
in CSS — `steps(1)` on stacked `<img>` elements, no JS timer — plus its instructions.

**Revised after the fact: the three paths are not equals.** Giving them three identical
tabs made search look like the primary way in, when searching a catalog nobody has
memorised is the *narrow* case — it only works if you already know the name. Browse is
how you shop for a movement and the only path a first-time user can succeed on, so
Recent and Browse now carry the labelled tabs and search is reduced to a magnifier icon.

The deeper problem was that browse did not deserve promotion as built. It sorted
alphabetically and truncated at 40 rows, which put "Alternating Floor Press" at the top
of chest and pushups (70th of 147) beyond reach entirely. Fixed by `Exercise.rank`
(see ARCHITECTURE.md — curated staples, then facet-derived order, zero-volume categories
last), by ranking your own logged movements above both, and by replacing the silent cap
with a "Show all 147" footer. Browse is also indexed by muscle at load instead of
re-scanning 873 rows per dropdown change.

Not done, and the obvious next step: **the body map as the picker** — tapping a region on
the figure to browse that group, reusing the `_body_figure.html` macro. It needs a
selectable variant of the macro and mobile layout work, and `rank` was the prerequisite.

### Images (formerly Phase 9)

The licensing question that gated Phase 9 dissolved: free-exercise-db is public domain,
and its images arrived with the catalog. 1,746 files at roughly 85 MB do not belong in
git, so they are served from jsDelivr pinned to the same commit, behind an
`EXERCISE_IMAGE_BASE` config value so self-hosting is a one-line switch.

Two frames per movement rather than the planned single still image, which is what makes
them read as a movement rather than a pose.

### Muscle regions — the answer to "split the chest and the delts"

Added after Phase 2, in response to wanting upper/mid/lower chest and the three deltoid
heads. Researching it first changed the shape of the answer, and the reasoning now lives
in [VOLUME_SCIENCE.md](VOLUME_SCIENCE.md). The short version:

**Regional growth is real and follows exercise selection — but no study has ever
established a weekly set target for a muscle head.** Nobody has run that experiment, for
any muscle. So subdividing a group into targets would mean inventing numbers and printing
them next to sourced ones, and three 10-set chest regions silently sets a 30-set chest
target that makes every user read as under-trained.

What shipped instead: six groups (chest, shoulders, back, triceps, hamstrings, calves)
break into 13 regions that report **where a group's volume landed** — share of the sets
that could be placed inside it, plus a `neglected` flag. No targets, no colour from the
volume ramp. Attribution is partial on purpose, so a deadlift's back volume sits
unattributed rather than being split between lats and mid back.

Deliberately excluded: biceps long/short head and "upper vs. lower abs" (EMG, not
hypertrophy data). Quads, glutes and traps are plausible but their movement-to-region
mapping is muddier — they can come later.

**The remaining work is data, not design.** `EXERCISE_REGIONS` covers ~140 movements of
873, because free-exercise-db carries nothing sub-muscular. Extending it is hand work or a
job for Phase 8's classifier — which must emit into `MUSCLE_REGIONS` rather than inventing
its own vocabulary. Should a region ever earn a target, it must **sum** into its parent's.

### Left for later

- **Data migration for existing rows** shipped as `flask --app app remap-exercises`
  (`squat` → `Barbell_Squat`, and three more), which Phase 3 folded into Alembic
  revision `0002` and deleted. Renamed ids are handled for the four that existed.
- **Per-exercise secondary weights** instead of a flat 0.5.
- **Delt granularity** — front/side/rear, if the single `shoulders` group proves too
  coarse.

---

## Phase 3 — Foundations: migrations and Postgres ✅ *done*

**Depended on:** nothing — ran in parallel with Phases 1–2. Placed here because it blocks
Phases 4 and 5 and nothing else. No user-visible change, and no endpoint or payload
moved, which is the check that it stayed in its lane.

Design spec: [2026-07-29-phase-3-migrations-postgres-design.md](superpowers/specs/2026-07-29-phase-3-migrations-postgres-design.md).

### What shipped

| Task | As built |
| --- | --- |
| Introduce migrations | Plain Alembic, three revisions, `migrations/` at the repo root. No Flask-Migrate — it wraps a CLI we would otherwise call directly. `env.py` resolves `DATABASE_URL` from app config, so `alembic upgrade head` and `flask --app app upgrade-db` cannot disagree. `init-db` is now a dev-only reset that refuses to run under production config. |
| Delete `ensure_db()` | **Deleted, not gated.** `create_app` now opens no connection, runs no DDL, and touches disk only for the SQLite dev default. `run.py` migrates before serving, so `python run.py` is still zero-setup, while `wsgi.py` and Phase 6's entry point import the factory and never migrate. |
| Abstract the data layer | SQLAlchemy Core. The deciding argument was that **Alembic depends on SQLAlchemy anyway**, so `psycopg`-with-`%s` meant installing it regardless and then hand-rolling `lastrowid` vs `RETURNING`, `AUTOINCREMENT` vs `IDENTITY` and `datetime('now')` vs `now()` beside it. `get_db()` kept its name and returns a Core `Connection`, so the SQL-only-in-`models.py` rule reads unchanged — and that rule is why the port touched one file. |
| Schema source of truth | `app/schema.sql` is gone; `app/tables.py` holds the `MetaData`, with a constraint `naming_convention` so Phase 5's `batch_alter_table` has names to work with. |
| Provision Postgres | Supabase, reached as plain Postgres over `DATABASE_URL`. Provider strings are normalised in `config.py`, since `postgres://` is what every provider prints and SQLAlchemy rejects it. |
| Connection pooling | `NullPool` plus `prepare_threshold=None` for Postgres. The pooler is the pool; a second one inside a serverless function exhausts connection limits at trivial traffic. |
| Secret hygiene | Production raises `ConfigError` on a placeholder `SECRET_KEY` **or** a SQLite `DATABASE_URL`. The instance `config.py` **stays** — it is a legitimate way to hold a secret outside the repo — so the check moved instead: it runs in `create_app` against the *resolved* config, which the instance file can satisfy but not bypass. |
| Data migration | `remap-exercises` deleted, folded into revision `0002`, which carries its own frozen copy of the mapping. A migration that imported `RETIRED_EXERCISE_IDS` would do different things depending on when it ran. |
| Test impact | Per-test SQLite file in `tmp_path` kept as the default. `BODYSHOP_TEST_DATABASE_URL` points the same suite at real Postgres, with the schema built by the migrations; CI adds a `postgres:16` job. |

### Where it diverged from this plan

**1. Three revisions, not one baseline.** The plan said "baseline the current schema as
revision 1". `0001` does exactly that, but the TEXT-date question below needed its own
revision, and `0002` is the folded-in data migration. Slightly redundant on a fresh
Postgres — `0001` creates a TEXT column that `0003` converts — and worth it: an existing
local database can be `stamp-db 0001`'d and carried forward, and `0003` exercised the
SQLite rebuild path before Phase 5 has to depend on it.

**2. The `entry_date BETWEEN` question resolved as "convert it".** The plan flagged the
lexicographic trick for revisiting. It is now a real `DATE`. The trick was never the
problem — on SQLite the stored form is still `'YYYY-MM-DD'`, so the comparison remains
correct — but on Postgres a TEXT date has no date semantics at all, and doing this later
would be another migration over a bigger table.

**3. `batch_alter_table` turned out to be unusable for that conversion, and dangerously
so.** Alembic's `SQLiteImpl.cast_for_batch_migrate` adds a `CAST` to its table-copy
whenever type affinity changes. SQLite has no date types, so `CAST('2026-07-28' AS DATE)`
is `CAST(… AS NUMERIC)` — which prefix-parses to the integer `2026`. The first
implementation silently destroyed every date and timestamp in the table; the test written
for the conversion caught it. `0003` branches by dialect instead: Postgres converts with
`USING`, SQLite re-declares the columns and copies the bytes untouched.

This is worth carrying into Phase 4, which changes column types again.

**4. Two smaller traps, both now written into CLAUDE.md.** Alembic applies the metadata's
`naming_convention` *on top of* whatever constraint name a revision passes, so a
fully-qualified name comes out double-prefixed — pass bare tokens. And SQLAlchemy **does**
reflect SQLite CHECK constraints, contrary to the usual advice about `table_args`, so
passing one explicitly to a batch operation creates a duplicate.

**5. `python-dotenv` became a dependency**, which the plan did not anticipate. Flask's CLI
loads `.env` natively when it is installed, so `flask --app app upgrade-db` reads the same
configuration `run.py` does. `.env.example` is committed and documents which Supabase
connection string belongs where — the transaction pooler for the app, the session pooler
for migrations.

### Left for later

- **`postgres://` normalisation covers three prefixes**, not every provider spelling that
  might appear.
- **`NullPool` unconditionally on Postgres.** Right for serverless, mildly wasteful under
  a long-lived gunicorn process. Revisit if Phase 6 does not end up on Vercel.
- **No `DELETE`-side ownership checks yet** — that is Phase 5's `user_id` sweep, and it is
  the phase where `delete_entry` stops being global.

---

## Phase 4 — Set-level logging: weight, reps and RPE

**Depends on:** Phase 3 (this is a destructive schema change and wants Alembic), Phase 1
(the set grid is the most interaction-heavy surface in the app). Coordinate with Phase 2 —
both rewrite `/log`.

**Why this early:** it is the gate on the entire competitive feature set. Previous-values-
inline, PR detection, 1RM estimates, per-exercise progress graphs, plate and warm-up
calculators, and volume-load charts are all reads over `(weight, reps)` per set. Building
Phase 7 without this is impossible; building it after means rewriting the log page twice.

### Schema

One child table, keeping `workout_entry` as the parent so the weekly summary keeps working:

```sql
CREATE TABLE workout_set (
    id          INTEGER PRIMARY KEY,
    entry_id    INTEGER NOT NULL REFERENCES workout_entry(id) ON DELETE CASCADE,
    set_index   INTEGER NOT NULL,          -- 1-based, order within the entry
    weight      REAL,                      -- NULL for bodyweight movements
    reps        INTEGER,
    rpe         REAL,                      -- NULL unless the user logs it
    set_type    TEXT NOT NULL DEFAULT 'normal',  -- normal | warmup | drop | failure
    UNIQUE (entry_id, set_index)
);
CREATE INDEX idx_workout_set_entry ON workout_set (entry_id);
```

`workout_entry.sets` becomes **derived, not stored** — it is `COUNT(*)` over the child
rows where `set_type != 'warmup'`. Warm-up sets are logged but must not count toward
weekly volume, or the muscle map inflates the moment anyone logs properly.

Two options for the existing column: drop it and compute, or keep it as a denormalised
cache. **Drop it.** The write path is one insert per workout, the read path is already
aggregating, and a cache that can disagree with its source is exactly the bug this app's
single-source-of-truth design exists to avoid.

### Blast radius

Comparable to Phase 5's `user_id` sweep, and touching mostly the same functions:

- **`models.py`** — `add_entry` takes a list of sets, not an int. `_row_to_entry` needs a
  join or a second query. `validate_entry`'s `1 <= sets <= 100` rule splits into per-set
  validation (weight ≥ 0, reps 1–1000, RPE 1–10 in 0.5 steps).
- **`services/summary.py`** — `bucket["sets"] += entry.sets` still works if `entry.sets`
  stays a derived property, which is the cheapest way to keep the muscle map untouched.
- **`api.py` / `docs/API.md`** — `POST /api/entries` takes a `sets` array instead of an
  integer. **This is a breaking API change**; it is also the last good moment to make one,
  since there are no external consumers before Phase 6 deploys.
- **`log.js` + `log.html`** — the radio-and-stepper form becomes a set grid: a row per set
  with weight/reps inputs, prefilled from the last time this exercise was logged.
- **`app/tables.py` + a new revision, `tests/`** — the `sets` column and its
  `sets > 0` check go away; the `add` fixture in `conftest.py` needs a set-list
  signature. Note Phase 3's finding before writing that revision: a type or column
  change on SQLite cannot go through `batch_alter_table` if affinity changes, or
  Alembic's `CAST` corrupts the data.

### Ship in this phase, not later

These are cheap once the data exists and are what make the model feel worth it:

| Feature | Why it belongs here |
| --- | --- |
| **Previous values inline** | Prefill each set row from the last session of that exercise. The single highest-rated logging feature in the category, and it is one indexed query. |
| **Rest timer** | Starts on set save. Pure client-side JS; no schema, no backend. Native notifications come in Phase 10. |
| **Set types** | Already in the schema above — warmup/normal/drop/failure. Free once the column exists, and warm-up exclusion is a correctness requirement, not a nicety. |
| **Plate calculator** | Pure function of weight and bar weight. No storage, no API. |

Defer 1RM, PRs and charts to Phase 7 — they want history to read against, and history only
accumulates after this ships.

### Migration note

Existing rows have a set count and nothing else. Backfill one `workout_set` per counted
set with `NULL` weight and reps; the muscle map is unchanged and the history stays
truthful about what was actually known. Do **not** invent weights.

---

## Phase 5 — Secure user login

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

**That `ALTER TABLE` does not run on SQLite** — and local dev stays SQLite, so this is not
a Postgres-only detail. SQLite refuses to add a `NOT NULL` column with no default, *and*
refuses to add a column with a `REFERENCES` clause and a non-NULL default. Both rules
apply to an empty table, so "wipe first" does not rescue it. Alembic's `batch_alter_table`
is the portable answer: it rebuilds the table under SQLite and emits a plain `ALTER` under
Postgres. Otherwise add the column nullable, backfill, then tighten.

### Blast radius

**Every function in `app/models.py` needs a `user_id` parameter and every query a
`WHERE user_id = ?` clause.** `list_entries`, `sets_by_date`, `get_entry` and
`delete_entry` are all currently global. `delete_entry` is the dangerous one — without an
ownership check it is an IDOR letting any user delete any row by guessing an id. This is
mechanical but must be exhaustive; one missed clause is a data leak.

`workout_set` from Phase 4 does **not** need its own `user_id` — ownership flows through
`entry_id`. But any query that reaches sets directly (the previous-values prefill, the
Phase 7 progress charts) must join back to `workout_entry` and filter there. A set query
that skips the join is the same IDOR wearing a different hat.

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

**Recommendation, recorded so this phase does not start with it open: take Supabase
Auth, with bearer tokens.** (Closes open decision 3 and the auth half of decision 2.)
Three arrows already point the same way: the database is already Supabase, Phase 10
requires token auth and mobile SDKs, and most of the table above — password hashing,
email flows, rate-limiting infrastructure, enumeration — exists only to support the
self-hosted option and becomes the provider's problem otherwise. Token auth also
dissolves the CSRF row, which is a cookie-session problem. Keeping Flask-Login on the
table is silently keeping the most expensive version of this phase alive.

**Design account deletion here, not in Phase 10.** Apple's 5.1.1(v) is what eventually
*requires* `DELETE /api/account`, but a launched app holding emails and training
history needs it as ordinary privacy hygiene — and it is a cascade design question
(`workout_entry`, `workout_set`, and every later per-user table), cheapest to answer
while the `user_id` sweep is already open.

Existing rows have no owner: either wipe or backfill to a seed account. Decide before
writing the migration — `NOT NULL` without a default fails on a non-empty table.

The **signed-out/signed-in split** lands here. Phase 1 already built `/` as a static
landing page and moved the calendar to `/calendar`, so this is now a branch inside
`home.html` — swap the hero's "Log a workout" CTA for a link into the app when a session
exists — rather than a new route.

---

## Phase 6 — Stack decision and Vercel deployment

**Depends on:** Phases 3 and 5. Placed before the AI feature deliberately: deployment is
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

**But challenge the host before the framework.** The table above compares Flask-on-Vercel
to a rewrite and skips the cheaper question: Vercel versus a container host (Fly,
Railway, Render) running the already-documented `gunicorn "wsgi:application"` entry
point as-is — no `api/index.py` shim, no Python cold starts (the weakness the table
itself concedes), and `NullPool` can become a real pool. Nothing from Phase 3 is wasted
either way; the no-DDL factory and env-driven config are good hygiene on any host. If
Vercel wins, it should be for a recorded reason (free tier, existing account), not by
default — as written, the plan optimises for the harder deployment target without
saying why.

### Deployment shape

```
vercel.json          → route all traffic to api/index.py
api/index.py         → from app import create_app; app = create_app("production")
requirements.txt     → runtime deps (Vercel installs automatically)
```

Serve `app/static/` from Vercel's CDN, not Flask. Everything is already env-driven
(`BODYSHOP_*` in `config.py`) — add `DATABASE_URL`, set `BODYSHOP_CONFIG=production`, and
set a real `BODYSHOP_SECRET_KEY` in Vercel's dashboard, never in the repo.

Audit `requirements.txt` while you are here: it pins Flask and nothing else, but CLAUDE.md
documents `gunicorn "wsgi:application"` as the production entry point and gunicorn is not
listed. Either add it or drop the claim — on Vercel neither `wsgi.py` nor gunicorn is used,
since the platform imports the app object directly.

Gate production deploys on the Postgres CI job added in Phase 3.

### The launch floor

Deployment is not launch. Before pointing anyone at the URL, the operational and legal
minimums for holding strangers' training history:

- **Backups with a tested restore.** Supabase's automated backups are a start; what
  matters is having actually restored one.
- **Error monitoring.** A Flask app failing silently in the cloud is invisible; wire in
  Sentry or equivalent before there are users to hit the errors.
- **A privacy policy.** Filed under Phase 10's store logistics until now, but the moment
  real emails and workout data are collected it is a launch requirement, not a store one.
- **CSV export** — moved here from Phase 7. One endpoint, trivial once the set model
  exists, and the honest answer to "can I leave?"; worth having before asking anyone to
  trust the app with a training history.

### Revisiting the stack — tripwires, not a debate

A full Vercel/Supabase stack (Next.js, or clients talking to Postgres through RLS) was
considered and rejected in the 2026-07-30 review: the rewrite hits the most valuable
code — the grading rules, region attribution and the tested API surface — and RLS can
express *ownership* but not "secondaries count 0.5 and warm-ups don't count", so the
rules would move into edge functions or the client, dissolving the one-place-rules
design. Adopting Supabase's *services* (Postgres, Auth) is not a stack switch and is
already the plan.

Revisit only if a tripwire fires: Python cold starts measurably hurt **and** Vercel is a
fixed constraint; Phase 7's routines UI outgrows vanilla JS; or mobile becomes the
primary surface, where one React codebase has real consolidation value. None of these is
decidable before launch.

---

## Phase 7 — Training essentials

**Depends on:** Phase 4 (every item here reads weight and reps), Phase 1, and — for the
per-user variants — Phase 5. Placed immediately after deployment because this is the
**competitive-parity phase**: the items below are table stakes in this category, not
differentiators. Shipping without them reads as a prototype next to Hevy or Strong.

Sequenced within the phase by cost-to-value, cheapest first. The first three are days of
work each; routines are the expensive one. One caution on that ordering: routines are
also the *point* — what makes the app repeatable rather than a diary — so cheapest-first
means the phase's reason for existing is what gets cut if time runs short. If the phase
must shrink, cut from the pure functions, not from routines and editing (see *The launch
line* above).

| Feature | Shape | Notes |
| --- | --- | --- |
| **1RM estimates** | Pure function | Epley or Brzycki over `(weight, reps)`. No storage — compute on read, so changing formula is not a migration. Offer the formula as a setting; lifters have opinions. |
| **PR detection** | Query + a badge | Per exercise: heaviest weight, best estimated 1RM, best volume-load. A live "new PR" toast on save is the single most-cited delight feature in the category. Cache per `(user_id, exercise_id)` only if the query proves slow — it will not at this scale. |
| **Per-exercise progress graphs** | New page + endpoint | `GET /api/exercises/<id>/history` → weight, est. 1RM and volume-load over time. **This is the first chart in the app**; pick a rendering approach deliberately — inline SVG keeps the zero-JS-dependency rule that Phase 1 already bent, a charting library breaks it further. |
| **Body weight and measurements** | New table | `body_metric(user_id, recorded_on, metric, value)` — long format, so adding waist/bodyfat/photos later is rows, not columns. Feeds nothing else; it is a standalone tab. |
| **Entry and set editing** | `PATCH` + a form | New with Phase 4: per-set data makes delete-and-relog genuinely punishing — one fat-fingered weight in a five-row grid means re-entering everything. Cheap against a flat count, missing entirely now. Design it aware of Phase 10: an edit is not replayable the way an insert is, so it sits in the same family as the delete tombstones. *(CSV export moved to Phase 6's launch floor.)* |
| **Routines / templates** | New tables + real UI | The expensive one. A routine is an ordered list of exercises with target sets/reps; starting a workout instantiates it into `workout_entry` rows. This is what makes the app repeatable rather than a diary, and it is the prerequisite for any programming feature later. Budget more than the rest of the phase combined. |

### What this phase deliberately excludes

**Auto-progression** — routines that advance weight week over week. It is the main axis
competitors differentiate on (Boostcamp's 11,000+ programs, Fitbod's generated sessions,
Hevy Trainer's auto-progression), and it is a genuine product decision rather than a
build task: progression schemes are opinionated, and picking one wrong is worse than
having none. Ship static routines, watch how people actually copy them forward, then see
*Post-launch candidates*.

---

## Phase 8 — AI-assisted custom exercises

**Depends on:** Phase 2 (the vocabulary the model classifies *into*), Phase 5 (custom
exercises are per-user by definition), Phase 6 (API key management is deployment config).

Placed last among functional phases for a product reason as well as a technical one: **the
value of this feature is a function of how often the catalog falls short.** Ship the
catalog, measure the miss rate, then build this. If the catalog covers 99% of what people
log, a search box that says "not found — request it" may be enough.

**Phase 2 raised that bar considerably.** The catalog shipped at 873 movements rather than
the ~180 this was scoped against, which makes a miss meaningfully rarer — and it means the
classifier's target vocabulary is free-exercise-db's facets (`equipment`, `category`,
`level`, `force`, `mechanic`), not the `pattern`/`modifiers` split sketched here. Update
the prompt's few-shot examples accordingly. Measure before building.

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

- Rate-limit per user (reuse the Phase 5 Flask-Limiter setup).
- Cap custom exercises per account.
- Treat the input as untrusted text — it reaches a model, so prompt injection is in scope.
  The `Literal` enum plus server-side validation contains the blast radius: the worst case
  is a wrong-but-valid muscle group, not arbitrary data.
- Log token usage per call. At Opus 5 pricing ($5/$25 per MTok) with a cached prompt, a
  classification is fractions of a cent — but it is a per-user-action cost, unlike the rest
  of the app.

---

## Phase 9 — Exercise images ✅ *shipped inside Phase 2*

This phase no longer exists as separate work. It was contingent on a licensing decision,
and the note below turned out to be the one that mattered:

> **This decision can move Phase 9 to Phase 2.** If you adopt free-exercise-db, the images
> and the catalog data arrive together — which would eliminate most of Phase 2's data-entry
> work *and* collapse this phase into it.

That is what happened. free-exercise-db is Unlicense (public domain), so there was nothing
to license, and its images ship with its data. See Phase 2 above for what was built.

Two things the original plan called for are worth carrying forward as small follow-ups:

- **A placeholder fallback.** `log.js` currently removes the frame block when an image
  fails to load, which is honest but bare. A real placeholder would be better.
- **`.webp` rather than `.jpg`.** The source ships JPEGs at ~50 KB each. Converting is
  only worth it alongside self-hosting, which `EXERCISE_IMAGE_BASE` already allows.

---

## Phase 10 — Mobile, watch and store distribution

**Depends on:** Phases 2, 4, 5, 6 and 7. Last because it consumes all of them — the catalog
is what makes a mobile logger worth opening, the set model is what it logs, routines are
what it opens to, auth is what makes it multi-device, and the deployed API is what it talks
to.

**But two of its constraints have to be honoured in Phase 5, not here.** See *Decisions
this forces earlier* below; retrofitting either is expensive.

**And re-plan it before starting it.** This is a program wearing a phase's clothes:
offline-first sync, a native client, a watch app and two store reviews is more work than
Phases 1–7 combined, and the "Alembic revisions rather than rewrites" framing below
covers only the schema — the easy part. The offline queue and replay logic are a client
rearchitecture. When its turn comes, it gets its own roadmap with its own phases rather
than one row in the summary table.

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

On-device camera work — *Computer-vision form tracking* under **Post-launch candidates**
— would clear 4.2 more decisively than any of the above, since it is a capability a
website structurally cannot have. It is also far more expensive than all of them
combined, so it is not a reason to choose a route; it is a reason to make sure the route
chosen here does not foreclose it. Route B and route C both keep it open; route A (PWA)
does not.

If mobile is a first-class surface rather than a checkbox, **C is the honest answer**, and
it moots the Next.js question from Phase 6 — React Native becomes the client and Flask
stays the API it already is.

### Offline-first is the real cost

The gym is where this app gets used and where reception dies. The current design fetches
everything from `/api` on load, which is a blank screen in a basement. This is also the
loudest complaint category in competitor App Store reviews — "continue my workout" that
does not work offline, forcing a restart mid-session, and history tabs that spin forever.
**Treat offline as a headline feature, not a resilience detail.**

**The append-only model is unusually well suited to sync**: entries are immutable rows,
so a client can queue inserts locally and replay them with no conflict resolution. Three
changes make it work, all Alembic revisions rather than rewrites:

- **Client-generated ids** (UUID instead of autoincrement) so a queued entry has an
  identity before it ever reaches the server.
- **Soft delete / tombstones** — `delete_entry` hard-deletes today, which cannot be
  replayed or ordered against a concurrent insert from another device.
- **Entry + sets must sync as one unit.** Phase 4's parent/child split means a replayed
  `workout_entry` with missing `workout_set` rows is a workout that silently reads as zero
  volume. Queue the whole aggregate, not row-by-row.

### Watch logging

Deliberately *after* the phone app rather than alongside it — it is a second client
against the same API, and it is worth nothing until the phone client works. Ranked by
what actually gets used mid-set:

1. **Rest timer on the wrist** — the one genuinely watch-native feature. Phase 4 ships the
   timer logic; this moves the notification to where you can see it without unlocking.
2. **Logging a set from the watch** with live sync to the phone, and auto-save on
   reconnect. Needs the offline queue above to already exist.
3. **Heart rate capture** and duration-based exercise timers.

Apple Health / Health Connect write-back sits here too. Note that reading *recovery* data
(HRV, sleep) is a different proposition — see *Post-launch candidates*.

### Decisions this forces earlier

| Decision | Phase | Why mobile changes it |
| --- | --- | --- |
| **Token auth, not cookie sessions** | 5 | Flask-Login cookie sessions are awkward from a native client. Choose bearer tokens (JWT + refresh) or a provider with mobile SDKs (Clerk, Supabase). Converting an API from cookies to tokens later touches every endpoint and the whole CSRF design. |
| **In-app account deletion** | 5 | **Apple Guideline 5.1.1(v) requires** any app offering account creation to offer account deletion *inside the app* — a support email does not satisfy it. Needs `DELETE /api/account` and a cascade to `workout_entry`, `workout_set`, `body_metric`, routines and `custom_exercise`. |
| **Client-generated set ids** | 4 | If the set model uses autoincrement ids, the offline queue needs a migration later. Choosing UUIDs when the table is created is free; changing them afterwards is not. |

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

## Post-launch candidates

Deliberately unscheduled. Each is a real competitive gap, but none belongs in a plan whose
current job is to reach a working, hosted, multi-user app — and each is a product decision
first and a build task second. Revisit after Phase 10 ships, in roughly this order.

### Auto-progression and programming

**The main axis competitors differentiate on.** Hevy is a blank canvas — progression across
weeks is the user's job — and Boostcamp attacks exactly that with pre-built programs that
advance automatically. Phase 7 ships static routines; this is the layer that advances them.

Cheap to start: linear progression (+2.5kg when all target reps are hit) is a rule over
data Phase 4 already stores. Expensive to get right: every scheme past linear is
opinionated, and being wrong here is worse than being absent. **Ship one scheme, make it
visible and overridable, and only add more if people ask.**

### Social

- [ ] Social feed, profiles, leaderboards, shareable routine folders, Strava integration

Hevy's real moat and the hardest thing here to bootstrap — a feed with no one in it is
worse than no feed, and it is the one feature whose value is zero at launch by definition.
It also pulls in moderation, blocking, reporting and privacy-settings work that the store
review process will ask about. **Explicitly not a launch feature.** The cheap precursor is
shareable read-only routine links, which needs no graph.

### Nutrition tracking

- [ ] Macro / calorie logging

Genuinely absent from most lifting trackers, Hevy included, and reportedly the most common
feature request in reviews of lean loggers — people resent needing a second, ad-heavy app.
That is a real opening, but it is close to a second product: a food database, barcode
scanning, and a daily-target model that shares almost nothing with the set model. Scope it
as its own project, not a phase.

### Recovery-aware programming

- [ ] Adapt volume from HRV, sleep and resting heart rate

Mostly unclaimed in this category — competitors are knocked specifically for not reading
sleep or HRV. Depends on watch integration from Phase 10 for the data, and on
auto-progression above for something to actually adapt. The most speculative of the
adaptation items: it only works if the adaptation is good enough to trust.

### Conversational AI coaching

- [ ] Chat-based programming and form guidance

Distinct from Phase 8, which classifies exercise names. Competitors ship *algorithmic*
progression marketed as AI; a genuine conversational coach over the user's own history is
the differentiated version. Wants Phase 7's history to be worth reasoning about, and it
inherits every cost control and prompt-injection concern already specced in Phase 8.

### Computer-vision form tracking

- [ ] Barbell path tracing from phone video, with velocity per rep

**The largest engineering effort on this page, and the one with the clearest
differentiator at the end of it.** Bar path is the standard diagnostic for the three
main lifts — a squat that drifts forward out of the hole and a bench that bar-paths in a
straight vertical line are both visible in a trace and invisible in a set log. Nothing in
the category ships it without hardware.

**Depends on Phase 10, hard.** It needs a camera, and it needs inference *on device* —
uploading gym video is the wrong answer on latency, cost and privacy simultaneously (see
below). That makes it a native-client feature, which means route C or a Capacitor shell
with a real plugin, not a web page. It also wants Phase 4's set model to attach results
to: a trace belongs to a `workout_set`, not to a day.

#### Trace before judgement

Two very different products get called "form checking", and only one of them is a
reasonable thing to build:

| | Barbell path tracing | Form correction |
| --- | --- | --- |
| What it does | Tracks the plate across frames, draws the path, derives velocity | Tells the user their knees cave or their depth is short |
| How hard | Tractable — a high-contrast circular plate is close to the easy case for object tracking | Full pose estimation plus a model of correct technique **per lift, per body proportion** |
| If it is wrong | A wobbly line | Someone changes how they lift under a load, on bad advice |

**Ship the trace, not the verdict.** The path and the velocity numbers are measurements;
the user supplies the interpretation, exactly as they do with a mirror or a coach's
video. Prescriptive form correction is close to injury advice, it is wrong often enough
at the tails of body proportion to matter, and being confidently wrong about it is worse
than being silent. If it is ever built, it belongs behind explicit hedging and never as
an auto-generated cue mid-set.

#### What falls out of the same data, nearly free

Once a plate is tracked frame to frame, **mean concentric velocity per rep** is
arithmetic. That is velocity-based training, which today requires a linear position
transducer costing a few hundred dollars — and it feeds auto-progression above with a
better signal than "did they hit the target reps": velocity loss across a set is a
readable proxy for proximity to failure. Rep counting and rough tempo come along too, and
rep counting is what makes the capture worth turning on for people who do not care about
bar path at all.

#### Constraints worth deciding before any of it

- **Never upload frames.** Gym video contains other people who did not consent to being
  recorded, let alone processed. On-device inference (Apple Vision / ML Kit / MediaPipe)
  keeps that contained, and it is also the only version that is free per use — unlike
  Phase 8, this would otherwise be a per-rep server cost.
- **Store the trace, not the video.** A path is a short time series and compresses to
  almost nothing; video is unbounded storage and an unbounded retention question. Keep
  the video local and optional.
- **It has to work in a real gym** — bad light, a phone propped against a water bottle,
  the lifter partly occluded, plates that are black on a black floor. This is where the
  effort actually goes, and it is not visible in a demo shot in good conditions.
- **Degrade to nothing gracefully.** If tracking fails, the set is still logged by hand.
  The camera must never be on the critical path to recording a workout.

The cheap precursor, if this ever wants proving out before the native client exists:
accept an uploaded video for a *single* set, trace it server-side offline, and see
whether anyone looks at the result twice.

---

## Summary

| # | Phase | Blocked by | Why here |
| --- | --- | --- | --- |
| 1 | Tailwind + DaisyUI ✅ | — | Soft dependency of every later UI surface; cheapest at three pages |
| 2 | Exercise catalog, 12 muscle groups, picker, images ✅ | 1 | Highest-value work independent of infrastructure; defines the vocabulary Phase 8 emits into. Absorbed Phase 9 |
| 3 | Migrations + Postgres ✅ | — | Blocked 4, 5 and 6; ran parallel to 1–2 |
| 4 | **Set-level logging: weight, reps, RPE** | 3 | The gate on the whole competitive feature set; everything in Phase 7 reads it |
| 5 | Auth, `user_id`, CSRF, rate limiting | 3 | Needs migrations and a real database |
| 6 | Vercel deploy, CI gates | 3, 5 | Critical path to being online; don't expose an unauthenticated app |
| 7 | **Training essentials: routines, PRs, 1RM, charts, export** | 4, 5 | Competitive parity, not differentiation — the app reads as a prototype without it |
| 8 | AI custom exercises | 2, 5, 6 | Needs the vocabulary, per-user ownership, and key management — and its value depends on the catalog's measured miss rate. **A 873-entry catalog raises the bar for this being worth building** |
| 9 | Exercise images ✅ | — | Shipped inside Phase 2: free-exercise-db is public domain, so its images arrived with its data |
| 10 | Mobile + watch + store distribution | 2, 4, 5, 6, 7 | Consumes everything before it — but dictates Phase 5's auth design and Phase 4's id strategy, so decide both early |
| — | Post-launch candidates | 10 | Auto-progression, social, nutrition, recovery, AI coaching, CV bar-path tracing — product decisions, not build tasks |

---

## Open decisions

A process rule, learned the hard way: **an open decision attaches to the phase that
needs it, as an entry gate.** Decision 2 said "answer before Phase 4"; nothing enforced
that, and Phase 4 started anyway (it hedged the set-id slice, which was the cheap part).
A phase whose gating decisions are still open has not started — it is being improvised.

1. ~~**Image licensing**~~ — **answered: adopt free-exercise-db.** Public domain, images
   included, which collapsed Phase 9 into Phase 2 exactly as predicted.
2. **Mobile approach — PWA, Capacitor shell, or React Native?** The "before Phase 4"
   deadline slipped; Phase 4's design spec answered the set-id slice (server-minted
   UUIDs, buying the client-id option without exercising it). The remaining halves —
   token auth and in-app account deletion — are **Phase 5 entry gates**, and Phase 5's
   recommendation (Supabase Auth with bearer tokens) satisfies both whichever route
   wins. Note that route C also retires the Phase 6 Next.js question permanently: Flask
   stays the API and the Jinja + vanilla-JS web app becomes the *permanent* lightweight
   web surface, not a placeholder awaiting a rewrite.
3. **Auth: self-hosted or provider?** Recommendation recorded under Phase 5: **Supabase
   Auth, with bearer tokens.** Barely open — the database is already Supabase, Phase 10
   requires tokens and mobile SDKs, and most of Phase 5's requirements table exists only
   to support the self-hosted option. Confirm before Phase 5 starts; it roughly halves
   the phase.
4. **Secondary-muscle weighting** — **shipped at 0.5, with fractional counting in the UI.**
   Still open as a refinement: one flat number stands in for a spectrum, and per-exercise
   weights are possible once there is evidence for them.
5. **Existing data on migration** — wipe, or backfill to a seed account? *(Phase 2's four
   retired ids are handled by revision `0002`; this is now only about Phase 5's
   `user_id`.)*
6. ~~**Delt granularity**~~ — **answered: one `shoulders` group.** The facets preserve
   front/side/rear, so splitting later is a data change plus SVG paths, not a re-model.
7. **AI feature scope** — per-user custom exercises only, or a review queue that promotes
   popular ones into the shared catalog?
8. **Does `workout_entry` survive Phase 4?** The parent/child split keeps the muscle map
   untouched, but a single flat `workout_set` table carrying `entry_date` and `exercise_id`
   is simpler and loses only the ability to attach a note to a whole exercise block.
   Decide before writing the migration, not after.
9. **Charting approach** — recommendation: **inline SVG.** Phase 7's charts are simple
   time series (weight, estimated 1RM, volume-load over dates), well inside inline-SVG
   territory; the repo already demonstrates hand-written-SVG fluency in the body map,
   and this preserves the zero-JS-dependency rule. A library earns its keep on
   interactivity, zoom, or many chart types — none of which Phase 7 or the post-launch
   list needs.

Decisions 1 and 2 can change the plan's *shape* rather than its detail — worth resolving
early even though both belong to late phases. Decision 8 gates Phase 4, which is now on
the critical path for everything competitive.
