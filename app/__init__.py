"""Body Shop — a workout logger with a weekly muscle-coverage body map.

Application factory.  Import ``create_app`` to build a configured Flask app::

    from app import create_app
    application = create_app()
"""

from __future__ import annotations

import os
from pathlib import Path

from flask import Flask

from .config import get_config

__version__ = "0.1.0"


def create_app(config_name: str | None = None, **overrides) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_name: ``development`` | ``testing`` | ``production``.
            Falls back to the ``BODYSHOP_CONFIG`` environment variable.
        **overrides: Config values applied last (used by the test suite).
    """
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    app.config.from_pyfile("config.py", silent=True)
    app.config.update(overrides)

    # Flask 3 reads key ordering from the JSON provider, not the config dict.
    app.json.sort_keys = bool(app.config.get("JSON_SORT_KEYS", False))

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    if not app.config.get("DATABASE"):
        app.config["DATABASE"] = os.path.join(app.instance_path, "bodyshop.sqlite3")

    from . import db

    db.init_app(app)

    from .api import bp as api_bp
    from .views import bp as views_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    # Create the schema on first use so `flask run` works with zero setup.
    with app.app_context():
        db.ensure_db()

    return app
