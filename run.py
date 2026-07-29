"""Development entry point: ``python run.py``.

For production use a WSGI server against ``wsgi:application`` instead, e.g.::

    gunicorn "wsgi:application"
"""

from __future__ import annotations

import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("BODYSHOP_HOST", "127.0.0.1"),
        port=int(os.environ.get("BODYSHOP_PORT", "5000")),
        debug=app.config.get("DEBUG", False),
    )
