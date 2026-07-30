"""Application configuration objects.

Configuration is selected by :func:`app.create_app` via the ``BODYSHOP_CONFIG``
environment variable (``development``, ``testing`` or ``production``).

Three layers are applied, last wins: the class below, then an optional
``instance/config.py``, then keyword overrides from the test suite.
:func:`validate` therefore runs in ``create_app`` against the *resolved* values —
checking a class attribute here would be checking the first layer only, and the
instance file exists precisely so that a secret can be supplied outside the
repository.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from dotenv import load_dotenv

# Must run before the classes below, whose attributes are evaluated at import.
# Real environment variables win over .env (load_dotenv does not override).
#
# The path is explicit rather than dotenv's default search, which walks up from
# the *calling stack frame* — that makes what gets loaded depend on who imported
# this module and fails outright where there is no frame to inspect. A missing
# file is a no-op, which is the normal case in a hosted environment where the
# platform injects the variables directly.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

#: The placeholder secret. Production refuses to boot while this is in force.
DEV_SECRET_KEY = "dev-secret-change-me"


class ConfigError(RuntimeError):
    """Raised at startup when the resolved configuration is unsafe to run."""


class BaseConfig:
    """Settings shared by every environment."""

    CONFIG_NAME = "development"

    #: Used by Flask for signing sessions/flash messages.
    SECRET_KEY = os.environ.get("BODYSHOP_SECRET_KEY", DEV_SECRET_KEY)

    #: SQLAlchemy URL for the database. ``None`` means "a SQLite file inside
    #: instance/", which is the zero-setup development default.
    #:
    #: ``DATABASE_URL`` is the name Supabase, Neon and Vercel all inject, so it
    #: is read directly; ``BODYSHOP_DATABASE_URL`` wins when both are set, which
    #: leaves a way to point the app somewhere other than whatever the host
    #: provided.
    DATABASE_URL = os.environ.get("BODYSHOP_DATABASE_URL") or os.environ.get(
        "DATABASE_URL"
    )

    #: ISO weekday the summary week starts on (1 = Monday ... 7 = Sunday).
    WEEK_STARTS_ON = int(os.environ.get("BODYSHOP_WEEK_STARTS_ON", "1"))

    #: Where exercise photographs are served from.
    #:
    #: The catalog's 1,746 images come to roughly 85 MB, which does not belong
    #: in the repository, so they are served from jsDelivr pinned to the same
    #: free-exercise-db commit ``tools/build_exercise_catalog.py`` vendored the
    #: data from. Point this at any origin holding the same ``<id>/<n>.jpg``
    #: layout to self-host instead.
    EXERCISE_IMAGE_BASE = os.environ.get(
        "BODYSHOP_EXERCISE_IMAGE_BASE",
        "https://cdn.jsdelivr.net/gh/yuhonas/free-exercise-db"
        "@b0eed061e1c832b3ed815fbaa4b45b3cdc14df49/exercises",
    )

    JSON_SORT_KEYS = False


class DevelopmentConfig(BaseConfig):
    CONFIG_NAME = "development"
    DEBUG = True


class TestingConfig(BaseConfig):
    CONFIG_NAME = "testing"
    TESTING = True
    SECRET_KEY = "testing"


class ProductionConfig(BaseConfig):
    CONFIG_NAME = "production"
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


def normalise_database_url(url: str) -> str:
    """Return ``url`` with a driver SQLAlchemy can actually load.

    Supabase, Neon and Heroku all print ``postgres://``, which SQLAlchemy rejects
    outright, and a bare ``postgresql://`` resolves to psycopg2, which this
    project does not install. Both are rewritten onto psycopg 3 so a connection
    string can be pasted in exactly as the provider gives it.
    """
    for prefix in ("postgres://", "postgresql://", "postgresql+psycopg2://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def validate(config: Mapping) -> None:
    """Raise :class:`ConfigError` if ``config`` is unsafe for its environment.

    Only production is checked; development and testing are expected to run on
    placeholder values. Called by :func:`app.create_app` after every
    configuration layer has been applied, so an ``instance/config.py`` can
    satisfy these requirements but cannot bypass them.
    """
    if config.get("CONFIG_NAME") != "production":
        return

    secret = config.get("SECRET_KEY")
    if not secret or secret == DEV_SECRET_KEY:
        raise ConfigError(
            "BODYSHOP_SECRET_KEY is unset or still the development default. "
            "Generate one with: python -c \"import secrets; "
            'print(secrets.token_urlsafe(48))"'
        )

    url = config.get("DATABASE_URL")
    if not url:
        raise ConfigError(
            "DATABASE_URL is unset. Production needs a Postgres connection "
            "string; see .env.example."
        )
    if url.startswith("sqlite"):
        raise ConfigError(
            f"DATABASE_URL points at SQLite ({url!r}). A hosted deployment has "
            "an ephemeral filesystem, so a SQLite file is silently lost between "
            "invocations. Use Postgres in production."
        )
