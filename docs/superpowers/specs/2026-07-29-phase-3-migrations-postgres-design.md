# Phase 3 — Foundations: migrations and Postgres

Design for [ROADMAP.md](../../ROADMAP.md) Phase 3, as built. Written before
implementation; divergences from the roadmap's plan are called out inline and
folded back into the roadmap when the phase lands.

No user-visible change. No endpoint, request field or response field moves, so
[API.md](../../API.md) is untouched — that is the check that this phase stayed in
its lane.

## What changes

| Before | After |
| --- | --- |
| `app/schema.sql`, applied whole | `app/tables.py` (SQLAlchemy `MetaData`) plus Alembic revisions |
| `sqlite3` with `?` placeholders | SQLAlchemy Core, one dialect-agnostic layer |
| SQLite only, path in `BODYSHOP_DATABASE` | SQLite **or** Postgres, URL in `DATABASE_URL` |
| `create_app` mkdirs and runs `schema.sql` at factory time | Factory is side-effect-free; dev convenience lives in `run.py` |
| `flask --app app remap-exercises` | Revision `0002`, a data migration |
| `SECRET_KEY` silently defaults in production | `ConfigError` at startup on the resolved value |
| CI: SQLite only | CI: SQLite matrix **and** a `postgres:16` service container |

## Decisions taken before building

1. **SQLAlchemy Core with `Table` metadata**, not `psycopg` with `%s` and not the
   ORM. The deciding argument is that **Alembic depends on SQLAlchemy anyway** —
   the `psycopg` route means installing SQLAlchemy regardless and then
   hand-rolling the dialect differences beside it (`lastrowid` vs `RETURNING`,
   `AUTOINCREMENT` vs `IDENTITY`, `datetime('now')` vs `now()`). Core costs no new
   dependency and hands Alembic a `target_metadata` so Phases 4 and 5 can
   autogenerate. The ORM would restructure the model layer now, for relationships
   nothing needs yet.
2. **`entry_date` becomes a real `DATE`.** The roadmap flags the lexicographic
   `BETWEEN` trick for revisiting against a real column; this is the moment, since
   doing it later is another migration. On SQLite the stored representation is
   unchanged (`YYYY-MM-DD` text), so the comparison stays chronologically correct;
   Postgres gets real date semantics. `created_at` becomes `timestamptz` for the
   same reason. **The ISO-8601 rule survives where it was actually load-bearing:**
   the API still speaks `YYYY-MM-DD` strings in both directions, and the backend
   still performs no time-zone conversion.

   > **Corrected during implementation.** This was specced as one
   > `batch_alter_table` call. That silently destroys the data:
   > `SQLiteImpl.cast_for_batch_migrate` adds a `CAST` to the table-copy whenever type
   > affinity changes, and `CAST('2026-07-28' AS DATE)` in SQLite is
   > `CAST(… AS NUMERIC)`, which prefix-parses to the integer `2026`. Revision `0003`
   > branches by dialect instead — Postgres converts with `USING`, SQLite re-declares
   > the columns and copies values verbatim. The claim below about passing the CHECK
   > constraint through `table_args` was also wrong: SQLAlchemy **does** reflect SQLite
   > CHECK constraints, so doing that produced a duplicate.
3. **`remap-exercises` is deleted, folded into revision `0002`.** The roadmap says
   fold *or* delete; folding leaves one mechanism for changing exercise ids
   instead of two.
4. **Three revisions, not one baseline.** Slightly redundant on a fresh Postgres —
   `0001` creates a TEXT column that `0003` converts — but it is an honest upgrade
   path for any collaborator's local database that already holds entries, and it
   exercises `batch_alter_table` before Phase 5's `user_id` sweep depends on it.
5. **The instance `config.py` stays.** The roadmap asks whether it survives,
   because it can override `BODYSHOP_SECRET_KEY` without appearing in the repo and
   would make a naive check bypassable. Keeping it is right — it is a legitimate
   way to hold a secret outside version control — so the check moves instead: it
   validates the **resolved** config inside `create_app`, after all three layers
   are applied, rather than the class attribute or the environment variable.

## Schema source of truth

`app/tables.py` holds a `MetaData` with a constraint `naming_convention` and one
`Table`. `app/schema.sql` is deleted.

The naming convention is not decoration: SQLite's `batch_alter_table` rebuilds a
table and must be able to name the constraints it recreates. Phase 5 adds a
column with a `REFERENCES` clause to this table, which is exactly the operation
that needs it.

One consequence found in implementation: **Alembic applies this convention on top of
whatever name a revision passes**, so revisions must pass bare tokens
(`sets_positive`) rather than finished names, or the result is double-prefixed.

```python
workout_entry = sa.Table(
    "workout_entry", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("entry_date", sa.Date, nullable=False),
    sa.Column("exercise_id", sa.Text, nullable=False),
    sa.Column("sets", sa.Integer, nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True),
              nullable=False, server_default=sa.func.now()),
    sa.CheckConstraint("sets > 0", name="sets_positive"),
    sa.Index("idx_workout_entry_date", "entry_date"),
)
```

## Connection layer

`app/db.py` keeps `get_db()` as its public name, now returning a request-scoped
Core `Connection` cached on `g`. That is deliberate: the *SQL-only-in-models.py*
invariant reads identically afterwards, and `models.py` is the only caller that
changes shape.

- **Engine per process**, built lazily and cached on `app.extensions`. Building it
  per request would defeat pooling.
- **Postgres:** `poolclass=NullPool` and `connect_args={"prepare_threshold": None}`.
  Supabase's transaction pooler (port 6543) cannot carry server-side prepared
  statements, and `None` is what disables them in psycopg 3 — `0` means "prepare
  on first execution", which is the opposite, and is the setting most guides get
  backwards. `NullPool` is correct behind an external pooler and required once
  Phase 6 puts this in a serverless function.
- **SQLite:** `PRAGMA foreign_keys = ON` via a `connect` event listener, preserving
  today's behaviour.

## Migrations

Plain Alembic, `alembic.ini` at the repo root and a `migrations/` package. No
Flask-Migrate: it wraps the CLI we would otherwise call directly, and this repo
pins dependencies sparingly.

`migrations/env.py` resolves the URL from app config, so `alembic upgrade head`
works with no environment variables in dev. `render_as_batch=True` and
`compare_type=True`.

| Revision | Does |
| --- | --- |
| `0001` | Baseline: `workout_entry` exactly as `schema.sql` had it, so an existing database can be `alembic stamp 0001`'d and carried forward |
| `0002` | Data: rewrites the four retired exercise ids, replacing the `remap-exercises` command |
| `0003` | `entry_date` → `DATE`, `created_at` → `timestamptz`, branching by dialect |

Revision `0002` **inlines its own copy** of the id mapping rather than importing
`exercises.RETIRED_EXERCISE_IDS`. A migration is a historical record; importing a
constant that can change under it makes what the migration did depend on when it
was run.

## Boot behaviour

`ensure_db()` is deleted. It is the roadmap's single biggest conflict with
migrations — it applies `schema.sql` whenever `workout_entry` is missing, so a
fresh deploy silently gets an unversioned schema Alembic has no revision to
stamp — and it is one of the two lines that would crash `create_app` on a
read-only filesystem.

After this phase `create_app` touches no filesystem and runs no DDL. The
instance-folder `mkdir` happens only when the resolved URL is a file-backed SQLite
database inside it. Dev's zero-setup convenience moves to `run.py`, the dev entry
point, which upgrades before serving; `wsgi.py` and Phase 6's Vercel entry point
import the factory and never migrate.

CLI: `init-db` becomes a dev-only reset (drop everything, then `upgrade head`)
that refuses to run under production config, and a new `upgrade-db` wraps
`alembic upgrade head`.

## Configuration

`DATABASE_URL` replaces `BODYSHOP_DATABASE`, normalised so Supabase's
`postgres://` form becomes `postgresql+psycopg://` — SQLAlchemy rejects the bare
`postgres://` scheme that most providers hand out. `BODYSHOP_DATABASE_URL` takes
precedence when both are set, keeping the app's own namespace available while
still reading the name every host supplies.

`.env.example` is committed; `.env` is gitignored. `python-dotenv` earns its place
as a dependency because Flask's CLI loads `.env` natively when it is installed, so
`flask --app app upgrade-db` sees the same configuration `run.py` does.

Under production config, `create_app` raises `ConfigError` when `SECRET_KEY` is
missing or still `dev-secret-change-me`, or when `DATABASE_URL` is unset or points
at SQLite.

## Testing

The per-test SQLite file in `tmp_path` stays the default — it is fast and the
isolation is genuinely good.

Setting `BODYSHOP_TEST_DATABASE_URL` points the whole suite at a real Postgres
instead. There, the schema is created **once per session by `alembic upgrade head`**,
so the verification run proves the migration chain rather than just the queries,
and each test `TRUNCATE`s. Truncating is one round trip where a drop-and-recreate
is a schema rebuild — the difference is minutes against a remote database.

Three new tests:

- **Migration/metadata drift** — `alembic upgrade head` on a scratch database
  produces the same tables, columns, types and indexes as `metadata.create_all()`.
  This catches editing `tables.py` and forgetting the revision, which is the
  failure mode this phase introduces.
- **Revision `0002`** actually remaps the retired ids, replacing the deleted CLI's
  test in `test_models.py`.
- **Production config** raises on a default secret and on a SQLite URL.

CI keeps the SQLite matrix unchanged and gains a `test-postgres` job on a
`postgres:16` service container, so dialect differences surface on every push.

## Blast radius

| File | Change |
| --- | --- |
| `app/tables.py` | New — schema source of truth |
| `app/schema.sql` | Deleted |
| `app/db.py` | Rewritten onto an engine; `ensure_db` and `remap-exercises` gone, `upgrade-db` added |
| `app/models.py` | Every query ported to Core; `remap_exercise_ids` deleted; date coercion at the boundary removed |
| `app/config.py` | `DATABASE_URL`, URL normalisation, `ConfigError`, `CONFIG_NAME` |
| `app/__init__.py` | Side-effect-free; validates the resolved config |
| `run.py` | Upgrades before serving |
| `alembic.ini`, `migrations/` | New |
| `tests/conftest.py` | `DATABASE_URL`; dual-dialect fixtures |
| `tests/test_models.py` | Remap test → migration test |
| `tests/test_config.py` | New |
| `tests/test_migrations.py` | New |
| `.env.example`, `requirements.txt`, `pyproject.toml`, `.github/workflows/ci.yml` | Dependencies and env |

Docs updated in the same commits: CLAUDE.md (commands, the dates-at-rest and
`schema.sql` invariants, the no-migrations line), ARCHITECTURE.md (layer table,
data model, testing, limitations), ROADMAP.md (Phase 3 → done), README,
CHANGELOG. API.md needs no change.

## Out of scope

Deliberately left for the phases that own them: no `user_id` and no auth
(Phase 5), no `workout_set` table (Phase 4), no `vercel.json` or deployment
config (Phase 6). This phase's job is to make those three possible, not to
anticipate them — beyond the naming convention, which is free now and awkward
later.
