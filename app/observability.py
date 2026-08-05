"""Error reporting.

Sentry is initialised from :func:`app.create_app`, but **only when a DSN is
configured** — which development and the test suite never are. That is what
keeps the suite offline and keeps the factory a no-op everywhere it is called in
a loop.

This is the one thing the factory does that reaches outside the process, and it
is permitted because it is not the thing the no-side-effects rule is about: that
rule exists because ``ensure_db()`` used to open a connection and apply DDL on
every boot, which crashed on a read-only filesystem and left fresh deployments
with an unversioned schema. Sentry's ``init`` opens no connection and touches no
disk; it registers hooks and starts a background transport that sends nothing
until something is captured.
"""

from __future__ import annotations

from flask import Flask

#: Set once a process has initialised, so a factory called twice — which the
#: test suite does constantly, and a WSGI server can — does not stack
#: integrations on top of each other.
_initialised = False


def init_sentry(app: Flask) -> bool:
    """Start error reporting for ``app``. Returns whether it did.

    A missing DSN is a valid configuration meaning "do not report", not an
    error: this must be a no-op in development, in the suite, and in any
    deployment that has not set one up.
    """
    global _initialised

    dsn = app.config.get("SENTRY_DSN")
    if not dsn or _initialised:
        return False

    # Imported here rather than at module scope so that a deployment without a
    # DSN — and every test run — pays neither the import nor its side effects.
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration

    from . import __version__

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        environment=app.config.get("CONFIG_NAME", "production"),
        release=f"body-shop@{__version__}",
        # /privacy says error reports carry no personal data. This is the line
        # that makes that true: with PII on, the SDK attaches request headers,
        # cookies and the user's address to every event.
        send_default_pii=False,
        # Errors, not performance. A workout log has no latency problem worth a
        # trace budget, and traces are the expensive half of the free tier.
        traces_sample_rate=0.0,
    )

    _initialised = True
    return True
