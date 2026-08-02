# API reference

Base URL: `/api`. All endpoints return JSON. Errors use HTTP status codes with a
body of `{"error": "<message>"}`.

Dates are ISO-8601 strings (`YYYY-MM-DD`) throughout, in the user's local calendar —
no time zone conversion is performed.

**Units.** Weight is kilograms everywhere in this API. The kg/lb choice shown to the
user is a display preference the front end applies on read — it never crosses the
wire.

---

## Authentication

**Every endpoint below that reads or writes workout data requires a bearer
token:**

```
Authorization: Bearer <supabase access token>
```

Tokens come from **Supabase Auth (GoTrue), which the browser calls directly**.
Login, signup, token refresh, password reset and email verification are
therefore *not* Flask endpoints and are not documented here — see
[app/static/js/auth.js](../app/static/js/auth.js) and Supabase's own GoTrue
reference. Flask only verifies the token's signature, expiry, audience and
issuer.

A missing, malformed, expired or foreign token returns:

```
401  {"error": "Sign in to continue."}
```

with `WWW-Authenticate: Bearer`. **The message never varies by cause.** A 401
that distinguishes "expired" from "forged" is a small oracle, and no client needs
the distinction — the only useful response to any of them is to refresh once and
then sign in again.

The account is mirrored into the local `user` table on the first authenticated
request carrying a `sub` we have not seen; there is no signup webhook.

| Endpoint | Auth |
| --- | --- |
| `GET /api/exercises` | **public** |
| `GET /api/exercises/<id>` | **public** |
| `GET /api/summary/week/bounds` | **public** |
| `GET /api/exercises/recent` | bearer |
| `GET /api/exercises/<id>/last-sets` | bearer |
| `GET /api/entries` | bearer |
| `POST /api/entries` | bearer |
| `DELETE /api/entries/<id>` | bearer |
| `GET /api/calendar` | bearer |
| `GET /api/summary/week` | bearer |
| `GET /api/progress/graph` | bearer |
| `GET /api/me` | bearer |
| `GET /api/profile` | bearer |
| `PUT /api/profile` | bearer |
| `DELETE /api/account` | bearer |

The three public endpoints are public deliberately: the catalog is public-domain
data that ships in the repo, and week bounds are calendar arithmetic over a query
parameter. Gating them would buy nothing and would leave `/login` unable to
render anything.

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
      "weight_mode": "barbell",
      "is_bodyweight": false,
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
| `weight_mode` | How a weight recorded against this movement should be read. Derived from `equipment`, never stored — see the table below. |
| `is_bodyweight` | `true` when a recorded weight means weight **added to the lifter** (a belt or a vest) rather than the load itself. Equivalent to `weight_mode == "bodyweight"`. |
| `rank` | How prominently to offer the movement, **lower first**. Not a field of the source data: it is Body Shop's "common lifts first" ordering (`STAPLE_EXERCISE_IDS` in `app/exercises.py`). `0`–~130 are the curated staples in order; `1000+` is everything else, ordered by `mechanic`, `level` and `equipment`, with zero-volume categories last. Sort on it; do not read meaning into the number. |

The twelve muscle group slugs are `chest`, `abs`, `shoulders`, `biceps`, `forearms`,
`quads`, `back`, `traps`, `triceps`, `glutes`, `hamstrings` and `calves`.

Ids come from [free-exercise-db](https://github.com/yuhonas/free-exercise-db) and are
case-sensitive (`Barbell_Squat`, `Sit-Up`, `3_4_Sit-Up`).

### Weight modes

`weight` on a set is always a number of kilograms, but **what that number is a weight
*of*** depends on the equipment. A client that renders every movement the same way gets
it wrong for most of the catalog — which is what Phase 6.5 fixed.

| `weight_mode` | Equipment | The number means | Plate breakdown |
| --- | --- | --- | --- |
| `barbell` | `barbell` | Total on the bar, bar included | Yes, 20 kg / 45 lb bar |
| `ez_bar` | `e-z curl bar` | Total on the EZ bar, bar included | Yes, 10 kg / 25 lb bar |
| `dumbbell` | `dumbbell` | Per dumbbell, **not** the pair's total | No |
| `kettlebell` | `kettlebells` | Per bell | No |
| `stack` | `cable`, `machine` | The stack setting as marked | No |
| `unweighted` | `foam roll` | **Nothing.** No weight field is offered at all | No |
| `bodyweight` | `body only`, `none` | Weight **added** to the lifter; usually `null` | No |
| `implement` | `bands`, `medicine ball`, `exercise ball`, `other` | Whatever the implement is marked as | No |

Two consequences for a client:

- **Never draw a bar where there is no bar.** Only the two barbell modes have one.
  Printing "20 kg bar + 12.5 per side" under a cable pulldown is arithmetic about
  equipment that is not in the room.
- **`unweighted` is not `bodyweight`.** A foam roller weighs what it weighs, there is
  no heavier one, and nothing straps to it — so the column is meaningless rather than
  usually-blank. Clients must draw no weight field and no way back to one; `bodyweight`
  hides the field behind a toggle, this removes it.
- **A `bodyweight` weight is additive and must be marked as such.** `20` on a pull-up
  and `20` on a curl are the same stored number meaning different things, so a set line
  reads `+20kg × 8` for the first and `20kg × 8` for the second.

The mapping is derived at read time from `equipment` and lives in
`EQUIPMENT_WEIGHT_MODES` in [app/exercises.py](../app/exercises.py). Every equipment
value in the catalog must appear there — an unmapped one raises `CatalogError` at
import rather than silently falling through to a default.

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

## `GET /api/exercises/<id>/last-sets`

The sets from the most recent session of this movement — backs the `/log` grid's
prefill.

```json
{
  "date": "2026-07-27",
  "sets": [
    {
      "id": "1f6a2b3c-4d5e-4f60-8a1b-9c0d1e2f3a4b",
      "set_index": 1,
      "weight": 100.0,
      "reps": 5,
      "rpe": null,
      "set_type": "normal"
    },
    {
      "id": "2a7b3c4d-5e6f-4071-9b2c-0d1e2f3a4b5c",
      "set_index": 2,
      "weight": 100.0,
      "reps": 4,
      "rpe": null,
      "set_type": "normal"
    }
  ]
}
```

Same set-field shape as `GET /api/entries`. `date` and `sets` are `null`/`[]` when the
movement has never been logged — the page renders that as empty placeholders, not an
error.

**404** with `{"error": "Unknown exercise: …"}` if the id is not in the catalog.

---

## `GET /api/routines`

The suggested sessions — Phase 8.1. The **light** shape: no exercises, for the same
reason `GET /api/exercises` omits images. Five routines' worth of photographs to render
five cards is most of a megabyte nobody looked at.

```json
{
  "routines": [
    {
      "key": "push",
      "name": "Push day",
      "focus": "Chest, shoulders, triceps",
      "blurb": "Everything that presses. …",
      "level": "intermediate",
      "total_sets": 19,
      "minutes": 75,
      "experimental": false,
      "inspired_by": null,
      "source": null
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `key` | Stable id, used by `GET /api/routines/<key>`. |
| `focus` | What the session trains, in the words someone would use to choose it. |
| `total_sets` | Sum of the prescribed sets. |
| `minutes` | **Derived** from `total_sets`, never typed — see `estimate_minutes` in `app/routines.py`. Rounded to five, because it is not known better than that. A session that does not work at the usual pace (a continuous band circuit) carries its own per-set cost; the duration is still derived from the sets. |
| `experimental` | `true` for a session **reconstructed from published coverage of a real athlete's training**. Clients must show it as such. |
| `inspired_by` | Whose training it approximates. Always present when `experimental`, `null` otherwise — checked at import. |
| `source` | Where the reporting came from, so the claim is checkable. Same rule. |

---

## `GET /api/routines/<key>`

One routine with its exercises hydrated — the catalog joined on, plus images and
instructions. One request rather than one per movement: the page shows every exercise at
once, so six round trips would be six chances to render half a routine.

```json
{
  "routine": {
    "key": "push",
    "name": "Push day",
    "focus": "Chest, shoulders, triceps",
    "blurb": "Everything that presses. …",
    "level": "intermediate",
    "total_sets": 19,
    "minutes": 75,
    "exercises": [
      {
        "exercise_id": "Barbell_Bench_Press_-_Medium_Grip",
        "name": "Barbell Bench Press - Medium Grip",
        "sets": 4,
        "reps": "6-8",
        "note": "Flat, heaviest first.",
        "primary": ["Chest"],
        "secondary": ["Shoulders", "Triceps"],
        "weight_mode": "barbell",
        "counts_toward_volume": true,
        "images": ["https://cdn.jsdelivr.net/…/0.jpg", "https://cdn.jsdelivr.net/…/1.jpg"],
        "instructions": ["Lie back on a flat bench. …"]
      }
    ]
  }
}
```

| Field | Meaning |
| --- | --- |
| `sets` | Working sets prescribed. A whole number, and what `minutes` is built from. |
| `reps` | Rep guidance **as written** — a string, because `"8-10"`, `"max"` and `"30-40 m"` are all things a routine legitimately says and none of them are arithmetic. |
| `note` | Why this movement is in this routine, in one line. |
| `primary` / `secondary` | Display labels (`"Chest"`), not slugs — this payload is for rendering a card. |
| `weight_mode` | So the quick log can head its weight column correctly. See [Weight modes](#weight-modes). |

**404** with `{"error": "Unknown routine: …"}` if the key is not one of the routines.

**The `experimental` tag is not decoration.** Those routines are second-hand, often
years old, and separated from the coaching, the training age and the rest of the week
that made them make sense for that person. Nobody named has endorsed anything, movements
are mapped onto the nearest catalog entry, and a client that renders these without the
tag is making a claim the API does not. Attribution is enforced at import: an
`experimental` routine with no `inspired_by`/`source` — or an attributed routine that is
not tagged — raises `RoutineError`.

**Logging from a routine uses `POST /api/entries` like anything else.** There is no
routine-specific write endpoint, and deliberately: a set recorded while following a
routine is the same object as one typed on `/log`, and it reaches the weekly summary the
same way. The prescription is a *suggestion* — clients must render `sets` and `reps` as
placeholders, never as values, or the log records what the routine said instead of what
happened.

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
      "weight_mode": "barbell",
      "set_count": 2,
      "sets": [
        {
          "id": "1f6a2b3c-4d5e-4f60-8a1b-9c0d1e2f3a4b",
          "set_index": 1,
          "weight": 100.0,
          "reps": 5,
          "rpe": null,
          "set_type": "normal"
        },
        {
          "id": "2a7b3c4d-5e6f-4071-9b2c-0d1e2f3a4b5c",
          "set_index": 2,
          "weight": 105.0,
          "reps": 3,
          "rpe": 8.5,
          "set_type": "failure"
        }
      ]
    }
  ]
}
```

`muscles` is `primary + secondary` and does not say which is which — fetch the
exercise if you need the split.

`weight_mode` rides on the entry so a rendered set line does not need a second request
for the catalog: it is the same value the exercise payload carries, and it is what tells
a client to print `+20kg × 8` rather than `20kg × 8` for a weighted pull-up. See
[Weight modes](#weight-modes).

`set_count` is the number of sets counting toward weekly volume — **warm-up sets are
stored but excluded from it**, same as everywhere else volume is counted. `sets` is
every set the entry has, in logged order, including warm-ups.

| Set field | Meaning |
| --- | --- |
| `id` | A UUID, unique per set. |
| `set_index` | 1-based position within the entry, assigned by submission order. |
| `weight` | Kilograms. `null` when not recorded. Read it through the entry's `weight_mode` — under `bodyweight` it is weight *added* to the lifter, not the load. |
| `reps` | `null` when not recorded. |
| `rpe` | `null` when not recorded. |
| `set_type` | One of `normal`, `warmup`, `drop`, `failure`. |

**400** if a date parameter is not a valid ISO date.

---

## `POST /api/entries`

Create an entry and its sets. Accepts a JSON body only — **form encoding is no
longer accepted**: it cannot carry a nested array, so keeping it would mean failing
every form post with a confusing message rather than an honest 400.

```json
{
  "date": "2026-07-28",
  "exercise_id": "Barbell_Squat",
  "sets": [
    { "weight": 100, "reps": 5 },
    { "weight": 100, "reps": 5 },
    { "weight": 105, "reps": 3, "rpe": 8.5, "set_type": "failure" }
  ]
}
```

| Field | Rules |
| --- | --- |
| `date` | Required, ISO-8601. |
| `exercise_id` | Required, must exist in the catalog. Case-sensitive. |
| `sets` | Required, array of 1–100 set objects. |

Each set object:

| Field | Rules |
| --- | --- |
| `weight` | Optional. Kilograms, ≥ 0. |
| `reps` | Optional. Integer, 1–1000. |
| `rpe` | Optional. 1–10, in steps of 0.5. |
| `set_type` | Optional. One of `normal`, `warmup`, `drop`, `failure`. Defaults to `normal`. |

**The integer form is no longer accepted** — three bare sets are `[{}, {}, {}]`, not
`3`. There were no external consumers before Phase 6 deploys, and this was the last
cheap moment to make the break.

**201** with `{"entry": {...}}` on success, **400** with an explanatory `error` otherwise.

```bash
curl -X POST http://127.0.0.1:5000/api/entries \
  -H 'Content-Type: application/json' \
  -d '{"date":"2026-07-28","exercise_id":"Barbell_Squat","sets":[{},{},{},{}]}'
```

---

## `DELETE /api/entries/<id>`

Delete one entry.

- **200** → `{"deleted": 12}`
- **404** → `{"error": "Entry not found."}`

---

**Another user's entry returns `404`, not `403`** — identical to an id that does
not exist. A 403 would confirm the id is real, which is the IDOR wearing a
politeness mask.

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

Warm-up sets are excluded from every count here, same as `set_count` on an entry — a
day of only warm-ups is indistinguishable from a day with nothing logged.

---

## `GET /api/summary/week`

The weekly muscle-coverage summary for the week containing `date` (defaults to
today). This is the endpoint that drives the body map.

| Query param | Default | Notes |
| --- | --- | --- |
| `date` | Today | Any day inside the week wanted. |

Targets come from the account's stored **trainer setup** — see
[`GET /api/profile`](#get-apiprofile). It used to travel on this query string as
`experience`/`sessions`/`minutes`; those parameters are gone, and a client still
sending them is ignored rather than 400ed. Two sources of truth meant a stale
client could be graded against something other than its own account's setup, and
because both answers render correctly the disagreement was invisible.

Example below: 12 sets of barbell bench press (primary chest; secondary shoulders and
triceps). Groups omitted for brevity all look like `abs`.

Warm-up sets are excluded from every count on this page — `total_sets`, each group's
`sets`, and `sets_per_day` — same as `set_count` on an entry.

```json
{
  "week_start": "2026-07-27",
  "week_end": "2026-08-02",
  "profile": {
    "experience": "experienced",
    "label": "Experienced",
    "shows_rpe": false,
    "volume_scale": 1.0,
    "limited_by": "experience",
    "sessions_per_week": 5,
    "minutes_per_session": 75,
    "targets": { "chest": 20, "abs": 10, "...": 0 }
  },
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

### Trainer setup

`profile` is the resolved trainer setup, echoed back beside the grading it produced.
**Clients must render `profile.targets` rather than re-deriving them** — the scaling
rule lives in [app/training.py](../app/training.py) and a second implementation on the
client is a disagreement waiting to happen.

| Field | Meaning |
| --- | --- |
| `experience` / `label` | The chosen level and its display name. |
| `shows_rpe` | Whether `/log` should offer an RPE field. `true` for `advanced` only. |
| `volume_scale` | The single multiplier applied to every baseline target. |
| `limited_by` | `experience` or `plan` — which of the two inputs is holding the targets down. Say so on screen: the plan is the one the user can change. |
| `sessions_per_week` / `minutes_per_session` | The session plan, after clamping. |
| `targets` | Every group's resolved weekly target. Always integers. |

The two inputs combine with **`min`, never by multiplying**: your target is the smaller
of what your experience asks for and what your week can hold. Training fewer hours *is*
how a lower experience level shows up, so applying both charges for the same fact twice.
A plan roomier than the baseline therefore changes nothing — having the time to train
more is not a reason for the app to ask for more sets.

No target ever falls below **4 sets a week**, the literature's approximate floor for a
muscle responding at all. That is the one sourced number in the module; the level
multipliers and the per-session overhead are named conventions. All of it is argued in
[docs/VOLUME_SCIENCE.md](VOLUME_SCIENCE.md).

### Volume grading

Each group also reports how its volume compares to a weekly `target`. At the default
setup that is 20 sets for the large groups (chest, back, shoulders, quads, hamstrings,
glutes) and 10 for the small ones (abs, biceps, triceps, forearms, traps, calves); the
trainer setup scales both together, so **do not hard-code either number** — read
`target` off the group, or `profile.targets`.

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

## `GET /api/progress/graph`

The training graph behind `/progress`: every movement logged in a window, joined to
the movements performed on the same day. Read-only, and the only endpoint Phase 4.5
added.

| Query param | Default | Values |
| --- | --- | --- |
| `window` | `8w` | `8w`, `6m`, `all` |
| `date` | Today | Anchors both ends of the window *and* the colouring week |

```json
{
  "window": "8w",
  "start": "2026-06-05",
  "end": "2026-07-30",
  "nodes": [
    {
      "exercise_id": "Barbell_Squat",
      "name": "Barbell Squat",
      "primary_muscle": "quads",
      "sets": 24,
      "sessions": 6,
      "last_logged": "2026-07-28",
      "orphan": false,
      "weight_mode": "barbell",
      "best": {
        "one_rep_max": 116.7,
        "weight": 100.0,
        "reps": 5,
        "achieved_on": "2026-07-24"
      }
    },
    {
      "exercise_id": "Pullups",
      "name": "Pullups",
      "primary_muscle": "back",
      "sets": 12,
      "sessions": 4,
      "last_logged": "2026-07-27",
      "orphan": false,
      "weight_mode": "bodyweight",
      "best": null
    }
  ],
  "edges": [
    { "source": "Barbell_Squat", "target": "Romanian_Deadlift", "days": 6 }
  ],
  "coverage": {
    "quads": { "state": "trained", "intensity": 0.6 }
  },
  "measured": 1,
  "sparse": false,
  "sparse_below": 15
}
```

**An unrecognised `window` falls back to `8w` rather than returning 400.** It arrives
from a view control, and the honest response to a bad view preference is the usual
view.

`sets` and `sessions` **exclude warm-ups**, the same rule as everywhere else. A
movement logged only as a warm-up therefore does not appear as a node at all — and
because nodes and edges are filtered by one shared subquery, it cannot leave an edge
pointing at a node that is not in the response either.

`edges` is undirected and deduplicated: each pair appears once, with `source` sorting
before `target`, and nothing links to itself. `days` counts the days the two movements
were logged together, not the sets.

`coverage` is the **current week's** grading — the same `state`/`intensity` pair
`GET /api/summary/week` returns, for every one of the twelve groups. It colours the
nodes, so the graph and the body map cannot say different things about the same week.
Note it is the week containing `date`, *not* the whole window: the question the page
answers is what this training is feeding now.

Node colour *is* the body map's grading, so this endpoint resolves the account's
trainer setup exactly as `GET /api/summary/week` does. Neither is told the setup by
its caller any more, which is what makes it impossible for the two pages to disagree
about one week.

`orphan` marks a movement that has fallen out of the training — logged fewer than
three times, or nothing in eight weeks. Both thresholds are **judgement, not
evidence**, and live as named constants in `app/services/graph.py` for the same reason
`REGION_NEGLECT_SHARE` does.

### Personal bests

`best` is the heaviest single the movement's sets in this window support, estimated
with Epley (`weight × (1 + reps / 30)`) in `app/services/strength.py`. It is **your own
best, from your own log** — not a strength standard. Nothing in this API compares a user
to a population; the app stores no bodyweight and has no business ranking anyone.

| Field | Meaning |
| --- | --- |
| `one_rep_max` | The estimate, in kilograms. A logged single passes through untouched — it is the lift, not an estimate. |
| `weight` / `reps` | The actual set it came from, so a client can show its working. |
| `achieved_on` | When that set was performed. Ties go to the **earlier** date: a best is when you first reached it. |

**`best` is `null` whenever no set can support an estimate** — bodyweight movements,
rows logged as a bare count, and everything from before Phase 4 added the weight column.
Clients **must draw a hollow ring rather than a small node**: an unmeasured lift is not
a light lift, and sizing it at zero states something false. `weight_mode` rides alongside
so a client can say *why* there is no number.

Sets longer than 12 reps are ignored for the estimate rather than extrapolated — every
rep-max formula drifts badly past ten, and Epley on a 20-rep set reports a single 67%
above the bar. Warm-ups are excluded, as everywhere else: on movements where the warm-up
is the heaviest thing logged it would routinely beat the real work.

Bests are scoped to the **window**, not to all time. A lifetime figure would keep a
movement large long after it was dropped, which is the opposite of what `orphan` is for.

`measured` counts the nodes carrying a `best`, so a client can say "6 of 14 movements
sized by load" rather than leaving a canvas of rings looking broken.

### There is no longer a minimum

`sparse` is **a note, not a gate**. Before Phase 6.7 the response carried `graph_ready`
and `/progress` refused to draw below fifteen movements — which meant a new user met an
explanation of a picture they could not see, and the picture then arrived all at once
instead of growing. The graph now draws from the first logged movement; `sparse` (with
`sparse_below`) only says whether it is dense enough to read as a *shape* yet. The one
case with nothing to draw is an empty window.

**Still not here, and deliberately:** a strength *standard*. Colouring or sizing against
what someone of a given bodyweight "should" lift needs a bodyweight the app does not
store and a population comparison it does not make.

---

## `GET /api/summary/week/bounds`

The start and end of the week containing `date`. Useful for building links without
fetching a whole summary.

```json
{ "week_start": "2026-07-27", "week_end": "2026-08-02" }
```

Week start day is configurable with `BODYSHOP_WEEK_STARTS_ON` (1 = Monday).

---

## `GET /api/me`

The signed-in user. Exists so a client can confirm a token server-side rather
than trusting its own decode of it.

```json
{
  "user": {
    "id": "11111111-1111-4111-8111-111111111111",
    "email": "you@example.com"
  }
}
```

`id` is the Supabase `auth.users` id — the token's `sub` — and the value every
`workout_entry` row is owned by.

---

## `GET /api/profile`

The account's trainer setup, resolved, with the targets it produces.

```json
{
  "profile": {
    "experience": "beginner",
    "label": "Beginner",
    "shows_rpe": false,
    "volume_scale": 0.6,
    "limited_by": "experience",
    "sessions_per_week": 6,
    "minutes_per_session": 90,
    "targets": { "chest": 12, "abs": 6, "...": 0 }
  },
  "configured": true
}
```

`profile` is the same shape `GET /api/summary/week` echoes, specified under
[Trainer setup](#trainer-setup).

`configured` is `false` when the account has never chosen a setup — the three
columns are NULL and `profile` is the app's default, which is the pre-Phase-6
grading exactly. It is a fact about storage rather than about training, which is
why it sits beside the profile rather than inside it. **The first-run dialog is
its one reader:** an account that has answered is never asked again, on any
device.

---

## `PUT /api/profile`

Stores the account's trainer setup.

```json
{"experience": "beginner", "sessions_per_week": 6, "minutes_per_session": 90}
```

Responds with the same shape `GET /api/profile` returns, and `configured: true`.

**Nothing here 400s.** An unknown experience level falls back to `experienced`
and out-of-range numbers are clamped to 1–14 sessions and 15–240 minutes — the
same rule `window` follows on the graph endpoint, and for the same reason: these
arrive from a settings control, and the honest response to an out-of-range number
is the nearest one that works.

**The stored values are the resolved ones**, not what was submitted, so the column
can never hold a setup the app would refuse to use. The echo is therefore what the
client's controls should settle on: a value corrected on the way in corrects itself
on screen rather than sitting there disagreeing with the grading it produced.

---

## `DELETE /api/account`

Deletes the account and, by cascade, every entry and set in it. **Irreversible.**

Local rows go first, the Supabase auth record second. That order is deliberate:
if the Supabase call fails, the account survives with no data, which is
recoverable and retryable. The reverse order risks the auth record being gone
while the rows are orphaned behind an account that can never sign in again to
delete them.

```json
{"deleted": true, "auth_record_removed": true}
```

```json
{"deleted": true, "auth_record_removed": false}
```

The second shape is still `200`: the workouts *are* deleted. It says Supabase
would not remove the sign-in record, and the client tells the user so rather than
claiming a clean success.

```
503  {"error": "Account deletion is not configured on this server."}
```

Returned when `SUPABASE_SERVICE_ROLE_KEY` is unset, and checked **before**
anything is deleted, so a misconfigured deployment refuses rather than
half-deleting an account.
