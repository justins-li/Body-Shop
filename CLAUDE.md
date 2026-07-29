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

CSS only, and only when editing [app/static/css/input.css](app/static/css/input.css):

```bash
python tools/fetch_css_toolchain.py   # once — downloads Tailwind CLI + daisyUI into tools/
tools/tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --minify
tools/tailwindcss ... --watch          # while working
```

CI ([.github/workflows/ci.yml](.github/workflows/ci.yml)) runs `pytest -q` on Python 3.10–3.13, then boots the app via `create_app("testing")` and asserts `GET /` returns 200. There is no linter or formatter configured, and **CI does not build CSS** — the compiled stylesheet is committed.

## Architecture

Flask + vanilla ES modules; Tailwind v4 + daisyUI for styling. Layers, strictly one-directional:

`app/api.py` (HTTP parsing/status codes) → `app/services/` (rules) → `app/models.py` (all SQL) → SQLite.

[app/views.py](app/views.py) renders four server-side shells (`/`, `/calendar`, `/log`, `/summary`); everything dynamic is fetched by the page's JS module from the same `/api` the tests exercise, so the HTML can't diverge from the API. Each page's JS module pairs with a template of the same name; [app/static/js/api.js](app/static/js/api.js) is the only place `fetch` is called. `/` is the exception — a static landing page with no JS module and no API calls.

Full layer-ownership table and rationale live in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md); endpoint reference in [docs/API.md](docs/API.md) — keep both updated when changing those surfaces. Planned direction is specified in phase order in [docs/ROADMAP.md](docs/ROADMAP.md) — Tailwind/DaisyUI, a ~180-exercise catalog, Postgres, auth, Vercel, AI-assisted custom exercises, then mobile/app-store distribution. Several phases deliberately reverse invariants below (Tailwind ends the no-build-step rule), so check it before assuming a constraint still holds.

### Invariants worth knowing before editing

- **The stylesheet is compiled. [app/static/css/input.css](app/static/css/input.css) is the source; `styles.css` is build output — editing it loses your work on the next build.** Both are committed, so running the app never needs the toolchain; only editing CSS does. The toolchain is npm-free by design: Tailwind ships a standalone binary and daisyUI is a tarball of CSS, both fetched into gitignored `tools/` by `tools/fetch_css_toolchain.py`. Do not add a `package.json` — the fetch script pins both versions.
- **Tailwind is v4, so config is CSS-first.** There is no `tailwind.config.js`; the theme lives in `@theme` and two `@plugin "daisyui/theme"` blocks inside `input.css`. Content globs are `@source` directives there, with `source(none)` disabling auto-detection — a new template directory needs a new `@source` line or its classes get purged.
- **Two hand-written daisyUI themes, `bodyshop` (default, light) and `bodyshop-dark` (`prefersdark`).** All 35 stock themes are off. The palette is deliberately achromatic — cream `#fff8ed`, warm ink `#312726`, warm grey `#7a716e` — so *the volume ramp is the only saturated colour in the app*. Don't introduce an accent hue; it competes with the heatmap for attention.
- **Static structure is utilities in templates; JS-toggled state is a named class in `input.css`'s `@layer components`.** Tailwind only sees classes it can read as literal text, so a class built by interpolation (`` `is-${state}` ``) is silently purged. Rather than safelisting, every runtime-toggled class (`.is-worked`, `.is-over`, `.day-cell.is-selected`, `.toast-bar.is-visible`) is hand-written CSS. The colour mixing has to stay hand-written regardless — see below.
- **Don't put `<figure>` inside a daisyUI `card` without `flex-col`.** daisyUI sets `.card figure { display: flex }` with no direction, which lays a figcaption out *beside* its figure. The body-map macro passes `flex flex-col` for this reason.
- **SQL only in [app/models.py](app/models.py).** Services and routes never touch `get_db()`.
- **[app/exercises.py](app/exercises.py) is the single source of truth.** `EXERCISES` drives the `/log` radio buttons, `validate_entry`'s accept-list, and summary aggregation simultaneously. Adding a movement is one line there. A *new muscle group* additionally needs entries in `MUSCLE_GROUPS`/`MUSCLE_LABELS` and an SVG path with a matching `data-muscle` slug in [app/templates/partials/_body_figure.html](app/templates/partials/_body_figure.html) — no JS changes.
- **The front and back figures show disjoint muscle groups** — front: chest, abs, biceps, quads; back: back, triceps, hamstrings. `.body-base` draws a complete silhouette and muscle regions overlay it, so a group can be several paths with anatomical gaps between them (they light up together, since selection is on `data-muscle`, not id). Squat targets both `quads` and `hamstrings` until a hinge movement exists to separate them.
- **Dates are ISO-8601 strings end to end.** Stored as TEXT so SQLite's lexicographic `BETWEEN` is chronologically correct, and passed to JSON unconverted. The backend never does time-zone conversion. In JS, parse with `new Date(y, m - 1, d)`, never `new Date(iso)` — the latter is UTC and shifts the day backwards west of Greenwich ([app/static/js/ui.js](app/static/js/ui.js)).
- **A set counts once per muscle group it targets.** 3 sets of bench press add 3 to *both* chest and triceps; `worked` flips true at one set.
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
- **`gh` is not installed**, so PRs, issues and reviews cannot be created from here — say so rather than improvising, and offer `winget install --id GitHub.cli`. Plain `git` works normally; `origin` is set.
- Rewriting published history needs the user's approval — the permission rules block it by default.
