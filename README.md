# Body Shop

> Log your workouts on a calendar and see, at a glance, which muscle groups you actually trained this week.

Body Shop is a small Flask + vanilla JS web app. You pick a date, log how many sets
of an exercise you did, and the weekly summary paints a body outline: each muscle
group deepens from **light green** at one set to **dark green** at its weekly set
target, then runs **light to dark red** for every set past it.

Targets are 20 sets a week for the large groups (chest, back, shoulders, quads,
hamstrings, glutes) and 10 for the small ones (abs, biceps, triceps, forearms,
traps, calves).

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
| **Calendar** | `/calendar` | Month grid of your training. Days with logged sets are dotted; click one to see what you did. |
| **Log workout** | `/log` | Pick date → exercise → sets. The picker has three ways in: recent, search (`incl db` finds "Dumbbell Incline Bench Press") and browse by muscle. Shows and deletes the entries for that day. |
| **Weekly summary** | `/summary` | Front/back body map shaded by weekly volume, plus each group's sets against its target. |

All four pages share a `?date=YYYY-MM-DD` query parameter, so navigating between
them keeps the day you were looking at.

## Quick start

```bash
git clone https://github.com/<you>/Body-Shop.git
cd Body-Shop

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python run.py
```

Open <http://127.0.0.1:5000>. The SQLite database is created automatically at
`instance/bodyshop.sqlite3` on first run — no migration step needed.

To wipe it and start over:

```bash
flask --app app init-db
```

Nothing else is needed to run or change the app — the compiled stylesheet is committed.

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

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

Everything is environment-driven; nothing is required for local development.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BODYSHOP_CONFIG` | `development` | `development`, `testing` or `production`. |
| `BODYSHOP_SECRET_KEY` | `dev-secret-change-me` | Flask secret key. **Set this in production.** |
| `BODYSHOP_DATABASE` | `instance/bodyshop.sqlite3` | Absolute path to the SQLite file. |
| `BODYSHOP_WEEK_STARTS_ON` | `1` (Monday) | ISO weekday the summary week begins on. |
| `BODYSHOP_EXERCISE_IMAGE_BASE` | jsDelivr, pinned | Origin serving `<exercise_id>/<0\|1>.jpg`. Set this to self-host the images. |
| `BODYSHOP_HOST` / `BODYSHOP_PORT` | `127.0.0.1` / `5000` | Dev server bind address. |

For production, serve the WSGI app instead of `run.py`:

```bash
pip install gunicorn
BODYSHOP_SECRET_KEY=... gunicorn "wsgi:application"
```

## Project layout

```
Body-Shop/
├── app/
│   ├── __init__.py           # application factory
│   ├── config.py             # environment-driven settings
│   ├── db.py                 # SQLite connection + `init-db` / `remap-exercises` CLI
│   ├── schema.sql            # table definitions
│   ├── exercises.py          # catalog loader, muscle groups, targets, volume weights
│   ├── data/exercises.json   # 873 vendored movements — generated, never hand-edited
│   ├── models.py             # all SQL lives here: validation + queries
│   ├── views.py              # the four HTML page routes
│   ├── api.py                # /api JSON endpoints
│   ├── services/
│   │   ├── weeks.py          # week/month boundary maths
│   │   └── summary.py        # weekly muscle-coverage aggregation
│   ├── templates/            # Jinja2: base + one per page + body-map partial
│   └── static/
│       ├── css/input.css     # design system — the file you edit
│       ├── css/styles.css    # compiled output — generated, committed
│       └── js/               # api.js, ui.js, and one module per page
├── tools/                    # fetch_css_toolchain.py, build_exercise_catalog.py
├── tests/                    # pytest suite (catalog, API, pages, aggregation, dates)
├── docs/                     # architecture + API reference
├── run.py                    # dev entry point
└── wsgi.py                   # production entry point
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the layers fit together and
[docs/API.md](docs/API.md) for the endpoint reference. [docs/ROADMAP.md](docs/ROADMAP.md)
specifies where it's going next.

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
`sit_ups`) no longer exist. Move that history onto the catalog:

```bash
flask --app app remap-exercises
```

## Roadmap

The full technical plan, in execution order — Postgres, **per-set weight and reps**,
accounts, Vercel hosting, routines and progress tracking, AI-assisted custom exercises,
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
