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
                     SQLite (instance/bodyshop.sqlite3)
```

`app/views.py` renders three server-side shells; everything dynamic is fetched by
the page's JavaScript module from the same `/api` the tests exercise. That means the
HTML never diverges from the API, and the API is testable without a browser.

## Layer responsibilities

| Module | Owns | Must not |
| --- | --- | --- |
| `app/exercises.py` | The exercise catalog and its muscle mapping. | Touch the database. |
| `app/models.py` | Every SQL statement, plus input validation. | Know about HTTP or Jinja. |
| `app/services/weeks.py` | Week/month boundary maths. | Query the database. |
| `app/services/summary.py` | Turning entries into per-muscle coverage and grading it against each target. | Build HTTP responses. |
| `app/api.py` | Request parsing, JSON shapes, status codes. | Contain business rules. |
| `app/views.py` | Page shells and template context. | Contain business rules. |
| `app/static/js/*` | DOM rendering and user interaction. | Duplicate aggregation logic. |

## The single source of truth

`app/exercises.py` defines both `EXERCISES` and `MUSCLE_GROUPS`. Adding a movement
there simultaneously:

- adds a radio button to `/log` (the view passes `all_exercises()` to the template),
- makes it valid input for `POST /api/entries` (`validate_entry` rejects unknown ids),
- makes its muscles countable in the weekly summary (`summarise_entries` iterates
  `entry.muscles`).

Nothing else hard-codes the list of exercises.

## The volume scale

`app/services/summary.py::summarise_entries` produces, for each of the seven groups
in `MUSCLE_GROUPS`:

```python
{"muscle": "chest", "label": "Chest", "worked": True, "sets": 12, "target": 20,
 "over": 0, "state": "trained", "intensity": 0.6, "exercises": ["Bench press"]}
```

`worked` is `True` as soon as a single set of a targeting exercise exists. Colour is
a *volume* scale on top of that, graded by `summary.py::grade`:

| Sets | `state` | `intensity` | Colour |
| --- | --- | --- | --- |
| 0 | `rest` | `0.0` | untrained grey |
| 1 … target | `trained` | `sets / target` | light green → dark green |
| target + 1 … | `over` | `over / (target // 2)`, clamped to 1 | light red → dark red |

`intensity` restarts at the bottom of the new ramp when a group crosses its target,
so the two scales are read independently — a group is never "dark green *and* faintly
red". Targets come from `exercises.py::MUSCLE_TARGETS`: 20 sets a week for the large
groups (chest, back, quads, hamstrings) and 10 for the small ones (abs, biceps,
triceps), which recover on less volume. Overshoot saturates at half the target, so
one extra set is a visible step on either scale.

The front-end does no grading of its own: `summary.js` writes `intensity` to a
`--level` custom property and toggles `.is-worked` / `.is-over` on every element with
the matching `data-muscle` attribute — SVG regions and breakdown rows alike. Colour
still lives entirely in CSS, which mixes between the ramp endpoints
(`--train-light`/`--train-dark`, `--over-light`/`--over-dark`) with `color-mix`.

Note that a set counts once per muscle group it targets — 3 sets of bench press add
3 to *both* chest and triceps. That is intentional: the page answers "how much work
did this muscle get", not "how many sets did I perform".

## The body map

`app/templates/partials/_body_figure.html` is a Jinja macro rendered twice, as
`figure("front")` and `figure("back")`. The two views draw **disjoint** sets of
muscle groups, so each figure carries information the other does not:

| View | Groups | Drawn as |
| --- | --- | --- |
| Front | `chest`, `abs`, `biceps`, `quads` | two pectorals split at the sternum; upper and lower abdominal blocks; upper arms; thighs |
| Back | `back`, `triceps`, `hamstrings` | trapezius plus a tapering lat sheet; upper arms; thighs |

`.body-base` draws a *complete* silhouette — head, neck, torso, arms, full legs,
forearms, hands, feet — and muscle regions are painted on top of it. That is why a
group can be several paths with anatomical gaps between them (sternum, ribs,
obliques, glutes, lower back, shins) without leaving holes in the outline.

Because a group is selected by `data-muscle` rather than by id, all of its paths
light up together — the two pectorals, or both thighs.

Adding a muscle group means adding a path with the right `data-muscle` slug to the
appropriate view; no JavaScript changes are needed.

## Data model

One table. Entries are append-only rows; there is no per-day "workout" record,
which keeps logging a single insert and makes range queries trivial.

```sql
workout_entry(id, entry_date TEXT, exercise_id TEXT, sets INTEGER, created_at TEXT)
```

`entry_date` is stored as an ISO-8601 string, so SQLite's lexicographic `BETWEEN`
comparison is also a correct chronological comparison, and the value needs no
conversion on the way to JSON.

## Dates and time zones

The backend never converts time zones. The browser sends `YYYY-MM-DD` strings that
the user picked, and gets the same strings back. `app/static/js/ui.js` deliberately
parses those with `new Date(y, m - 1, d)` rather than `new Date(iso)` — the latter
parses as UTC and can shift a day backwards for users west of Greenwich.

Weeks start Monday (ISO), configurable via `BODYSHOP_WEEK_STARTS_ON`.

## Testing strategy

- `tests/test_weeks.py` — boundary maths, no app needed.
- `tests/test_summary.py` — the muscle-coverage and volume-grading rules, both as
  pure functions and through the database.
- `tests/test_api.py` — every endpoint, including the validation failure modes.
- `tests/test_pages.py` — the three pages render and contain every muscle region.

Each test gets a fresh SQLite file in pytest's `tmp_path`, so tests are isolated and
run in any order.

## Deliberate limitations

- **Single user.** There is no auth and no `user_id` column; the database is
  whoever's machine it runs on. Adding accounts means a `user` table and a foreign
  key on `workout_entry`.
- **No migrations.** `schema.sql` is applied once; schema changes currently mean
  re-running `init-db`. Introduce Alembic before the data matters.
- **Sets only.** No weight or reps — `workout_entry` stores a bare count, so 3 sets at
  60kg and 3 sets at 140kg are the same row. This blocks 1RM estimates, PR detection,
  progress graphs and plate calculators, and is scheduled as
  [Phase 4](ROADMAP.md) rather than a to-do.
- **Squat covers the whole thigh.** It targets `quads` *and* `hamstrings` because
  the catalog has no hinge movement to distinguish them yet. Adding a deadlift or
  leg curl is the point at which squat should narrow to `quads`.
