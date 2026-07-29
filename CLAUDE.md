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
gunicorn "wsgi:application"           # production entry point
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs `pytest -q` on Python 3.10–3.13, then boots the app via `create_app("testing")` and asserts `GET /` returns 200. There is no linter or formatter configured.

## Architecture

Flask + vanilla ES modules, no build step, no JS dependencies. Layers, strictly one-directional:

`app/api.py` (HTTP parsing/status codes) → `app/services/` (rules) → `app/models.py` (all SQL) → SQLite.

[app/views.py](app/views.py) renders three server-side shells (`/`, `/log`, `/summary`); everything dynamic is fetched by the page's JS module from the same `/api` the tests exercise, so the HTML can't diverge from the API. Each page's JS module pairs with a template of the same name; [app/static/js/api.js](app/static/js/api.js) is the only place `fetch` is called.

Full layer-ownership table and rationale live in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); endpoint reference in [docs/API.md](docs/API.md) — keep both updated when changing those surfaces.

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
