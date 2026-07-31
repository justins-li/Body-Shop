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

`app/views.py` renders six server-side shells (`/`, `/how-to-use`, `/routines`, `/log`,
`/summary`, `/progress`); everything dynamic is fetched by the page's JavaScript module
from the same `/api` the tests exercise. That means the HTML never diverges from the
API, and the API is testable without a browser. `/calendar` was a seventh until Phase
8.3 folded it into `/summary`; it survives as a 301 so shared `?date=` links still land
on the right week.

`/` and `/how-to-use` are the exceptions: static pages with no JS module and no API
calls. `/` is the one page that will render identically for a visitor and a signed-in
user, which is why it is worth having before auth exists.

## Layer responsibilities

| Module | Owns | Must not |
| --- | --- | --- |
| `app/data/exercises.json` | The catalog data itself — 873 vendored movements. | Be hand-edited; it is generated output. |
| `tools/build_exercise_catalog.py` | Fetching the pinned source and mapping its vocabulary onto ours. | Run at import, in CI, or at request time. |
| `app/exercises.py` | Loading and validating the catalog, the muscle groups, **baseline** targets, volume weights, and the equipment → `weight_mode` rule. | Touch the database, or scale a target — that is `training.py`'s job. |
| `app/training.py` | The trainer setup: experience levels, the session plan, and the one multiplier they resolve to. Pure functions over `exercises.py`'s baseline. | Touch the database, or know about HTTP. |
| `app/tables.py` | The schema, as SQLAlchemy `MetaData`. Source of truth for both dialects. | Change any existing database — that needs a migration. |
| `migrations/` | How a database reaches the schema `tables.py` describes. Revisions are append-only history. | Import app constants that a later commit could change. |
| `app/db.py` | The engine, request-scoped connections, and the migration commands. | Contain queries. |
| `app/models.py` | Every SQL statement, plus input validation. | Know about HTTP or Jinja, or know which dialect it is on. |
| `app/services/weeks.py` | Week/month boundary maths. | Query the database. |
| `app/services/summary.py` | Turning entries into per-muscle coverage and grading it against each target. | Build HTTP responses, or decide what a target *is*. |
| `app/services/graph.py` | The training graph's rules: what a window means, what makes a movement an orphan, and joining this week's coverage and personal bests onto the nodes. | Query the database, or invent a strength *standard* (see below). |
| `app/services/strength.py` | Estimating a one-rep max from the user's own sets, and reducing a window to one best per movement. | Query the database, or compare a user to anyone but themselves. |
| `app/routines.py` | The suggested sessions, and the time estimate derived from their sets. Editorial content, validated against the catalog at import. | Touch the database, or state a duration that is not computed from the sets listed. |
| `app/api.py` | Request parsing, JSON shapes, status codes. | Contain business rules. |
| `app/views.py` | Page shells and template context. | Contain business rules. |
| `app/static/js/*` | DOM rendering and user interaction. | Duplicate aggregation logic. |
| `app/static/js/timer.js` | The rest countdown, booted from `base.html` on every page. Pure client state, persisted as a *deadline* so it survives navigation and tab throttling. | Touch the API, or persist anything but its duration and that deadline. |
| `app/static/js/plates.js` | Plate arithmetic — a pure function of weight and bar. | Store anything, or fetch. |
| `app/static/js/layout.js` | The force-directed layout — a pure, deterministic function of the graph. | Touch the canvas, the DOM, or `Math.random`. |
| `app/static/js/progress.js` | The canvas, the gestures, the size-by control and the detail panel on `/progress`. | Contain layout maths, or re-simulate on a render. |
| `app/static/js/onboarding.js` | The one-time first-run question, and the record that it was asked. | Open on `/` or `/how-to-use`, or ask twice. |
| `app/static/js/pageturn.js` | The transition between chapters: holding a navigation while the leaf falls, and which side it falls from. | Let a departure skip it — an unheld navigation tears the animation down. |
| `app/static/js/setgrid.js` | **What a set is**: the rows, weight modes, added weight, the RPE gate, plate hints, repeat, and starting the rest timer. Mounted by `/log` and by a routine's quick-log. | Know which page it is on, or fetch anything. |
| `app/static/js/routines.js` | The routines page: choosing a session, drawing its movements, and pointing the shared grid at one. | Reimplement any part of the grid. |
| `app/static/js/weekstrip.js` | The calendar strip on `/summary`: seven boxes, expanding to the month; reports clicks and double-clicks on a day. | Own the anchor date, or navigate — it reports a gesture and the page decides. |
| `app/static/css/input.css` | The design system: theme pair, tokens, and every hand-written rule. | — (`styles.css` beside it is generated; never edit it) |

## Styling

Tailwind v4 + daisyUI, compiled by a **CSS-only, npm-free build step**: Tailwind ships a
standalone CLI binary and daisyUI is a tarball of CSS, both fetched into gitignored
`tools/` by `tools/fetch_css_toolchain.py`. JavaScript is still served exactly as
written — there is no bundler. The compiled `styles.css` is committed, so running the
app or CI never needs the toolchain; only editing `input.css` does.

Configuration is CSS-first (Tailwind v4): no `tailwind.config.js`. `@theme` holds the
tokens, two `@plugin "daisyui/theme"` blocks define the `bodyshop` and `bodyshop-dark`
themes, and `@source` directives list the content globs.

There are **two themes and a toggle** — cream (`bodyshop`, the markup default) and
Phase 4.5's instrument palette (`bodyshop-dark`). All 35 stock daisyUI themes stay off.
A theme here is never only a palette swap: **the volume ramp inverts with the ground**,
because a scale has to climb in whichever direction reads as "more" where it is drawn —
pale → deep on cream, dim → lit on near-black. Neither ramp was derived from the other.
Each satisfies the same binding rule, that one set must never look like none, with its
own numbers (3.02:1 on cream, 3.12:1 on dark), because the constraint that binds moves
with the ground. The chosen theme is applied by a blocking inline script in `base.html`'s
head, before the stylesheet: a module is deferred and would paint one theme then flip.

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

### Weight modes: the catalog decides how a set is logged

`equipment` is not just a browse filter. It decides how a weight is *recorded*, through
`weight_mode` — derived on read in `exercises.py`, never stored:

| Mode | The number means | Has a bar |
| --- | --- | --- |
| `barbell` / `ez_bar` | The loaded total, bar included | Yes — 20 kg / 45 lb, and 10 kg / 25 lb |
| `dumbbell` / `kettlebell` | Per implement, not the pair | No |
| `stack` | The pin setting on a cable or machine | No |
| `bodyweight` | Weight **added** to the lifter; usually nothing | No |
| `implement` | Whatever the thing is marked as | No |

Before Phase 6.5 the set grid assumed every movement was a loaded barbell: one column
called "Weight", and a plate breakdown under whatever was typed. That is right for a
squat and wrong for a cable pushdown, a dumbbell press and a pull-up in three different
ways — the pulldown in particular reported a bar that is not in the room.

Three decisions worth keeping:

- **The rule is server-side, the wording is not.** `EQUIPMENT_WEIGHT_MODES` is one map
  in `exercises.py` and reaches `/log` on the exercise payload; what a mode is *called*
  lives in `WEIGHT_MODE_DISPLAY` in `ui.js`, beside the rest of the display vocabulary.
  Bar weights live in `plates.js`, which already owned plate arithmetic.
- **An unmapped equipment value is an import-time error.** `_check_weight_modes` raises
  `CatalogError` rather than falling through to a default, because the fallback's failure
  is exactly the one this feature exists to fix — a movement quietly logged as a barbell.
- **A field the mode does not call for is removed from the DOM, not hidden.** `log.js`
  reads the grid back through those nodes, and a hidden input still carries its value, so
  a weight typed before "Added weight" was unticked would submit anyway.

## Routines, and one set grid

Phase 8.1. The app could always say what your week *was*; it had nothing to say about
what a session could be, and a new user's first screen was an empty picker over 873
movements — the worst possible introduction to a catalog.

`app/routines.py` holds five sessions, each focused on one thing. They are **editorial
content in code**, the same status as `STAPLE_EXERCISE_IDS`: `exercises.json` is
generated from a pinned commit and never hand-edited, and a routine is a judgement about
training rather than a fact about the source. `_check_routines` runs at import and
refuses an id that no longer resolves, a movement listed twice, or a routine with no
exercises — the first would render a card with a blank name and a dead log button.

Two rules worth keeping:

- **The time estimate is derived, never typed.** `estimate_minutes` builds it from the
  prescribed sets via `training.MINUTES_PER_WORKING_SET` plus the per-session overhead
  that module already names, then rounds to five minutes because it is not known better
  than that. A hand-written "45 min" drifts the first time anyone edits the list above
  it. It also means the routines come out at one session of Phase 6's `REFERENCE_PLAN`,
  which is not a coincidence — both are the same arithmetic.
- **A routine is a suggestion, and its prescription is a placeholder.** The quick log
  opens with the routine's set count and its reps as placeholders, exactly as `/log`
  offers last session's numbers. An untouched row still saves as `NULL`. Recording what
  a routine *told you to do* as though it happened is the one thing a training log must
  never do.

`MINUTES_PER_WORKING_SET` is new, and mildly contradicts Phase 6, which pointedly needed
no such constant: scaling targets is a ratio against the reference plan, so a per-set
cost appears in both halves and cancels. An estimate is an absolute answer, where nothing
cancels — so the number is now stated in one place rather than implied.

### One grid, two entrances

`setgrid.js` is what a set *is*: rows, weight modes and their plate hints, the
added-weight toggle, the RPE gate, warm-ups, units, repeat, and starting the rest timer.
It lived inside `log.js` while `/log` was the only way to record anything. Routines added
a second entrance, and a "quick log" with its own simpler grid would have been a second
set of rules about all of the above — the exact divergence this codebase keeps one copy
of everything to avoid. The two entrances differ in what they are *for*, not in what a
set is.

The component **builds its own markup**, including the header. That reverses a stated
reason: the header used to be server-rendered so the column names survived with no
script. The rows never did, so it bought a header over nothing — and it cannot be true of
a grid mounted into a dialog. `/log` now ships `<div id="set-grid-mount">`.

## Turning a page

The app is arranged as a book — chapters down the sides, numbered marks, a chapter that
keeps its side. Navigation between them was the one place that did not say so. It raised
a veil to cover the server round trip, and since these pages render in a few
milliseconds the veil was a flicker: a hint that something loaded, rather than a sense
of having moved.

The transition is now **timed rather than measured.** `pageturn.js` intercepts the click,
raises the veil, and holds the navigation for `TURN_MS` while a leaf falls across the
screen. That is a real cost, taken on purpose: the app is slower by the length of the
animation, because "instant and imperceptible" and "you turned a page" are different
experiences and this one is a book.

Four things keep it from being a wipe with extra steps:

- **It hinges.** The leaf is `.page-veil::before` rotating about a vertical spine from
  edge-on to flat, under a `perspective` on the veil — without which the rotation is a
  horizontal squash rather than a page.
- **It follows the shelves.** The stacks split around the open chapter, so an earlier
  chapter is to your left and a later one to your right. `data-turn` picks the side:
  `forward` falls from the right, `back` from the left, read off which stack was clicked.
  The gesture agrees with where the thing you clicked was standing.
- **The arrival is the other half.** `.shell-main` animates in on load — transform-only,
  so it cannot change layout height, which `/` being pinned to exactly one screen
  requires. It is pure CSS, so it happens with no JavaScript at all.
- **The leaf stays on-system.** A flat fill with a hairline at its spine that fades as it
  lands, not a shadow and not a gradient wash — both of which the design rules ban. The
  rotation is the only thing here depicting a physical object, and it does the work.

Three constraints worth knowing before touching it:

- **`TURN_MS` and `--page-turn-ms` must agree.** The script waits for the animation; if
  they drift, either the leaf is torn down mid-fall or the app sits still after it lands.
- **Every departure goes through `turnTo`.** A navigation that only raises the veil and
  leaves replaces the document a few milliseconds in, and the turn is a flicker again —
  which is why `/summary`'s double-click-to-log calls it rather than assigning directly.
- **Shelves must stay real `<a href>`s.** The whole fallback — before the module loads,
  and with JavaScript off — is that a shelf is an ordinary link that simply navigates.

`prefers-reduced-motion` drops the rotation and shortens the hold to 140ms. Someone who
has asked for less movement has not asked to be kept waiting for it.

## The calendar, folded in

Phase 8.3 retired `/calendar`. A whole chapter for a month grid was more room than the
feature earned: it answered "what did I do that day", which the summary's own entry list
already answers for the week being read.

What was worth keeping is the *shape of a month* — which days you trained, and how hard.
So it collapses. `weekstrip.js` draws **this week's seven boxes** by default, costing one
row above the body map, and expands to the surrounding month on request. Both states are
the same `.day-cell` against the same fixed `FULL_DAY_SETS` reference, so expanding
changes how many are drawn and never what one means; scaling to the range's own busiest
day would make the strip and the expanded month incomparable, and they are the same cells.

The whole month's totals are fetched even when a week is drawn — one request either way,
and it makes expanding instant. Clicking a day goes through `goToDate` in `summary.js`,
the one place the anchor moves, because `?date=` is shared state every page honours.

**Double-clicking a day opens `/log` for it.** Reading the week and adding to it are the
two things anyone does here, and the second used to mean finding the day, then the shelf,
then the date field again. The single click still does the cheap, reversible thing and
the second commits — and it deliberately does *not* debounce the first, which would cost
every ordinary click a quarter-second wait to serve the rarer gesture. `dblclick` fires
after both clicks, so the page has already re-anchored to that day, which is wanted
anyway before leaving it.

The strip reports both gestures through callbacks and navigates from neither: where a
click goes is the page's business, which is what keeps the module mountable somewhere
that answers differently. It is an accelerator, never the only route — the caption under
the grid and every cell's `aria-label` both name it, so it is not pointer-only lore.

The shelf became **Routines, keeping chapter 02**, so Log, Weekly summary and Graph did
not renumber around the change: a chapter mark you can navigate by is one that stays put.

## The trainer setup

Phase 6. Until then every user was graded against one set of targets. `app/training.py`
keeps `MUSCLE_TARGETS` as the *baseline* and scales it by two things the user knows about
themselves: how long they have been training (`EXPERIENCE_LEVELS`) and how much time they
intend to spend (`SessionPlan`).

**The two combine with `min`, not by multiplying**, and that is the whole model:

> your target is the smaller of what your experience asks for and what your week can hold.

Multiplying was the first attempt and it double-counts. Training three short sessions
*is* how a beginner's lower volume shows up, so applying both factors charged them twice
for one fact and drove every group onto the floor. Under `min` the session plan can only
ever reduce a target — which is the honest direction, since more hours available is not a
reason for the app to ask for more sets, but fewer hours is a reason it cannot ask for as
many.

One consequence is worth knowing before it reads as a bug: `REFERENCE_PLAN` is defined as
the week the baseline targets already describe, so **switching to Advanced without
lengthening the week changes nothing.** An advanced lifter asking for 1.3× the volume has
to find 1.3× the time. `limited_by` in the payload names which input is binding, and the
summary page says so in words, because the plan is the one the user can act on.

What is sourced and what is convention:

| | Status |
| --- | --- |
| `MIN_GROUP_TARGET = 4` | **Sourced** — the floor at which a muscle responds at all (Pelland et al. 2025) |
| `volume_scale` per level (0.6 / 1.0 / 1.3) | Convention. Tune freely; do not defend as findings |
| `SESSION_OVERHEAD_MINUTES = 10` | Judgement. Fixed per session, which is why 2 × 30 holds fewer working sets than 1 × 60 |
| `REFERENCE_PLAN` (5 × 75) | Derived, and the arithmetic is in the docstring: 180 weighted units ÷ ~2.0 per set ≈ 90 sets ≈ 315 working minutes |

**No ownership yet.** Phase 5 makes this a column on the user row; until then it is a
`localStorage` preference sent with each request (`experience`/`sessions`/`minutes`), and
`resolve_profile` treats every input as untrusted — falling back and clamping rather than
raising, the same discipline `window` follows on the graph. The API shape does not change
when Phase 5 lands.

**The client never computes a target.** It sends the three values and renders
`profile.targets` from the response. `/progress` sends them too, because node colour *is*
the body map's grading and the two pages must not disagree about one week.

### Asking once, on first run

The setup's default is a guess about a stranger, so `onboarding.js` puts the question
once, in a `<dialog>` booted from `base.html` beside the timer and the theme toggle.
Three rules keep it from becoming a nag:

- **It runs on the app pages only.** `data-page` gates it: `/` and `/how-to-use` are
  static, make no API calls, and must render identically for any visitor — and `/` is
  pinned to exactly one screen. A dialog over either would break the one property that
  makes them worth having before auth exists.
- **Skipping is an answer.** `bodyshop:onboarded` is written by both exits, and by
  `Escape`. It is deliberately a *separate* key from the stored profile: were they the
  same, someone who skipped would be asked on every visit, and someone who cleared only
  their preferences would never be asked again — both backwards.
- **A browser with storage blocked is treated as already asked**, since a question whose
  answer cannot be recorded would reappear on every page load.

Answering reloads the page. Everything on screen was fetched and graded before the
answer existed, and one request on a page that has just opened is cheaper than a
partial re-render that could leave two targets on screen at once.

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
red". Targets come from the trainer setup (above), which scales
`exercises.py::MUSCLE_TARGETS`: at the default setup, 20 sets a week for the large
groups (chest, back, shoulders, quads, hamstrings, glutes) and 10 for the small ones
(abs, biceps, triceps, forearms, traps, calves), which recover on less volume. **Nothing
downstream may hard-code those two numbers** — `summarise_entries` takes a profile and
every consumer reads `target` off the group. Overshoot saturates at half the target, so
one extra set is a visible step on either scale.

The front-end does no grading of its own: `summary.js` writes `intensity` to a
`--level` custom property and toggles `.is-worked` / `.is-over` on every element with
the matching `data-muscle` attribute — SVG regions and breakdown rows alike. Colour
still lives entirely in CSS, which mixes between the ramp endpoints
(`--train-min`/`--train-max`, `--over-min`/`--over-max`) with `color-mix`.

**The ramp climbs in luminance.** Phase 4.5 re-derived it for the dark ground and
renamed the tokens with it: a dark green against near-black is the *least*-lit thing on
screen, so the old light→dark direction said "less" where it meant "more", and "dark"
would now have named the bright end. Both ramps peak at similar brightness, so crossing
the target reads as a hue flip rather than a fade — which is what keeps one set past
target a visible step on either scale.

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
`12.0`). Only the per-muscle aggregate is fractional — the count feeding it is a
whole number of sets performed, now derived from the child rows in `workout_set`
rather than read from a column (see *Data model*).

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

## The training graph

`/progress` draws every movement logged in a window as a node, joined to the
movements performed on the same day. Added in Phase 4.5 as the redesign's signature
element, and scoped hard to data that already exists.

**The encodings are the app's own thesis, not a borrowed one.** Node colour is the
*current* weekly coverage state of the movement's primary muscle — the same
`state`/`intensity` pair the body map uses, so the two pages cannot disagree about a
week. Edge opacity is how many days two movements were logged together.

**Node size answers one of two questions, and the reader picks which** (Phase 6.7):
cumulative non-warmup sets, or the best single the movement's sets support. The second
is *your own best from your own log*, estimated with Epley — arithmetic on data the
user typed in, not a benchmark imported from elsewhere. A strength **standard** — what
someone of your bodyweight "should" press — remains out, and always was: the app stores
no bodyweight and has no business ranking anyone against a population.

The honesty rule this module wrote down *before* the data to break it existed is now
enforced rather than aspirational: **a movement with no recorded load has no estimate and
draws as a hollow ring.** Sizing it at zero would claim it is light, which is a different
and false statement from "not measured". Bodyweight work and every pre-Phase-4 row land
there, so the payload also reports `measured` — how much of the drawing can be sized at
all — because a canvas of rings should explain itself rather than look broken.

**There is no minimum node count.** Until Phase 6.7 the page refused to draw below
fifteen movements and showed a ranked list with a note about what would unlock the
picture. That was backwards for the one visual the app has: a new user met an
explanation of something they could not see, and the drawing then arrived all at once
rather than growing. `SPARSE_GRAPH_NODES` survives only as a note under the canvas, so a
two-node picture says it is early instead of pretending to be a map.

Switching the size question is a **re-draw, never a refetch and never a re-simulation** —
both numbers are already in the payload, and the layout fingerprint ignores size for
exactly the reason it ignores colour.

**Orphans are the point.** Movements logged fewer than `ORPHAN_MIN_SESSIONS` times, or
not inside `ORPHAN_STALE_WEEKS`, are pushed to a ring outside the core and drawn as
hollow rings. Both thresholds are opinion, so they are named constants with docstrings
— the same discipline `REGION_NEGLECT_SHARE` follows. They are also listed in words
below the canvas, because a force-directed graph that is only a hairball is
decoration; the written list is the finding, and it stands whether or not the drawing
above it is dense enough to read.

Note the graph now carries **two** kinds of hollow ring, and they mean different
things. Bone means *fallen out of the training*; the muscle's own coverage colour means
*no load recorded*, so it still says what the movement feeds while saying it cannot be
sized. The legend only shows the second under the strength view, where it is the only
place it can occur.

Three implementation decisions worth keeping:

- **Nodes and edges are filtered by one shared subquery** (`_counted_sessions` in
  `models.py`). Warm-ups are excluded from both in the same place, so a warm-up-only
  entry cannot become an edge pointing at a node that does not exist. Filtering them
  separately is the obvious way to write it and the bug is invisible until you look at
  the drawing.
- **The layout is pure and deterministic.** `layout.js` seeds positions from a hash of
  each exercise id rather than `Math.random`, so the same training draws the same
  picture every time — a graph that rearranges itself on each visit cannot become a
  mental map, which is the only reason to draw one. It runs to completion once and is
  cached against a fingerprint of the nodes and edges; panning and zooming are
  transforms over the result, never a re-simulation. The fingerprint deliberately
  ignores colour, so logging a workout does not rearrange the drawing.
- **The radial force is one force with two targets.** Core nodes target radius 0,
  orphans target `ORPHAN_RADIUS`; both are restoring forces and therefore bounded. The
  first implementation pushed orphans outward with a negative centering constant,
  which is unbounded — each step scaled the displacement that produced it, positions
  reached 1e19 within the loop, and the fit-to-view scale collapsed to a blank canvas.

Canvas rather than SVG or DOM nodes: at a few hundred movements with every pairing
drawn, an element per node is hundreds of layout objects re-composited on every pan.

### The lit field

The graph's only "background" is **made of the data**: every node casts light in its own
ramp colour, so where training is dense the field warms toward that muscle's coverage
colour and a page of over-target work reads hot before a single node is examined.
Orphans cast a faint cold bone light instead — they are not feeding anything.

That is the form the depth had to take. A decorative gradient was ruled out twice over:
[redesign-brief.md](redesign-brief.md) bans gradient backgrounds and blurred colour
blobs outright, and the volume ramp has to stay the most saturated thing on screen.
Light *emitted by* the ramp does not compete with the ramp; it is the same reading,
spread. Edges take the blend of the two movements they join for the same reason — a
uniform brick web said nothing about what it connected, and at this density the web is
most of the drawing.

Two performance notes that are the whole reason it is affordable:

- **The glow is rendered once, in world units, and blitted.** Pan and zoom are a
  transform over the layout, so the lit field does not change with them. Redrawing a few
  hundred large radial gradients per frame would not hold 60fps; one `drawImage` does.
  It renders at well under one pixel per world unit, which costs nothing to look at
  because there is no edge in it to appear pixelated.
- **Edge colours are blended when the data lands, never per frame.** A gradient per edge
  per frame is the one thing here that would cost the frame rate.

Measured at the brief's ceiling — 250 nodes, 1,500 edges, 3× device pixel ratio — the
draw loop runs 0.5 ms median against a 16.7 ms budget.

**Order matters in `load()`.** Everything the draw loop reads is derived from the graph
that has just arrived, so nothing may paint until that derived state has been rebuilt.
Clearing the selection used to draw immediately, which threw on every window change
because the new edges had no colours yet.

## Data model

Two tables, defined in [`app/tables.py`](../app/tables.py). Entries are append-only
rows; there is no per-day "workout" record, which keeps logging a single insert
and makes range queries trivial.

```sql
workout_entry(id, entry_date DATE, exercise_id TEXT, created_at TIMESTAMPTZ)
workout_set(id UUID, entry_id -> workout_entry ON DELETE CASCADE,
            set_index INTEGER, weight REAL, reps INTEGER, rpe REAL, set_type TEXT)
```

`workout_entry.sets` was an integer column until Phase 4. It is now **derived**:
`WorkoutEntry.sets` counts child rows whose `set_type` is not `warmup`. A
denormalised cache was considered and rejected — a cache that can disagree with
its source is the bug this app's single-source-of-truth design exists to avoid.
Keeping it an `int` property is what let `services/summary.py` survive the change
essentially untouched.

**Warm-ups are logged but never counted.** They are excluded from `sets`, from the
weekly map and from the calendar's per-day totals; counting them would inflate the
body map the moment anyone logged properly.

**`weight` is kilograms, always** — at rest and over the wire. The kg/lb choice is
a display preference in `localStorage`, converted only in
[`ui.js`](../app/static/js/ui.js), so Phase 7's charts aggregate over one unit.
`weight`, `reps` and `rpe` are nullable: "not recorded" and "zero" are different
facts, and revision `0004`'s backfill produces rows that know a set happened and
nothing else.

Set ids are **UUIDs generated server-side**, so Phase 10's offline queue becomes an
API change rather than a migration. They do not round-trip as strings: SQLAlchemy
stores 32-character hex and returns the hyphenated 36-character form.

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
- `tests/test_training.py` — the trainer setup, also pure: that the two inputs
  combine with `min` rather than by multiplying, that a plan beyond the level
  stops raising targets, that the 2:1 shape of the week survives scaling, that
  nothing falls below the four-set floor, and that `resolve_profile` clamps and
  falls back on every kind of bad input rather than raising.
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
- `tests/test_graph.py` — the training graph's rules: the warm-up exclusion reaching
  both nodes and edges, that no edge survives pointing at a movement that is not a
  node, the co-occurrence count, the orphan thresholds asserted directly so changing
  one is a deliberate edit, and — since Phase 6.7 — that a single movement still draws,
  that bests are window-scoped, and that a movement with no load carries `best: null`.
- `tests/test_strength.py` — the one-rep-max estimate, pure. Weighted toward the cases
  where it must **refuse**: no weight, no reps, a set too long to extrapolate from. An
  unmeasurable movement drawing as a small node instead of a ring is the failure the
  whole module is arranged to prevent.
- `tests/test_pages.py` — the five pages render and contain every muscle region, and
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
- **No strength standard, and no bodyweight.** Phase 6.7 added an estimated one-rep
  max from your own sets, but the app still stores no bodyweight and compares you to
  no one — so it can say "you have pressed the equivalent of 98 kg" and cannot say
  "that is intermediate". Whether it ever should is a product question, not a missing
  feature.
- **No PR detection.** The best is recomputed per window rather than recorded when it
  happens, so nothing notices or announces a new one. That is [Phase 8](ROADMAP.md).
- **No editing.** Entries and sets are append-only; a mistake is deleted and
  re-logged. Also Phase 8.
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
