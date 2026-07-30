# Architecture

## Why this shape

The product is small but has one non-trivial rule — *which muscle groups did this
week's sets cover?* — that three different surfaces need to agree on (the API, the
summary page, and eventually any export). So the code is organised around keeping
that rule in exactly one place, with thin layers on either side of it.

```
browser  ──fetch──▶  app/api.py        (HTTP: parse, serialise, status codes)
                          │
                          ▼
                     app/services/     (rules: week boundaries, muscle coverage)
                          │
                          ▼
                     app/models.py     (SQL: validation + queries, all of it)
                          │
                          ▼
                     SQLAlchemy Core   (app/db.py: engine, request-scoped connection)
                          │
                          ▼
                     SQLite (instance/bodyshop.sqlite3) or Postgres
```

Which backend is in use is decided entirely by `DATABASE_URL`, and nothing above
`app/db.py` knows the difference. Core is what buys that: the dialect decides
`lastrowid` versus `RETURNING`, `AUTOINCREMENT` versus `IDENTITY`, and how a
`DATE` is stored, so `models.py` expresses queries once.

`app/views.py` renders four server-side shells; everything dynamic is fetched by
the page's JavaScript module from the same `/api` the tests exercise. That means the
HTML never diverges from the API, and the API is testable without a browser.

`/` is the exception: a static landing page with no JS module and no API calls. It is
the one page that will render identically for a visitor and a signed-in user, which is
why it is worth having before auth exists.

## Layer responsibilities

| Module | Owns | Must not |
| --- | --- | --- |
| `app/data/exercises.json` | The catalog data itself — 873 vendored movements. | Be hand-edited; it is generated output. |
| `tools/build_exercise_catalog.py` | Fetching the pinned source and mapping its vocabulary onto ours. | Run at import, in CI, or at request time. |
| `app/exercises.py` | Loading and validating the catalog, the muscle groups, targets and volume weights. | Touch the database. |
| `app/tables.py` | The schema, as SQLAlchemy `MetaData`. Source of truth for both dialects. | Change any existing database — that needs a migration. |
| `migrations/` | How a database reaches the schema `tables.py` describes. Revisions are append-only history. | Import app constants that a later commit could change. |
| `app/db.py` | The engine, request-scoped connections, and the migration commands. | Contain queries. |
| `app/models.py` | Every SQL statement, plus input validation. | Know about HTTP or Jinja, or know which dialect it is on. |
| `app/services/weeks.py` | Week/month boundary maths. | Query the database. |
| `app/services/summary.py` | Turning entries into per-muscle coverage and grading it against each target. | Build HTTP responses. |
| `app/api.py` | Request parsing, JSON shapes, status codes. | Contain business rules. |
| `app/views.py` | Page shells and template context. | Contain business rules. |
| `app/static/js/*` | DOM rendering and user interaction. | Duplicate aggregation logic. |
| `app/static/css/input.css` | The design system: theme pair, tokens, and every hand-written rule. | — (`styles.css` beside it is generated; never edit it) |

## Styling

Tailwind v4 + daisyUI, compiled by a **CSS-only, npm-free build step**: Tailwind ships a
standalone CLI binary and daisyUI is a tarball of CSS, both fetched into gitignored
`tools/` by `tools/fetch_css_toolchain.py`. JavaScript is still served exactly as
written — there is no bundler. The compiled `styles.css` is committed, so running the
app or CI never needs the toolchain; only editing `input.css` does.

Configuration is CSS-first (Tailwind v4): no `tailwind.config.js`. `@theme` holds the
tokens, two `@plugin "daisyui/theme"` blocks define the `bodyshop` / `bodyshop-dark`
pair, and `@source` directives list the content globs.

The division of labour is the part worth internalising:

| Kind of style | Lives in |
| --- | --- |
| Static structure and spacing | Tailwind utilities, in the template |
| Standard controls (buttons, inputs, badges, cards) | daisyUI component classes |
| Anything a JS module toggles at runtime | A named class in `input.css`, `@layer components` |
| The volume-scale colour mixing and SVG geometry | Hand-written CSS, same block |

The last two are not stylistic preferences. Tailwind's scanner reads class names as
literal text, so a class assembled at runtime (`` `is-${state}` ``) is purged silently —
and the colour mixing is computed from a continuous `--level`, which no finite set of
utilities can express without banding the gradient.

## The single source of truth

`app/exercises.py` defines both `EXERCISES` and `MUSCLE_GROUPS`. A movement present
there is simultaneously:

- findable in the `/log` picker (which fetches `GET /api/exercises`),
- valid input for `POST /api/entries` (`validate_entry` rejects unknown ids),
- countable in the weekly summary (`summarise_entries` reads its primary/secondary
  split and its category).

Nothing else hard-codes the list of exercises.

### The catalog is vendored data

The 873 rows are **not** written in Python. They live in `app/data/exercises.json`,
generated by `tools/build_exercise_catalog.py` from
[free-exercise-db](https://github.com/yuhonas/free-exercise-db) (Unlicense, public
domain) at a pinned commit. The generator maps that project's 17 muscle slugs onto
our 12 and drops secondaries that collapse onto their own primary.

This mirrors the CSS toolchain's contract: a pinned fetch whose *output* is
committed, so running the app or CI never needs the network — only changing the pin
does. It also means the ids are free-exercise-db's (`Barbell_Squat`, `Sit-Up`)
rather than slugs of our own.

`exercises.py` validates at import and raises `CatalogError` rather than returning a
partial catalog: unique ids, every muscle slug in `MUSCLE_GROUPS`, a non-empty
`primary`, and exactly two images. A silently wrong slug would corrupt every weekly
summary after it.

Facets come from the source (`equipment`, `category`, `level`, `force`, `mechanic`)
rather than the pattern/modifier split the roadmap originally sketched — deriving
patterns for 873 movements by hand is the error-prone data entry that adopting a
dataset was meant to avoid.

### Ranking is ours, and lives in code

What the source does **not** carry is any notion of how common a movement is, and
alphabetical order at 873 rows is actively hostile: browsing chest opened with
"Alternating Floor Press" and "Around The Worlds", the bench press sat mid-list, and
pushups — 70th of 147 — fell past the picker's row cap where browsing could not reach
them at all.

So `Exercise.rank` exists (**lower sorts first**), in two tiers that never interleave:

| Tier | Rank | Ordered by |
| --- | --- | --- |
| Staples | `0`–`len(STAPLE_EXERCISE_IDS) - 1` | Position in `STAPLE_EXERCISE_IDS` — a curated list, most common first |
| Everything else | `UNRANKED_RANK_BASE` (1000) upward | `mechanic`, then `level`, then whether the equipment is gym-standard; zero-volume categories take a flat 400 penalty and land last |

Two decisions worth keeping:

- **It is in `exercises.py`, not in the JSON.** The catalog is generated from a pinned
  upstream commit and never hand-edited; a popularity ordering is an editorial
  judgement about lifters rather than a fact about the source, and keeping it in code
  means revising it does not mean regenerating the catalog.
- **Every staple id is checked at import**, raising `CatalogError`. A rename upstream
  would otherwise silently demote a staple to the bottom of every browse list, which is
  precisely the failure the ranking exists to prevent.

`rank` rides on the light payload, and `/log` sorts by *history first, then rank*:
`GET /api/exercises/recent` returns `uses` per movement, and a movement you have logged
outranks one the staple list merely believes is popular. The tiers stay disjoint so no
combination of facets can lift an obscure movement above a named staple — a property
`tests/test_exercises.py` asserts directly.

### Images

Each movement carries exactly two photographs, its start and end position. They are
**not** stored in the repo — 1,746 files at roughly 85 MB — but served from jsDelivr
at the same pinned commit, via the `EXERCISE_IMAGE_BASE` config value. `/log` stacks
the pair and cross-fades them in CSS, which turns them into a short loop of the
movement with no JS timer and no player.

`GET /api/exercises` therefore returns a **light** shape with neither images nor
instructions: the picker fetches the whole catalog to filter it locally, and the
full payload is four times the size. `GET /api/exercises/<id>` serves the rest for
the one movement actually selected.

### Grouping schemes: one list, four headings

Twelve rows is an inventory, not a summary — nobody trains "forearms" as a decision, they
train a push day. So `/summary`'s breakdown offers `MUSCLE_SCHEMES`: **Push · Pull · Legs**
(the default), **Upper · Lower**, **Front · Back** (the same split as the two figures, so
the list reads like the map) and **Every group** (the flat twelve).

The rules that keep it honest:

- **A scheme is a view, never a filter.** Every scheme must file all twelve groups exactly
  once, checked at import by `_check_schemes` — a scheme that dropped a group would hide
  volume the user logged, and one that repeated a group would double it in a bucket total.
- **Buckets have no target.** Summing twelve targets into a "push target" would put a
  number on screen that nobody has studied; same reasoning as regions below.
- **One definition, two consumers.** `scheme_map()` serialises the schemes and
  `views.summary_page` passes them into `initSummary`, so the JS never restates the split.
- **The rows are rendered once and *moved*,** not duplicated or re-ordered with CSS
  `order`: nodes get re-appended in scheme order so a screen reader's reading order
  matches the screen. Bucket headings for all four schemes ship in the markup and the
  inactive ones are `hidden`.
- The choice persists in `localStorage` under `bodyshop:summary-scheme`, not in the URL —
  `?date=` is shared state every page honours, this is a reading preference.

### Regions: a second layer that is deliberately not graded

Six groups subdivide into regions (`MUSCLE_REGIONS`): chest, shoulders, back, triceps,
hamstrings and calves. The other six do not, and biceps heads and "upper vs. lower abs"
are excluded specifically — the evidence there is EMG rather than growth.

The asymmetry with muscle groups is the whole design:

| | Muscle group | Region |
| --- | --- | --- |
| Weekly target | Yes (`MUSCLE_TARGETS`) | **None** |
| `state` / `intensity` | Yes | **None** |
| Colour | The volume ramp | Achromatic — length only |
| Reports | Volume against a target | Share of the volume placed inside its parent |

Because no study has ever established how many weekly sets a muscle *head* needs. The
subdivisions are real — growth within a muscle is non-uniform and follows exercise
selection — but that supports a *distribution*, not a target, and a fabricated target
would sit on the summary page indistinguishable from the sourced ones. Full evidence and
the rules in [VOLUME_SCIENCE.md](VOLUME_SCIENCE.md).

Two consequences worth knowing before editing:

- **Attribution is partial by design.** `EXERCISE_REGIONS` maps a movement to a region
  only where the emphasis is defensible. A deadlift trains the back without saying
  anything about lats vs. mid back, so its volume is *unattributed*, and `region_sets`
  reports how much of the group's total could be placed. Shares are of `region_sets`,
  never of `sets` — otherwise unplaceable volume would read as neglect.
- **Import-time validation refuses to attribute a movement to a region whose parent
  muscle it does not train.** `_check_regions` raises `CatalogError`, which is what keeps
  a mapping slip from becoming a plausible-looking number on the summary page.

The only invented numbers are `REGION_NEGLECT_SHARE` (0.15) and
`REGION_NEGLECT_MIN_PARENT_SETS` (4.0, the literature's rough floor for a muscle
responding at all), both named constants in `services/summary.py` rather than literals, so
what is opinion stays visible.

## The volume scale

`app/services/summary.py::summarise_entries` produces, for each of the twelve groups
in `MUSCLE_GROUPS`:

```python
{"muscle": "chest", "label": "Chest", "worked": True, "sets": 12.0, "target": 20,
 "over": 0.0, "state": "trained", "intensity": 0.6,
 "exercises": ["Barbell Bench Press - Medium Grip"]}
```

`worked` is `True` as soon as a group receives any volume at all. Colour is a
*volume* scale on top of that, graded by `summary.py::grade`:

| Sets | `state` | `intensity` | Colour |
| --- | --- | --- | --- |
| 0 | `rest` | `0.0` | untrained grey |
| 1 … target | `trained` | `sets / target` | light green → dark green |
| target + 1 … | `over` | `over / (target // 2)`, clamped to 1 | light red → dark red |

`intensity` restarts at the bottom of the new ramp when a group crosses its target,
so the two scales are read independently — a group is never "dark green *and* faintly
red". Targets come from `exercises.py::MUSCLE_TARGETS`: 20 sets a week for the large
groups (chest, back, shoulders, quads, hamstrings, glutes) and 10 for the small ones
(abs, biceps, triceps, forearms, traps, calves), which recover on less volume.
Overshoot saturates at half the target, so one extra set is a visible step on either
scale.

The front-end does no grading of its own: `summary.js` writes `intensity` to a
`--level` custom property and toggles `.is-worked` / `.is-over` on every element with
the matching `data-muscle` attribute — SVG regions and breakdown rows alike. Colour
still lives entirely in CSS, which mixes between the ramp endpoints
(`--train-light`/`--train-dark`, `--over-light`/`--over-dark`) with `color-mix`.

### Weighted sets

A set counts once per muscle group it targets, but **not at the same weight**. The
group's share depends on how directly the movement trains it:

| Role | Weight | Example: 3 sets of barbell bench press |
| --- | --- | --- |
| `primary` | 1.0 | chest +3 |
| `secondary` | 0.5 | shoulders +1.5, triceps +1.5 |

Counting secondaries in full would inflate every accessory group — pressing alone
would fill the triceps target twice over — and ignoring them entirely would
under-report real work. Totals are therefore floats; `format_sets()` in
`exercises.py` and `formatSets()` in `ui.js` render them (`12.5`, but `12` not
`12.0`). The schema is untouched: `sets` is still an integer column storing whole
sets performed, and only the per-muscle aggregate is fractional.

The page answers "how much work did this muscle get", not "how many sets did I
perform" — `total_sets` in the weekly payload still answers the latter.

### What does not count

The catalog carries 123 stretches, 61 plyometrics and 14 cardio entries alongside
581 strength movements. Only categories in `exercises.py::VOLUME_CATEGORIES` —
`strength`, `powerlifting`, `olympic weightlifting`, `strongman` — contribute
volume. Everything else is loggable but grades as zero and never marks a group
`worked`, because a hamstring stretch shading the hamstrings green would be a lie
about what the week contained. `/log` labels the excluded ones on selection rather
than letting the omission be silent.

## The body map

`app/templates/partials/_body_figure.html` is a Jinja macro rendered twice per page, as
`figure("front")` and `figure("back")`. Region geometry is held as data (slug, element
id, path) at the top of the partial and rendered by a single loop, so adding a group is
one row.

The macro takes an optional `demo` argument mapping muscle → `(state, level)`, which
bakes the grading into the markup as classes and an inline `--level`. That exists for
surfaces with no JavaScript: the home page uses it to show an illustrative week instead
of an empty silhouette. `/summary` passes nothing, so `summary.js` owns every region's
state there — `tests/test_pages.py` asserts both halves of that split.

The two views draw **disjoint** sets of muscle groups, so each figure carries
information the other does not:

| View | Groups | Drawn as |
| --- | --- | --- |
| Front | `chest`, `abs`, `shoulders`, `biceps`, `forearms`, `quads` | two pectorals split at the sternum; upper and lower abdominal blocks; deltoid caps; upper arms; lower arms; thighs |
| Back | `back`, `traps`, `triceps`, `glutes`, `hamstrings`, `calves` | a tapering lat sheet; the trapezius yoke above it; upper arms; two glute blocks; thighs; lower legs |

`.body-base` draws a *complete* silhouette — head, neck, torso, deltoid caps, arms,
full legs, forearms, hands, feet — and muscle regions are painted on top of it. That
is why a group can be several paths with anatomical gaps between them (sternum, ribs,
obliques, lower back, shins) without leaving holes in the outline.

Because a group is selected by `data-muscle` rather than by id, all of its paths
light up together — the two pectorals, or both thighs.

**Regions within a view must not overlap.** They are painted in document order, so
an overlap lets the later group's colour hide the earlier one's, and the map then
misreports volume. The glutes stop at `y=232` and the hamstrings start at `y=242`
for exactly this reason; the bare silhouette between them reads as the crease.

Adding a muscle group means adding a path with the right `data-muscle` slug to the
appropriate view; no JavaScript changes are needed. `shoulders` was the exception —
the torso met the upper arms at a bare corner, so `.body-base` needed deltoid caps
before there was anything to overlay.

## Data model

One table, defined in [`app/tables.py`](../app/tables.py). Entries are append-only
rows; there is no per-day "workout" record, which keeps logging a single insert
and makes range queries trivial.

```sql
workout_entry(id, entry_date DATE, exercise_id TEXT, sets INTEGER, created_at TIMESTAMPTZ)
```

`entry_date` was TEXT until Phase 3. On SQLite the stored form is still
`'YYYY-MM-DD'` — SQLite has no date type, so a `DATE` column is a declaration over
the same text — which means the lexicographic `BETWEEN` that range queries rely on
is still a correct chronological comparison. On Postgres it is a real date. Either
way `models.py` passes and receives `datetime.date`, and converts to ISO-8601
strings at its edge.

### Migrations

`app/tables.py` says what the schema *is*; `migrations/versions/` is how a
database gets there. The two can disagree — editing the metadata changes no
existing database — so `tests/test_migrations.py` compares them using Alembic's
own autogenerate diff and fails if a revision is missing.

| Revision | Does |
| --- | --- |
| `0001` | The schema as the original hand-written `schema.sql` built it. A database predating Alembic is `stamp-db 0001`'d onto the chain rather than rebuilt. |
| `0002` | Moves the four pre-Phase-2 exercise ids onto the catalog. Replaced the `remap-exercises` command. |
| `0003` | `entry_date` → `DATE`, `created_at` → `TIMESTAMPTZ`. |

`0003` is worth reading before writing another type change. It **cannot** use
Alembic's `batch_alter_table`: `SQLiteImpl.cast_for_batch_migrate` adds a `CAST` to
its table-copy whenever type affinity changes, and SQLite resolves
`CAST('2026-07-28' AS DATE)` as `CAST(… AS NUMERIC)`, which prefix-parses to the
integer `2026`. It branches by dialect instead — Postgres converts with `USING`,
SQLite re-declares the columns and copies the values untouched, because the values
are already in the form a `DATE` column reads back.

## Dates and time zones

The backend never converts time zones. The browser sends `YYYY-MM-DD` strings that
the user picked, and gets the same strings back. `app/static/js/ui.js` deliberately
parses those with `new Date(y, m - 1, d)` rather than `new Date(iso)` — the latter
parses as UTC and can shift a day backwards for users west of Greenwich.

Weeks start Monday (ISO), configurable via `BODYSHOP_WEEK_STARTS_ON`.

## Testing strategy

- `tests/test_weeks.py` — boundary maths, no app needed.
- `tests/test_exercises.py` — the catalog's contract: known slugs, unique ids, two
  frames each, no muscle both primary and secondary, the volume weights, and the
  ranking's invariants (every staple id resolves, the tiers do not interleave, every
  muscle group has a staple).
- `tests/test_summary.py` — the muscle-coverage and volume-grading rules, both as
  pure functions and through the database, plus the region distribution: that regions
  carry no target or grade, that unplaceable volume is reported rather than spread, and
  that a balanced week flags nothing.
- `tests/test_models.py` — the data layer's non-API surface: the retired-id remap and
  the recent-exercise query.
- `tests/test_api.py` — every endpoint, including the validation failure modes.
- `tests/test_pages.py` — the four pages render and contain every muscle region, and
  `/log` ships a picker shell rather than the catalog. Page markers are chosen to be
  unique to their page, since the nav links appear on all four.
- `tests/test_migrations.py` — that the migration chain builds exactly what
  `tables.py` describes, that the data migration moves every retired id, that the
  `DATE` conversion preserves real dates, and that the chain downgrades.
- `tests/test_config.py` — URL normalisation, and that production refuses to boot on
  a placeholder secret or a SQLite database.

Each test gets a fresh SQLite file in pytest's `tmp_path`, so tests are isolated and
run in any order.

Setting `BODYSHOP_TEST_DATABASE_URL` runs the same suite against a real Postgres
instead, where the schema is built by the migrations rather than from the metadata —
so that run also verifies the migration chain on the dialect it matters on. CI does
this on a `postgres:16` service container. Isolation there is a `TRUNCATE` between
tests rather than a fresh database: one round trip instead of a schema rebuild,
which is the difference between seconds and minutes against a hosted database.

## Deliberate limitations

- **Single user.** There is no auth and no `user_id` column; the database is
  whoever's machine it runs on. Adding accounts means a `user` table and a foreign
  key on `workout_entry`.
- **No connection pooling of our own on Postgres.** `NullPool` is deliberate: both
  Supabase and Neon put a pooler in front, and a second pool inside a serverless
  function exhausts connection limits at trivial traffic. Under a long-lived
  process (gunicorn) this trades a little latency for that safety.
- **Sets only.** No weight or reps — `workout_entry` stores a bare count, so 3 sets at
  60kg and 3 sets at 140kg are the same row. This blocks 1RM estimates, PR detection,
  progress graphs and plate calculators, and is scheduled as
  [Phase 4](ROADMAP.md) rather than a to-do.
- **One `shoulders` group.** The catalog distinguishes front, side and rear raises in
  its facets, but the map shades a single deltoid region. Splitting into three is a
  data change plus SVG paths, not a re-model — see [ROADMAP.md](ROADMAP.md).
- **The secondary weight is a guess.** 0.5 is defensible and uniform, but it is one
  number standing in for a spectrum: the triceps' share of a close-grip press is not
  the calves' share of a squat. Per-exercise weights are possible once there is any
  evidence for them.
- **Images depend on a third party.** jsDelivr serving free-exercise-db at a pinned
  commit is free and fast, but it is not our origin. `EXERCISE_IMAGE_BASE` exists so
  that self-hosting is a config change rather than a rewrite.
