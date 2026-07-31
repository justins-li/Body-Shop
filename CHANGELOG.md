# Changelog

All notable changes to Body Shop are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **The whole front end is rebuilt against a reference design** (glukhovsky.com), and it
  is a deliberate reversal of Phase 4.5 rather than a restyle:
  - **The theme is light.** Warm cream `#faf4eb`, dark brown ink `#2a1c0e`, the same
    oxidised brick accent. Phase 4.5 had retired the light theme; this brings it back and
    removes the dark one, so there is still exactly one.
  - **The volume ramp was re-derived, not flipped.** A ramp has to climb in whichever
    direction reads as "more" on its own ground: dim → lit on near-black, pale → deep on
    cream. The binding constraint moves too — on cream a pale green sits too close to the
    untrained fill, so `--color-train-min` is now a mid-tone (`#4f9068`, 3.02:1 against
    `--color-rest`), which is what keeps "one set" distinguishable from "no sets".
  - **The top header is gone.** Navigation is thin vertical shelves down the sides, with
    the section name set sideways. The leftmost is always Home; the right stack is every
    section except the one being read, so a page never appears as a shelf beside itself.
  - **`/` is exactly one screen**, and enforced as one: `height: 100vh; overflow: hidden`,
    with the specimen as the only element that flexes, so the wordmark, the two actions
    and the follow row are always in view without scrolling.
  - **`/how-to-use` is a new chapter** holding the explainer that used to sit below the
    landing page — the sequence, the colour scale and the closing prompt. It became a
    shelf rather than a scroll nobody reached.
  - **The shelves split around the open chapter**: everything numbered before it stacks on
    the left, everything after on the right, each still in chapter order. Open chapter 03
    and Home, How to use and Calendar sit to the left, Weekly summary and Graph to the
    right — where they were before you opened anything.
  - **Every shelf carries a drawn mark**, and the chapter index sits directly above its
    sideways name. The stack is sticky at full window height, so the names track the middle
    of the screen while a long page scrolls past them.
  - **Chapter numbers are fixed to the section**, not to a shelf's position in the stack:
    Calendar is `02` whether it is the first shelf on screen or the third. A mark that
    renumbers itself by where you happen to be reading from is not one you can navigate by.
  - **Noto Serif 300 carries the identity** — wordmark, shelf names, headings — at the
    reference's measurements (`7.15vw`, `-0.21vw` tracking, `106%` leading). A fourth
    face, display use only.
  - The rotating subheading is a clipped strip with the lines translating up through it,
    matching the reference's motion rather than cross-fading.
  - A `.page-veil` covers the round trip when a shelf is clicked; pages are still
    server-rendered, so it covers a real request rather than decorating a fake one.
  - The rest timer moved from the header to a bottom-left dock. Same contract: every
    page, a persisted deadline rather than a count.

### Added

- **A dark, instrument-like interface (Phase 4.5).** The cream palette is gone and the
  light theme is retired rather than re-derived. Six colour tokens on a near-black
  blue-black ground, warm bone for data marks, cold slate for structure, and an oxidised
  brick red as the only accent. Three typefaces in four named voices — Big Shoulders
  Display for headings, IBM Plex Sans for copy, IBM Plex Mono for micro-labels and, new,
  for **every number in the app**, with tabular figures so digits don't shift width as
  they change. Cards give way to hairline-ruled bands on one continuous ground.
- **`/progress`, the training graph.** Every movement logged in a window drawn as a node
  on a canvas, joined to the movements done on the same day. Size is sets, colour is the
  current weekly coverage of its main muscle, and movements that have fallen out —
  logged under three times, or not in eight weeks — ring the outside as hollow circles
  and are listed by name beneath. Nothing is strength-relative: no bodyweight is stored
  and no 1RM computed, so a strength-standard colouring would be a guess (Phase 7). Time
  window switches between 8 weeks, 6 months and all time. Backed by one new read-only
  endpoint, `GET /api/progress/graph`.
- **A mobile bottom tab bar**, so the app is reachable one-handed. Logging a set is two
  taps from opening the app, and `/log`'s submit is docked in the thumb zone.

### Changed

- **The volume ramp climbs in luminance rather than darkening.** It ran pale-to-dark as
  volume rose, which reads correctly on cream and backwards on near-black, where a dark
  green is the least-lit thing on screen. `--color-train-light/dark` are now
  `--color-train-min/max`, since "dark" would otherwise name the bright end.
- **The rest timer survives navigation.** It lives in the shared header and persists a
  deadline rather than a remaining count, so rest keeps running while you look at the
  calendar and does not drift when the tab is backgrounded.
- **`/log`'s set row is two tiers.** Weight and reps lead at full tap size; RPE and set
  type sit on a quieter second tier with their own labels. Numeric fields raise the
  numeric keypad and select on focus, so overwriting a prefilled weight is one tap.
- **The calendar's day dot became a bar** whose height is the sets logged that day,
  against a fixed reference so two months can be compared.
- **The weekly summary leads with the body map**, and the week's figures became readout
  cells instead of a dot-separated sentence that wrapped to five lines on a phone.

### Fixed

- **The home page no longer claims an entry is "no weight, no reps"**, which Phase 4 made
  false, and the colour-scale legend no longer describes the ramp running the wrong way.
- **A group with one set is now distinguishable from an untrained one.** The trained
  ramp's dim end sat 1.80:1 against untrained, so "barely trained" and "not trained at
  all" looked alike — which defeats the coverage model the app is built on.
- **Crossing the target no longer depends on telling green from red.** The two ramps peak
  at similar brightness, which is what makes the crossing unmistakable to most eyes and
  nearly invisible under red-green colour blindness; over-target regions and graph nodes
  now also carry a heavier bone outline.

- **Alembic migrations.** `app/tables.py` describes the schema as SQLAlchemy metadata and
  `migrations/versions/` is how a database reaches it; `app/schema.sql` is gone. Three
  revisions: `0001` reproduces the old hand-written schema so an existing database can be
  `stamp-db 0001`'d onto the chain, `0002` moves the four pre-catalog exercise ids, and
  `0003` converts `entry_date` to a real `DATE`. New commands: `flask --app app upgrade-db`,
  `stamp-db`; plain `alembic` works too and reads the same `DATABASE_URL`.
- **Postgres support.** The data layer is SQLAlchemy Core, so the same `models.py` runs on
  SQLite locally and Postgres when `DATABASE_URL` is set. Provider strings are normalised,
  so Supabase's `postgres://` form works as pasted. Postgres connections use `NullPool` and
  disable prepared statements, which a transaction-mode pooler cannot carry.
- **A Postgres CI job**, running the same suite on a `postgres:16` service container and
  round-tripping the migration chain — the SQLite job cannot surface a dialect difference.
  Locally, `BODYSHOP_TEST_DATABASE_URL=... pytest` does the same thing.
- **Production configuration checks.** `create_app` raises `ConfigError` when production
  has a placeholder `SECRET_KEY` or a SQLite `DATABASE_URL`. The check reads the resolved
  config, so `instance/config.py` can satisfy it but not bypass it.
- `.env` support via `python-dotenv`, with a documented `.env.example`.
- **The weekly breakdown groups into a split you choose.** "Sets by muscle group" was
  twelve rows in body-map order; it is now "Sets by split", headed by **Push · Pull · Legs**
  (the default), **Upper · Lower**, **Front · Back** — the same split as the two figures —
  or **Every group** for the flat list. Each heading totals its sets. A scheme is a *view*,
  never a filter: every one files all twelve groups exactly once, enforced at import, so
  switching can only regroup volume, never hide it. Buckets carry no target, since a "push
  target" is a number nobody has studied. The choice is remembered per browser.
- **Muscle regions on the weekly summary.** Six groups — chest, shoulders, back, triceps,
  hamstrings and calves — break into 13 regions (upper vs. mid/lower chest, the three delt
  heads, lats vs. mid back, triceps long vs. lateral/medial, knee- vs. hip-dominant
  hamstrings, gastrocnemius vs. soleus) and report **where a group's volume landed**: each
  region's share of the sets that could be placed inside it, plus a flag when one is left
  thin. A shoulder week that was all pressing now reads as one instead of hiding in a
  total.
  **Regions carry no target, no state and none of the volume ramp's colours**, because no
  study has established how many weekly sets a muscle head needs — the subdivisions are
  a distribution, not a score. Attribution is partial on purpose: a deadlift trains the
  back without saying anything about lats vs. mid back, so its volume is left unattributed
  and `region_sets` reports how much could be placed. Import-time validation refuses to
  attribute a movement to a region whose parent muscle it does not train.
- **[docs/VOLUME_SCIENCE.md](docs/VOLUME_SCIENCE.md)** — the evidence behind every number
  in the volume model, which of them are sourced and which are convention, the rules that
  fall out (regions never get targets; targets partition rather than multiply), and the
  product-voice rules: never print a set range as advice, and frame the app around
  coverage rather than maximisation. Notably, Pelland et al. (2025) found that counting
  indirect sets at **0.5** fit 67 studies better than 1.0 or 0.0 — the weighting Body Shop
  already uses.
- `regions_neglected` on `GET /api/summary/week`, and `regions` / `region_sets` on every
  muscle group in the payload.

- **A popularity ranking, `rank`, on every exercise** — lower sorts first. free-exercise-db
  carries no popularity signal, so `STAPLE_EXERCISE_IDS` in `app/exercises.py` names ~130
  movements most lifters actually program, in order; everything else starts at
  `UNRANKED_RANK_BASE` and is ordered by `mechanic`, `level` and whether the equipment is
  gym-standard, with stretching, cardio and plyometrics last. The tiers never interleave.
  It lives in code rather than `exercises.json` because the catalog is generated from a
  pinned commit and never hand-edited, and every staple id is validated at import.
- **`uses` on `GET /api/exercises/recent`** — how many times each movement has been
  logged. `/log` fetches 50, lists 12, and ranks browse and search by the rest: a
  movement you have logged outranks one the staple list merely thinks is popular.
- **A "Show all N" footer on browse**, replacing a silent truncation, plus a line saying
  how much of the list is showing.
- **873 exercises, each with two photographs**, vendored from
  [free-exercise-db](https://github.com/yuhonas/free-exercise-db) (Unlicense, public
  domain) at a pinned commit. `app/data/exercises.json` is generated by
  `tools/build_exercise_catalog.py` and committed, so nothing at runtime or in CI needs
  the network; `app/exercises.py` validates it at import and refuses a catalog with
  duplicate ids, unknown muscle slugs, no primary muscle or the wrong number of images.
- **Five new muscle groups** — `shoulders`, `forearms`, `traps`, `glutes` and `calves` —
  taking the body map from 7 groups to 12. Front now draws chest, abs, shoulders,
  biceps, forearms and quads; back draws back, traps, triceps, glutes, hamstrings and
  calves. `.body-base` gained deltoid caps, since the torso previously met the arms at a
  bare corner with no shoulder to overlay.
- **Weighted set counting.** A movement's `primary` muscles take a whole set and its
  `secondary` muscles half, so 3 sets of bench press give chest 3 and shoulders and
  triceps 1.5 each. Per-group totals are now fractional and render as `12.5 / 20`.
- **An exercise picker on `/log`** with three ways in: recent (from entry history),
  search over name, equipment and muscles, and browse by muscle group then equipment.
  Search understands gym shorthand, so `incl db` finds "Dumbbell Incline Bench Press".
  The chosen movement shows its two frames cross-fading into a short loop, plus its
  instructions.
- `GET /api/exercises/<id>` for one exercise in full (instructions and absolute image
  URLs) and `GET /api/exercises/recent` for the picker's default tab.
- `BODYSHOP_EXERCISE_IMAGE_BASE`, defaulting to jsDelivr pinned to the catalog's source
  commit. The 1,746 images are ~85 MB and deliberately not in the repo; point this
  elsewhere to self-host.
- Migration of entries logged against the four retired ids (`squat`, `bench_press`,
  `pull_ups`, `sit_ups`) onto their catalog equivalents. This shipped first as a
  `remap-exercises` command and is now Alembic revision `0002`, so it happens as part of
  migrating. Idempotent either way.
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
  (chest, back, shoulders, quads, hamstrings, glutes), 10 for small ones (abs, biceps,
  triceps, forearms, traps, calves).
- `target`, `over`, `state` and `intensity` on every group in the weekly summary
  payload, plus `muscles_at_target` and `muscles_over` lists.
- `abs` as a tracked muscle group, drawn on the front figure as upper and lower
  abdominal blocks.

### Changed

- **Home and summary copy now lead with coverage rather than volume.** The app's purpose
  is keeping every group — and every region of the six that subdivide — inside a
  productive range: nothing skipped long enough to become a weak link, nothing hammered
  while its neighbours idle. The home page's third stat is the region count in place of
  the raw targets, and step 02 explains the half-weight for assisting muscles.
- **The `/log` picker leads with Recent and Browse; search is now an icon.** Three equal
  tabs implied search was the way in, but searching a catalog nobody has memorised only
  works if you already know the name. Browse is how you shop for a movement and the only
  path a first-time user can succeed on, so it keeps a labelled tab and search collapses
  to a magnifier. With nothing logged yet, the picker opens on Browse.
- **Browse is ordered by usefulness instead of the alphabet.** It sorted alphabetically
  and truncated at 40 rows, so chest opened with "Alternating Floor Press" and pushups —
  70th of 147 — could not be reached by browsing at all. Order is now primary muscle,
  then your own logging history, then `rank`, with name only as a tiebreak. Search takes
  the same keys after its name-match tiers, so "press" leads with the bench press.
- **Browse is indexed by muscle once at load** rather than re-scanning all 873 rows (and
  rebuilding the equipment dropdown from them) on every filter change.
- **Exercise ids are now free-exercise-db's** (`Barbell_Squat`, `Sit-Up`) and are
  case-sensitive. The four hand-written ids are gone; migrating carries an existing
  database across (Alembic revision `0002`).
- **`entry_date` is a real `DATE` column** rather than TEXT, and `created_at` a real
  timestamp. Nothing changes at the API, which still speaks ISO-8601 strings in both
  directions, and SQLite's stored form is unchanged so range queries behave identically.
- **`create_app` no longer creates the schema or touches the filesystem** except to make
  `instance/` for the SQLite development default. `python run.py` migrates before serving,
  so local use is still zero-setup; `wsgi.py` does not, so importing the app can never
  change a schema. Deployments run `upgrade-db` as an explicit step.
- **`init-db` is a development convenience** and refuses to run under production config.
- **`BODYSHOP_DATABASE` (a SQLite path) is replaced by `DATABASE_URL`** (a SQLAlchemy URL).
- **`GET /api/exercises` returns a lighter shape** — `primary`/`secondary` instead of a
  flat `muscles` list (which is still present, as their concatenation), plus `equipment`,
  `category`, `level`, `force`, `mechanic` and `counts_toward_volume`. Instructions and
  images moved to `GET /api/exercises/<id>`, since the picker fetches the whole catalog
  and they quadruple the payload.
- **`sets` in the weekly summary payload is a float**, and `over` with it.
- **Stretching, cardio and plyometrics grade as zero volume.** They are loggable and
  appear in history, but add no sets and never mark a group as worked — a hamstring
  stretch shading the hamstrings green would misreport the week. `/log` labels them on
  selection rather than letting the omission be silent.
- **`traps` is its own group**, no longer folded into `back`. Historical `back` counts
  are not comparable across this change.
- **`glutes`, `calves` and `forearms` are tracked**, reversing their previous status as
  deliberate silhouette gaps.
- **`/log` no longer renders the catalog server-side.** The view passes only a count;
  `log.js` fetches `/api/exercises` and drives the picker.
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
- The front and back body maps now show disjoint muscle groups instead of mirroring
  the same regions. Regions within a view must not overlap — they paint in order, so an
  overlap hides one group's colour behind another's.
- The chest is drawn as two pectorals split at the sternum, and the back as a tapering
  lat sheet with the trapezius yoke above it.
- `legs` is replaced by `quads`, `hamstrings`, `glutes` and `calves`.
- `.body-base` draws a full silhouette beneath the muscle overlays, so untracked
  anatomy (sternum, obliques, lower back, shins) shows through as gaps.

### Fixed

- CI, which had failed on every run since the workflow was added. `pytest` aborted
  during collection with `ModuleNotFoundError: No module named 'app'` because
  `conftest.py` sits in `tests/`, so the repo root never reached `sys.path`.
  `pythonpath = ["."]` in `pyproject.toml` fixes both `pytest` and `python -m pytest`.

### Removed

- `app/schema.sql` — superseded by `app/tables.py` plus the migrations.
- `models.remap_exercise_ids()` and the `remap-exercises` command it backed — folded into
  Alembic revision `0002`, leaving one mechanism for changing exercise ids rather than two.
- `db.ensure_db()`, which applied the schema on every boot. It would have crashed
  `create_app` on a read-only filesystem, and it gave a fresh deployment an unversioned
  schema that Alembic had no revision to stamp.

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
