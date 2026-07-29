"""Tests for configuration resolution and the production safety checks.

The checks exist because both failure modes are silent. A deployment running on
``dev-secret-change-me`` signs session cookies with a value that is in the git
history; a deployment pointed at SQLite writes to a filesystem that a serverless
platform discards between invocations, losing every workout with no error. Both
should refuse to boot instead.
"""

from __future__ import annotations

import pytest

from app import create_app
from app.config import DEV_SECRET_KEY, ConfigError, normalise_database_url

POSTGRES = "postgresql+psycopg://u:p@localhost:5432/bodyshop"


class TestNormaliseDatabaseUrl:
    """Provider connection strings have to be usable as pasted."""

    @pytest.mark.parametrize(
        "given",
        [
            "postgres://u:p@host:6543/postgres",
            "postgresql://u:p@host:6543/postgres",
            "postgresql+psycopg2://u:p@host:6543/postgres",
        ],
    )
    def test_postgres_urls_are_rewritten_onto_psycopg3(self, given):
        assert normalise_database_url(given) == (
            "postgresql+psycopg://u:p@host:6543/postgres"
        )

    def test_sqlite_urls_are_left_alone(self):
        assert normalise_database_url("sqlite:///a.sqlite3") == "sqlite:///a.sqlite3"

    def test_a_percent_encoded_password_survives(self):
        """Supabase passwords routinely contain characters that get encoded."""
        given = "postgres://postgres:p%40ss%25word@host:5432/postgres"
        assert normalise_database_url(given).endswith("p%40ss%25word@host:5432/postgres")


class TestProductionRefusesUnsafeConfig:
    def test_the_default_secret_key_is_rejected(self):
        with pytest.raises(ConfigError, match="SECRET_KEY"):
            create_app("production", SECRET_KEY=DEV_SECRET_KEY, DATABASE_URL=POSTGRES)

    def test_an_empty_secret_key_is_rejected(self):
        with pytest.raises(ConfigError, match="SECRET_KEY"):
            create_app("production", SECRET_KEY="", DATABASE_URL=POSTGRES)

    def test_a_sqlite_database_is_rejected(self):
        with pytest.raises(ConfigError, match="ephemeral"):
            create_app("production", SECRET_KEY="real", DATABASE_URL="sqlite:///x.db")

    def test_an_unset_database_url_is_rejected(self):
        """Falling back to the instance-folder default must not happen here."""
        with pytest.raises(ConfigError, match="DATABASE_URL is unset"):
            create_app("production", SECRET_KEY="real", DATABASE_URL=None)

    def test_a_real_secret_and_postgres_boots(self):
        app = create_app("production", SECRET_KEY="real", DATABASE_URL=POSTGRES)
        assert app.config["DATABASE_URL"] == POSTGRES

    def test_an_instance_config_can_satisfy_the_check_but_not_bypass_it(self):
        """The check reads the resolved value, so layering order cannot defeat it.

        ``instance/config.py`` is applied after the config class, which is why the
        check lives in ``create_app`` rather than on the class attribute.
        """
        app = create_app("production", SECRET_KEY="from-instance-file",
                         DATABASE_URL=POSTGRES)
        assert app.config["SECRET_KEY"] == "from-instance-file"


class TestDevelopmentDefaults:
    def test_development_tolerates_the_placeholder_secret(self):
        app = create_app("development")
        assert app.config["SECRET_KEY"] == DEV_SECRET_KEY

    def test_an_unconfigured_database_lands_in_the_instance_folder(self):
        app = create_app("development", DATABASE_URL=None)
        assert app.config["DATABASE_URL"].startswith("sqlite:///")
        assert app.instance_path in app.config["DATABASE_URL"]
