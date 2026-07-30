# Phase 4 — Set-level logging: weight, reps and RPE

Design spec for [ROADMAP.md](../../ROADMAP.md)'s Phase 4. Written before
implementation; divergences get folded back into the roadmap's phase section when
the work lands.

**Depends on:** Phase 3 (Alembic, and a second dialect to get the migration right),
Phase 1 (the set grid is the most interaction-heavy surface in the app).

**Why now:** every competitive feature in Phase 7 — 1RM estimates, PR detection,
per-exercise progress graphs, volume-load charts, plate and warm-up calculators — is
a read over `(weight, reps)` per set. None of them can be prototyped against a flat
`sets` integer, and building Phase 7 first means writing the log page twice.

---

## Decisions this spec settles

Two of the roadmap's open decisions gate this phase. Both are now answered.

### Open decision 8 — does `workout_entry` survive? **Yes.**

`workout_entry` stays the parent; `workout_set` is a child with
`ON DELETE CASCADE`. The alternative — one flat `workout_set` table carrying
`entry_date` and `exercise_id` — is a simpler schema but a worse fit here:

- `summarise_entries`, `weekly_summary`, `sets_by_date` and `recent_exercise_usage`
  all aggregate per *session*, not per set. A flat table rewrites every one of them.
- `uses` in the picker means "times you have logged this movement". Flat, it would
  silently become "sets performed", which reorders the picker for the worse.
- Region attribution in `summary.py` is per exercise per entry. Flat, the same
  exercise logged twice in a day becomes indistinguishable from one longer block.
- There is nowhere to hang a per-exercise note, which Phase 7's routines will want.

The cost is a join on every read, addressed under *Read path* below.

### Open decision 2 (partial) — set id strategy. **UUID, generated server-side.**

Phase 10's table requires this to be decided here: "if the set model uses
autoincrement ids, the offline queue needs a migration later. Choosing UUIDs when
the table is created is free; changing them afterwards is not."

The mobile route is still unchosen, so this buys the option rather than exercising
it. Sets get a `sa.Uuid(as_uuid=False)` primary key — native `uuid` on Postgres,
`CHAR(32)` on SQLite — minted server-side with `uuid4().hex`. Accepting a
*client*-supplied id later becomes an API change, not a migration.

**One trap, verified against SQLAlchemy 2.0.43 rather than assumed:** with
`as_uuid=False` the type stores the 32-character hex but its result processor
returns the **hyphenated 36-character form**. An id therefore does not come back as
the string that was inserted:

```
inserted:   4cbfec1dd1e24b37a393e29446abbf39   (uuid4().hex, 32)
stored:     4cbfec1dd1e24b37a393e29446abbf39   (CHAR(32) on SQLite)
read back:  4cbfec1d-d1e2-4b37-a393-e29446abbf39   (36)
```

Both forms are accepted on the way in, so lookups work either way — but a test that
asserts the returned id equals `uuid4().hex` will fail, and the API emits the
hyphenated form. `docs/API.md`'s examples must show that form.

**`workout_entry` keeps its integer id.** Converting it too would rewrite existing
entry ids and every `/api/entries/<int:entry_id>` route for no benefit this phase
can name.

### Not in the roadmap, decided here — weight units. **Kilograms, canonical.**

The roadmap specs `weight REAL` and never says what the number means. A unit-less
number is ambiguous the moment a second person reads it, and Phase 7 aggregates
across it.

The column is **always kilograms**. A `kg`/`lb` display preference converts at the
UI boundary, persisted in `localStorage` — the same pattern `/summary` already uses
for its muscle scheme, and a user column in Phase 5. Display rounds to one decimal
place, so 135 lb round-trips as `135` rather than `134.99998`.

Rejected: a per-set `unit` column (every Phase 7 aggregate converts anyway, and
mixed units in one chart read badly) and a config-only label (flipping it silently
relabels every past row — 100 kg becomes 100 lb).

---

## Schema

### `workout_set`

```python
workout_set = sa.Table(
    "workout_set",
    metadata,
    sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column(
        "entry_id",
        sa.Integer,
        sa.ForeignKey("workout_entry.id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column("set_index", sa.Integer, nullable=False),   # 1-based, order within the entry
    sa.Column("weight", sa.Float),                        # kilograms; NULL = not recorded
    sa.Column("reps", sa.Integer),
    sa.Column("rpe", sa.Float),
    sa.Column("set_type", sa.Text, nullable=False, server_default=sa.text("'normal'")),
    sa.CheckConstraint("set_index > 0", name="set_index_positive"),
    sa.CheckConstraint("weight IS NULL OR weight >= 0", name="weight_non_negative"),
    sa.CheckConstraint("reps IS NULL OR (reps > 0 AND reps <= 1000)", name="reps_in_range"),
    sa.CheckConstraint("rpe IS NULL OR (rpe >= 1 AND rpe <= 10)", name="rpe_in_range"),
    sa.CheckConstraint(
        "set_type IN ('normal', 'warmup', 'drop', 'failure')", name="set_type_known"
    ),
    sa.UniqueConstraint("entry_id", "set_index", name="entry_set_index"),
    sa.Index("idx_workout_set_entry", "entry_id"),
)
```

Constraint names are **bare tokens** (`reps_in_range`, not
`ck_workout_set_reps_in_range`). The metadata's `naming_convention` is applied on
top; a finished name comes out double-prefixed. This is already written into
CLAUDE.md as a Phase 3 finding.

`weight`, `reps` and `rpe` are all nullable, and that is load-bearing rather than
lax: the backfill produces rows that know a set happened and nothing else, and the
form must be able to express the same thing.

Three rules deliberately live in Python rather than in a constraint:

| Rule | Why not a CHECK |
| --- | --- |
| RPE in 0.5 steps | Float modulo is dialect-specific and ugly in both. |
| At most 100 sets per entry | A count across rows, not a row predicate. |
| `set_index` contiguous from 1 | The unique constraint stops duplicates; contiguity is the writer's job, and enforcing it in SQL would block a mid-list delete. |

### `workout_entry`

Loses the `sets` column and its `sets_positive` check. Nothing else changes.

`sets` becomes **derived, not stored** — the roadmap considered keeping it as a
denormalised cache and rejected it: "a cache that can disagree with its source is
exactly the bug this app's single-source-of-truth design exists to avoid."

---

## Migration `0004`

**The two dialects need different work, so this revision branches rather than using
batch mode** — the same shape as `0003`, for a related reason. Phase 3's finding was
that `SQLiteImpl.cast_for_batch_migrate` inserts a `CAST` when type affinity
changes, and `CAST('2026-07-28' AS DATE)` prefix-parses to the integer `2026`.
`workout_entry` still carries the `DATE` and `DATETIME` columns that trap applies
to, so the rebuild is spelled out by hand and copies bytes verbatim.

### Order of operations differs by dialect, and must

**Postgres** — dropping a column does not touch the table's identity, so the safe
order holds:

1. Create `workout_set`.
2. Backfill from `workout_entry.sets`.
3. Drop the `sets` column.

Postgres drops a CHECK constraint that depends solely on a dropped column, so
`ck_workout_entry_sets_positive` goes with it and needs no separate
`op.drop_constraint`. If one is added anyway it must use the **full** stored name,
not the bare token — the bare-token rule applies to constraints Alembic *creates*
(where the convention is layered on top), not to ones it looks up by name.

**SQLite** — dropping a column means rebuilding the table: create a replacement,
copy, `DROP TABLE workout_entry`, rename. With `PRAGMA foreign_keys = ON` (which
`app/db.py` sets on every connection), **dropping a parent table that already has
child rows pointing at it is a foreign-key violation.** So the order inverts:

1. Read `(id, sets)` into Python memory.
2. Rebuild `workout_entry` without `sets` — no child table exists yet, so no FK to
   violate.
3. Create `workout_set`.
4. Insert the backfill rows from memory.

SQLite DDL is transactional, so the whole revision is still atomic; an interrupted
run rolls back rather than leaving a table half-rebuilt.

### The backfill runs in Python, not SQL

```python
bind = op.get_bind()
rows = bind.execute(sa.text("SELECT id, sets FROM workout_entry")).all()
for row in rows:
    bind.execute(
        sa.insert(workout_set_frozen),
        [
            {
                "id": uuid4().hex,
                "entry_id": row.id,
                "set_index": index,
                "weight": None,
                "reps": None,
                "rpe": None,
                "set_type": "normal",
            }
            for index in range(1, row.sets + 1)
        ],
    )
```

A recursive CTE could expand the counts on both dialects but could not mint UUIDs
on either, so Python does both. `workout_set_frozen` is a **local table definition
inside the revision**, not an import from `app/tables.py` — CLAUDE.md's rule that a
migration must not import a constant a later commit can change applies equally to a
`Table` object.

The roadmap is explicit that the backfill must **not invent weights**: existing rows
know a set count and nothing else, and `NULL` is the truthful record of that.

### `downgrade()`

Recreates `sets` as the non-warmup count per entry, restores the check constraint,
and drops `workout_set`. **Lossy** — weight, reps, RPE and set type are discarded —
and the docstring says so plainly. That is inherent to reversing this change, not a
shortcut.

---

## Data layer (`app/models.py`)

### Read path — one batched second query

Three options were weighed:

| | How | Verdict |
| --- | --- | --- |
| **A. Second batched query** | Fetch entries, then all their sets in one `WHERE entry_id IN (...)`, group in Python | **Chosen.** Two queries regardless of entry count |
| B. `LEFT JOIN` with an aggregate | One query for the counts | Cannot return set rows without multiplying entry rows |
| C. Fetch sets per entry on demand | Lazy | N+1 the moment the day panel renders |

A costs `summary.py` a little work it does not need — a week is on the order of a
hundred set rows — and in exchange one code path serves both the summary (counts
only) and the log page (full rows).

### Shapes

```python
@dataclass(frozen=True)
class WorkoutSet:
    id: str
    set_index: int
    weight: float | None   # kilograms
    reps: int | None
    rpe: float | None
    set_type: str


@dataclass(frozen=True)
class WorkoutEntry:
    id: int
    entry_date: date
    exercise_id: str
    set_rows: tuple[WorkoutSet, ...]

    @property
    def sets(self) -> int:
        """Sets counting toward weekly volume — warm-ups excluded."""
        return sum(1 for s in self.set_rows if s.set_type != "warmup")
```

**Keeping `entry.sets` as an int property is the trick that contains the blast
radius.** `summarise_entries`' `bucket["sets"] += entry.sets * exercise.weight_for(muscle)`
and `weekly_summary`'s `total_sets` and `sets_per_day` need **no changes at all**.
The roadmap predicted this ("still works if `entry.sets` stays a derived property,
which is the cheapest way to keep the muscle map untouched") and it holds.

Warm-up exclusion is a **correctness requirement, not a nicety**: without it the
muscle map inflates the moment anyone logs properly, and the volume ramp starts
lying about the week.

One consequence, and it is why the old `sets > 0` check cannot survive: **an entry
of nothing but warm-ups has `sets == 0`** and contributes no volume. That is the
right answer, and the summary already handles a zero contribution.

### Function-by-function

| Function | Change |
| --- | --- |
| `add_entry` | Takes a list of set dicts instead of an int. One insert for the entry, one executemany for its sets, one commit. |
| `list_entries` | Second batched query for sets; groups them onto entries by `entry_id`, ordered by `set_index`. |
| `get_entry` | Same, for one entry. |
| `delete_entry` | Unchanged — `ON DELETE CASCADE` takes the sets, and `app/db.py` already enables SQLite foreign keys per connection. |
| `sets_by_date` | **Changes.** Now joins `workout_set` and counts non-warmup rows per day, in SQL rather than Python. |
| `recent_exercise_usage` | Unchanged. `uses` still counts entries, so the picker's ordering is unaffected. |
| `validate_entry` | Splits: date + exercise stay here; per-set rules move to a new `validate_sets`. |
| `last_sets_for_exercise` | **New.** Most recent entry for an exercise, with its sets — backs the prefill. |

### `validate_sets`

Replaces the old `1 <= sets <= 100` rule:

- 1–100 rows; empty or non-list is a `ValidationError`.
- `weight`: absent/`None`/`""` → `NULL`; otherwise a number ≥ 0.
- `reps`: absent → `NULL`; otherwise an integer 1–1000.
- `rpe`: absent → `NULL`; otherwise a number 1–10 **in 0.5 steps**.
- `set_type`: absent → `"normal"`; otherwise one of the four known values.
- `set_index` is assigned by the server, 1..N in submission order. Clients do not
  send it — it is derived from position, so it cannot arrive with a gap.

---

## API (`app/api.py`, `docs/API.md`)

### `POST /api/entries` — breaking change, array only

```json
{
  "date": "2026-07-30",
  "exercise_id": "Barbell_Squat",
  "sets": [
    {"weight": 100, "reps": 5},
    {"weight": 100, "reps": 5},
    {"weight": 100, "reps": 5, "rpe": 8.5, "set_type": "failure"}
  ]
}
```

The integer form is **not** accepted. Logging three bare sets is `[{}, {}, {}]`.
The roadmap calls this "the last good moment to make a breaking change" — there are
no external consumers before Phase 6 deploys, and carrying a shorthand forever costs
two documented shapes and two validation paths.

`400` on a missing, empty, or non-array `sets`.

### `GET /api/entries` — `sets` is the array, `set_count` beside it

```json
{
  "id": 12,
  "date": "2026-07-28",
  "exercise_id": "Barbell_Squat",
  "exercise_name": "Barbell Squat",
  "muscles": ["quads", "back", "calves", "glutes", "hamstrings"],
  "set_count": 3,
  "sets": [
    {"id": "4cbfec1d-d1e2-4b37-a393-e29446abbf39", "set_index": 1,
     "weight": 100.0, "reps": 5, "rpe": null, "set_type": "normal"}
  ]
}
```

`sets` is the array, symmetric with `POST`. `set_count` is the **non-warmup** count
— the number the muscle map grades on — named so no client reads it as
`len(sets)`. `weight` is kilograms.

### `GET /api/exercises/<id>/last-sets` — new

Backs the prefill. The roadmap calls previous-values-inline "the single
highest-rated logging feature in the category, and it is one indexed query."

```json
{
  "date": "2026-07-24",
  "sets": [{"weight": 100.0, "reps": 5, "rpe": null, "set_type": "normal"}]
}
```

`{"date": null, "sets": []}` when the movement has never been logged, and `404` for
an unknown exercise id, matching `GET /api/exercises/<id>`.

**This is the first query that reaches set rows directly.** Phase 5's note applies
and goes in the docstring now rather than being rediscovered later: it joins back
through `workout_entry`, because once `user_id` exists a set query that skips that
join is the same IDOR as an unguarded `delete_entry`, wearing a different hat.

### Unchanged

`DELETE /api/entries/<id>`, `GET /api/calendar`, `GET /api/summary/week` and
`/bounds`, `GET /api/exercises` and `/recent`. The weekly summary payload is
**byte-identical** in shape — that is the check that the derived-property approach
worked.

---

## Front end

### The set grid (`log.html`, `log.js`)

Replaces the `+`/`−` sets stepper entirely. A row per set: index, weight, reps, RPE,
type, remove. "Add set" appends a row seeded from the one above it.

Previous values render as **greyed placeholders, not values** — present enough to
read, absent enough that an untouched row saves as `NULL` rather than silently
re-logging last week's weights.

Blank fields are legal, so logging bare sets stays a two-click path. This is the
same freedom the backfill needs; a form that could not produce a NULL-weight row
would contradict rows the migration creates.

### Units toggle

A `kg`/`lb` control on `/log`, persisted in `localStorage`. New helpers in `ui.js`:

```js
const LB_PER_KG = 2.2046226218;
export function toKg(value, unit)   { return unit === "lb" ? value / LB_PER_KG : value; }
export function fromKg(value, unit) { return unit === "lb" ? value * LB_PER_KG : value; }
export function formatWeight(kg, unit) { /* 1dp, trailing .0 trimmed */ }
```

`formatWeight` mirrors `formatSets`' existing convention: `12.5`, but `12` not
`12.0`.

### Rest timer (`app/static/js/timer.js`, new)

Starts on save, counts down in the page, with a 60/90/120/180s select. Pure
client-side — no schema, no endpoint. Native notifications are explicitly Phase 10,
and this phase ships only the logic that phase will move to the wrist.

### Plate calculator (`app/static/js/plates.js`, new)

A pure function of target weight and bar weight, returning plates per side. Bar
defaults to 20 kg / 45 lb; plate sets are the standard ones per unit. Rendered as a
hint under the focused weight input. No storage, no API.

### CSS

Every class the JS toggles must be **hand-written in `input.css`'s
`@layer components`** — Tailwind's scanner reads literal text only, so a class built
by interpolation is purged silently. New ones: `.set-row`, `.set-row.is-warmup`,
`.rest-timer.is-running`, `.plate-hint`.

This needs the toolchain, which is gitignored:

```bash
python tools/fetch_css_toolchain.py                     # network fetch, once
tools/tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --minify
```

`styles.css` is build output and is committed. **If the fetch fails, say so** — do
not hand-edit the compiled stylesheet, which the next build overwrites.

---

## Tests

`conftest.py`'s `add` fixture takes a set list:

```python
add("2026-07-28", "Barbell_Squat", [{"weight": 100, "reps": 5}] * 3)
```

An integer is still accepted **in the fixture only**, expanding to `[{}] * n`, so
the existing call sites that only care about a count stay readable. The fixture is
test scaffolding; the API itself takes the array and nothing else.

New coverage:

- Warm-up sets are stored, excluded from `set_count`, excluded from the muscle map,
  and excluded from the calendar's per-day totals.
- An entry of only warm-ups has `set_count == 0` and contributes no volume.
- Per-set validation at every bound: weight < 0, reps 0 and 1001, RPE 0.9, 10.1 and
  8.3 (not a 0.5 step), an unknown `set_type`, 0 sets and 101 sets.
- `DELETE /api/entries/<id>` cascades — no orphan `workout_set` rows survive.
- kg round-trip: a weight posted and read back is unchanged.
- Set ids come back as parseable UUIDs and are unique within an entry — asserted
  through `uuid.UUID(value)`, never by string equality with `uuid4().hex`, for the
  hyphenation reason above.
- `GET /api/exercises/<id>/last-sets` returns the most recent entry's sets, `[]` for
  an unlogged movement, `404` for an unknown id.
- Migration `0004` produces exactly N sets per entry with NULL weight/reps, and the
  chain survives `downgrade` → `upgrade`.

One existing test **must move**: `test_revision_0003_keeps_the_sets_check_constraint`
migrates to `head` and asserts `sets=0` is rejected. At head the column no longer
exists, so it pins to `to("0003")`.

---

## Docs to update in the same commit

Per CLAUDE.md's read-before-edit protocol, these are not follow-ups:

| Doc | What changes |
| --- | --- |
| `docs/API.md` | `POST`/`GET /api/entries` payloads, the new `last-sets` endpoint, a units note. Payload examples there are exhaustive, not illustrative. |
| `docs/ARCHITECTURE.md` | Layer-ownership table, the data-model section, the two new JS modules. |
| `docs/ROADMAP.md` | Phase 4 → done, what diverged, open decisions 2 (partial) and 8 marked resolved. |
| `CLAUDE.md` | The `sets`-is-an-integer-column invariant is now **false**. It gets replaced, not appended to — the file's own rule is that a stale CLAUDE.md is worse than a short one. New invariants: sets are child rows, `entry.sets` is derived and excludes warm-ups, weight is kilograms at rest, set ids are UUIDs. |

`docs/VOLUME_SCIENCE.md` needs **no change**. This phase adds no target, no region
and no claim about how much to train — `set_count` feeds the existing grading
untouched.

---

## Explicitly out of scope

Deferred to Phase 7, which wants history to read against and history only
accumulates after this ships: 1RM estimates, PR detection, per-exercise progress
graphs, volume-load charts, CSV export.

Deferred to Phase 10: native rest-timer notifications, the offline queue. The UUID
decision above is the only concession this phase makes to either.
