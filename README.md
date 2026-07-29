# Body Shop

> Log your workouts on a calendar and see, at a glance, which muscle groups you actually trained this week.

Body Shop is a small Flask + vanilla JS web app. You pick a date, log how many sets
of an exercise you did, and the weekly summary paints a body outline: each muscle
group deepens from **light green** at one set to **dark green** at its weekly set
target, then runs **light to dark red** for every set past it.

Targets are 20 sets a week for the large groups (chest, back, quads, hamstrings)
and 10 for the small ones (abs, biceps, triceps).

```
Bench press → triceps + chest
Pull ups    → biceps + back
Squat       → quads + hamstrings
Sit ups     → abs
```

The front figure shows chest, abs, biceps and quads; the back figure shows back,
triceps and hamstrings. No group appears on both, so the two outlines tell you
different things.

## Pages

| Page | Route | What it does |
| --- | --- | --- |
| **Calendar** | `/` | Month grid of your training. Days with logged sets are dotted; click one to see what you did. |
| **Log workout** | `/log` | Pick date → exercise → sets. Shows and deletes the entries for that day. |
| **Weekly summary** | `/summary` | Front/back body map shaded by weekly volume, plus each group's sets against its target. |

All three pages share a `?date=YYYY-MM-DD` query parameter, so navigating between
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

## Running the tests

```bash
pip install -r requirements-dev.txt
pytest
```

## Configuration

Everything is environment-driven; nothing is required for local development.

| Variable | Default | Purpose |
| --- | --- | --- |
| `BODYSHOP_CONFIG` | `development` | `development`, `testing` or `production`. |
| `BODYSHOP_SECRET_KEY` | `dev-secret-change-me` | Flask secret key. **Set this in production.** |
| `BODYSHOP_DATABASE` | `instance/bodyshop.sqlite3` | Absolute path to the SQLite file. |
| `BODYSHOP_WEEK_STARTS_ON` | `1` (Monday) | ISO weekday the summary week begins on. |
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
│   ├── db.py                 # SQLite connection + `init-db` CLI command
│   ├── schema.sql            # table definitions
│   ├── exercises.py          # exercise → muscle-group catalog (single source of truth)
│   ├── models.py             # all SQL lives here: validation + queries
│   ├── views.py              # the three HTML page routes
│   ├── api.py                # /api JSON endpoints
│   ├── services/
│   │   ├── weeks.py          # week/month boundary maths
│   │   └── summary.py        # weekly muscle-coverage aggregation
│   ├── templates/            # Jinja2: base + one per page + body-map partial
│   └── static/
│       ├── css/styles.css
│       └── js/               # api.js, ui.js, and one module per page
├── tests/                    # pytest suite (API, pages, aggregation, dates)
├── docs/                     # architecture + API reference
├── run.py                    # dev entry point
└── wsgi.py                   # production entry point
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for how the layers fit together and
[docs/API.md](docs/API.md) for the endpoint reference. [docs/ROADMAP.md](docs/ROADMAP.md)
specifies where it's going next.

## Adding an exercise

One edit. Append to `EXERCISES` in [`app/exercises.py`](app/exercises.py):

```python
Exercise("overhead_press", "Overhead press", ("shoulders", "triceps")),
```

The input form, API validation and weekly summary all read from that dict. If the
new movement introduces a *new* muscle group, also add it to `MUSCLE_GROUPS`,
`MUSCLE_LABELS` and `MUSCLE_TARGETS`, then draw a region for it in
`app/templates/partials/_body_figure.html` with a matching `data-muscle` attribute.

## Roadmap

The full technical plan, in execution order — Tailwind/DaisyUI, a ~180-exercise catalog,
Postgres, **per-set weight and reps**, accounts, Vercel hosting, routines and progress
tracking, AI-assisted custom exercises, then mobile and watch — is in
[docs/ROADMAP.md](docs/ROADMAP.md), along with the post-launch candidates (auto-progression,
social, nutrition) and the reasoning for why each waits.

Smaller items not covered there:

- [ ] A hinge movement (deadlift / leg curl) so quads and hamstrings can differ
- [ ] Per-user set targets instead of the fixed 20/10 split

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and feature requests use the
templates in [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE/).

## License

[MIT](LICENSE)
