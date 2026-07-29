# Contributing to Body Shop

Thanks for helping out. This is a small codebase — the guidelines are short on purpose.

## Getting set up

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
python run.py
```

That is everything you need to run, test and change the app. **The CSS toolchain is a
separate, optional step** — the compiled stylesheet is committed, so you only need this
if you are editing `app/static/css/input.css`:

```bash
python tools/fetch_css_toolchain.py   # once — no npm; downloads into gitignored tools/
tools/tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --watch
```

If you do edit CSS, **commit the rebuilt `styles.css` alongside your `input.css`
change** — CI does not build it.

## Before you open a pull request

1. `pytest` passes.
2. New behaviour has a test. The suite is fast; there's no excuse.
3. Docstrings on new public functions, and a comment wherever the *why* isn't obvious
   from the code.
4. If you changed the API surface, update [docs/API.md](docs/API.md). If you changed
   how the layers fit together, update [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Where code goes

Read [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) first — it has a table of what
each module owns. The short version:

- SQL belongs in `app/models.py`, nowhere else.
- Business rules belong in `app/services/`, not in route handlers.
- `app/api.py` and `app/views.py` should only parse input and shape output.
- The exercise catalog lives in `app/exercises.py` and is the only place exercises
  are enumerated.

## Style

- Python: standard library formatting conventions, 4-space indent, type hints on
  function signatures, `from __future__ import annotations` at the top of modules.
- JavaScript: ES modules, no dependencies, no bundler — it is served as written. Keep it
  that way unless there's a strong reason.
- CSS: `input.css` is the source, `styles.css` is generated — never edit the latter.
  Reach for a daisyUI component first, then Tailwind utilities, then hand-written CSS.
  Never a raw hex value: use the theme colours so both light and dark stay correct.
  Separation is a hairline border, not a shadow.
- Anything a JS module toggles at runtime needs a named class in `input.css`, not a
  utility — Tailwind's scanner reads literal text, so an interpolated class name gets
  purged without warning.

## Commits

Present tense, one logical change per commit:

```
Add rest-day markers to the calendar grid
```

## Reporting bugs

Use the issue templates in [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE/). For a
bug, the most useful thing you can include is the exact sequence of dates,
exercises and set counts that reproduces it.
