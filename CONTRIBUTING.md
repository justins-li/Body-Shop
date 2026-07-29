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
- JavaScript: ES modules, no build step, no dependencies. Keep it that way unless
  there's a strong reason.
- CSS: design tokens at the top of `styles.css`; use the existing custom properties
  rather than adding new hex values.

## Commits

Present tense, one logical change per commit:

```
Add rest-day markers to the calendar grid
```

## Reporting bugs

Use the issue templates in [.github/ISSUE_TEMPLATE](.github/ISSUE_TEMPLATE/). For a
bug, the most useful thing you can include is the exact sequence of dates,
exercises and set counts that reproduces it.
