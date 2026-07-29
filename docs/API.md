# API reference

Base URL: `/api`. All endpoints return JSON. Errors use HTTP status codes with a
body of `{"error": "<message>"}`.

Dates are ISO-8601 strings (`YYYY-MM-DD`) throughout, in the user's local calendar —
no time zone conversion is performed.

---

## `GET /api/exercises`

The exercise catalog.

```json
{
  "exercises": [
    { "id": "bench_press", "name": "Bench press", "muscles": ["triceps", "chest"] },
    { "id": "pull_ups",    "name": "Pull ups",    "muscles": ["biceps", "back"] },
    { "id": "squat",       "name": "Squat",       "muscles": ["legs"] }
  ]
}
```

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
      "exercise_id": "bench_press",
      "exercise_name": "Bench press",
      "muscles": ["triceps", "chest"],
      "sets": 3
    }
  ]
}
```

**400** if a date parameter is not a valid ISO date.

---

## `POST /api/entries`

Create an entry. Accepts a JSON body or form encoding.

```json
{ "date": "2026-07-28", "exercise_id": "squat", "sets": 4 }
```

| Field | Rules |
| --- | --- |
| `date` | Required, ISO-8601. |
| `exercise_id` | Required, must exist in the catalog. |
| `sets` | Required, integer 1–100. |

**201** with `{"entry": {...}}` on success, **400** with an explanatory `error` otherwise.

```bash
curl -X POST http://127.0.0.1:5000/api/entries \
  -H 'Content-Type: application/json' \
  -d '{"date":"2026-07-28","exercise_id":"squat","sets":4}'
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

```json
{
  "week_start": "2026-07-27",
  "week_end": "2026-08-02",
  "total_sets": 7,
  "total_entries": 2,
  "muscles": {
    "chest":   { "muscle": "chest",   "label": "Chest",   "worked": true,  "sets": 3, "exercises": ["Bench press"] },
    "back":    { "muscle": "back",    "label": "Back",    "worked": false, "sets": 0, "exercises": [] },
    "biceps":  { "muscle": "biceps",  "label": "Biceps",  "worked": false, "sets": 0, "exercises": [] },
    "triceps": { "muscle": "triceps", "label": "Triceps", "worked": true,  "sets": 3, "exercises": ["Bench press"] },
    "legs":    { "muscle": "legs",    "label": "Legs",    "worked": true,  "sets": 4, "exercises": ["Squat"] }
  },
  "muscles_worked": ["chest", "triceps", "legs"],
  "sets_per_day": { "2026-07-27": 4, "2026-07-28": 3, "...": 0 },
  "entries": [ /* same shape as GET /api/entries */ ]
}
```

`worked` is `true` when the week contains **at least one set** of an exercise that
targets the group. `sets` counts a set once per targeted group, so 3 sets of bench
press contribute 3 to both chest and triceps.

---

## `GET /api/summary/week/bounds`

The start and end of the week containing `date`. Useful for building links without
fetching a whole summary.

```json
{ "week_start": "2026-07-27", "week_end": "2026-08-02" }
```

Week start day is configurable with `BODYSHOP_WEEK_STARTS_ON` (1 = Monday).
