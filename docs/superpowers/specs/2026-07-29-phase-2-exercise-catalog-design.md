# Phase 2 — Exercise catalog and muscle map

Design for [ROADMAP.md](../../ROADMAP.md) Phase 2, as built. Written before
implementation; divergences from the roadmap's plan are called out inline and
folded back into the roadmap when the phase lands.

## What changes

| Before | After |
| --- | --- |
| 4 hand-written exercises in `app/exercises.py` | 873 vendored from free-exercise-db |
| 7 muscle groups | 12 |
| A flat `muscles` tuple | `primary` / `secondary`, weighted 1.0 / 0.5 at aggregation |
| No images | Two frames per exercise, cross-faded as a two-frame loop |
| 873 radio buttons would not fit on `/log` | Recent / search / browse picker |

## Decisions taken before building

Four questions were open. All are resolved here and in the roadmap's *Open
decisions* list.

1. **Catalog source — adopt free-exercise-db wholesale.** All 873 entries, not the
   roadmap's curated ~180. It is Unlicense (public domain), every entry carries
   exactly two images, and every id is already a clean slug. This resolves roadmap
   open decision 1 and collapses Phase 9 into this phase.
2. **Images — CDN, pinned.** No image bytes in the repo.
3. **Non-strength categories do not count toward volume.** Loggable, graded zero.
4. **Existing rows are remapped, not wiped.**

## Data pipeline

`tools/build_exercise_catalog.py` fetches free-exercise-db pinned at commit
`b0eed061e1c832b3ed815fbaa4b45b3cdc14df49`, maps it, and writes
`app/data/exercises.json`. It follows the `tools/fetch_css_toolchain.py`
precedent: a pinned, re-runnable fetch whose *output* is committed, so nothing at
runtime or in CI needs the network.

**JSON, not the YAML the roadmap proposed.** The file is generated rather than
hand-edited, so YAML's readability advantage does not apply, and PyYAML would be
the first new runtime dependency in a repo that pins only Flask.

### Muscle mapping

17 source slugs collapse to our 12. Verified across all 873 entries: none loses
its muscles, and every entry keeps a non-empty `primary`.

| Source | Ours |
| --- | --- |
| `abdominals` | `abs` |
| `lats`, `middle back`, `lower back` | `back` |
| `quadriceps`, `adductors` | `quads` |
| `abductors`, `glutes` | `glutes` |
| `neck`, `traps` | `traps` |
| `chest`, `shoulders`, `biceps`, `triceps`, `forearms`, `hamstrings`, `calves` | unchanged |

107 entries list a secondary muscle that collapses onto their own primary (lats
primary plus middle-back secondary, for instance). Primary wins; the duplicate is
dropped from `secondary`, so no muscle is ever counted at both weights.

## The `Exercise` model

The roadmap proposed `pattern` and `modifiers` facets. free-exercise-db has
neither — it carries `force`, `level`, `mechanic` and `category` instead.
Deriving 29 patterns across 873 rows by hand is exactly the error-prone data
entry the dataset exists to avoid, so **the dataset's facets are adopted as-is**.
They serve Phase 8's purpose equally well: they are a fixed vocabulary a model can
classify into.

```python
@dataclass(frozen=True)
class Exercise:
    id: str
    name: str
    primary: tuple[str, ...]
    secondary: tuple[str, ...]
    equipment: str
    category: str
    level: str
    force: str | None
    mechanic: str | None
    images: tuple[str, ...]        # exactly two: start and end position
    instructions: tuple[str, ...]

    @property
    def muscles(self) -> tuple[str, ...]:
        return self.primary + self.secondary
```

Keeping `muscles` as a derived property is what holds the blast radius down:
`WorkoutEntry.muscles`, `muscles_for()` and the exercise badges keep working
without edits.

The loader validates at import and raises on: a duplicate id, a muscle slug
outside `MUSCLE_GROUPS`, an empty `primary`, or an image count other than two.
These are errors the previous hand-written design could only catch by eye.

## Grading

```python
PRIMARY_WEIGHT = 1.0
SECONDARY_WEIGHT = 0.5
```

Applied in `summarise_entries`, so a group's `sets` becomes a float and the UI
renders `12.5 / 20`. Trailing `.0` is dropped for display in both Python and JS.

**Non-strength categories contribute zero and do not set `worked`.** A hamstring
stretch must not light up the body map. `VOLUME_CATEGORIES` — `strength`,
`powerlifting`, `olympic weightlifting`, `strongman` — lives in `exercises.py` as
catalog vocabulary; the multiplication lives in `summary.py` as an aggregation
rule, preserving the layer split.

`schema.sql` does not change. `sets INTEGER NOT NULL CHECK (sets > 0)` still
stores what the user did; only the per-muscle aggregate is fractional.

This replaces the CLAUDE.md invariant "a set counts once per muscle group it
targets".

## Muscle map, 7 → 12

Preserving the disjoint-views rule:

- **Front:** chest, abs, shoulders, biceps, forearms, quads
- **Back:** back, traps, triceps, glutes, hamstrings, calves

Targets stay two-tier. Large (20): chest, back, shoulders, quads, hamstrings,
glutes. Small (10): abs, biceps, triceps, forearms, traps, calves.

Three of the five additions are reversals of stated decisions, not new paths:

- **`traps` moves out of `back`.** The existing `back-traps` path carries
  `data-muscle="back"`; its slug is reassigned. This reduces every historical
  `back` count — a data-comparability change, not just a rendering one.
- **`glutes`, `calves` and `forearms` were documented as deliberate gaps** in the
  `_body_figure.html` header comment and the ARCHITECTURE body-map section. Both
  documents are corrected in the same change.
- **`shoulders` has no geometry to overlay.** The torso runs into the upper arms
  at a bare corner. This needs new `.body-base` deltoid geometry, not just a
  `.muscle` path.

## Selection UI

873 server-rendered radios is not a page, so `/log` stops receiving the catalog
and renders a picker shell that its JS module fills. Three access paths over one
client-side fetch:

1. **Recent** — default view, from entry history. The 90% path.
2. **Search** — substring match over name, equipment and muscle labels.
3. **Browse** — muscle group → equipment → exercise.

The selected exercise renders a card with its two frames cross-fading in CSS —
stacked `<img>` elements on a `steps(1)` animation, no JS timer. Under
`prefers-reduced-motion` the animation is disabled and frame 0 shows.

## API

`GET /api/exercises` returns a **light** payload — no instructions, no image
paths. 186 KB, roughly 35 KB gzipped, which is a reasonable one-time cost for a
fully client-side filter.

Two endpoints the roadmap did not budget for, both falling out of 873 rather than
180 entries:

- `GET /api/exercises/<id>` — full record with instructions and absolute image
  URLs. Avoids shipping 850 KB to render one card.
- `GET /api/exercises/recent` — the Recent tab reads entry history, which is a
  database query and cannot be done client-side.

`GET /api/summary/week` is unchanged in shape; its `sets` values become floats.

## Images

No image bytes in the repo — 1,746 files at roughly 85 MB. `EXERCISE_IMAGE_BASE`
defaults to
`https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db@b0eed061e1c832b3ed815fbaa4b45b3cdc14df49/exercises`,
pinned to the SHA so the assets cannot shift underneath us, and swappable to a
self-hosted origin in one config line.

## Migration

`flask --app app remap-exercises` rewrites the four retired ids in place:

| Old | New |
| --- | --- |
| `bench_press` | `Barbell_Bench_Press_-_Medium_Grip` |
| `pull_ups` | `Pullups` |
| `squat` | `Barbell_Squat` |
| `sit_ups` | `Sit-Up` |

It reports how many rows moved and is safe to run twice.

## Testing

- `tests/test_pages.py` asserts every muscle region renders, so it fails loudly on
  a half-finished body map. The front/back disjointness assertion is updated to
  the new six-and-six split.
- New coverage: the catalog loads and validates, muscle slugs are all known,
  weighting produces the expected fractional totals, non-strength categories grade
  zero, and the new endpoints return the documented shapes.
- `tests/test_summary.py`'s integer equality assertions move to the weighted
  values.

## Docs updated in the same change

Required by the read-before-edit protocol in CLAUDE.md:

- **CLAUDE.md** — the 7-group, flat-`muscles` and set-counting invariants.
- **docs/ARCHITECTURE.md** — layer table, volume scale, body-map table, single
  source of truth.
- **docs/API.md** — every affected payload.
- **docs/ROADMAP.md** — Phase 2 marked done with divergences; Phase 9 collapsed
  into it; open decisions 1, 4 and 6 resolved.
- **`_body_figure.html`** header comment — the deliberate-gaps reversal.
- **README.md**, **CHANGELOG.md**.
