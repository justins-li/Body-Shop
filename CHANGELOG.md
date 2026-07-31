# Changelog

All notable changes to Body Shop are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Routines: something to follow, instead of a blank log** (Phase 8.1). Five sessions,
  each built around one thing — push, pull, legs, a beginner full body, an athletic
  whole-body day. Each shows every movement's photographs and how to do it, and puts a
  **log button** beside it that writes straight into the week.

  The time estimate is **derived from the prescribed sets, never typed** beside them: a
  hand-written "45 min" drifts the first time anyone edits the list above it. It comes
  out at one session of Phase 6's reference week, which is not a coincidence — both are
  the same arithmetic, and `MINUTES_PER_WORKING_SET` is now stated in one place rather
  than implied. (Phase 6 pointedly needed no such constant, because scaling targets is a
  ratio and a per-set cost cancels. An estimate is absolute, where nothing cancels.)

  Routines are **editorial content in code**, the same status as `STAPLE_EXERCISE_IDS`,
  validated against the catalog at import: an id that stopped resolving would render a
  card with a blank name and a dead log button. And a routine's prescription is a
  **placeholder, not a value** — an untouched row still saves as "not recorded", because
  logging what a routine *told you to do* as though it happened is the one thing a
  training log must never do.

- **One set grid, two entrances** (Phase 8.2). The quick log on a routine is not a
  lesser cousin of `/log` — it is the same component. Weight modes and their plate hints,
  the added-weight toggle, the RPE gate, warm-ups, the kg/lb preference, repeat and the
  rest timer all came out of `log.js` into `setgrid.js`, because a second, simpler grid
  would have been a second set of rules about every one of them. The two entrances differ
  in what they are *for*, not in what a set is.

- **The training graph draws from your first workout, and can be sized by what you
  lift** (Phase 6.7). Two changes, and the first is the one that matters:

  **The fifteen-movement gate is gone.** `/progress` used to refuse to draw below
  fifteen and show a ranked list with a note about what would unlock the picture — so a
  new user met an explanation of something they could not see, and the drawing then
  arrived all at once instead of growing. It now starts as one dot and fills in, and the
  note under it counts up rather than saying "not yet". The only case with nothing to
  draw is a window with nothing in it.

  **Node size now answers one of two questions.** "Sets" is the volume reading it always
  had; "Best lift" sizes each movement by the heaviest single its sets support, estimated
  with Epley from weight and reps you logged yourself. That is *your own log*, not a
  strength standard — the app still stores no bodyweight and compares you to nobody, and
  that stays deliberate. Switching between them is a re-draw, never a refetch and never a
  re-simulation, so the arrangement holds still while you ask the other question of it.

  The honesty rule `graph.py` wrote down before the data to break it existed is now
  enforced: **a movement with no recorded load draws as a hollow ring, not a small node.**
  Sizing an unmeasured lift at zero would claim it is light, which is false rather than
  merely unknown. Bodyweight work and every pre-Phase-4 row land there, so the payload
  also reports how many movements *can* be sized — a canvas of rings should explain
  itself rather than look broken. Sets past twelve reps are ignored rather than
  extrapolated (Epley on a 20-rep set reports a single 67% above the bar), warm-ups never
  become a best, and the panel always shows its working: `Est. 1RM 117kg — from 100kg × 5
  on Jul 24`, never a bare number.

- **One question on first run.** The trainer setup decides every weekly target, and its
  default is a guess about a stranger — so a new browser is asked once which level it is
  training at, and how long its week is. Skipping counts as an answer, so it cannot
  become a nag, and the flag is stored separately from the preferences: sharing one key
  would re-ask anyone who skipped and never re-ask anyone who cleared their settings. It
  never opens on `/` or `/how-to-use`, which are static and must render identically for
  any visitor.

- **Trainer setups, and weekly targets that fit the week you actually have** (Phase 6).
  `/summary` gains three controls — experience level, sessions a week, minutes a session
  — and they decide every muscle group's weekly target. Beginner asks for 0.6 of the
  baseline, Experienced for the baseline, Advanced for 1.3 and unlocks RPE on every set.
  The whole model is one line: **your target is the smaller of what your experience asks
  for and what your week can hold.** The two inputs combine with `min`, not by
  multiplying — training fewer hours *is* how a beginner's lower volume shows up, so
  applying both charged the same lifter twice for one fact and pushed every group onto
  the floor. A roomier week therefore never *raises* a target: having time available is
  a ceiling, not a licence. `limited_by` in the payload names which input is binding,
  because the week is the one the user can act on.

  Two things are worth separating. `MIN_GROUP_TARGET = 4` is **sourced** — the floor at
  which a muscle responds at all (Pelland et al. 2025) — and nothing can fall below it.
  The three multipliers and the per-session overhead are **conventions**, named and
  documented as such. `REFERENCE_PLAN` (5 × 75 min) is derived rather than picked: 180
  weighted set units at roughly 2.0 per set is ~90 working sets, which is ~315 working
  minutes. One consequence reads as a bug and is not — that reference is the *baseline's*
  week, so switching to Advanced without lengthening the week changes nothing, and the
  page says so.

  No user row exists yet, so the setup lives in `localStorage` and rides on the query
  string; Phase 5 moves it without changing the API's shape. **The client never computes
  a target** — it renders the ones the server graded against. `/progress` sends the
  setup too, because node colour *is* the body map's grading and the two pages must not
  disagree about one week.

- **A repeat-set button on `/log`.** Straight sets are most of what anyone logs, and were
  five rounds of the same typing. It copies the row above outright, falling back to its
  placeholders when the row is still blank so the first tap repeats last session.

- **Credits and a contact block on `/how-to-use`.** Justin Li and Owen Zhang, both
  lead developers, with portraits; plus a "Have questions?" section. The address is a
  placeholder on the reserved `.example` TLD, so nothing sent to it can reach a stranger
  who happens to own the domain — swap it before launch.
- **A dark mode, and a toggle for it** (bottom-left, beside the rest readout). The cream
  theme stays the default; the dark one is Phase 4.5's instrument palette restored as an
  option rather than reinvented, so it arrives with its contrast reasoning intact.
  **The volume ramp inverts with the ground** — pale → deep on cream, dim → lit on
  near-black — because a volume scale has to climb in whichever direction reads as "more"
  where it is drawn. The two ramps are not derived from each other; each satisfies the
  same rule, that one set never looks like none, with its own numbers (3.02:1 and 3.12:1
  against untrained). The choice is remembered per browser, the system preference decides
  until you make one, and the theme is applied before first paint so neither flashes.

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

- **The calendar folded into the weekly summary, and `/calendar` retired** (Phase 8.3).
  A whole chapter for a month grid was more room than it earned: it answered "what did I
  do that day", which the summary's own entry list already answers for the week being
  read. What was worth keeping — the shape of a month, at a glance — is now a strip above
  the body map: **seven boxes for this week, expanding to the month on request** and
  remembering which you prefer. Both states are the same cell against the same fixed
  reference, so expanding changes how many are drawn and never what one means.

  **Double-clicking a day opens `/log` for it** — reading the week and adding to it are
  the two things anyone does on this page, and the second used to mean finding the day,
  then the shelf, then the date field again. The single click still does the cheap,
  reversible thing and the second commits. It is an accelerator rather than the only
  route, and it is named in the caption and on every cell's label, because a gesture
  nobody is told about is a gesture nobody uses.

  The shelf it vacated became **Routines, keeping chapter 02**, so Log, Weekly summary
  and Graph did not renumber around the change — a chapter mark you can navigate by is
  one that stays put. `/calendar` is a 301 rather than a 404, because `?date=` links to
  it are the app's own shared state and an old one should still land on the right week.

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

- **Logging no longer assumes every movement is a loaded barbell** (Phase 6.5). The set
  grid had one column called "Weight" and printed a plate breakdown — "20kg bar + 25 / 5
  per side" — under whatever was typed. That is right for a squat and wrong for a cable
  pushdown, a dumbbell press and a pull-up, in three different ways. A `weight_mode` is
  now derived from each movement's equipment and decides what the column is called, what
  the number means, and whether a plate breakdown is offered **at all**:

  - `barbell` and `ez_bar` are the only modes with a bar, and the EZ bar is 10 kg / 25 lb
    rather than 20 / 45. Everything else gets no plate line, because telling someone
    their 45 kg pulldown is a bar plus plates is arithmetic about equipment that is not
    in the room.
  - `dumbbell` says per bell rather than the pair's total; `stack` says the pin setting.
  - `bodyweight` — pull-ups, dips, push-ups — asks for no weight at all. A checkbox
    reveals a field for weight actually strapped on, and that reads back as `+20kg × 8`
    so it can never be mistaken for the load itself.

  An equipment value with no mode raises `CatalogError` at import rather than falling
  through to a default, since the fallback's failure is exactly the bug being fixed. A
  field the mode does not call for is removed from the DOM rather than hidden — a hidden
  input still submits, so a weight typed before the checkbox was unticked would have been
  logged anyway.

- **Three stale claims in `docs/ARCHITECTURE.md`**: that there is one dark theme (there
  are two themes and a toggle), that entries store a bare set count with no weight or
  reps (Phase 4 ended that), and that `views.py` renders five pages (six).

- **The date field's calendar button on `/log` now looks like a button.** Left to itself
  the browser renders it as a faint glyph the same weight as the digits beside it, so the
  one control on that row that opens something did not read as a control. It is outlined
  in the accent rather than filled, since a filled accent means "over target" on the
  volume ramp and nothing else may claim it.

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
