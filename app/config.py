"""Application configuration objects.

Configuration is selected by :func:`app.create_app` via the ``BODYSHOP_CONFIG``
environment variable (``development``, ``testing`` or ``production``).
"""

from __future__ import annotations

import os


class BaseConfig:
    """Settings shared by every environment."""

    #: Used by Flask for signing sessions/flash messages.
    SECRET_KEY = os.environ.get("BODYSHOP_SECRET_KEY", "dev-secret-change-me")

    #: Absolute path to the SQLite file. ``None`` means "inside instance/".
    DATABASE = os.environ.get("BODYSHOP_DATABASE")

    #: ISO weekday the summary week starts on (1 = Monday ... 7 = Sunday).
    WEEK_STARTS_ON = int(os.environ.get("BODYSHOP_WEEK_STARTS_ON", "1"))

    JSON_SORT_KEYS = False


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "testing"


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIGS: dict[str, type[BaseConfig]] = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str | None = None) -> type[BaseConfig]:
    """Return the config class for ``name`` (defaults to ``BODYSHOP_CONFIG``)."""
    key = (name or os.environ.get("BODYSHOP_CONFIG") or "development").lower()
    return CONFIGS.get(key, DevelopmentConfig)
