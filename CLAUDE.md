# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Keep this file current.** If work in this repo contradicts something below, or establishes a new invariant, command, or convention that a future session would otherwise have to rediscover, update the relevant section as part of that change. Prefer editing an existing line over appending a new one, and delete guidance that has stopped being true — a stale CLAUDE.md is worse than a short one.

## Commands

```bash
pip install -r requirements-dev.txt   # runtime + pytest
python run.py                         # dev server on 127.0.0.1:5000
pytest                                # full suite (quiet mode via pyproject addopts)
pytest tests/test_api.py::test_name    # single test
flask --app app init-db               # drop and recreate the schema (destroys data)
flask --app app remap-exercises       # one-off: move pre-Phase-2 exercise ids onto the catalog
gunicorn "wsgi:application"           # production entry point — NB: gunicorn is not in requirements.txt, install it separately
```

Exercise catalog, only when changing the pinned source or the muscle mapping:

```bash
python tools/build_exercise_catalog.py   # regenerates the committed app/data/exercises.json
```

CSS only, and only when editing [app/static/css/input.css](app/static/css/input.css):

```bash
python tools/fetch_css_toolchain.py   # once — downloads Tailwind CLI + daisyUI into tools/
tools/tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --minify
tools/tailwindcss ... --watch          # while working
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs `pytest -q` on Python 3.10–3.13, then boots the app via `create_app("testing")` and asserts `GET /` returns 200. There is no linter or formatter configured, and **CI does not build CSS** — the compiled stylesheet is committed.

## Read-before-edit protocol

The docs in this repo are specifications, not summaries — they state *why* the code is shaped as it is, and several of them describe decisions the roadmap deliberately reverses. Read the relevant one **before** touching the surface it covers, and update it **in the same commit** as the change. Never open a code file for one of these tasks without opening its doc first.

| If the task is… | Read first | Then update |
| --- | --- | --- |
| Anything naming a phase ("implement Phase 1", "start the Tailwind work", "add the exercise catalog") | [docs/ROADMAP.md](docs/ROADMAP.md) — that phase **and** its dependencies in the graph | The phase section, if the work revealed the plan was wrong |
| Adding/removing/renaming an endpoint, or changing a request or response field | [docs/API.md](docs/API.md) | [docs/API.md](docs/API.md) — payload examples are exhaustive, not illustrative |
| Moving logic between layers, adding a module under `app/`, or changing what a layer owns | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — the layer-ownership table | The table, plus the Architecture section here |
| Adding an exercise, a muscle group, or changing grading/targets | [app/exercises.py](app/exercises.py) and [tools/build_exercise_catalog.py](tools/build_exercise_catalog.py), then the volume-scale and body-map sections of [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | [docs/API.md](docs/API.md) (slug list + summary payload) and the invariants below |
| **Anything touching a set target, a muscle *region*/head, the primary/secondary weights, or user-facing copy about how much to train** | [docs/VOLUME_SCIENCE.md](docs/VOLUME_SCIENCE.md) — the evidence, what is convention vs. finding, and the product-voice rules. Several obvious-seeming changes are ruled out there with reasons | That file, if the evidence base moved |
| Editing the SVG body map | The header comment in [app/templates/partials/_body_figure.html](app/templates/partials/_body_figure.html) — it documents which gaps are deliberate and which regions must not overlap | That comment, plus the body-map table in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Schema changes | [app/schema.sql](app/schema.sql) and the Phase 3 notes in [docs/ROADMAP.md](docs/ROADMAP.md) | Data-model sections in both docs |
| Anything about commits, branches, or pushing | The Git and GitHub section below | — |

Two standing rules that fall out of this:

- **The roadmap outranks the invariants below.** Phases 1, 2, 4 and 5 each reverse something stated here as a rule — Phase 1 ended the no-build-step rule, Phase 2 replaced 7 muscle groups with 12 and the flat set count with weighted primary/secondary, Phase 4 replaces the `sets` column, Phase 5 adds `user_id`. Before defending an invariant, check whether the current phase is supposed to be breaking it — and when you do break one, edit this file in the same change rather than leaving both statements standing.
- **A doc that contradicts the code is a bug.** If you find one while working, fix it or say so explicitly; don't quietly code around it.

## Architecture

Flask + vanilla ES modules; Tailwind v4 + daisyUI for styling. Layers, strictly one-directional:

`app/api.py` (HTTP parsing/status codes) → `app/services/` (rules) → `app/models.py` (all SQL) → SQLite.

[app/views.py](app/views.py) renders four server-side shells (`/`, `/calendar`, `/log`, `/summary`); everything dynamic is fetched by the page's JS module from the same `/api` the tests exercise, so the HTML can't diverge from the API. Each page's JS module pairs with a template of the same name; [app/static/js/api.js](app/static/js/api.js) is the only place `fetch` is called. `/` is the exception — a static landing page with no JS module and no API calls.

Full layer-ownership table and rationale live in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); endpoint reference in [docs/API.md](docs/API.md) — keep both updated when changing those surfaces. Planned direction is specified in phase order in [docs/ROADMAP.md](docs/ROADMAP.md): Postgres + migrations, **per-set weight and reps**, auth, Vercel, routines and progress tracking, AI-assisted custom exercises, then mobile/watch/app-store — plus post-launch candidates (auto-progression, social, nutrition, recovery) that are parked with reasons. Phases 1 (Tailwind/daisyUI) and 2 (873-exercise catalog, 12 muscle groups) are done; Phase 9 (images) landed inside Phase 2 with the catalog. Several remaining phases deliberately reverse invariants below (Phase 4 replaces the flat `sets` count), so check it before assuming a constraint still holds.

### Invariants worth knowing before editing

- **The stylesheet is compiled. [app/static/css/input.css](app/static/css/input.css) is the source; `styles.css` is build output — editing it loses your work on the next build.** Both are committed, so running the app never needs the toolchain; only editing CSS does. The toolchain is npm-free by design: Tailwind ships a standalone binary and daisyUI is a tarball of CSS, both fetched into gitignored `tools/` by `tools/fetch_css_toolchain.py`. Do not add a `package.json` — the fetch script pins both versions.
- **Tailwind is v4, so config is CSS-first.** There is no `tailwind.config.js`; the theme lives in `@theme` and two `@plugin "daisyui/theme"` blocks inside `input.css`. Content globs are `@source` directives there, with `source(none)` disabling auto-detection — a new template directory needs a new `@source` line or its classes get purged.
- **Two hand-written daisyUI themes, `bodyshop` (default, light) and `bodyshop-dark` (`prefersdark`).** All 35 stock themes are off. The palette is deliberately achromatic — cream `#fff8ed`, warm ink `#312726`, warm grey `#7a716e` — so *the volume ramp is the only saturated colour in the app*. Don't introduce an accent hue; it competes with the heatmap for attention.
- **Static structure is utilities in templates; JS-toggled state is a named class in `input.css`'s `@layer components`.** Tailwind only sees classes it can read as literal text, so a class built by interpolation (`` `is-${state}` ``) is silently purged. Rather than safelisting, every runtime-toggled class (`.is-worked`, `.is-over`, `.day-cell.is-selected`, `.toast-bar.is-visible`) is hand-written CSS. The colour mixing has to stay hand-written regardless — see below.
- **Don't put `<figure>` inside a daisyUI `card` without `flex-col`.** daisyUI sets `.card figure { display: flex }` with no direction, which lays a figcaption out *beside* its figure. The body-map macro passes `flex flex-col` for this reason.
- **SQL only in [app/models.py](app/models.py).** Services and routes never touch `get_db()`.
- **[app/exercises.py](app/exercises.py) is the single source of truth, but the catalog is *data*.** `EXERCISES` drives the `/log` picker, `validate_entry`'s accept-list and summary aggregation simultaneously — but its 873 rows are loaded from [app/data/exercises.json](app/data/exercises.json), vendored from [free-exercise-db](https://github.com/yuhonas/free-exercise-db) (Unlicense) by `tools/build_exercise_catalog.py` at a pinned commit. **Never hand-edit the JSON**: change the pin or the mapping in the generator and re-run it. The loader validates at import (unique ids, known muscle slugs, non-empty `primary`, exactly two images) and raises `CatalogError` rather than returning a partial catalog.
- **A *new muscle group*** needs entries in `MUSCLE_GROUPS`/`MUSCLE_LABELS`/`MUSCLE_TARGETS`, a mapping in the generator's `MUSCLE_MAP`, and an SVG path with a matching `data-muscle` slug in [_body_figure.html](app/templates/partials/_body_figure.html) — no JS changes.
- **The front and back figures show disjoint muscle groups** — front: chest, abs, shoulders, biceps, forearms, quads; back: back, traps, triceps, glutes, hamstrings, calves. `.body-base` draws a complete silhouette and muscle regions overlay it, so a group can be several paths with anatomical gaps between them (they light up together, since selection is on `data-muscle`, not id). **Regions within a view must not overlap** — they paint in order, so an overlap hides one group's colour behind another's.
- **`/log` renders no exercises server-side.** At 873 movements the radio list is gone: `views.log_page` passes only a count, and `log.js` fetches `/api/exercises` once and drives the picker client-side. `GET /api/exercises` is deliberately the *light* shape (no instructions, no images); `GET /api/exercises/<id>` serves the rest.
- **The picker's three paths are not equals: Recent and Browse are tabs, search is an icon.** Search only works if you already know the name; browse is how you shop for a movement and the only path a new user can succeed on. Don't promote search back to a peer tab — and don't let browse fall back to alphabetical order, which is what made it useless before (chest opened with "Alternating Floor Press"; pushups, 70th of 147, sat past the row cap). Browse is indexed by muscle once at load, never re-scanned per keystroke, and its cap is a visible "Show all N", not a silent truncation.
- **Ordering is history, then `rank`, then name — never name first.** `Exercise.rank` (lower first) is *ours*, not the dataset's: `STAPLE_EXERCISE_IDS` in [app/exercises.py](app/exercises.py) is a curated list whose index *is* the rank, and everything else starts at `UNRANKED_RANK_BASE` ordered by `mechanic`/`level`/`equipment` with zero-volume categories last. The tiers must not interleave. It lives in code, not `exercises.json`, because the JSON is generated and never hand-edited — and every staple id is checked at import, so an upstream rename raises `CatalogError` instead of silently demoting a lift. `GET /api/exercises/recent` carries `uses` so a movement you actually log outranks one the staple list merely thinks is popular.
- **Dates are ISO-8601 strings end to end.** Stored as TEXT so SQLite's lexicographic `BETWEEN` is chronologically correct, and passed to JSON unconverted. The backend never does time-zone conversion. In JS, parse with `new Date(y, m - 1, d)`, never `new Date(iso)` — the latter is UTC and shifts the day backwards west of Greenwich ([app/static/js/ui.js](app/static/js/ui.js)).
- **Muscle *regions* are a distribution, never a grade.** Six groups subdivide (`MUSCLE_REGIONS`: chest, shoulders, back, triceps, hamstrings, calves); the other six don't, and biceps heads / "upper vs lower abs" are excluded on purpose — EMG, not hypertrophy data. **A region has no target, no `state`, no `intensity`, and never takes the volume ramp's colours**, because no study has ever established a weekly set target for a muscle head. Attribution is deliberately partial: a movement only maps to a region in `EXERCISE_REGIONS` when its emphasis is defensible, so a deadlift's back volume is *unattributed* rather than split, and `region_sets` reports how much could be placed. Shares are of `region_sets`, never of the group's total. Import-time validation rejects mapping a movement to a region whose parent muscle it doesn't train. Should regions ever get targets, they must **sum to the parent's**, never multiply it. All of this is argued in [docs/VOLUME_SCIENCE.md](docs/VOLUME_SCIENCE.md).
- **Product voice on volume: never print a range as advice.** No "aim for 10–20 sets", no per-head prescriptions. One target per group, and the app's purpose is *coverage* — every group and region inside a productive range, nothing skipped into a weak link, nothing hammered while its neighbours idle. Say "balanced"/"covered"/"in range", not "optimal"/"maximal", and don't make medical or injury claims.
- **`SECONDARY_WEIGHT = 0.5` is the best-evidenced number in the app** — Pelland et al. (2025) found the 0.5 "fractional" count of indirect sets fit 67 studies better than 1.0 or 0.0. `MUSCLE_TARGETS` (20/10), by contrast, is a defensible *convention*; tune it freely, but don't defend it as a finding.
- **Sets are weighted by how directly a movement trains a group, so per-muscle totals are floats.** A `primary` muscle takes the whole set, a `secondary` muscle half (`PRIMARY_WEIGHT` / `SECONDARY_WEIGHT`): 3 sets of bench press add 3 to chest and 1.5 to triceps and shoulders. `worked` flips true at any non-zero contribution. Render with `format_sets()` in Python or `formatSets()` in [ui.js](app/static/js/ui.js) — `12.5`, but `12` not `12.0`. `schema.sql` is unaffected; only the aggregate is fractional.
- **Movements outside `VOLUME_CATEGORIES` grade as zero.** The catalog carries stretches, cardio and plyometrics alongside strength work. They are loggable, but contribute no sets and never mark a group `worked` — a hamstring stretch must not shade the body map. `/log` says so on the chosen exercise rather than letting it be silent.
- **Exercise ids are free-exercise-db's** (`Barbell_Squat`, `Sit-Up`), not slugs we coin. The four hand-written ids that predate the catalog are listed in `RETIRED_EXERCISE_IDS` and migrated by `flask --app app remap-exercises`.
- **Colour is a volume scale, graded server-side.** `grade()` in [app/services/summary.py](app/services/summary.py) maps sets against the group's weekly `MUSCLE_TARGETS` value (20 large / 10 small) to a `state` (`rest`/`trained`/`over`) plus an `intensity` 0–1 *within that state's ramp* — green light→dark up to target, then red light→dark across the next `target // 2` sets. The front end grades nothing: `summary.js` writes `intensity` to a `--level` custom property and toggles `.is-worked`/`.is-over`; CSS mixes between `--color-train-light`/`--color-train-dark` and `--color-over-light`/`--color-over-dark` with `color-mix`. **This cannot become utilities** — `--level` is continuous, and quantising it into fixed classes visibly bands the gradient. `.is-over` must stay after `.is-worked` in the stylesheet — an over-target group carries both classes.
- **The body-map macro takes an optional `demo` argument** mapping muscle → `(state, level)`, which bakes grading into the markup for surfaces that run no JS. Only `/` uses it; `/summary` passes nothing so `summary.js` owns every region. Tests assert both halves of that split.
- **All four pages share `?date=YYYY-MM-DD`,** so navigation preserves the day being viewed.
- **One append-only table** (`workout_entry`), no `user_id`, no auth, no migrations. Schema changes currently mean re-running `init-db`.

## Conventions

- Python: type hints on signatures, `from __future__ import annotations` at module top, docstrings on public functions.
- JS: ES modules, zero dependencies — keep it that way. The build step is CSS-only; there is no bundler and JS is served as written.
- CSS: reach for a daisyUI component, then Tailwind utilities, then hand-written CSS in `input.css` — in that order. Never a raw hex value: use the theme's colours (`base-100/200/300`, `base-content`, `secondary`, `primary`) so both themes stay correct. Separation is a hairline border, not a shadow — `--depth`/`--noise` are 0 and nothing in the app casts one.
- Type: one family (Archivo, loaded from Google Fonts in `base.html`). The display voice is `.type-display` (wide via the variable width axis, tight tracking), micro-labels are `.type-label` (uppercase, wide tracking), body copy is `.type-lede`. Prefer those three over ad-hoc size/weight/tracking stacks.
- Tests: each gets a fresh SQLite file in `tmp_path` via the `app`/`client`/`add` fixtures in [tests/conftest.py](tests/conftest.py), so order never matters.

## Git and GitHub

**Claude drives git in this repo** — branching, committing, pulling and pushing. Don't hand the user a command to run when you can run it; don't ask them to write a commit message.

- **Commit messages:** present tense, one logical change per commit ([CONTRIBUTING.md](CONTRIBUTING.md)). The subject line says what changed; the body says *why*, and is worth writing whenever the reasoning isn't obvious from the diff.
- **Never add attribution trailers.** No `Co-Authored-By:`, no "Generated with" footers — GitHub renders co-authors as contributors on the PR, and the user does not want that.
- **Work directly on `main`.** Justin asked for this on 2026-07-29; don't create a feature branch or open a PR unless he asks for one.
- **Run the suite before committing.** CI only runs `pytest -q`, so a green local run is the whole signal.
- **`gh` is not installed**, so PRs, issues and reviews cannot be created from here — say so rather than improvising, and offer `brew install gh` (macOS) or `winget install --id GitHub.cli` (Windows). Plain `git` works normally; `origin` is set.
- Rewriting published history needs the user's approval — the permission rules block it by default.
