"""Body Shop — a workout logger with a weekly muscle-coverage body map.

Application factory.  Import ``create_app`` to build a configured Flask app::

    from app import create_app
    application = create_app()

The factory is deliberately side-effect-free: it opens no connection, runs no
DDL, and touches the filesystem only to create ``instance/`` for the SQLite
development default. That matters because Phase 6 puts it in a serverless
function whose filesystem is read-only, and because applying a schema at import
time gives a fresh deployment an unversioned database. Migrations run when
something asks for them — ``flask --app app upgrade-db``, or ``run.py`` in
development.

The one outward-facing thing it does is :func:`app.observability.init_sentry`,
and only when a DSN is configured. That is not the same class of side effect:
it opens no connection and touches no disk, which is what the rule above is
actually about.
"""

from __future__ import annotations

from pathlib import Path

from flask import Flask

from .config import get_config, normalise_database_url
from .config import validate as validate_config

__version__ = "0.1.0"


def create_app(config_name: str | None = None, **overrides) -> Flask:
    """Create and configure the Flask application.

    Args:
        config_name: ``development`` | ``testing`` | ``production``.
            Falls back to the ``BODYSHOP_CONFIG`` environment variable.
        **overrides: Config values applied last (used by the test suite).

    Raises:
        ConfigError: If the resolved configuration is unsafe for production.
    """
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    app.config.from_pyfile("config.py", silent=True)
    app.config.update(overrides)

    # Flask 3 reads key ordering from the JSON provider, not the config dict.
    app.json.sort_keys = bool(app.config.get("JSON_SORT_KEYS", False))

    is_production = app.config.get("CONFIG_NAME") == "production"

    if not app.config.get("DATABASE_URL") and not is_production:
        # No database configured: fall back to a SQLite file in the instance
        # folder so `python run.py` works with zero setup. This is the only
        # branch that writes to disk, and production is excluded from it for two
        # reasons — a hosted filesystem is ephemeral, and falling back here would
        # mean an unset DATABASE_URL got reported as "you configured SQLite"
        # rather than as the missing configuration it actually is.
        Path(app.instance_path).mkdir(parents=True, exist_ok=True)
        app.config["DATABASE_URL"] = (
            f"sqlite:///{Path(app.instance_path) / 'bodyshop.sqlite3'}"
        )

    if app.config.get("DATABASE_URL"):
        app.config["DATABASE_URL"] = normalise_database_url(
            app.config["DATABASE_URL"]
        )

    # Last, so that every layer above — including instance/config.py — has had
    # its say and none of them can bypass the check.
    validate_config(app.config)

    # After validation, so a misconfigured production deploy fails on its own
    # terms rather than reporting the failure to a service it may not have. A
    # no-op unless SENTRY_DSN is set — see app/observability.py for why this is
    # the one permitted exception to the factory's no-side-effects rule.
    from .observability import init_sentry

    init_sentry(app)

    from . import db

    db.init_app(app)

    from .api import bp as api_bp
    from .views import bp as views_bp

    app.register_blueprint(views_bp)
    app.register_blueprint(api_bp)

    return app
