# Redesign brief — dark, instrument-like UI overhaul

Agent brief for the Phase 4.5 UI revamp. Written for a Claude Code session with this
repo open. Everything stack-specific below is fact, not preference — verify against
the docs it cites before overriding any of it.

**Prerequisite: Phase 4 is merged.** The set grid, rest timer and unit toggle are the
most interaction-heavy surfaces in the app and this redesign restyles them; starting
before they exist means doing `/log` twice.

---

## Context — the real stack

- Flask + Jinja server-rendered shells; every dynamic byte fetched by a per-page
  vanilla ES module from `/api`. **Zero JS dependencies, no bundler** — JS is served
  as written, and that rule survives this redesign.
- Tailwind v4 + daisyUI, compiled by an **npm-free** toolchain
  (`python tools/fetch_css_toolchain.py`, then `tools/tailwindcss -i app/static/css/input.css
  -o app/static/css/styles.css --minify`). `styles.css` is committed build output —
  never hand-edit it.
- Config is CSS-first: tokens in `@theme`, the theme pair in two
  `@plugin "daisyui/theme"` blocks, content globs as `@source` directives in
  `input.css`. **A new template directory or page needs a new `@source` line.**
- Pages: `/` (static landing, no JS), `/calendar`, `/log`, `/summary` — plus a new
  `/progress` page this brief adds.
- Primary user: one lifter, logging on a phone mid-session. Design for a hand that
  is holding a barbell, not a dashboard reviewer.

**Read first, in this order — this is repo protocol, not a suggestion:** `CLAUDE.md`,
`docs/ARCHITECTURE.md` (styling and volume-scale sections), `docs/VOLUME_SCIENCE.md`
(product-voice rules). Update each doc you contradict **in the same commit** as the
change.

## Ground rules

- **Presentation layer only.** No schema changes, no migrations, no service-layer
  changes. A new **read-only** API endpoint is allowed where a visualization needs
  data no current endpoint serves — documented in `docs/API.md` in the same commit,
  with SQL in `app/models.py` only, per the layer rules.
- **No new dependencies.** No npm, no React, no Radix/Motion/shadcn/d3, no charting
  library. Canvas and hand-written code. Fonts come from Google Fonts in
  `base.html`, nothing self-hosted, nothing else.
- Every class a JS module toggles at runtime is **hand-written in `input.css`'s
  `@layer components`** — Tailwind purges interpolated class names silently.
- Work on a branch named `redesign`. (This deliberately overrides CLAUDE.md's
  work-on-main rule for this effort — the user chose the branch.)
- Run `pytest` before every commit. One commit per screen. `tests/test_pages.py`
  asserts page markers and body-map structure — keep it green or update it with
  reasons.

## Invariants that survive the redesign — revised, not deleted

The current design system is being replaced, but four of its rules are product
decisions, not styling:

1. **The volume ramp must win the eye.** Today that is enforced by an achromatic
   base palette. The new palette has chromatic accents, so the rule changes form:
   nothing on `/summary` or the body map may compete with the ramp in saturation or
   area. State in your plan how the new palette preserves this.
2. **Named problem your plan must solve explicitly: the accent/over-target
   collision.** The primary accent is a muted brick red; the ramp's over-target
   scale is also red (`--color-over-light/dark`). If they are confusable, the body
   map starts reading as decoration. Re-derive the ramp endpoints for the dark
   ground so "over target" remains unmistakably distinct from ordinary accented UI
   — or move the accent's hue. Do not quietly ship both reds.
3. **The ramp is continuous.** `--level` is a 0–1 custom property mixed with
   `color-mix`; it cannot become utility classes without visible banding. Keep the
   hand-written `.muscle`/`.muscle-row` rules, restyled. `.is-over` stays after
   `.is-worked` in the stylesheet.
4. **Product voice holds.** Regions never take ramp colours or targets; no
   "optimal", no ranges printed as advice; labels name what the user controls, in
   sentence case, in plain verbs. `docs/VOLUME_SCIENCE.md` rules out several
   obvious-seeming moves with reasons — read it before inventing a number.

**Themes:** dark becomes the default. Propose in your plan whether the light theme
is re-derived from the new tokens or retired outright, and carry the answer into
`CLAUDE.md` and `ARCHITECTURE.md`.

## Process — before writing code

1. Read every template and its paired JS module. List each screen, its job, and its
   current component structure. Do not design until you can name what each screen
   is for.
2. Write a design plan: 5–6 named colour tokens (they live in `@theme` and the
   daisyUI theme block — that *is* the token file), two typefaces with defined
   roles plus a tabular-figure monospace for every number in the app, a layout
   concept, and one signature element (the training graph below).
3. Critique your own plan. For each choice ask: "would I have produced this for any
   fitness app?" If yes, revise it and say what changed and why.
4. **Present the plan for approval before building.** Use plan mode; do not start
   restyling on your own judgment.
5. Build. Screenshot every screen at 390×844 with the Playwright tools, critique
   the result against the plan, and fix what doesn't hold up.

## Visual direction

Dark, dense, and instrument-like — closer to a telemetry readout or a lab
instrument than to a consumer wellness app. Confident, high-contrast, slightly
severe.

**Palette** — near-black ground (a very dark desaturated blue-black, never
`#000000`, so surfaces can layer), muted brick red as the primary accent, cold
slate blue as the secondary, warm off-white for data marks. Not neon, not
saturated. The red reads as oxidized, not as an alert — and see invariant 2 above
before fixing its hex. Derive exact values yourself and name them in the theme
block; raw hex values appear nowhere outside it.

**Type** — a characterful display face paired with a neutral body face, and a
tabular-figure monospace for weights, reps, times and percentages so digits don't
shift width as they change. The current single-family setup (Archivo, three
voices: `.type-display`, `.type-label`, `.type-lede`) is the structure to replace
or extend deliberately — keep the "three named voices, no ad-hoc stacks" rule even
if every face changes.

**Density** — this app is read by someone holding a barbell. Information density
beats whitespace: tight leading, real data on screen, minimal decorative padding.

**Motion** — CSS only (no animation library exists or gets added). One
orchestrated moment, not scattered effects. Respect `prefers-reduced-motion`.
The existing image cross-fade on `/log` (`steps(1)` on stacked frames) stays.

### Banlist

None of the following appear anywhere in the output:

- Purple-to-blue or any multi-stop gradient background
- Glassmorphism, frosted panels, `backdrop-blur` on cards
- Uniform large border-radius on every surface
- Emoji in headings, labels, or empty states
- Inter, or the default system stack, as the display face
- Centered hero with a blurred colour blob behind it
- Soft drop shadows faking elevation — the repo already sets `--depth`/`--noise`
  to 0 and separates with hairline borders; keep that discipline on the dark ground
- Scroll-triggered fade-ins on sections
- Marketing copy ("Track your progress like never before")
- Any new package manager, dependency, or hand edit to `styles.css`

## Mobile

Mobile is the primary target; desktop is the adaptation. Design at 390×844 first,
verify at 360px and 430px.

- Every interactive target ≥44pt. Primary actions in the bottom third, reachable
  one-handed.
- Nothing important depends on hover; every hover affordance has a tap equivalent.
- Safe-area insets respected top and bottom.
- **Logging a set is the hot path**: reachable in ≤2 taps from app open,
  completable without leaving the keyboard-adjacent zone.
- The rest timer persists across page navigations — its state is already
  client-side; back it with `localStorage` and render it from the shared base
  template so navigating to `/calendar` doesn't kill the countdown.
- Numeric inputs use `inputmode` for the numeric keypad and select-on-focus.
- No horizontal scroll at any breakpoint. Test with the catalog's longest
  exercise names.

## Signature element: the training graph

A force-directed graph on a **new `/progress` page** (shell in `views.py`,
`progress.html`, `progress.js`, nav link, `@source` already covers the template
dirs — verify). Reference aesthetic: dark field, small dense nodes, thin red
edges, a few larger nodes, occasional off-white and slate-blue marks, sparse
orphan nodes trailing on the outer edge. It never appears in the logging flow.

**Encodings — scoped to data that exists.** (The original concept coloured nodes
by estimated 1RM against a bodyweight-relative strength standard. That is a
**Phase 7 upgrade**: the app stores no bodyweight, computes no 1RM, and pre-Phase-4
history has `NULL` weights. When Phase 7 lands it, keep the honesty rule: a lift
with no benchmark renders as a hollow ring, never a guess.)

- **Node** = an exercise that has been logged.
- **Edge** = two exercises performed on the same `entry_date`; opacity scales with
  co-occurrence count.
- **Node size** = cumulative non-warmup sets in the selected window (volume-load
  where weights exist is a refinement, not the default — most history has none).
- **Node colour** = the current weekly coverage state of the exercise's primary
  muscle (`rest`/`trained`/`over`), i.e. the app's own thesis: the graph shows
  where your training lives and what it feeds. No invented benchmarks.
- **Orphan nodes** = exercises logged fewer than 3 times, or not in 8 weeks; they
  drift to the outside. They are the insight: neglected movements.

**Data**: one new read-only endpoint (e.g. `GET /api/progress/graph?window=8w|6m|all`)
returning per-entry `(date, exercise_id, set_count)` plus whatever the colour
encoding needs — shaped in `models.py`/`api.py` per the layer rules, documented in
`docs/API.md`. **Tap a node** → a small panel with the exercise's name, muscles,
and its last logged sets via the existing `GET /api/exercises/<id>/last-sets` —
there is no history page until Phase 7, so link no further than data that exists.

**Interaction**: tap to open the panel, pinch to zoom, drag to pan, a time-window
control (8 weeks / 6 months / all time) that re-renders.

**Performance — not optional:**

- Canvas, not DOM/SVG nodes. The force simulation is hand-written (no d3): a
  simple repulsion/spring/centering loop is ~100 lines and plenty at this scale.
- Run the simulation once, cache positions keyed by a hash of the underlying data,
  and re-run only when the data changes. Never simulate on every mount.
- Seed the layout deterministically — a graph that rearranges itself on every
  visit is unreadable as a mental map.
- Hold 60fps while panning with 250 nodes on a mid-range phone; reduce visual
  fidelity before frame rate.
- Degrade honestly: under ~15 logged exercises the graph is meaningless. Show a
  simpler view and say what unlocks the graph.

## Deliverables

1. The design plan and self-critique, presented for approval before any code.
2. The revised `@theme` + daisyUI theme block as the single source of tokens.
3. Rebuilt screens, one commit per screen, suite green at each.
4. The training graph as an isolated module (`progress.js` + a pure layout
   function that is testable without a canvas).
5. Screenshots of every screen at 390×844.
6. Doc updates riding in the same commits: `ARCHITECTURE.md` styling section,
   `CLAUDE.md`'s theme/palette invariants, `docs/API.md` for the new endpoint,
   and the roadmap's Phase 4.5 section marked done with divergences noted.
7. A short list of anything that couldn't be done without touching the data layer.

## Quality floor

Visible keyboard focus states. Reduced motion respected. Contrast ratios meet
WCAG AA against the dark ground — check the brick red specifically; muted reds
fail easily on near-black. No layout shift on data load.
