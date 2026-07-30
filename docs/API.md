# API reference

Base URL: `/api`. All endpoints return JSON. Errors use HTTP status codes with a
body of `{"error": "<message>"}`.

Dates are ISO-8601 strings (`YYYY-MM-DD`) throughout, in the user's local calendar —
no time zone conversion is performed.

---

## `GET /api/exercises`

The whole catalog — 873 movements, ordered by name.

This is the **light** shape: no `instructions`, no `images`. The `/log` picker fetches
it once and filters client-side, and including them quadruples the payload. Use
`GET /api/exercises/<id>` for those.

```json
{
  "exercises": [
    {
      "id": "Barbell_Bench_Press_-_Medium_Grip",
      "name": "Barbell Bench Press - Medium Grip",
      "primary": ["chest"],
      "secondary": ["shoulders", "triceps"],
      "muscles": ["chest", "shoulders", "triceps"],
      "equipment": "barbell",
      "category": "strength",
      "level": "beginner",
      "force": "push",
      "mechanic": "compound",
      "counts_toward_volume": true,
      "rank": 0
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `primary` | Groups the movement trains directly. Each takes a **whole** set of volume. |
| `secondary` | Groups it trains indirectly. Each takes **half** a set. Never overlaps `primary`. |
| `muscles` | `primary + secondary`, in that order — for callers that only need "was this group touched". |
| `equipment` | One of `barbell`, `dumbbell`, `cable`, `machine`, `kettlebells`, `bands`, `body only`, `medicine ball`, `exercise ball`, `foam roll`, `e-z curl bar`, `other`, `none`. |
| `category` | `strength`, `stretching`, `plyometrics`, `powerlifting`, `olympic weightlifting`, `strongman` or `cardio`. |
| `level` | `beginner`, `intermediate` or `expert`. |
| `force` | `push`, `pull`, `static` or `null`. |
| `mechanic` | `compound`, `isolation` or `null`. |
| `counts_toward_volume` | `false` for stretching, cardio and plyometrics — still loggable, but graded as zero sets. |
| `rank` | How prominently to offer the movement, **lower first**. Not a field of the source data: it is Body Shop's "common lifts first" ordering (`STAPLE_EXERCISE_IDS` in `app/exercises.py`). `0`–~130 are the curated staples in order; `1000+` is everything else, ordered by `mechanic`, `level` and `equipment`, with zero-volume categories last. Sort on it; do not read meaning into the number. |

The twelve muscle group slugs are `chest`, `abs`, `shoulders`, `biceps`, `forearms`,
`quads`, `back`, `traps`, `triceps`, `glutes`, `hamstrings` and `calves`.

Ids come from [free-exercise-db](https://github.com/yuhonas/free-exercise-db) and are
case-sensitive (`Barbell_Squat`, `Sit-Up`, `3_4_Sit-Up`).

---

## `GET /api/exercises/recent`

Recently logged exercises, most recently used first, ties broken by total uses. Backs
the picker's default view; unlike search and browse it reads entry history, so it
cannot be derived from the catalog payload.

| Query param | Default | Notes |
| --- | --- | --- |
| `limit` | `12` | Clamped to 1–50. |

Same object shape as `GET /api/exercises`, **plus `uses`** — how many entries have been
logged against that exercise:

```json
{ "exercises": [ { "id": "Barbell_Squat", "uses": 14, "rank": 1, "…": "…" } ] }
```

`/log` asks for 50, lists the first 12, and keeps the rest for their counts: `uses`
outranks `rank` in browse and search, so your own movements lead every list. Returns an
empty list before anything has been logged.

---

## `GET /api/exercises/<id>`

One exercise in full: everything above, plus its instructions and image URLs.

```json
{
  "exercise": {
    "id": "Barbell_Squat",
    "name": "Barbell Squat",
    "primary": ["quads"],
    "secondary": ["back", "calves", "glutes", "hamstrings"],
    "muscles": ["quads", "back", "calves", "glutes", "hamstrings"],
    "equipment": "barbell",
    "category": "strength",
    "level": "beginner",
    "force": "push",
    "mechanic": "compound",
    "counts_toward_volume": true,
    "rank": 1,
    "instructions": [
      "This exercise is best performed inside a squat rack for safety purposes. …",
      "…"
    ],
    "images": [
      "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@b0eed06…/exercises/Barbell_Squat/0.jpg",
      "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@b0eed06…/exercises/Barbell_Squat/1.jpg"
    ]
  }
}
```

`images` is **always exactly two** — the start and end position of the movement, which
`/log` cross-fades into a two-frame loop. They are absolute URLs built from the
`EXERCISE_IMAGE_BASE` config value (`BODYSHOP_EXERCISE_IMAGE_BASE`), pinned to the
free-exercise-db commit the catalog was generated from.

**404** with `{"error": "Unknown exercise: …"}` if the id is not in the catalog.

---

## `GET /api/entries`

List workout entries, newest first.

| Query param | Description |
| --- | --- |
| `date` | Single day. Takes precedence over `start`/`end`. |
| `start` | Inclusive range start. |
| `end` | Inclusive range end. |

With no parameters, returns every entry.

```json
{
  "entries": [
    {
      "id": 12,
      "date": "2026-07-28",
      "exercise_id": "Barbell_Bench_Press_-_Medium_Grip",
      "exercise_name": "Barbell Bench Press - Medium Grip",
      "muscles": ["chest", "shoulders", "triceps"],
      "sets": 3
    }
  ]
}
```

`muscles` is `primary + secondary` and does not say which is which — fetch the
exercise if you need the split. `sets` is the whole number the user logged, not a
weighted figure.

**400** if a date parameter is not a valid ISO date.

---

## `POST /api/entries`

Create an entry. Accepts a JSON body or form encoding.

```json
{ "date": "2026-07-28", "exercise_id": "Barbell_Squat", "sets": 4 }
```

| Field | Rules |
| --- | --- |
| `date` | Required, ISO-8601. |
| `exercise_id` | Required, must exist in the catalog. Case-sensitive. |
| `sets` | Required, integer 1–100. |

**201** with `{"entry": {...}}` on success, **400** with an explanatory `error` otherwise.

```bash
curl -X POST http://127.0.0.1:5000/api/entries \
  -H 'Content-Type: application/json' \
  -d '{"date":"2026-07-28","exercise_id":"Barbell_Squat","sets":4}'
```

---

## `DELETE /api/entries/<id>`

Delete one entry.

- **200** → `{"deleted": 12}`
- **404** → `{"error": "Entry not found."}`

---

## `GET /api/calendar`

Total sets per day for a month — what the calendar dots are drawn from.

| Query param | Default |
| --- | --- |
| `year` | Current year |
| `month` | Current month (1–12) |

```json
{
  "year": 2026,
  "month": 7,
  "days": { "2026-07-28": 5, "2026-07-29": 4 }
}
```

Days with nothing logged are omitted. **400** if `month` is outside 1–12.

---

## `GET /api/summary/week`

The weekly muscle-coverage summary for the week containing `date` (defaults to
today). This is the endpoint that drives the body map.

Example below: 12 sets of barbell bench press (primary chest; secondary shoulders and
triceps). Groups omitted for brevity all look like `abs`.

```json
{
  "week_start": "2026-07-27",
  "week_end": "2026-08-02",
  "total_sets": 12,
  "total_entries": 1,
  "muscles": {
    "chest":      { "muscle": "chest",     "label": "Chest",     "worked": true,  "sets": 12.0, "target": 20, "over": 0.0, "state": "trained", "intensity": 0.6, "exercises": ["Barbell Bench Press - Medium Grip"] },
    "abs":        { "muscle": "abs",       "label": "Abs",       "worked": false, "sets": 0.0,  "target": 10, "over": 0.0, "state": "rest",    "intensity": 0.0, "exercises": [] },
    "shoulders":  { "muscle": "shoulders", "label": "Shoulders", "worked": true,  "sets": 6.0,  "target": 20, "over": 0.0, "state": "trained", "intensity": 0.3, "exercises": ["Barbell Bench Press - Medium Grip"] },
    "biceps":     { "muscle": "biceps",    "label": "Biceps",    "worked": false, "sets": 0.0,  "target": 10, "over": 0.0, "state": "rest",    "intensity": 0.0, "exercises": [] },
    "forearms":   { "muscle": "forearms",  "label": "Forearms",  "worked": false, "sets": 0.0,  "target": 10, "over": 0.0, "state": "rest",    "intensity": 0.0, "exercises": [] },
    "quads":      { "muscle": "quads",     "label": "Quads",     "worked": false, "sets": 0.0,  "target": 20, "over": 0.0, "state": "rest",    "intensity": 0.0, "exercises": [] },
    "back":       { "muscle": "back",      "label": "Back",      "worked": false, "sets": 0.0,  "target": 20, "over": 0.0, "state": "rest",    "intensity": 0.0, "exercises": [] },
    "traps":      { "muscle": "traps",     "label": "Traps",     "worked": false, "sets": 0.0,  "target": 10, "over": 0.0, "state": "rest",    "intensity": 0.0, "exercises": [] },
    "triceps":    { "muscle": "triceps",   "label": "Triceps",   "worked": true,  "sets": 6.0,  "target": 10, "over": 0.0, "state": "trained", "intensity": 0.6, "exercises": ["Barbell Bench Press - Medium Grip"] },
    "glutes":     { "muscle": "glutes",    "label": "Glutes",    "worked": false, "sets": 0.0,  "target": 20, "over": 0.0, "state": "rest",    "intensity": 0.0, "exercises": [] },
    "hamstrings": { "muscle": "hamstrings","label": "Hamstrings","worked": false, "sets": 0.0,  "target": 20, "over": 0.0, "state": "rest",    "intensity": 0.0, "exercises": [] },
    "calves":     { "muscle": "calves",    "label": "Calves",    "worked": false, "sets": 0.0,  "target": 10, "over": 0.0, "state": "rest",    "intensity": 0.0, "exercises": [] }
  },
  "muscles_worked": ["chest", "shoulders", "triceps"],
  "muscles_at_target": [],
  "muscles_over": [],
  "regions_neglected": [
    { "muscle": "shoulders", "region": "delt_side", "label": "Side delt" },
    { "muscle": "shoulders", "region": "delt_rear", "label": "Rear delt" }
  ],
  "sets_per_day": { "2026-07-28": 12, "...": 0 },
  "entries": [ /* same shape as GET /api/entries */ ]
}
```

Every group additionally carries `regions` and `region_sets`, specified in full under
[Regions](#regions) below. They are left out of the example above only for line width.

### Weighted sets

**`sets` is a float, not an integer.** A set counts once per targeted group, but at a
weight that depends on how directly the movement trains it:

| Role | Weight |
| --- | --- |
| `primary` | 1.0 |
| `secondary` | 0.5 |

So 12 sets of bench press give chest 12 and shoulders and triceps 6 each. Values are
rounded to one decimal place, so `12.5` is a normal reading and clients must format
accordingly. `total_sets` is unweighted — it counts sets actually performed.

Movements whose `counts_toward_volume` is `false` (stretching, cardio, plyometrics)
contribute **nothing**: they add no sets, do not appear in `exercises`, and do not
mark a group `worked`.

`worked` is `true` when the week gave the group any volume at all — including a
single set at half weight.

### Volume grading

Each group also reports how its volume compares to a weekly `target` — 20 sets for
the large groups (chest, back, shoulders, quads, hamstrings, glutes), 10 for the small
ones (abs, biceps, triceps, forearms, traps, calves).

| Field | Meaning |
| --- | --- |
| `target` | Sets per week the group is aiming for. Always an integer. |
| `over` | Sets beyond `target`; `0` while at or under it. Fractional, like `sets`. |
| `state` | `rest` (no volume), `trained` (up to target) or `over` (past target). |
| `intensity` | `0.0`–`1.0` position **within that state's colour ramp**: green light→dark across `sets / target`, then red light→dark across `over / (target // 2)`, clamped at 1. |

`muscles_at_target` lists groups whose sets have reached `target`; `muscles_over`
lists the subset that went past it. Both are in `MUSCLE_GROUPS` display order.

### Regions

Six groups break into regions that respond to different movements: `chest`,
`shoulders`, `back`, `triceps`, `hamstrings` and `calves`. The other six carry
`"regions": []` and `"region_sets": 0.0`.

```json
"shoulders": {
  "muscle": "shoulders", "label": "Shoulders", "worked": true, "sets": 6.0,
  "target": 20, "over": 0.0, "state": "trained", "intensity": 0.3,
  "exercises": ["Barbell Bench Press - Medium Grip"],
  "region_sets": 6.0,
  "regions": [
    { "region": "delt_front", "label": "Front delt", "sets": 6.0, "share": 1.0,  "neglected": false },
    { "region": "delt_side",  "label": "Side delt",  "sets": 0.0, "share": 0.0,  "neglected": true  },
    { "region": "delt_rear",  "label": "Rear delt",  "sets": 0.0, "share": 0.0,  "neglected": true  }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `region_sets` | The group's volume that could be **placed** in a region. `≤ sets`: a deadlift trains the back without saying anything about lats vs. mid back, so it is attributed to neither. |
| `regions[].sets` | Region volume, same weighting as the parent. A movement emphasising two regions splits its contribution evenly. |
| `regions[].share` | Fraction of `region_sets`, **not** of `sets` — otherwise unplaceable volume would read as neglect. `0.0` when `region_sets` is `0`. |
| `regions[].neglected` | `true` when the group received real volume (`region_sets ≥ 4.0`) and this region took under 15% of it. |

**Regions carry no `target`, `state` or `intensity`, and this is deliberate.** No study
has established a weekly set target for a muscle head — see
[docs/VOLUME_SCIENCE.md](VOLUME_SCIENCE.md). Clients must render regions as a
distribution, never on the volume ramp's colours. `regions_neglected` is the flat list
of every flagged region, in group then region order.

---

## `GET /api/summary/week/bounds`

The start and end of the week containing `date`. Useful for building links without
fetching a whole summary.

```json
{ "week_start": "2026-07-27", "week_end": "2026-08-02" }
```

Week start day is configurable with `BODYSHOP_WEEK_STARTS_ON` (1 = Monday).
