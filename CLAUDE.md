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
gunicorn "wsgi:application"           # production entry point — NB: gunicorn is not in requirements.txt, install it separately
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs `pytest -q` on Python 3.10–3.13, then boots the app via `create_app("testing")` and asserts `GET /` returns 200. There is no linter or formatter configured.

## Read-before-edit protocol

The docs in this repo are specifications, not summaries — they state *why* the code is shaped as it is, and several of them describe decisions the roadmap deliberately reverses. Read the relevant one **before** touching the surface it covers, and update it **in the same commit** as the change. Never open a code file for one of these tasks without opening its doc first.

| If the task is… | Read first | Then update |
| --- | --- | --- |
| Anything naming a phase ("implement Phase 1", "start the Tailwind work", "add the exercise catalog") | [docs/ROADMAP.md](docs/ROADMAP.md) — that phase **and** its dependencies in the graph | The phase section, if the work revealed the plan was wrong |
| Adding/removing/renaming an endpoint, or changing a request or response field | [docs/API.md](docs/API.md) | [docs/API.md](docs/API.md) — payload examples are exhaustive, not illustrative |
| Moving logic between layers, adding a module under `app/`, or changing what a layer owns | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — the layer-ownership table | The table, plus the Architecture section here |
| Adding an exercise, a muscle group, or changing grading/targets | [app/exercises.py](app/exercises.py), then the volume-scale and body-map sections of [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | [docs/API.md](docs/API.md) (slug list + summary payload) and the invariants below |
| Editing the SVG body map | The header comment in [app/templates/partials/_body_figure.html](app/templates/partials/_body_figure.html) — it documents which gaps are deliberate | That comment, plus the body-map table in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Schema changes | [app/schema.sql](app/schema.sql) and the Phase 3 notes in [docs/ROADMAP.md](docs/ROADMAP.md) | Data-model sections in both docs |
| Anything about commits, branches, or pushing | The Git and GitHub section below | — |

Two standing rules that fall out of this:

- **The roadmap outranks the invariants below.** Phases 1–4 each reverse something stated here as a rule (no build step, 7 muscle groups, one flat set count, no `user_id`). Before defending an invariant, check whether the current phase is supposed to be breaking it — and when you do break one, edit this file in the same change rather than leaving both statements standing.
- **A doc that contradicts the code is a bug.** If you find one while working, fix it or say so explicitly; don't quietly code around it.

## Architecture

Flask + vanilla ES modules, no build step, no JS dependencies. Layers, strictly one-directional:

`app/api.py` (HTTP parsing/status codes) → `app/services/` (rules) → `app/models.py` (all SQL) → SQLite.

[app/views.py](app/views.py) renders three server-side shells (`/`, `/log`, `/summary`); everything dynamic is fetched by the page's JS module from the same `/api` the tests exercise, so the HTML can't diverge from the API. Each page's JS module pairs with a template of the same name; [app/static/js/api.js](app/static/js/api.js) is the only place `fetch` is called.

Full layer-ownership table and rationale live in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); endpoint reference in [docs/API.md](docs/API.md) — keep both updated when changing those surfaces. Planned direction is specified in phase order in [docs/ROADMAP.md](docs/ROADMAP.md): Tailwind/DaisyUI, a ~180-exercise catalog, Postgres + migrations, **per-set weight and reps**, auth, Vercel, routines and progress tracking, AI-assisted custom exercises, images, then mobile/watch/app-store — plus post-launch candidates (auto-progression, social, nutrition, recovery) that are parked with reasons. Several phases deliberately reverse invariants below (Tailwind ends the no-build-step rule; Phase 4 replaces the flat `sets` count), so check it before assuming a constraint still holds.

### Invariants worth knowing before editing

- **SQL only in [app/models.py](app/models.py).** Services and routes never touch `get_db()`.
- **[app/exercises.py](app/exercises.py) is the single source of truth.** `EXERCISES` drives the `/log` radio buttons, `validate_entry`'s accept-list, and summary aggregation simultaneously. Adding a movement is one line there. A *new muscle group* additionally needs entries in `MUSCLE_GROUPS`/`MUSCLE_LABELS` and an SVG path with a matching `data-muscle` slug in [app/templates/partials/_body_figure.html](app/templates/partials/_body_figure.html) — no JS changes.
- **The front and back figures show disjoint muscle groups** — front: chest, abs, biceps, quads; back: back, triceps, hamstrings. `.body-base` draws a complete silhouette and muscle regions overlay it, so a group can be several paths with anatomical gaps between them (they light up together, since selection is on `data-muscle`, not id). Squat targets both `quads` and `hamstrings` until a hinge movement exists to separate them.
- **Dates are ISO-8601 strings end to end.** Stored as TEXT so SQLite's lexicographic `BETWEEN` is chronologically correct, and passed to JSON unconverted. The backend never does time-zone conversion. In JS, parse with `new Date(y, m - 1, d)`, never `new Date(iso)` — the latter is UTC and shifts the day backwards west of Greenwich ([app/static/js/ui.js](app/static/js/ui.js)).
- **A set counts once per muscle group it targets.** 3 sets of bench press add 3 to *both* chest and triceps; `worked` flips true at one set.
- **Colour is a volume scale, graded server-side.** `grade()` in [app/services/summary.py](app/services/summary.py) maps sets against the group's weekly `MUSCLE_TARGETS` value (20 large / 10 small) to a `state` (`rest`/`trained`/`over`) plus an `intensity` 0–1 *within that state's ramp* — green light→dark up to target, then red light→dark across the next `target // 2` sets. The front end grades nothing: `summary.js` writes `intensity` to a `--level` custom property and toggles `.is-worked`/`.is-over`; CSS mixes between `--train-light`/`--train-dark` and `--over-light`/`--over-dark` with `color-mix`. `.is-over` must stay after `.is-worked` in the stylesheet — an over-target group carries both classes.
- **All three pages share `?date=YYYY-MM-DD`,** so navigation preserves the day being viewed.
- **One append-only table** (`workout_entry`), no `user_id`, no auth, no migrations. Schema changes currently mean re-running `init-db`.

## Conventions

- Python: type hints on signatures, `from __future__ import annotations` at module top, docstrings on public functions.
- JS: ES modules, zero dependencies — keep it that way.
- CSS: use the design tokens at the top of `styles.css` rather than new hex values.
- Tests: each gets a fresh SQLite file in `tmp_path` via the `app`/`client`/`add` fixtures in [tests/conftest.py](tests/conftest.py), so order never matters.

## Git and GitHub

**Claude drives git in this repo** — branching, committing, pulling and pushing. Don't hand the user a command to run when you can run it; don't ask them to write a commit message.

- **Commit messages:** present tense, one logical change per commit ([CONTRIBUTING.md](CONTRIBUTING.md)). The subject line says what changed; the body says *why*, and is worth writing whenever the reasoning isn't obvious from the diff.
- **Never add attribution trailers.** No `Co-Authored-By:`, no "Generated with" footers — GitHub renders co-authors as contributors on the PR, and the user does not want that.
- **Work directly on `main`.** Justin asked for this on 2026-07-29; don't create a feature branch or open a PR unless he asks for one.
- **Run the suite before committing.** CI only runs `pytest -q`, so a green local run is the whole signal.
- **`gh` is not installed**, so PRs, issues and reviews cannot be created from here — say so rather than improvising, and offer `brew install gh` (macOS) or `winget install --id GitHub.cli` (Windows). Plain `git` works normally; `origin` is set.
- Rewriting published history needs the user's approval — the permission rules block it by default.
