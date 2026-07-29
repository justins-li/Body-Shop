# Changelog

All notable changes to Body Shop are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Home page at `/`** — a static landing page with the hero, a pre-graded body map
  showing an illustrative week, a three-step explainer and the colour-scale key. It
  makes no API calls and loads no JS module.
- **Tailwind v4 + daisyUI**, with two hand-written themes: `bodyshop` (light, default)
  and `bodyshop-dark` (follows `prefers-color-scheme`). All 35 stock daisyUI themes are
  disabled. `app/static/css/input.css` is the new source of truth for styling; the
  compiled `styles.css` is committed so nothing at runtime or in CI needs the toolchain.
- `tools/fetch_css_toolchain.py`, which downloads a pinned Tailwind CLI binary and the
  daisyUI package into gitignored `tools/`. **No npm and no `package.json`** — Tailwind
  publishes a standalone binary and daisyUI is a tarball of CSS, so the build step is
  CSS-only and JavaScript is still served exactly as written.
- An optional `demo` argument on the body-map macro, mapping muscle → `(state, level)`,
  which bakes grading into the markup for pages that run no JavaScript.
- Weekly set targets per muscle group (`MUSCLE_TARGETS`): 20 for large groups
  (chest, back, quads, hamstrings), 10 for small ones (abs, biceps, triceps).
- `target`, `over`, `state` and `intensity` on every group in the weekly summary
  payload, plus `muscles_at_target` and `muscles_over` lists.
- `abs` as a tracked muscle group, drawn on the front figure as upper and lower
  abdominal blocks, plus a **Sit ups** exercise that targets it.

### Changed

- **The calendar moved from `/` to `/calendar`** to make room for the home page. All four
  pages still share `?date=YYYY-MM-DD`.
- Every page was redesigned against a warm, achromatic palette — cream `#fff8ed`, warm
  ink `#312726` — with hairline borders instead of shadows and one variable typeface
  (Archivo) whose width axis carries the display voice. The palette has no accent hue on
  purpose: the muscle heatmap is the only saturated colour in the app.
- The body-map partial now holds its region geometry as data and renders it in a single
  loop, rather than repeating one `<path>` block per region.
- The body map is now shaded by volume rather than filled a single red: light
  green at one set, deepening to dark green at the group's weekly target, then
  light-to-dark red across the next `target / 2` sets of overshoot.
- The breakdown bars scale against each group's target instead of the busiest
  group, read `12 / 20` rather than `12 sets`, and take the same colour as the
  body map.
- The front and back body maps now show disjoint muscle groups — front: chest,
  abs, biceps, quads; back: back, triceps, hamstrings — instead of mirroring the
  same regions.
- The chest is drawn as two pectorals split at the sternum, and the back as a
  trapezius plus a tapering lat sheet.
- `legs` is replaced by `quads` and `hamstrings`. **Squat** targets both for now,
  since the catalog has no hinge movement to separate them.
- `.body-base` draws a full silhouette beneath the muscle overlays, so untracked
  anatomy (sternum, obliques, glutes, lower back, shins) shows through as gaps.

### Fixed

- CI, which had failed on every run since the workflow was added. `pytest` aborted
  during collection with `ModuleNotFoundError: No module named 'app'` because
  `conftest.py` sits in `tests/`, so the repo root never reached `sys.path`.
  `pythonpath = ["."]` in `pyproject.toml` fixes both `pytest` and `python -m pytest`.

## [0.1.0] — 2026-07-28

First functional release.

### Added

- **Calendar page** (`/`) — month grid with a dot on every day that has logged
  sets, a side panel showing that day's entries, arrow-key day navigation and a
  "jump to today" shortcut.
- **Log page** (`/log`) — date picker, exercise selector (bench press, pull ups,
  squat) with the muscle groups each movement trains, a set stepper, and inline
  deletion of the day's entries.
- **Weekly summary page** (`/summary`) — front and back body outlines that fill
  red for every muscle group trained at least one set that week, a per-group set
  breakdown, and week-by-week navigation.
- JSON API under `/api` covering exercises, entries, calendar totals and the
  weekly summary — see [docs/API.md](docs/API.md).
- SQLite persistence with a `flask --app app init-db` reset command; the database
  is created automatically on first run.
- pytest suite covering week maths, muscle-coverage aggregation, every API
  endpoint and all three pages.
- GitHub Actions CI running the suite on Python 3.10–3.13.
