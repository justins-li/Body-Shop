# Body Shop

> Follow a routine or log your own sets, and see at a glance which muscle groups you actually trained this week.

Body Shop is a small Flask + vanilla JS web app. You pick a date, log the sets you
finished — with weight, reps and RPE if you want them — and the weekly summary paints a
body outline: each muscle group **brightens toward green** as it works toward its weekly
set target, then turns **red** for every set past it.

Targets start at 20 sets a week for the large groups (chest, back, shoulders, quads,
hamstrings, glutes) and 10 for the small ones (abs, biceps, triceps, forearms,
traps, calves), and the **trainer setup** on `/summary` scales them: tell it whether you
are a beginner, experienced or advanced, and how many sessions of how many minutes you
intend to train, and every target moves together. Your target is the smaller of what
your experience asks for and what your week can hold — nothing ever drops below four
sets, the point at which a muscle stops responding at all.

**873 movements**, each with two photographs that alternate to show the movement,
are catalogued from [free-exercise-db](https://github.com/yuhonas/free-exercise-db).
A set counts toward every group the movement trains, weighted by how directly:

```
3 sets of barbell bench press
  → chest      +3     (primary)
  → shoulders  +1.5   (secondary)
  → triceps    +1.5   (secondary)
```

So per-group totals are fractional — `12.5 / 20` is a normal reading. Stretches,
cardio and plyometrics are loggable but don't count toward volume; a hamstring
stretch is not hamstring training.

The front figure shows chest, abs, shoulders, biceps, forearms and quads; the back
figure shows back, traps, triceps, glutes, hamstrings and calves. No group appears
on both, so the two outlines tell you different things.

## Pages

| Page | Route | What it does |
| --- | --- | --- |
| **Home** | `/` | What the app does, and the way in. Static — no API calls. |
| **Routines** | `/routines` | Five sessions worth following — push, pull, legs, a beginner full body, an athletic whole-body day. Each says how long it takes (derived from its sets, not typed), shows every movement's photographs and how to do it, and puts a **log button** beside each one that writes straight into the week. |
| **Log workout** | `/log` | Pick date → exercise → sets, with weight, reps and set type per row (RPE too, on the advanced trainer setup), prefilled from last time. The weight column follows the equipment: a barbell gets a plate breakdown, a dumbbell asks per bell, a cable asks for the pin setting, and a pull-up asks for nothing unless you tick "Added weight". A repeat button copies the set you just entered. The picker has three ways in: recent, browse by muscle, and search (`incl db` finds "Dumbbell Incline Bench Press"). Shows and deletes the entries for that day. |
| **Weekly summary** | `/summary` | Front/back body map shaded by weekly volume, each group's sets against its target, and where inside six of them the work landed. Also the trainer setup, and the calendar: seven boxes for this week, expanding to the month when you want it. |
| **Training graph** | `/progress` | Every movement you have logged, joined to the ones you do on the same day. It draws from your very first workout and fills in as you train. Node size is either the sets a movement carried or your best lift on it, estimated from your own weight × reps — a movement with no load recorded stays a hollow ring rather than pretending to be small. The movements that have fallen out ring the outside, and are named underneath. |

Every page shares a `?date=YYYY-MM-DD` query parameter, so navigating between them
keeps the day you were looking at. `/calendar` was its own page until the month grid
folded into the weekly summary; it still redirects, so old links land on the right week.

Logging from a routine and logging on `/log` are **the same grid** — the weight column
follows the equipment, bodyweight movements ask for nothing unless you tick "Added
weight", and a set recorded either way reaches the summary identically.

The interface is dark and dense by design — it is read on a phone, mid-session, with a
barbell in the other hand. The volume ramp is the only saturated colour in it.

## Quick start

```bash
git clone https://github.com/<you>/Body-Shop.git
cd Body-Shop

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python run.py
```

Open <http://127.0.0.1:5000>. `run.py` applies migrations before serving, so a SQLite
database appears at `instance/bodyshop.sqlite3` on first run with no setup step.

Nothing else is needed to run or change the app — the compiled stylesheet is committed.

## The database

SQLite by default, Postgres when `DATABASE_URL` is set. Schema changes are Alembic
revisions; `app/tables.py` describes the schema and `migrations/versions/` is how a
database gets there.

```bash
flask --app app upgrade-db        # apply migrations — this is the deploy step
flask --app app init-db           # drop everything and migrate up (destroys data; dev only)
flask --app app stamp-db 0001     # for a database created before migrations existed
```

Plain Alembic works too, against the same `DATABASE_URL`:

```bash
alembic revision -m "add a thing" --autogenerate
alembic history
alembic downgrade -1
```

To run against Postgres, copy `.env.example` to `.env` and set `DATABASE_URL`. With
Supabase, use the **transaction pooler** (port 6543) for the app and the **session
pooler or direct connection** (port 5432) for migrations; `.env.example` explains why.

**Changing `app/tables.py` requires a revision in the same commit.** The test suite
builds SQLite from the metadata, so a missing revision leaves the tests green and the
migrated schema wrong — `tests/test_migrations.py` is what catches it.

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

Each test gets its own SQLite file, so order never matters. To run the same suite
against Postgres — which is how dialect differences surface, and what CI does on a
`postgres:16` container:

```bash
BODYSHOP_TEST_DATABASE_URL=postgresql://user:pass@host:5432/scratch pytest
```

That database is truncated between tests, so point it at a scratch one.

## Editing the styles

The UI is Tailwind v4 + daisyUI. `app/static/css/input.css` is the source;
`app/static/css/styles.css` is generated output and should never be edited by hand.
The toolchain needs **no npm** — Tailwind ships a standalone binary and daisyUI is a
tarball of CSS:

```bash
python tools/fetch_css_toolchain.py   # once, into gitignored tools/
tools/tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --watch
```

Commit the rebuilt `styles.css` with your change; CI does not build it.

## Configuration

Everything is environment-driven; nothing is required for local development. Values are
read from the environment and from a gitignored `.env` — see `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BODYSHOP_CONFIG` | `development` | `development`, `testing` or `production`. |
| `BODYSHOP_SECRET_KEY` | `dev-secret-change-me` | Flask secret key. **Production refuses to boot without a real one.** |
| `DATABASE_URL` | a SQLite file in `instance/` | SQLAlchemy URL. A provider's `postgres://` string works as pasted. Production refuses SQLite. |
| `BODYSHOP_DATABASE_URL` | — | Wins over `DATABASE_URL`, for pointing the app somewhere other than what a host injected. |
| `BODYSHOP_TEST_DATABASE_URL` | — | Runs the test suite against this database instead of SQLite. Truncated between tests. |
| `BODYSHOP_WEEK_STARTS_ON` | `1` (Monday) | ISO weekday the summary week begins on. |
| `BODYSHOP_EXERCISE_IMAGE_BASE` | jsDelivr, pinned | Origin serving `<exercise_id>/<0\|1>.jpg`. Set this to self-host the images. |
| `BODYSHOP_HOST` / `BODYSHOP_PORT` | `127.0.0.1` / `5000` | Dev server bind address. |

`BODYSHOP_DATABASE` (a bare SQLite path) was replaced by `DATABASE_URL` in Phase 3.

For production, serve the WSGI app instead of `run.py` and migrate as a deploy step —
`wsgi.py` deliberately does not, so that importing the app never changes a schema:

```bash
pip install gunicorn
export BODYSHOP_CONFIG=production
export BODYSHOP_SECRET_KEY=...            # python -c "import secrets; print(secrets.token_urlsafe(48))"
export DATABASE_URL=postgresql://...
flask --app app upgrade-db
gunicorn "wsgi:application"
```

## Project layout

```
Body-Shop/
├── app/
│   ├── __init__.py           # application factory
│   ├── config.py             # environment-driven settings
│   ├── db.py                 # engine, request-scoped connection, migration CLI
│   ├── tables.py             # the schema, as SQLAlchemy metadata
│   ├── exercises.py          # catalog loader, muscle groups, baseline targets, weight modes
│   ├── routines.py           # suggested sessions, with derived time estimates
│   ├── training.py           # trainer setups: how experience and time scale the targets
│   ├── data/exercises.json   # 873 vendored movements — generated, never hand-edited
│   ├── models.py             # all SQL lives here: validation + queries
│   ├── views.py              # the six HTML page routes
│   ├── api.py                # /api JSON endpoints
│   ├── services/
│   │   ├── weeks.py          # week/month boundary maths
│   │   ├── summary.py        # weekly muscle-coverage aggregation
│   │   ├── strength.py       # personal bests, estimated from your own sets
│   │   └── graph.py          # training-graph windows, orphans, node colouring
│   ├── templates/            # Jinja2: base + one per page + body-map partial
│   └── static/
│       ├── css/input.css     # design system — the file you edit
│       ├── css/styles.css    # compiled output — generated, committed
│       └── js/               # api.js, ui.js, setgrid.js, one module per page, + layout.js
├── migrations/               # Alembic: env.py + versions/
├── alembic.ini
├── tools/                    # fetch_css_toolchain.py, build_exercise_catalog.py
├── tests/                    # pytest suite (catalog, API, pages, aggregation, migrations)
├── docs/                     # architecture + API reference
├── .env.example              # copy to .env
├── run.py                    # dev entry point — migrates, then serves
└── wsgi.py                   # production entry point — never migrates
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the layers fit together and
[docs/API.md](docs/API.md) for the endpoint reference.
[docs/VOLUME_SCIENCE.md](docs/VOLUME_SCIENCE.md) is the evidence behind the set targets,
the primary/secondary weighting and the region breakdown — including which numbers are
sourced and which are convention. [docs/ROADMAP.md](docs/ROADMAP.md) specifies where it's
going next.

## The exercise catalog

The 873 movements in [`app/data/exercises.json`](app/data/exercises.json) are
**generated, not written**. `tools/build_exercise_catalog.py` fetches
[free-exercise-db](https://github.com/yuhonas/free-exercise-db) at a pinned commit and
maps its 17 muscle slugs onto our 12. Don't hand-edit the JSON — change the pin or the
mapping and re-run:

```bash
python tools/build_exercise_catalog.py
```

Like the stylesheet, the *output* is committed, so running the app or CI never needs
the network. [`app/exercises.py`](app/exercises.py) validates it at import — unique ids,
known muscle slugs, a non-empty primary, exactly two images — and refuses to load a
catalog that fails any of those.

Images aren't in the repo (1,746 files, ~85 MB); they're served from jsDelivr at the
same pinned commit. Point `BODYSHOP_EXERCISE_IMAGE_BASE` elsewhere to self-host.

Adding a *new muscle group* means adding it to `MUSCLE_GROUPS`, `MUSCLE_LABELS` and
`MUSCLE_TARGETS`, mapping to it in the generator's `MUSCLE_MAP`, and drawing a region
in `app/templates/partials/_body_figure.html` with a matching `data-muscle` attribute.
Regions in one view must not overlap — they paint in order, so an overlap hides one
group's colour behind another's.

### Upgrading a database logged before the catalog

The four hand-written exercises that predate it (`squat`, `bench_press`, `pull_ups`,
`sit_ups`) no longer exist. Moving that history onto the catalog is Alembic revision
`0002`, so it happens as part of migrating — there is no separate command:

```bash
flask --app app stamp-db 0001     # only for a database created before migrations
flask --app app upgrade-db
```

## Roadmap

The full technical plan, in execution order — **per-set weight and reps**, accounts,
Vercel hosting, routines and progress tracking, AI-assisted custom exercises,
then mobile and watch — is in [docs/ROADMAP.md](docs/ROADMAP.md), along with the
post-launch candidates (auto-progression, social, nutrition) and the reasoning for why
each waits.

Phase 1 (Tailwind/daisyUI, home page) and Phase 2 (the catalog, 12 muscle groups, the
picker) are done; Phase 9 (images) shipped inside Phase 2. Smaller items not covered
there:

- [ ] Per-user set targets instead of the fixed 20/10 split
- [ ] Per-exercise secondary weights instead of a flat 0.5
- [ ] A placeholder image, rather than dropping the frame block when the CDN fails

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and feature requests use the
templates in [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE/).

## License

[MIT](LICENSE)
