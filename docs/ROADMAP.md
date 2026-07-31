# Roadmap

Technical plan for taking Body Shop from a single-user local Flask app to a hosted,
multi-user product.

This file now tracks only the current, prioritized path forward. The implementation
history and retired tradeoffs live in [ARCHITECTURE.md](ARCHITECTURE.md).

Current state: **Phases 1, 2, 3, 4, and 4.5 are done**, and **Phase 9 was absorbed into
Phase 2**. The app already has Tailwind v4 + daisyUI, 873 exercises with images across
12 muscle groups, Alembic migrations on SQLite/Postgres, per-set weight/reps/RPE, and
the dark instrument-style UI with `/progress`.

## Prioritized roadmap

### 1. Phase 5 — Secure user login

This is the next hard dependency. Everything user-owned depends on it.

- Add ownership to every user data model and query.
- Decide auth with a strong default toward Supabase Auth + bearer tokens.
- Add in-app account deletion and a migration/backfill plan for existing rows.
- Keep the CSRF and cookie-session question aligned with the auth choice.

### 2. Phase 6 — Stack decision and deployment

Deploy the current Flask app before adding more product surface.

- Prefer Flask unless a measured constraint forces a rewrite.
- Choose Vercel only if it wins on record; otherwise use a container host.
- Add the launch floor: backups with tested restore, error monitoring, privacy policy,
  and CSV export.
- Keep production gated on the Postgres CI job.

### 3. Phase 7 — Training essentials

This is the parity phase. It should make the app feel complete next to mature trackers.

- Add 1RM estimates, PR detection, per-exercise progress graphs, and body metrics.
- Add entry and set editing.
- Add routines and templates; this is the expensive core of the phase.
- Keep the volume-coverage model intact while adding the parity features.

### 4. Phase 8 — AI-assisted custom exercises

Only build this after the catalog has been in front of real users long enough to show
what it misses.

- Measure the miss rate before building.
- Classify into the existing muscle and facet vocabulary.
- Require user review before saving any AI suggestion.
- Log corrections so the prompt can be tuned against real misses.

### 5. Phase 10 — Mobile, watch, and store distribution

This is last because it consumes the earlier phases.

- Ship a native client or a truly native-capable shell, not a wrapped website.
- Support offline queueing and replay.
- Add watch logging and rest timers.
- Close the store requirements: privacy policy, privacy labels, data safety, and
  account deletion.

## Already shipped

- Phase 1: Tailwind + DaisyUI, CSS-only build step.
- Phase 2: exercise catalog and muscle map, with images folded in.
- Phase 3: Alembic migrations and Postgres support.
- Phase 4: set-level logging, derived volume, previous values, rest timer, plate
  calculator.
- Phase 4.5: dark redesign and the `/progress` training graph.

## Later, if the product earns it

- Auto-progression and programming.
- Social features.
- Nutrition tracking.
- Recovery-aware programming.
- Conversational AI coaching.

## Dependency shape

The live chain is simple:

```mermaid
graph TD
  P5[Phase 5: Secure user login] --> P6[Phase 6: Deploy]
  P6 --> P7[Phase 7: Training essentials]
  P5 --> P8[Phase 8: AI custom exercises]
  P6 --> P8
  P7 --> P10[Phase 10: Mobile/watch/store]
  P5 --> P10
```

Phase 5 gates ownership and account deletion. Phase 6 gates launch. Phase 7 is the
competitive parity floor. Phase 8 depends on actual usage. Phase 10 depends on all of
the above.