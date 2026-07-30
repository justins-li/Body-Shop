"""Development entry point: ``python run.py``.

Migrations run here rather than in the application factory. ``create_app`` is
imported by the test suite, by ``wsgi.py`` and (from Phase 6) by a serverless
function, none of which should have a schema applied underneath them as a side
effect of being imported — that is what made the old ``ensure_db()`` both a
Vercel crash and a migration hazard. This file is the dev convenience, so the
convenience lives here.

For production use a WSGI server against ``wsgi:application`` instead, e.g.::

    gunicorn "wsgi:application"

and migrate deliberately, as a deploy step::

    flask --app app upgrade-db
"""

from __future__ import annotations

import os

from app import create_app
from app.db import upgrade_db

app = create_app()

if __name__ == "__main__":
    with app.app_context():
        upgrade_db()

    app.run(
        host=os.environ.get("BODYSHOP_HOST", "127.0.0.1"),
        port=int(os.environ.get("BODYSHOP_PORT", "5000")),
        debug=app.config.get("DEBUG", False),
    )
