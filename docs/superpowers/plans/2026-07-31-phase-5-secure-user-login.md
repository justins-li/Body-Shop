# Phase 5 — Secure User Login Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Body Shop real accounts — every workout entry belongs to one Supabase-authenticated user, and no request can read or delete another user's data.

**Architecture:** Supabase Auth (GoTrue) owns credentials; the browser talks to it directly and stores a bearer token. Flask verifies that token's signature per request, mirrors the user into a local `user` table just-in-time, and threads `user_id` as the first positional parameter of every query that touches `workout_entry`. Page shells stay public; the page's JS module redirects to `/login` when the API answers 401.

**Tech Stack:** Flask 3, SQLAlchemy Core, Alembic, PyJWT[crypto], vanilla ES modules, Tailwind v4 + daisyUI, pytest.

**Source spec:** [docs/superpowers/specs/2026-07-31-phase-5-secure-user-login-design.md](../specs/2026-07-31-phase-5-secure-user-login-design.md)

## Global Constraints

- **SQL only in `app/models.py`.** Services and routes never call `get_db()`. Queries are SQLAlchemy Core expressions, never strings.
- **Layers are one-directional:** `app/api.py` (HTTP parsing, status codes, `request`, `g`) → `app/services/` (rules, Flask-free) → `app/models.py` (SQL) → DB.
- **`user_id` is the first positional parameter** of every `models.py` function touching `workout_entry`. Positional-and-first is the safety property: a missed call site raises `TypeError` instead of silently querying across all users.
- **A metadata change needs an Alembic revision in the same commit.** `tests/test_migrations.py` autogenerates a diff between `app/tables.py` and the migration chain and fails when they disagree.
- **Migrations carry frozen local copies of constants**, never imports from `app/`. A migration that imports a definition a later commit can change does different things depending on when it runs.
- **Constraint names in migrations are bare tokens** where the convention prefixes them (`ck`), and fully spelled where it does not (`uq`, `pk`, `fk`, indexes).
- **No new JS dependencies.** `auth.js` uses plain `fetch` against GoTrue's REST API — no Supabase SDK. The build step is CSS-only.
- **Never edit `app/static/css/styles.css`** — it is build output. Edit `app/static/css/input.css` and rebuild. Both are committed.
- **Never a raw hex value in CSS.** Use the theme's colours (`base-100/200/300`, `base-content`, `secondary`, `primary`).
- **Every interactive target clears 44pt.**
- **No filled accent buttons.** Primary actions are hairline-outlined with a brick border and lifted-brick text. Red *area* means volume past target; red *outline or text* means an action.
- **`/` is exactly one screen.** Signed-in state *swaps* the primary action rather than adding to it.
- **Dates are ISO-8601 strings at the API boundary**, `datetime.date` inside `models.py`. The backend does no time-zone conversion.
- **Weight is kilograms at rest and over the wire.**
- **Commit messages:** present tense, one logical change per commit. **Never add attribution trailers** — no `Co-Authored-By:`, no "Generated with" footers.
- **Branch:** work stays on `phase-5-secure-login`. Do not open a PR.
- **Run `pytest` before every commit.** CI only runs `pytest -q`, so a green local run is the whole signal.
- **`gh` is not installed.**

## File Structure

**New files:**

| Path | Responsibility |
| --- | --- |
| `app/services/auth.py` | Token rules: decode and verify a Supabase JWT; delete a Supabase auth record. Pure, Flask-free, directly testable. |
| `migrations/versions/0005_user_accounts.py` | Wipe existing rows, create `user`, add `workout_entry.user_id`. |
| `app/static/js/auth.js` | The token store plus GoTrue calls. The **only** place Supabase is called from the browser. |
| `app/templates/login.html` | Sign-in form. |
| `app/templates/signup.html` | Sign-up form. |
| `app/templates/reset_password.html` | Both halves of the reset flow. |
| `app/templates/verify.html` | Landing page for the email confirmation link. |
| `app/templates/account.html` | Email, sign out, delete account. |
| `tests/test_auth.py` | `decode_token` and JIT provisioning. |
| `tests/test_ownership.py` | Two users, every read and write endpoint. The file that proves the sweep. |
| `tests/test_account.py` | `DELETE /api/account`. |

**Modified files:**

| Path | Change |
| --- | --- |
| `app/config.py` | Four Supabase settings; production `validate()` checks. |
| `app/tables.py` | The `user` table; `workout_entry.user_id` + composite index. |
| `app/models.py` | The `user_id` sweep; `ensure_user` / `get_user` / `delete_user`. |
| `app/services/summary.py` | `weekly_summary` threads `user_id`. |
| `app/services/graph.py` | `training_graph` threads `user_id`. |
| `app/api.py` | `require_user`, gating, `GET /api/me`, `DELETE /api/account`. |
| `app/views.py` | Five new routes; Supabase config in the context processor. |
| `app/templates/base.html` | `bare` flag; the Supabase config script. |
| `app/templates/home.html` | The signed-in / signed-out split. |
| `app/static/js/api.js` | Bearer header; one silent refresh-and-retry on 401. |
| `app/static/css/input.css` | `.auth-*` components; the `data-auth` split rules. |
| `tests/conftest.py` | Authed test client; token minting; `"user"` in the Postgres `TRUNCATE`. |
| `requirements.txt` | `PyJWT[crypto]`. |
| Docs | `CLAUDE.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `.env.example`, `README.md`, `CHANGELOG.md`. |

**One refinement of the spec, applied throughout:** the spec writes `decode_token(raw) -> Claims` as shorthand. Because `services/` must stay Flask-free, the real signature takes its configuration explicitly:

```python
decode_token(raw: str, *, supabase_url: str, jwt_secret: str | None = None) -> Claims
```

`api.py`'s `require_user` reads `current_app.config` and passes those in.

**A second refinement:** the spec says `services/weeks.py` threads `user_id` through. It does not — `week_bounds`, `week_days` and `month_bounds` are pure date arithmetic with no database access. Only `summary.py` and `graph.py` change.

---

### Task 1: Supabase configuration

**Files:**
- Modify: `app/config.py:40-91` (add settings to `BaseConfig` and `TestingConfig`), `app/config.py:121-151` (extend `validate`)
- Modify: `requirements.txt`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: config keys `SUPABASE_URL: str`, `SUPABASE_ANON_KEY: str | None`, `SUPABASE_JWT_SECRET: str | None`, `SUPABASE_SERVICE_ROLE_KEY: str | None`. Under `create_app("testing")` these resolve to `"https://test.supabase.co"`, `"test-anon-key"`, `"test-jwt-secret"`, `"test-service-role-key"`.

- [ ] **Step 1: Add the dependency**

In `requirements.txt`, after the `psycopg[binary]` block:

```
# Verifies Supabase's JWTs. The `crypto` extra pulls cryptography, which the
# asymmetric (ES256/RS256) branch of app/services/auth.py needs; projects old
# enough to sign with the shared HS256 secret do not, but one resolver serves
# both rather than guessing which kind of project this is.
PyJWT[crypto]>=2.8,<3.0
```

Then run: `pip install -r requirements-dev.txt`

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_config.py`, inside `class TestProductionRefusesUnsafeConfig`:

```python
    def test_a_missing_supabase_url_is_rejected(self):
        with pytest.raises(ConfigError, match="SUPABASE_URL"):
            create_app("production", SECRET_KEY="real", DATABASE_URL=POSTGRES,
                       SUPABASE_URL=None)

    def test_a_missing_anon_key_is_rejected(self):
        with pytest.raises(ConfigError, match="SUPABASE_ANON_KEY"):
            create_app("production", SECRET_KEY="real", DATABASE_URL=POSTGRES,
                       SUPABASE_URL="https://p.supabase.co", SUPABASE_ANON_KEY=None)

    def test_a_missing_service_role_key_is_rejected(self):
        with pytest.raises(ConfigError, match="SERVICE_ROLE"):
            create_app("production", SECRET_KEY="real", DATABASE_URL=POSTGRES,
                       SUPABASE_URL="https://p.supabase.co",
                       SUPABASE_ANON_KEY="anon", SUPABASE_SERVICE_ROLE_KEY=None)

    def test_a_missing_jwt_secret_is_allowed(self):
        """Its absence is a valid configuration meaning "verify against JWKS"."""
        app = create_app("production", SECRET_KEY="real", DATABASE_URL=POSTGRES,
                         SUPABASE_URL="https://p.supabase.co",
                         SUPABASE_ANON_KEY="anon",
                         SUPABASE_SERVICE_ROLE_KEY="service",
                         SUPABASE_JWT_SECRET=None)
        assert app.config["SUPABASE_JWT_SECRET"] is None
```

And a new class at the end of the file:

```python
class TestTestingConfigPinsSupabase:
    """The suite mints its own HS256 tokens, so no test reaches the network."""

    def test_testing_pins_a_url_and_a_jwt_secret(self):
        app = create_app("testing", DATABASE_URL="sqlite:///x.db")
        assert app.config["SUPABASE_URL"] == "https://test.supabase.co"
        assert app.config["SUPABASE_JWT_SECRET"] == "test-jwt-secret"
        assert app.config["SUPABASE_ANON_KEY"] == "test-anon-key"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/test_config.py -v`
Expected: the four new production tests FAIL (no `ConfigError` raised — `create_app` returns normally), and `test_testing_pins_a_url_and_a_jwt_secret` FAILS with `KeyError: 'SUPABASE_URL'`.

- [ ] **Step 4: Add the settings to `BaseConfig`**

In `app/config.py`, inside `class BaseConfig`, after the `EXERCISE_IMAGE_BASE` block and before `JSON_SORT_KEYS`:

```python
    #: Supabase project URL, e.g. ``https://abcdefgh.supabase.co``.
    #:
    #: Three things derive from it: the GoTrue base the browser posts to, the
    #: ``iss`` claim every token must carry, and the JWKS path used when no
    #: shared secret is configured. Stored without a trailing slash so those
    #: three concatenations cannot produce a double one.
    SUPABASE_URL = (os.environ.get("BODYSHOP_SUPABASE_URL") or "").rstrip("/")

    #: Public by design — it is rendered into every page and identifies the
    #: project to GoTrue. It grants nothing on its own; row access is decided by
    #: the bearer token, which this key cannot mint.
    SUPABASE_ANON_KEY = os.environ.get("BODYSHOP_SUPABASE_ANON_KEY")

    #: Optional. Set → tokens are verified as HS256 against this shared secret.
    #: Unset → verified as ES256/RS256 against the project's published JWKS.
    #: Supabase projects differ by age, so both are supported behind one
    #: resolver; see app/services/auth.py.
    SUPABASE_JWT_SECRET = os.environ.get("BODYSHOP_SUPABASE_JWT_SECRET")

    #: **Secret.** Used by ``DELETE /api/account`` and nowhere else — a user
    #: cannot delete their own auth record with the anon key. This is the one
    #: place Flask holds a Supabase credential.
    SUPABASE_SERVICE_ROLE_KEY = os.environ.get("BODYSHOP_SUPABASE_SERVICE_ROLE_KEY")
```

- [ ] **Step 5: Pin the testing values**

Replace `class TestingConfig` in `app/config.py`:

```python
class TestingConfig(BaseConfig):
    CONFIG_NAME = "testing"
    TESTING = True
    SECRET_KEY = "testing"

    # Pinned rather than read from the environment, and the JWT secret is what
    # buys back the offline suite: with it set, app/services/auth.py always
    # takes the HS256 branch, so conftest mints tokens in-process and no test
    # ever resolves a JWKS document over the network.
    SUPABASE_URL = "https://test.supabase.co"
    SUPABASE_ANON_KEY = "test-anon-key"
    SUPABASE_JWT_SECRET = "test-jwt-secret"
    SUPABASE_SERVICE_ROLE_KEY = "test-service-role-key"
```

- [ ] **Step 6: Extend `validate`**

Append to `validate` in `app/config.py`, after the SQLite check:

```python
    if not config.get("SUPABASE_URL"):
        raise ConfigError(
            "BODYSHOP_SUPABASE_URL is unset. Production needs the Supabase "
            "project URL — it is the GoTrue base, the expected token issuer and "
            "the JWKS location. See .env.example."
        )

    if not config.get("SUPABASE_ANON_KEY"):
        raise ConfigError(
            "BODYSHOP_SUPABASE_ANON_KEY is unset. Without it the sign-in pages "
            "cannot reach Supabase at all."
        )

    if not config.get("SUPABASE_SERVICE_ROLE_KEY"):
        raise ConfigError(
            "BODYSHOP_SUPABASE_SERVICE_ROLE_KEY is unset. Account deletion needs "
            "it — a user cannot delete their own auth record with the anon key, "
            "and shipping without in-app deletion fails Apple's Guideline "
            "5.1.1(v)."
        )

    # SUPABASE_JWT_SECRET is deliberately not required. Its absence is a valid
    # configuration meaning "this project signs asymmetrically; verify against
    # the published JWKS".
```

- [ ] **Step 7: Run the tests to verify they pass**

Run: `pytest tests/test_config.py -v`
Expected: PASS, all of them.

- [ ] **Step 8: Document the settings in `.env.example`**

Insert before the `# --- Tests ---` section:

```
# --- Supabase Auth ---------------------------------------------------------
# Credentials live in Supabase, not here. Find these under Project Settings →
# API, and the JWT secret under Project Settings → API → JWT Settings.
#
# Production refuses to boot without the URL, the anon key and the service-role
# key. The JWT secret is optional: set it and tokens are verified as HS256
# against it; leave it unset and they are verified against the project's
# published JWKS (which is what newer projects, signing with ES256, need).

# BODYSHOP_SUPABASE_URL=https://abcdefgh.supabase.co

# Public by design — this is rendered into every page. It identifies the
# project; it grants nothing.
# BODYSHOP_SUPABASE_ANON_KEY=

# Optional. Legacy projects signing with the shared HS256 secret.
# BODYSHOP_SUPABASE_JWT_SECRET=

# SECRET. Used only by DELETE /api/account. Never rendered into a page, never
# sent to the browser.
# BODYSHOP_SUPABASE_SERVICE_ROLE_KEY=

# Supabase dashboard configuration this app assumes, recorded because it is not
# in the repo: under Authentication → URL Configuration, the Site URL and the
# additional redirect URLs must include <origin>/verify and
# <origin>/reset-password, and the confirmation and recovery email templates
# must point at them.
```

- [ ] **Step 9: Run the full suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add requirements.txt app/config.py tests/test_config.py .env.example
git commit -m "Add Supabase configuration and require it in production

Four settings: the project URL (which is also the expected token issuer
and the JWKS location), the public anon key, an optional HS256 secret and
the service-role key that account deletion needs. Production refuses to
boot without three of them; the JWT secret is optional because its absence
is a valid configuration meaning 'verify against JWKS'.

Testing pins all four. The pinned JWT secret is what keeps the suite
offline: the HS256 branch means tests mint their own tokens in-process."
```

---

### Task 2: Token verification (`app/services/auth.py`)

**Files:**
- Create: `app/services/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: config values from Task 1, passed in explicitly.
- Produces:
  ```python
  class AuthError(Exception): ...

  @dataclass(frozen=True)
  class Claims:
      sub: str
      email: str

  AUDIENCE: str = "authenticated"

  def issuer(supabase_url: str) -> str: ...
  def decode_token(raw: str, *, supabase_url: str,
                   jwt_secret: str | None = None) -> Claims: ...
  def delete_auth_user(user_id: str, *, supabase_url: str,
                       service_role_key: str, timeout: float = 10.0) -> None: ...
  ```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_auth.py`:

```python
"""Token verification, and the just-in-time user mirror.

Every token here is minted in-process against the testing config's pinned
HS256 secret. Nothing in this file — or anywhere else in the suite — resolves a
JWKS document or otherwise reaches the network.
"""

from __future__ import annotations

import time

import jwt
import pytest

from app.services.auth import AUDIENCE, AuthError, Claims, decode_token, issuer

URL = "https://test.supabase.co"
SECRET = "test-jwt-secret"
SUB = "11111111-1111-4111-8111-111111111111"


def mint(secret=SECRET, **overrides) -> str:
    payload = {
        "sub": SUB,
        "email": "tester@example.com",
        "aud": AUDIENCE,
        "iss": issuer(URL),
        "exp": int(time.time()) + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, secret, algorithm="HS256")


class TestIssuer:
    def test_the_issuer_is_the_gotrue_base(self):
        assert issuer(URL) == "https://test.supabase.co/auth/v1"

    def test_a_trailing_slash_does_not_double_up(self):
        assert issuer("https://test.supabase.co/") == "https://test.supabase.co/auth/v1"


class TestDecodeToken:
    def test_a_valid_token_yields_its_claims(self):
        claims = decode_token(mint(), supabase_url=URL, jwt_secret=SECRET)
        assert claims == Claims(sub=SUB, email="tester@example.com")

    @pytest.mark.parametrize(
        ("name", "token"),
        [
            ("expired", lambda: mint(exp=int(time.time()) - 60)),
            ("wrong secret", lambda: mint(secret="not-the-secret")),
            ("wrong audience", lambda: mint(aud="anon")),
            ("wrong issuer", lambda: mint(iss="https://evil.example.com/auth/v1")),
            ("no sub", lambda: mint(sub=None)),
            ("empty sub", lambda: mint(sub="")),
            ("no exp", lambda: jwt.encode(
                {"sub": SUB, "email": "t@e.com", "aud": AUDIENCE, "iss": issuer(URL)},
                SECRET, algorithm="HS256")),
            ("malformed", lambda: "not.a.token"),
            ("empty", lambda: ""),
        ],
    )
    def test_every_failure_raises_the_same_error(self, name, token):
        with pytest.raises(AuthError):
            decode_token(token(), supabase_url=URL, jwt_secret=SECRET)

    def test_every_failure_carries_the_same_message(self):
        """A 401 that says *why* is an oracle. Nothing in the client needs it."""
        messages = set()
        for token in (mint(exp=1), mint(secret="wrong"), mint(aud="anon"), "junk"):
            with pytest.raises(AuthError) as caught:
                decode_token(token, supabase_url=URL, jwt_secret=SECRET)
            messages.add(str(caught.value))
        assert len(messages) == 1

    def test_a_token_with_no_email_still_decodes(self):
        """Email is not load-bearing for authorisation; `sub` is."""
        claims = decode_token(mint(email=None), supabase_url=URL, jwt_secret=SECRET)
        assert claims.sub == SUB
        assert claims.email == ""

    def test_none_is_rejected_without_calling_out_to_a_jwks(self):
        """An empty token must fail before the key resolver is ever consulted."""
        with pytest.raises(AuthError):
            decode_token("", supabase_url=URL, jwt_secret=None)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL at collection — `ModuleNotFoundError: No module named 'app.services.auth'`.

- [ ] **Step 3: Write the implementation**

Create `app/services/auth.py`:

```python
"""Supabase token rules.

Pure and Flask-free: nothing here touches ``request``, ``g`` or
``current_app``. The HTTP glue — reading the ``Authorization`` header, setting
``g.user_id``, rendering a 401 — lives in :mod:`app.api`, because that is what
the layer rule says HTTP concerns are.

**Two key types, behind one resolver.** Supabase projects differ by age: newer
ones sign asymmetrically (ES256) with keys published at
``/auth/v1/.well-known/jwks.json``, while projects created before that default
to a shared HS256 secret. Committing to one would either leave the app unable to
verify a token at all, or force a stubbed HTTP endpoint into the test suite.
Setting ``SUPABASE_JWT_SECRET`` selects HS256; leaving it unset selects JWKS.

**Every failure raises the same :class:`AuthError` with the same message.** A
401 that distinguishes "expired" from "forged" from "wrong project" is a small
oracle, and no client needs the distinction — the only useful response to any of
them is to refresh once and then sign in again.
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

#: Supabase stamps this into every signed-in token's ``aud``.
AUDIENCE = "authenticated"

#: Said once, everywhere. See the module docstring on why it never varies.
_REJECTED = "Sign in to continue."


class AuthError(Exception):
    """Raised when a token is absent, malformed, expired or not ours."""


@dataclass(frozen=True)
class Claims:
    """The only two claims this app reads.

    ``sub`` is the Supabase ``auth.users`` id and the value every row is owned
    by. ``email`` is display and mirror data only — never an authorisation
    input, which is why an absent one is an empty string rather than an error.
    """

    sub: str
    email: str


def issuer(supabase_url: str) -> str:
    """The ``iss`` every token from this project must carry."""
    return f"{supabase_url.rstrip('/')}/auth/v1"


#: One client per JWKS URL, so the keys are fetched once per process rather than
#: once per request. PyJWKClient caches internally; this caches the client.
_jwks_clients: dict[str, PyJWKClient] = {}
_jwks_lock = threading.Lock()


def _jwks_client(supabase_url: str) -> PyJWKClient:
    url = f"{issuer(supabase_url)}/.well-known/jwks.json"
    with _jwks_lock:
        client = _jwks_clients.get(url)
        if client is None:
            client = PyJWKClient(url, cache_keys=True)
            _jwks_clients[url] = client
        return client


def decode_token(
    raw: str,
    *,
    supabase_url: str,
    jwt_secret: str | None = None,
) -> Claims:
    """Verify ``raw`` and return its claims, or raise :class:`AuthError`.

    Signature, expiry, audience and issuer are all verified, and ``exp``,
    ``sub``, ``aud`` and ``iss`` must all be *present* — a token that simply
    omits an expiry must not be treated as one that never expires.

    Args:
        raw: The bare JWT, with the ``Bearer `` prefix already stripped.
        supabase_url: The project URL. Derives the expected issuer and the JWKS.
        jwt_secret: The shared HS256 secret, or ``None`` to use the JWKS.

    Raises:
        AuthError: For every failure, with one message. Deliberately.
    """
    if not raw:
        raise AuthError(_REJECTED)

    options = {"require": ["exp", "sub", "aud", "iss"]}
    try:
        if jwt_secret:
            payload = jwt.decode(
                raw,
                jwt_secret,
                algorithms=["HS256"],
                audience=AUDIENCE,
                issuer=issuer(supabase_url),
                options=options,
            )
        else:
            key = _jwks_client(supabase_url).get_signing_key_from_jwt(raw).key
            payload = jwt.decode(
                raw,
                key,
                algorithms=["ES256", "RS256"],
                audience=AUDIENCE,
                issuer=issuer(supabase_url),
                options=options,
            )
    except Exception as exc:  # noqa: BLE001 - every cause collapses to one 401
        raise AuthError(_REJECTED) from exc

    sub = payload.get("sub")
    if not sub:
        raise AuthError(_REJECTED)

    # Email is optional in the token and optional here. `or ""` rather than a
    # default, because Supabase sends an explicit null for a phone-only account.
    return Claims(sub=str(sub), email=str(payload.get("email") or ""))


def delete_auth_user(
    user_id: str,
    *,
    supabase_url: str,
    service_role_key: str,
    timeout: float = 10.0,
) -> None:
    """Delete the Supabase auth record for ``user_id``.

    Uses ``urllib`` from the standard library rather than adding an HTTP client:
    this is one authenticated DELETE, made from one endpoint.

    Raises:
        AuthError: If Supabase refuses or is unreachable. The caller has already
            deleted the local rows by then, and reports the partial outcome
            honestly rather than pretending the account is gone.
    """
    request = urllib.request.Request(
        f"{issuer(supabase_url)}/admin/users/{user_id}",
        method="DELETE",
        headers={
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            return
    except (urllib.error.URLError, OSError) as exc:
        raise AuthError(f"Supabase would not delete the auth record: {exc}") from exc
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/auth.py tests/test_auth.py
git commit -m "Verify Supabase tokens in a Flask-free service module

Signature, expiry, audience and issuer are all checked, and all four
claims must be present — a token omitting exp must not read as one that
never expires.

Two key types behind one resolver, because Supabase projects differ by
age: a shared HS256 secret when SUPABASE_JWT_SECRET is set, the project's
published JWKS otherwise. Guessing wrong means either being unable to
verify anything or needing a stubbed HTTP endpoint in the suite.

Every failure raises one AuthError with one message. A 401 that says why
is an oracle, and no client needs the distinction."
```

---

### Task 3: The `user` table and migration `0005`

> **This task is destructive.** `upgrade()` deletes every existing `workout_set`
> and `workout_entry` row, on both dialects, and `downgrade()` cannot restore
> them. The user has approved this. It runs against whatever `DATABASE_URL`
> points at — check that before running `flask --app app upgrade-db`.

**Files:**
- Modify: `app/tables.py:34-65` (the `user` table, then `workout_entry.user_id`)
- Create: `migrations/versions/0005_user_accounts.py`
- Modify: `tests/conftest.py:50-59` (the Postgres `TRUNCATE`)
- Test: `tests/test_migrations.py` (existing, unchanged — it must keep passing)

**Interfaces:**
- Consumes: nothing.
- Produces: `app.tables.user` — a `sa.Table` with columns `id` (`Uuid(as_uuid=False)`, PK), `email` (`Text`, not null, unique), `created_at` (`DateTime(timezone=True)`, not null). `app.tables.workout_entry` gains `user_id` (`Uuid(as_uuid=False)`, not null, FK → `user.id` `ON DELETE CASCADE`) and the index `idx_workout_entry_user_date` over `(user_id, entry_date)`.

- [ ] **Step 1: Add the `user` table to the metadata**

In `app/tables.py`, insert between the `metadata = ...` line and the `workout_entry` definition:

```python
#: The account. **A mirror row, not the source of truth.**
#:
#: Supabase owns credentials; this table exists because ``user_id`` has to be a
#: real foreign key on both dialects and SQLite has no ``auth.users`` to point
#: at. It therefore carries no ``password_hash`` (a credential we chose not to
#: own) and no ``verified_at`` (Supabase's ``email_confirmed_at`` is the truth,
#: and a mirrored copy drifts invisibly until someone is wrongly let in or
#: wrongly kept out).
#:
#: Rows appear just-in-time, on the first authenticated request carrying a
#: ``sub`` we have not seen — there is no signup webhook. See
#: ``models.ensure_user``.
#:
#: ``user`` is a reserved word in Postgres. SQLAlchemy quotes identifiers
#: automatically in both dialects, so this is safe — but it is why the name must
#: never be interpolated into a string query.
user = sa.Table(
    "user",
    metadata,
    # The Supabase auth.users id, which is the JWT's `sub`. Not minted here.
    # as_uuid=False stores 32-char hex and returns the hyphenated 36-char form,
    # exactly as workout_set.id does — compare with uuid.UUID(...), never with
    # string equality against a `.hex`.
    sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column("email", sa.Text, nullable=False, unique=True),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
)
```

- [ ] **Step 2: Add `user_id` to `workout_entry`**

In `app/tables.py`, replace the `exercise_id` column line and the docstring above the table.

Change the table's leading comment from `No ``user_id`` yet — see Phase 5.` to:

```python
#: Append-only, and there is no per-day "workout" parent row, which keeps logging
#: a single insert and range queries trivial. Every row belongs to exactly one
#: user as of Phase 5.
```

Then insert after the `exercise_id` column:

```python
    #: The owning account. ``ON DELETE CASCADE`` all the way down, so deleting a
    #: user is one DELETE and needs no cascade handling in Python — the same
    #: property delete_entry has relied on since Phase 4.
    sa.Column(
        "user_id",
        sa.Uuid(as_uuid=False),
        sa.ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
    ),
```

And add the composite index beside the existing one:

```python
    sa.Index("idx_workout_entry_date", "entry_date"),
    # Every query in models.py now filters on user_id first and ranges on
    # entry_date second, which is the order this index is built in.
    sa.Index("idx_workout_entry_user_date", "user_id", "entry_date"),
```

- [ ] **Step 3: Run the migration test to verify it fails**

Run: `pytest tests/test_migrations.py -v`
Expected: FAIL — autogenerate reports a diff, because `tables.py` now describes a table and a column no revision creates.

- [ ] **Step 4: Write the migration**

Create `migrations/versions/0005_user_accounts.py`:

```python
"""Add user accounts and give every entry an owner

Phase 5. Two append-only tables become two append-only tables plus an account,
and every ``workout_entry`` row gains a ``user_id``.

**This revision is destructive and irreversible.** It deletes every existing
``workout_set`` and ``workout_entry`` row before adding the column. That is a
decision, not a shortcut: a backfill onto a seed account would carry
single-user development history into the multi-user world as one account's
workouts and leave a permanent "who is user 1" question behind it.
``downgrade()`` puts the column and the table back. It cannot put the rows back.

**``batch_alter_table`` unconditionally, not branched by dialect.** SQLite
refuses to ``ADD COLUMN`` when the column is ``NOT NULL`` with no default, and
refuses again when it carries a ``REFERENCES`` clause. Both rules apply to an
empty table, so wiping first does not rescue a plain ``ALTER``. Batch mode
rebuilds under SQLite and emits a plain ``ALTER`` under Postgres, which is one
code path where revisions 0003 and 0004 each needed two.

Revision 0003's CAST trap does not bite here: ``cast_for_batch_migrate`` only
fires when a column's type *changes*, and nothing here changes type.

``copy_from`` is passed rather than letting batch mode reflect the table.
Reflection would lose ``sqlite_autoincrement``, and SQLite would start reusing
the ids of deleted rows.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-31

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | None = None
depends_on: str | None = None

#: A frozen copy, not an import from app/tables.py — the rule revision 0002
#: established. Batch mode needs the convention passed explicitly or SQLite's
#: rebuilt constraints come out unnamed.
_NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def _entry_table(*, with_user: bool) -> sa.Table:
    """A frozen handle on ``workout_entry``, for ``batch_alter_table(copy_from=)``.

    Spelled out rather than reflected so ``sqlite_autoincrement`` survives the
    rebuild. Each call gets its own MetaData because a Table name can only be
    registered once per MetaData.
    """
    columns = [
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("entry_date", sa.Date, nullable=False),
        sa.Column("exercise_id", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    ]
    if with_user:
        columns.append(
            sa.Column(
                "user_id",
                sa.Uuid(as_uuid=False),
                sa.ForeignKey("user.id", ondelete="CASCADE"),
                nullable=False,
            )
        )
    return sa.Table(
        "workout_entry",
        sa.MetaData(naming_convention=_NAMING_CONVENTION),
        *columns,
        sa.Index("idx_workout_entry_date", "entry_date"),
        sqlite_autoincrement=True,
    )


def upgrade() -> None:
    # The wipe. Children first — app/db.py turns SQLite foreign keys on for
    # every connection, so the order is enforced rather than merely tidy.
    op.execute("DELETE FROM workout_set")
    op.execute("DELETE FROM workout_entry")

    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(as_uuid=False), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user"),
        # Spelled in full, not as a bare token: the `uq` convention carries no
        # %(constraint_name)s, so a name given here is used verbatim rather than
        # prefixed. `ck` is the opposite, which is why 0004's checks are bare.
        sa.UniqueConstraint("email", name="uq_user_email"),
    )

    with op.batch_alter_table(
        "workout_entry",
        copy_from=_entry_table(with_user=False),
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.add_column(
            sa.Column("user_id", sa.Uuid(as_uuid=False), nullable=False)
        )
        batch.create_foreign_key(
            "fk_workout_entry_user_id_user",
            "user",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    op.create_index(
        "idx_workout_entry_user_date", "workout_entry", ["user_id", "entry_date"]
    )


def downgrade() -> None:
    """Remove accounts.

    **Does not restore the rows ``upgrade()`` deleted.** Nothing can — they were
    not copied anywhere. This returns the schema to its Phase 4 shape and leaves
    it empty.
    """
    op.drop_index("idx_workout_entry_user_date", table_name="workout_entry")

    with op.batch_alter_table(
        "workout_entry",
        copy_from=_entry_table(with_user=True),
        naming_convention=_NAMING_CONVENTION,
    ) as batch:
        batch.drop_constraint("fk_workout_entry_user_id_user", type_="foreignkey")
        batch.drop_column("user_id")

    op.drop_table("user")
```

- [ ] **Step 5: Run the migration test to verify it passes**

Run: `pytest tests/test_migrations.py -v`
Expected: PASS — autogenerate finds no diff between `tables.py` and the chain.

- [ ] **Step 6: Add `"user"` to the Postgres truncate**

In `tests/conftest.py`, replace the `TRUNCATE` string:

```python
                    sa.text(
                        'TRUNCATE TABLE workout_set, workout_entry, "user" '
                        "RESTART IDENTITY CASCADE"
                    )
```

Note the double quotes around `user` inside a single-quoted Python string — this is the one place in the project that writes raw SQL, and the one place the reserved word needs quoting by hand.

- [ ] **Step 7: Verify the chain round-trips**

Run:
```bash
rm -f /tmp/chain-check.sqlite3
DATABASE_URL=sqlite:////tmp/chain-check.sqlite3 alembic upgrade head
DATABASE_URL=sqlite:////tmp/chain-check.sqlite3 alembic downgrade -1
DATABASE_URL=sqlite:////tmp/chain-check.sqlite3 alembic upgrade head
```
Expected: three clean runs, no traceback. This is what the Postgres CI job does against a real dialect; doing it here catches the SQLite rebuild.

- [ ] **Step 8: Run the full suite**

Run: `pytest`
Expected: FAIL — many tests in `test_api.py`, `test_models.py`, `test_summary.py` and `test_graph.py` now fail with `IntegrityError: NOT NULL constraint failed: workout_entry.user_id`. That is correct and expected: the column exists but nothing writes it yet. Tasks 4–6 close this. Do not patch the tests here.

- [ ] **Step 9: Commit**

```bash
git add app/tables.py migrations/versions/0005_user_accounts.py tests/conftest.py
git commit -m "Add the user table and give every entry an owner

A mirror row, not a source of truth: Supabase owns credentials, and this
table exists because user_id has to be a real foreign key on both dialects
and SQLite has no auth.users to point at. No password_hash, no verified_at
— a mirrored verification flag drifts invisibly until someone is wrongly
let in or wrongly kept out.

Revision 0005 wipes every existing entry and set before adding the column.
Backfilling onto a seed account would carry development history into the
multi-user world as one account's workouts and leave a permanent 'who is
user 1' question. downgrade() cannot undo it and says so.

batch_alter_table unconditionally: SQLite refuses ADD COLUMN for a NOT NULL
column with a REFERENCES clause even on an empty table, so wiping first
does not rescue a plain ALTER. copy_from is passed so the rebuild does not
lose sqlite_autoincrement.

The suite fails after this commit until models.py writes the column."
```

---

> **Tasks 4 and 5 leave the broad suite red.** Revision `0005` added a `NOT NULL`
> column that nothing writes yet, so `test_api.py`, `test_models.py`,
> `test_summary.py` and `test_graph.py` fail with `IntegrityError` until Task 6
> lands the authed test client. Each of these tasks has its own targeted tests,
> which do pass. Run those, not the whole suite, at the "verify it passes" step —
> the step says which.

### Task 4: The user mirror in `app/models.py`

**Files:**
- Modify: `app/models.py:26-30` (imports), and append three functions after `parse_date`
- Test: `tests/test_auth.py` (append a class)

**Interfaces:**
- Consumes: `app.tables.user` from Task 3.
- Produces:
  ```python
  def ensure_user(user_id: str, email: str) -> None: ...
  def get_user(user_id: str) -> dict | None: ...   # {"id": str, "email": str}
  def delete_user(user_id: str) -> bool: ...
  ```

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_auth.py`:

```python
from app.models import add_entry, delete_user, ensure_user, get_user


class TestUserMirror:
    """Rows appear just-in-time. There is no signup webhook to create them."""

    def test_a_new_sub_is_inserted(self, app):
        with app.app_context():
            ensure_user(SUB, "tester@example.com")
            assert get_user(SUB) == {"id": SUB, "email": "tester@example.com"}

    def test_an_unknown_sub_reads_as_none(self, app):
        with app.app_context():
            assert get_user(SUB) is None

    def test_a_second_call_does_not_duplicate_the_row(self, app):
        with app.app_context():
            ensure_user(SUB, "tester@example.com")
            ensure_user(SUB, "tester@example.com")
            assert get_user(SUB) == {"id": SUB, "email": "tester@example.com"}

    def test_a_changed_email_is_written_through(self, app):
        """Supabase is the source of truth for the address, so it wins."""
        with app.app_context():
            ensure_user(SUB, "old@example.com")
            ensure_user(SUB, "new@example.com")
            assert get_user(SUB)["email"] == "new@example.com"

    def test_deleting_a_user_reports_it(self, app):
        with app.app_context():
            ensure_user(SUB, "tester@example.com")
            assert delete_user(SUB) is True
            assert get_user(SUB) is None

    def test_deleting_an_absent_user_reports_false(self, app):
        with app.app_context():
            assert delete_user(SUB) is False

    def test_deleting_a_user_cascades_to_entries_and_sets(self, app):
        """One DELETE, no cascade handling in Python — the FK does the work."""
        with app.app_context():
            ensure_user(SUB, "tester@example.com")
            entry = add_entry(SUB, "2026-07-28", "Barbell_Squat", [{}, {}])
            assert entry.sets == 2
            delete_user(SUB)
            assert get_user(SUB) is None
```

Note `test_deleting_a_user_cascades_to_entries_and_sets` calls `add_entry` with the Task 5 signature. It will keep failing until Task 5; that is deliberate and the step below says so.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_auth.py::TestUserMirror -v`
Expected: FAIL at collection — `ImportError: cannot import name 'ensure_user' from 'app.models'`.

- [ ] **Step 3: Write the implementation**

In `app/models.py`, extend the imports:

```python
from .tables import user, workout_entry, workout_set
```

and add `import sqlalchemy.exc` is **not** needed — `sa.exc` is available from the existing `import sqlalchemy as sa`.

Append after `parse_date`:

```python
def ensure_user(user_id: str, email: str) -> None:
    """Create the mirror row for ``user_id`` if it is not there, or refresh it.

    Called on **every** authenticated request, which makes this the only place
    in the app where a GET writes. Worth knowing before anyone adds a read
    replica or wonders why a summary request opened a transaction.

    The insert catches ``IntegrityError`` rather than using an upsert, because
    ``on_conflict_do_nothing()`` is spelled differently per dialect and this
    layer serves both. Two concurrent first requests therefore race safely: one
    inserts, the other rolls back and carries on.

    The email is written through on change — Supabase owns the address, so a
    stale mirror is simply wrong.
    """
    db = get_db()
    row = db.execute(sa.select(user.c.email).where(user.c.id == user_id)).first()

    if row is None:
        try:
            db.execute(sa.insert(user).values(id=user_id, email=email))
            db.commit()
        except sa.exc.IntegrityError:
            # Lost the race, or the address belongs to another sub. Either way
            # the row we needed exists; a failed mirror must not fail the request.
            db.rollback()
        return

    if row.email != email:
        db.execute(sa.update(user).where(user.c.id == user_id).values(email=email))
        db.commit()


def get_user(user_id: str) -> dict | None:
    """Return ``{"id", "email"}`` for ``user_id``, or ``None``."""
    row = get_db().execute(sa.select(user).where(user.c.id == user_id)).first()
    if row is None:
        return None
    # str() for the same reason WorkoutSet.id does it: Postgres hands back a
    # UUID object where SQLite hands back the hyphenated string.
    return {"id": str(row.id), "email": row.email}


def delete_user(user_id: str) -> bool:
    """Delete an account and, by cascade, everything it owns.

    One statement. ``workout_entry.user_id`` and ``workout_set.entry_id`` are
    both ``ON DELETE CASCADE`` and app/db.py enables SQLite foreign keys per
    connection, so there is no cascade handling to write here — and Phase 7's
    ``body_metric`` and Phase 8's ``custom_exercise`` inherit that by declaring
    the same FK.
    """
    db = get_db()
    result = db.execute(sa.delete(user).where(user.c.id == user_id))
    db.commit()
    return result.rowcount > 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_auth.py::TestUserMirror -v`
Expected: six PASS; `test_deleting_a_user_cascades_to_entries_and_sets` FAILS with `TypeError: add_entry() takes 3 positional arguments but 4 were given`. Task 5 closes it.

- [ ] **Step 5: Commit**

```bash
git add app/models.py tests/test_auth.py
git commit -m "Mirror Supabase users into the database just-in-time

There is no signup webhook, so the row appears on the first authenticated
request carrying a sub we have not seen. That makes ensure_user the only
place in the app where a GET writes.

The insert swallows IntegrityError rather than using an upsert:
on_conflict_do_nothing() is spelled per dialect, and this layer serves
both. Two concurrent first requests race safely.

delete_user is one statement — the cascade does the rest, which is the
same property delete_entry has relied on since Phase 4."
```

---

### Task 5: The `user_id` sweep

**Files:**
- Modify: `app/models.py` — every function touching `workout_entry`
- Modify: `app/services/summary.py:189-220` (`weekly_summary`)
- Modify: `app/services/graph.py:92-158` (`training_graph`)
- Test: `tests/test_models.py` (existing calls updated), `tests/test_auth.py::TestUserMirror` (the cascade test goes green)

**Interfaces:**
- Consumes: `ensure_user` from Task 4.
- Produces — every signature below is exact, and `user_id: str` is **first and positional** in all of them:
  ```python
  def add_entry(user_id: str, entry_date, exercise_id: str,
                sets: list[dict]) -> WorkoutEntry: ...
  def get_entry(user_id: str, entry_id: int) -> WorkoutEntry | None: ...
  def list_entries(user_id: str, start: date | None = None,
                   end: date | None = None) -> list[WorkoutEntry]: ...
  def delete_entry(user_id: str, entry_id: int) -> bool: ...
  def recent_exercise_usage(user_id: str, limit: int = 12) -> list[tuple[str, int]]: ...
  def recent_exercise_ids(user_id: str, limit: int = 12) -> list[str]: ...
  def last_sets_for_exercise(user_id: str,
                             exercise_id: str) -> tuple[date | None, list[WorkoutSet]]: ...
  def exercise_activity(user_id: str, start: date,
                        end: date) -> list[tuple[str, int, int, date]]: ...
  def exercise_co_occurrence(user_id: str, start: date,
                             end: date) -> list[tuple[str, str, int]]: ...
  def sets_by_date(user_id: str, start: date, end: date) -> dict[str, int]: ...

  # services
  def weekly_summary(user_id: str, day: date, week_starts_on: int = 1) -> dict: ...
  def training_graph(user_id: str, window: str = DEFAULT_WINDOW,
                     today: date | None = None, week_starts_on: int = 1) -> dict: ...
  ```
  `_sets_for(entry_ids)` and `_entries_from(rows)` keep their signatures unchanged.

- [ ] **Step 1: Write the failing test**

Create the ownership boundary test now, at the model layer, before touching the API. Append to `tests/test_auth.py`:

```python
OTHER_SUB = "22222222-2222-4222-8222-222222222222"


class TestQueriesAreScopedToOneUser:
    """The model layer is where the WHERE clause has to be right.

    tests/test_ownership.py proves the same thing through the API. This proves
    it one layer down, so a failure says which layer lost the clause.
    """

    @pytest.fixture
    def two_users(self, app):
        with app.app_context():
            ensure_user(SUB, "one@example.com")
            ensure_user(OTHER_SUB, "two@example.com")
            add_entry(SUB, "2026-07-28", "Barbell_Squat", [{}, {}, {}])
            add_entry(OTHER_SUB, "2026-07-28", "Barbell_Bench_Press", [{}, {}])
            yield

    def test_list_entries_sees_only_its_own(self, app, two_users):
        from app.models import list_entries
        with app.app_context():
            mine = list_entries(SUB)
            assert [e.exercise_id for e in mine] == ["Barbell_Squat"]

    def test_get_entry_refuses_another_users_row(self, app, two_users):
        from app.models import get_entry, list_entries
        with app.app_context():
            theirs = list_entries(OTHER_SUB)[0]
            assert get_entry(OTHER_SUB, theirs.id) is not None
            assert get_entry(SUB, theirs.id) is None

    def test_delete_entry_refuses_another_users_row_and_leaves_it(self, app, two_users):
        from app.models import delete_entry, get_entry, list_entries
        with app.app_context():
            theirs = list_entries(OTHER_SUB)[0]
            assert delete_entry(SUB, theirs.id) is False
            assert get_entry(OTHER_SUB, theirs.id) is not None

    def test_sets_by_date_counts_only_its_own(self, app, two_users):
        from app.models import sets_by_date
        from datetime import date as _date
        with app.app_context():
            totals = sets_by_date(SUB, _date(2026, 7, 1), _date(2026, 7, 31))
            assert totals == {"2026-07-28": 3}

    def test_recent_usage_sees_only_its_own(self, app, two_users):
        from app.models import recent_exercise_usage
        with app.app_context():
            assert recent_exercise_usage(SUB) == [("Barbell_Squat", 1)]

    def test_last_sets_does_not_leak_through_the_set_table(self, app, two_users):
        """The join back through workout_entry is what stops this being an IDOR."""
        from app.models import last_sets_for_exercise
        with app.app_context():
            day, sets = last_sets_for_exercise(SUB, "Barbell_Bench_Press")
            assert day is None
            assert sets == []

    def test_activity_and_co_occurrence_see_only_their_own(self, app, two_users):
        from app.models import exercise_activity, exercise_co_occurrence
        from datetime import date as _date
        with app.app_context():
            start, end = _date(2026, 7, 1), _date(2026, 7, 31)
            assert [row[0] for row in exercise_activity(SUB, start, end)] == [
                "Barbell_Squat"
            ]
            assert exercise_co_occurrence(SUB, start, end) == []

    def test_the_weekly_summary_is_per_user(self, app, two_users):
        from app.services.summary import weekly_summary
        from datetime import date as _date
        with app.app_context():
            week = weekly_summary(SUB, _date(2026, 7, 28))
            assert week["total_sets"] == 3
            assert week["total_entries"] == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_auth.py::TestQueriesAreScopedToOneUser -v`
Expected: every test FAILS with `TypeError: ... takes N positional arguments but N+1 were given`.

- [ ] **Step 3: Sweep `app/models.py`**

Ten changes. Each adds `user_id: str` as the first parameter and a `WHERE` clause.

`add_entry` — write the column:

```python
def add_entry(
    user_id: str, entry_date, exercise_id: str, sets: list[dict]
) -> WorkoutEntry:
    """Insert an entry and its sets, owned by ``user_id``, after validating both."""
    parsed_date, parsed_exercise = validate_entry(entry_date, exercise_id)
    rows = validate_sets(sets)

    db = get_db()
    result = db.execute(
        sa.insert(workout_entry).values(
            user_id=user_id, entry_date=parsed_date, exercise_id=parsed_exercise
        )
    )
    entry_id = int(result.inserted_primary_key[0])
    db.execute(
        sa.insert(workout_set),
        [{"id": uuid4().hex, "entry_id": entry_id, **row} for row in rows],
    )
    db.commit()

    stored = get_entry(user_id, entry_id)
    if stored is None:  # pragma: no cover - the insert just succeeded
        raise ValidationError("Entry could not be stored.")
    return stored
```

`get_entry`:

```python
def get_entry(user_id: str, entry_id: int) -> WorkoutEntry | None:
    """Return one of ``user_id``'s entries with its sets, or ``None``.

    Another user's id reads as absent rather than forbidden — the caller turns
    that into a 404, which is the same answer an id that does not exist gets. A
    403 would confirm the id is real.
    """
    rows = (
        get_db()
        .execute(
            sa.select(workout_entry).where(
                workout_entry.c.id == entry_id,
                workout_entry.c.user_id == user_id,
            )
        )
        .all()
    )
    entries = _entries_from(rows)
    return entries[0] if entries else None
```

`list_entries`:

```python
def list_entries(
    user_id: str, start: date | None = None, end: date | None = None
) -> list[WorkoutEntry]:
    """Return ``user_id``'s entries in the inclusive ``start``–``end`` range."""
    query = sa.select(workout_entry).where(workout_entry.c.user_id == user_id)
    if start is not None:
        query = query.where(workout_entry.c.entry_date >= start)
    if end is not None:
        query = query.where(workout_entry.c.entry_date <= end)
    query = query.order_by(
        workout_entry.c.entry_date.desc(), workout_entry.c.id.desc()
    )
    return _entries_from(get_db().execute(query).all())
```

`delete_entry`:

```python
def delete_entry(user_id: str, entry_id: int) -> bool:
    """Delete one of ``user_id``'s entries. ``True`` if a row was removed.

    Returns ``False`` for another user's row, so the API answers 404 — identical
    to a row that does not exist. This is the endpoint the roadmap named as the
    live IDOR before Phase 5.
    """
    db = get_db()
    result = db.execute(
        sa.delete(workout_entry).where(
            workout_entry.c.id == entry_id,
            workout_entry.c.user_id == user_id,
        )
    )
    db.commit()
    return result.rowcount > 0
```

`recent_exercise_usage` — add the filter before `group_by`:

```python
def recent_exercise_usage(user_id: str, limit: int = 12) -> list[tuple[str, int]]:
```
```python
            sa.select(workout_entry.c.exercise_id, last_used, uses)
            .where(workout_entry.c.user_id == user_id)
            .group_by(workout_entry.c.exercise_id)
```

`recent_exercise_ids`:

```python
def recent_exercise_ids(user_id: str, limit: int = 12) -> list[str]:
    """Return ``user_id``'s recently-logged exercise ids, most recent first."""
    return [exercise_id for exercise_id, _uses in recent_exercise_usage(user_id, limit)]
```

`last_sets_for_exercise` — the docstring's Phase 5 promise comes due:

```python
def last_sets_for_exercise(
    user_id: str, exercise_id: str
) -> tuple[date | None, list[WorkoutSet]]:
    """The most recent entry's sets for ``exercise_id`` — the /log prefill.

    **Joins back through ``workout_entry`` rather than reading ``workout_set``
    directly**, which is what makes the ``user_id`` filter below reachable at
    all. A set query that skipped this join would be the same IDOR as an
    unguarded ``delete_entry``, wearing a different hat.
    """
    row = (
        get_db()
        .execute(
            sa.select(workout_entry.c.id, workout_entry.c.entry_date)
            .where(
                workout_entry.c.exercise_id == exercise_id,
                workout_entry.c.user_id == user_id,
            )
            .order_by(
                workout_entry.c.entry_date.desc(), workout_entry.c.id.desc()
            )
            .limit(1)
        )
        .first()
    )
    if row is None:
        return None, []
    return row.entry_date, _sets_for([row.id]).get(row.id, [])
```

`_counted_sessions`:

```python
def _counted_sessions(user_id: str, start: date, end: date):
```
with `workout_entry.c.user_id == user_id,` added to its existing `.where(...)`.

`exercise_activity`:

```python
def exercise_activity(
    user_id: str, start: date, end: date
) -> list[tuple[str, int, int, date]]:
```
with `workout_entry.c.user_id == user_id,` added to its existing `.where(...)`.

`exercise_co_occurrence`:

```python
def exercise_co_occurrence(
    user_id: str, start: date, end: date
) -> list[tuple[str, str, int]]:
```
with both subquery calls becoming `_counted_sessions(user_id, start, end)`.

`sets_by_date`:

```python
def sets_by_date(user_id: str, start: date, end: date) -> dict[str, int]:
```
with `workout_entry.c.user_id == user_id,` added to its existing `.where(...)`.

- [ ] **Step 4: Annotate `_sets_for` with why it is the exception**

Replace the docstring of `_sets_for` in `app/models.py`:

```python
def _sets_for(entry_ids: list[int]) -> dict[int, list[WorkoutSet]]:
    """Fetch every set for the given entries in **one** query.

    One batched query rather than one per entry: the day panel renders every
    entry's sets, and a per-entry fetch would be an N+1 the moment anyone logs
    a full session.

    **This is the one query in the module that does not filter by ``user_id``,
    and that is safe only because of who calls it.** Every caller passes ids
    that came out of an already-filtered query, so the join would be redundant.
    A new caller that sources entry ids any other way — a client-supplied id, a
    join from ``workout_set``, anything — **must** join back through
    ``workout_entry`` and filter there, or it is an IDOR.
    """
```

- [ ] **Step 5: Thread `user_id` through `services/summary.py`**

Change `weekly_summary` only — `grade`, `overshoot_span`, `summarise_entries` and `_finish_regions` are pure and unchanged:

```python
def weekly_summary(user_id: str, day: date, week_starts_on: int = 1) -> dict:
    """Build the full payload backing the weekly summary page for ``day``."""
    start, end = week_bounds(day, week_starts_on)
    entries = list_entries(user_id, start, end)
```

- [ ] **Step 6: Thread `user_id` through `services/graph.py`**

```python
def training_graph(
    user_id: str,
    window: str = DEFAULT_WINDOW,
    today: date | None = None,
    week_starts_on: int = 1,
) -> dict:
```

and three call sites inside it:

```python
    activity = exercise_activity(user_id, start or date(1970, 1, 1), end)
```
```python
        for a, b, days in exercise_co_occurrence(user_id, start or date(1970, 1, 1), end)
```
```python
    week = weekly_summary(user_id, today, week_starts_on)
```

- [ ] **Step 7: Run the targeted tests to verify they pass**

Run: `pytest tests/test_auth.py -v`
Expected: PASS, including `test_deleting_a_user_cascades_to_entries_and_sets`, which Task 4 left failing.

- [ ] **Step 8: Commit**

```bash
git add app/models.py app/services/summary.py app/services/graph.py tests/test_auth.py
git commit -m "Scope every entry query to one user

user_id is the first positional parameter of all ten functions that touch
workout_entry. Positional-and-first is the safety property, not a style
choice: a call site that was not updated fails loudly as a TypeError
instead of silently querying across all users.

delete_entry and get_entry return nothing for another user's row, so the
API answers 404 — the same answer an id that does not exist gets.
Returning 403 would confirm the id is real.

_sets_for is the one query that does not filter, because every caller
passes ids from an already-filtered query. Its docstring now says so, and
says what a new caller has to do instead.

weekly_summary and training_graph thread it through; their rules are
unchanged. services/weeks.py needs nothing — it is pure date arithmetic.

The broad suite stays red until the API supplies g.user_id."
```

---

### Task 6: `require_user`, endpoint gating, and the authed test client

This is the task that turns the suite green again.

**Files:**
- Modify: `app/api.py` (imports, `require_user`, seven decorated endpoints, `GET /api/me`)
- Modify: `tests/conftest.py` (token minting, the authed client, seeding the test user)
- Modify: `tests/test_summary.py:216-243, 336-339`, `tests/test_graph.py:72-...`, `tests/test_models.py:49-66` (pass `TEST_USER_ID`)
- Test: `tests/test_api.py` (append an auth class)

**Interfaces:**
- Consumes: `decode_token`, `Claims`, `AuthError` (Task 2); `ensure_user`, `get_user` (Task 4); the swept model and service signatures (Task 5).
- Produces:
  - `app.api.require_user` — a decorator setting `g.user_id: str`.
  - `GET /api/me` → `{"user": {"id": str, "email": str}}`.
  - 401 body `{"error": "Sign in to continue."}` with header `WWW-Authenticate: Bearer`.
  - `tests.conftest.TEST_USER_ID: str`, `tests.conftest.TEST_USER_EMAIL: str`, `tests.conftest.OTHER_USER_ID: str`, `tests.conftest.OTHER_USER_EMAIL: str`, `tests.conftest.make_token(app, user_id=..., email=..., **overrides) -> str`, and the `other_client` fixture.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_api.py`:

```python
class TestGatedEndpoints:
    """Everything reading or writing entries needs a token. The catalog does not."""

    GATED = [
        ("get", "/api/entries?date=2026-07-28"),
        ("get", "/api/entries/../entries"),
        ("get", "/api/calendar?year=2026&month=7"),
        ("get", "/api/summary/week?date=2026-07-28"),
        ("get", "/api/progress/graph?window=8w"),
        ("get", "/api/exercises/recent"),
        ("get", "/api/exercises/Barbell_Squat/last-sets"),
        ("get", "/api/me"),
    ]

    PUBLIC = [
        "/api/exercises",
        "/api/exercises/Barbell_Squat",
        "/api/summary/week/bounds?date=2026-07-28",
    ]

    @pytest.mark.parametrize(("method", "path"), GATED)
    def test_a_missing_token_is_401(self, app, method, path):
        anonymous = app.test_client()
        response = getattr(anonymous, method)(path)
        assert response.status_code == 401
        assert response.get_json()["error"] == "Sign in to continue."
        assert response.headers["WWW-Authenticate"] == "Bearer"

    def test_posting_an_entry_without_a_token_is_401(self, app):
        anonymous = app.test_client()
        response = anonymous.post(
            "/api/entries",
            json={"date": "2026-07-28", "exercise_id": "Barbell_Squat", "sets": [{}]},
        )
        assert response.status_code == 401

    def test_deleting_an_entry_without_a_token_is_401(self, app):
        anonymous = app.test_client()
        assert anonymous.delete("/api/entries/1").status_code == 401

    @pytest.mark.parametrize("path", PUBLIC)
    def test_public_endpoints_need_no_token(self, app, path):
        """The catalog ships in the repo and week bounds are date arithmetic.

        Gating them would buy nothing and would leave the login page unable to
        render anything.
        """
        anonymous = app.test_client()
        assert anonymous.get(path).status_code == 200

    def test_a_non_bearer_scheme_is_401(self, app):
        anonymous = app.test_client()
        response = anonymous.get(
            "/api/entries", headers={"Authorization": "Basic abc123"}
        )
        assert response.status_code == 401

    def test_a_garbage_token_is_401(self, app):
        anonymous = app.test_client()
        response = anonymous.get(
            "/api/entries", headers={"Authorization": "Bearer not.a.token"}
        )
        assert response.status_code == 401


class TestMe:
    def test_me_returns_the_signed_in_user(self, client):
        from tests.conftest import TEST_USER_EMAIL, TEST_USER_ID

        response = client.get("/api/me")
        assert response.status_code == 200
        assert response.get_json()["user"] == {
            "id": TEST_USER_ID,
            "email": TEST_USER_EMAIL,
        }

    def test_a_first_request_provisions_the_mirror_row(self, app):
        """No signup webhook: the row appears on first authenticated contact."""
        from app.models import get_user
        from tests.conftest import make_token

        fresh = "33333333-3333-4333-8333-333333333333"
        with app.app_context():
            assert get_user(fresh) is None

        anonymous = app.test_client()
        token = make_token(app, user_id=fresh, email="fresh@example.com")
        response = anonymous.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200

        with app.app_context():
            assert get_user(fresh)["email"] == "fresh@example.com"
```

Delete the stray `("get", "/api/entries/../entries")` line from `GATED` — it was a typo; the list should read:

```python
    GATED = [
        ("get", "/api/entries?date=2026-07-28"),
        ("get", "/api/calendar?year=2026&month=7"),
        ("get", "/api/summary/week?date=2026-07-28"),
        ("get", "/api/progress/graph?window=8w"),
        ("get", "/api/exercises/recent"),
        ("get", "/api/exercises/Barbell_Squat/last-sets"),
        ("get", "/api/me"),
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_api.py::TestGatedEndpoints tests/test_api.py::TestMe -v`
Expected: the 401 tests FAIL (endpoints answer 200 or 500), and the `/api/me` tests FAIL with 404.

- [ ] **Step 3: Add `require_user` and gate the endpoints**

In `app/api.py`, extend the imports:

```python
import functools

from flask import Blueprint, current_app, g, jsonify, request

from .models import (
    ValidationError,
    add_entry,
    delete_entry,
    get_user,
    last_sets_for_exercise,
    list_entries,
    parse_date,
    recent_exercise_usage,
    sets_by_date,
)
from .services.auth import AuthError, decode_token
```

Add after `_image_base()`:

```python
def _unauthorised():
    """The one 401 this app produces.

    ``WWW-Authenticate: Bearer`` is what lets api.js tell this apart from a
    validation 400 without parsing prose. The body says the same thing for every
    cause — expired, forged, wrong project — because a 401 that distinguishes
    them is a small oracle and no client needs the distinction.
    """
    response = jsonify({"error": "Sign in to continue."})
    response.headers["WWW-Authenticate"] = "Bearer"
    return response, 401


def require_user(view):
    """Verify the bearer token, mirror the user, and set ``g.user_id``.

    The Flask glue for :mod:`app.services.auth`, and it lives here rather than
    there because it touches ``request``, ``g`` and ``current_app`` — which the
    layer rule calls HTTP.

    Note that this **writes** on a GET: ``ensure_user`` provisions the mirror row
    on first contact, since Supabase sends no signup webhook.
    """

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return _unauthorised()

        try:
            claims = decode_token(
                token.strip(),
                supabase_url=current_app.config.get("SUPABASE_URL") or "",
                jwt_secret=current_app.config.get("SUPABASE_JWT_SECRET"),
            )
        except AuthError:
            return _unauthorised()

        ensure_user(claims.sub, claims.email)
        g.user_id = claims.sub
        return view(*args, **kwargs)

    return wrapped
```

Add `ensure_user` to the `from .models import (...)` list.

Then decorate and thread `g.user_id`. Seven existing endpoints change; the decorator goes **below** the route decorator:

```python
@bp.get("/exercises/recent")
@require_user
def get_recent_exercises():
    ...
            for exercise_id, uses in recent_exercise_usage(g.user_id, limit)
```
```python
@bp.get("/exercises/<exercise_id>/last-sets")
@require_user
def get_last_sets(exercise_id: str):
    ...
    day, sets = last_sets_for_exercise(g.user_id, exercise_id)
```
```python
@bp.get("/entries")
@require_user
def get_entries():
    ...
    entries = list_entries(g.user_id, start, end)
```
```python
@bp.post("/entries")
@require_user
def create_entry():
    ...
    entry = add_entry(
        g.user_id,
        payload.get("date"),
        payload.get("exercise_id"),
        payload.get("sets"),
    )
```
```python
@bp.delete("/entries/<int:entry_id>")
@require_user
def remove_entry(entry_id: int):
    """Delete a workout entry by id.

    Another user's id answers 404, not 403 — see ``models.delete_entry``.
    """
    if not delete_entry(g.user_id, entry_id):
        return jsonify({"error": "Entry not found."}), 404
    return jsonify({"deleted": entry_id})
```
```python
@bp.get("/calendar")
@require_user
def get_calendar():
    ...
    return jsonify({"year": year, "month": month,
                    "days": sets_by_date(g.user_id, start, end)})
```
```python
@bp.get("/summary/week")
@require_user
def get_weekly_summary():
    day = _query_date("date")
    return jsonify(weekly_summary(g.user_id, day, _week_start()))
```
```python
@bp.get("/progress/graph")
@require_user
def get_progress_graph():
    ...
    return jsonify(
        training_graph(
            g.user_id,
            request.args.get("window", DEFAULT_WINDOW),
            _query_date("date"),
            _week_start(),
        )
    )
```

`get_exercises`, `get_exercise_detail` and `get_week_bounds` are **not** decorated. Add a comment above `get_exercises`:

```python
# Public, deliberately. The catalog is public-domain data that ships in the
# repo and the week-bounds endpoint is arithmetic over a query parameter;
# gating either would buy nothing and would leave /login unable to render.
```

Finally, the new endpoint, placed after `get_week_bounds`:

```python
@bp.get("/me")
@require_user
def get_me():
    """The signed-in user.

    Exists so the client can confirm a token server-side rather than trusting
    its own decode of it. The mirror row is guaranteed present by the time this
    runs — ``require_user`` provisioned it.
    """
    return jsonify({"user": get_user(g.user_id)})
```

- [ ] **Step 4: Give the test client a token**

Replace the fixtures section of `tests/conftest.py` (everything from `@pytest.fixture` for `client` onward) and extend the imports:

```python
import time

import jwt
from flask.testing import FlaskClient
from werkzeug.datastructures import Headers

from app.models import ensure_user

#: The user every test is signed in as, unless it says otherwise.
TEST_USER_ID = "11111111-1111-4111-8111-111111111111"
TEST_USER_EMAIL = "tester@example.com"

#: A second account, for tests/test_ownership.py.
OTHER_USER_ID = "22222222-2222-4222-8222-222222222222"
OTHER_USER_EMAIL = "other@example.com"


def make_token(app, user_id=TEST_USER_ID, email=TEST_USER_EMAIL, **overrides) -> str:
    """Mint an HS256 token the app will accept.

    Signed with the testing config's pinned ``SUPABASE_JWT_SECRET``, which is
    what keeps the suite offline: no test resolves a JWKS document, and no test
    reaches Supabase. ``overrides`` replaces any claim, which is how
    tests/test_auth.py builds its rejected tokens.
    """
    payload = {
        "sub": user_id,
        "email": email,
        "aud": "authenticated",
        "iss": f"{app.config['SUPABASE_URL']}/auth/v1",
        "exp": int(time.time()) + 3600,
    }
    payload.update(overrides)
    return jwt.encode(payload, app.config["SUPABASE_JWT_SECRET"], algorithm="HS256")


class AuthedClient(FlaskClient):
    """A test client that signs every request as :data:`token`'s user.

    Injecting the header here rather than at each call site is what let the
    whole pre-Phase-5 suite survive the sweep unedited. A request that sets its
    own ``Authorization`` wins, so a test can still be anonymous by using
    ``app.test_client()`` directly.
    """

    token: str | None = None

    def open(self, *args, **kwargs):
        headers = Headers(kwargs.get("headers") or {})
        if self.token and "Authorization" not in headers:
            headers["Authorization"] = f"Bearer {self.token}"
        kwargs["headers"] = headers
        return super().open(*args, **kwargs)


def _signed_in_client(app, user_id, email) -> AuthedClient:
    app.test_client_class = AuthedClient
    client = app.test_client()
    client.token = make_token(app, user_id=user_id, email=email)
    # Seeded rather than left to just-in-time provisioning, because tests that
    # call models.add_entry directly never go through require_user and would
    # otherwise trip the foreign key.
    with app.app_context():
        ensure_user(user_id, email)
    return client


@pytest.fixture
def client(app):
    """A Flask test client signed in as :data:`TEST_USER_ID`."""
    return _signed_in_client(app, TEST_USER_ID, TEST_USER_EMAIL)


@pytest.fixture
def other_client(app):
    """A second signed-in client, for the ownership tests."""
    return _signed_in_client(app, OTHER_USER_ID, OTHER_USER_EMAIL)
```

Keep the existing `add` fixture exactly as it is — it posts through `client`, so it inherits the header and needs no change.

- [ ] **Step 5: Update the tests that call models and services directly**

Three files call past the API and so must name a user.

`tests/test_summary.py` — import the id and pass it. Add to the imports:

```python
from tests.conftest import TEST_USER_ID
```

then in the four app-context tests, `add_entry("2026-07-28", ...)` becomes `add_entry(TEST_USER_ID, "2026-07-28", ...)` and `weekly_summary(date(2026, 7, 28))` becomes `weekly_summary(TEST_USER_ID, date(2026, 7, 28))`. The tests that build `WorkoutEntry` objects by hand and call `summarise_entries` are unchanged — that function is pure.

Those tests use the `app` fixture but not `client`, so the user row is not seeded for them. Change their signature from `(app)` to `(app, client)` — requesting `client` seeds the row and costs nothing else.

`tests/test_graph.py` — add the same import; `training_graph("8w", TODAY)` becomes `training_graph(TEST_USER_ID, "8w", TODAY)` at every call site. These tests already take the `add` fixture, which pulls in `client`, so the row is seeded.

`tests/test_models.py` — its raw inserts must carry the column. Add:

```python
from tests.conftest import TEST_USER_ID
```

give each raw `sa.insert(workout_entry)` a `user_id=TEST_USER_ID` value, change `recent_exercise_ids(2)` to `recent_exercise_ids(TEST_USER_ID, 2)` and `recent_exercise_ids()` to `recent_exercise_ids(TEST_USER_ID)`, and add `client` to both tests' parameters so the user row exists before the insert.

- [ ] **Step 6: Run the full suite**

Run: `pytest`
Expected: PASS. Everything red since Task 3 is now green.

- [ ] **Step 7: Verify against Postgres too**

The SQLite job cannot catch a dialect difference by construction, and this task is the first one where a reserved-word table name and a UUID foreign key meet real Postgres.

Run: `BODYSHOP_TEST_DATABASE_URL=postgresql://... pytest`
Expected: PASS. If no scratch Postgres is available, say so in the handoff rather than skipping it silently — CI runs it.

- [ ] **Step 8: Commit**

```bash
git add app/api.py tests/conftest.py tests/test_api.py tests/test_summary.py \
        tests/test_graph.py tests/test_models.py
git commit -m "Require a bearer token on every endpoint that touches entries

require_user verifies the token, provisions the mirror row and sets
g.user_id. It lives in api.py rather than services/ because it touches
request, g and current_app, which the layer rule calls HTTP.

Left public: GET /api/exercises, GET /api/exercises/<id> and
GET /api/summary/week/bounds. The catalog is public-domain data that ships
in the repo and week bounds are arithmetic over a query parameter; gating
either would leave /login unable to render anything.

GET /api/me is new, so a client can confirm a token server-side rather
than trusting its own decode of it.

The test client subclass injects the header by default, which is why the
pre-Phase-5 suite needed no per-call edits. Only the tests that call
models and services directly name a user."
```

---

### Task 7: `tests/test_ownership.py` — the proof

No production code changes here. This is the file that proves the sweep: the
roadmap's warning is that one missed `WHERE` clause is a data leak, and a table
of endpoints in one file is what makes a missed one visible.

**Files:**
- Create: `tests/test_ownership.py`

**Interfaces:**
- Consumes: `client`, `other_client`, `TEST_USER_ID`, `OTHER_USER_ID` from `tests/conftest.py` (Task 6); every gated endpoint from Task 6.
- Produces: nothing.

- [ ] **Step 1: Write the test file**

Create `tests/test_ownership.py`:

```python
"""Two users, exhaustively.

Phase 5's whole risk is one endpoint that forgot its ``WHERE user_id``. This
file walks every read and every write, with two accounts logging different
movements on the same day, and asserts each sees only its own. A missed clause
shows up here as a specific named failure rather than as a leak nobody notices.

The same-day, same-week overlap is deliberate: it makes a missing filter *fail*,
where two users training in different weeks would hide it behind a date range.
"""

from __future__ import annotations

import pytest

from tests.conftest import OTHER_USER_ID, TEST_USER_ID

DAY = "2026-07-28"          # a Tuesday
WEEK_START = "2026-07-27"
MINE = "Barbell_Squat"
THEIRS = "Barbell_Bench_Press"


@pytest.fixture
def two_users(add, other_client):
    """Both accounts log on the same day, in the same week."""
    assert add(DAY, MINE, 3).status_code == 201
    response = other_client.post(
        "/api/entries",
        json={"date": DAY, "exercise_id": THEIRS, "sets": [{}, {}]},
    )
    assert response.status_code == 201
    return response.get_json()["entry"]


class TestReadsAreScoped:
    def test_entries_for_a_day(self, client, other_client, two_users):
        mine = client.get(f"/api/entries?date={DAY}").get_json()["entries"]
        theirs = other_client.get(f"/api/entries?date={DAY}").get_json()["entries"]
        assert [e["exercise_id"] for e in mine] == [MINE]
        assert [e["exercise_id"] for e in theirs] == [THEIRS]

    def test_entries_over_a_range(self, client, two_users):
        entries = client.get(
            f"/api/entries?start=2026-07-01&end=2026-07-31"
        ).get_json()["entries"]
        assert [e["exercise_id"] for e in entries] == [MINE]

    def test_the_calendar(self, client, other_client, two_users):
        mine = client.get("/api/calendar?year=2026&month=7").get_json()["days"]
        theirs = other_client.get("/api/calendar?year=2026&month=7").get_json()["days"]
        assert mine == {DAY: 3}
        assert theirs == {DAY: 2}

    def test_the_weekly_summary(self, client, other_client, two_users):
        mine = client.get(f"/api/summary/week?date={DAY}").get_json()
        theirs = other_client.get(f"/api/summary/week?date={DAY}").get_json()
        assert mine["total_sets"] == 3
        assert theirs["total_sets"] == 2
        # Squat is a quad movement; bench is a chest movement. Neither week may
        # show any trace of the other's.
        assert mine["muscles"]["chest"]["sets"] == 0.0
        assert theirs["muscles"]["quadriceps"]["sets"] == 0.0

    def test_the_training_graph(self, client, other_client, two_users):
        mine = client.get("/api/progress/graph?window=all").get_json()
        theirs = other_client.get("/api/progress/graph?window=all").get_json()
        assert [n["exercise_id"] for n in mine["nodes"]] == [MINE]
        assert [n["exercise_id"] for n in theirs["nodes"]] == [THEIRS]

    def test_recent_exercises(self, client, other_client, two_users):
        mine = client.get("/api/exercises/recent").get_json()["exercises"]
        theirs = other_client.get("/api/exercises/recent").get_json()["exercises"]
        assert [e["id"] for e in mine] == [MINE]
        assert [e["id"] for e in theirs] == [THEIRS]

    def test_last_sets_does_not_reach_through_the_set_table(self, client, two_users):
        """The prefill joins back through workout_entry. This is why."""
        payload = client.get(f"/api/exercises/{THEIRS}/last-sets").get_json()
        assert payload == {"date": None, "sets": []}

    def test_last_sets_still_finds_your_own(self, client, two_users):
        payload = client.get(f"/api/exercises/{MINE}/last-sets").get_json()
        assert payload["date"] == DAY
        assert len(payload["sets"]) == 3


class TestWritesAreScoped:
    def test_deleting_another_users_entry_is_404(self, client, two_users):
        """404, not 403 — a 403 would confirm the id is real."""
        response = client.delete(f"/api/entries/{two_users['id']}")
        assert response.status_code == 404
        assert response.get_json()["error"] == "Entry not found."

    def test_the_refused_delete_leaves_the_row_intact(
        self, client, other_client, two_users
    ):
        """The half that matters. A 404 that still deleted would pass the test above."""
        client.delete(f"/api/entries/{two_users['id']}")
        still_there = other_client.get(f"/api/entries?date={DAY}").get_json()["entries"]
        assert [e["id"] for e in still_there] == [two_users["id"]]

    def test_deleting_your_own_entry_works(self, client, add, two_users):
        mine = client.get(f"/api/entries?date={DAY}").get_json()["entries"][0]
        assert client.delete(f"/api/entries/{mine['id']}").status_code == 200
        assert client.get(f"/api/entries?date={DAY}").get_json()["entries"] == []

    def test_a_new_entry_is_owned_by_its_poster(self, client, other_client, add):
        assert add(DAY, MINE, 1).status_code == 201
        assert other_client.get(f"/api/entries?date={DAY}").get_json()["entries"] == []


class TestIdentity:
    def test_each_client_is_a_different_user(self, client, other_client):
        assert client.get("/api/me").get_json()["user"]["id"] == TEST_USER_ID
        assert other_client.get("/api/me").get_json()["user"]["id"] == OTHER_USER_ID
```

- [ ] **Step 2: Run the tests**

Run: `pytest tests/test_ownership.py -v`
Expected: PASS, all of them. Tasks 5 and 6 already did the work; this file exists to prove it and to fail loudly if a later change loses a clause.

If anything fails here, **fix the query in `app/models.py`, not the test.** A failure in this file is a data leak.

- [ ] **Step 3: Deliberately break one clause, to check the test can see it**

Temporarily delete `workout_entry.c.user_id == user_id,` from `sets_by_date` in `app/models.py`.

Run: `pytest tests/test_ownership.py::TestReadsAreScoped::test_the_calendar -v`
Expected: FAIL. Then restore the line and re-run to confirm PASS.

A test file that cannot fail is not evidence, and this is the one file in the project where that is worth thirty seconds to verify.

- [ ] **Step 4: Run the full suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_ownership.py
git commit -m "Prove the ownership sweep endpoint by endpoint

Two accounts logging different movements on the same day, walked across
every read and every write. The same-day overlap is deliberate: it makes a
missing WHERE clause fail, where two users training in different weeks
would hide it behind a date range.

The delete case asserts both halves — 404 for another user's row, and the
row still there afterwards. A 404 that deleted anyway would pass the first
assertion alone."
```

---

### Task 8: `DELETE /api/account`

**Files:**
- Modify: `app/api.py` (one endpoint, one import)
- Create: `tests/test_account.py`

**Interfaces:**
- Consumes: `delete_auth_user`, `AuthError` (Task 2); `delete_user` (Task 4); `require_user` (Task 6).
- Produces: `DELETE /api/account` → `200 {"deleted": true, "auth_record_removed": bool}`, or `503 {"error": ...}` when `SUPABASE_SERVICE_ROLE_KEY` is unset.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_account.py`:

```python
"""In-app account deletion.

Apple's Guideline 5.1.1(v) is what eventually *requires* this, but an app
holding email addresses and training history needs it as ordinary privacy
hygiene, which is why it is here rather than deferred to Phase 10.

**Local rows go first, the auth record second.** If the Supabase call fails the
account survives with no data — recoverable, retryable, and the response says so.
Supabase-first would risk the opposite: the auth record gone, the rows orphaned
behind an account that can never sign in again to delete them.

Nothing here reaches the network. ``delete_auth_user`` is patched at its use
site in ``app.api``.
"""

from __future__ import annotations

import pytest

from app.models import get_user
from app.services.auth import AuthError
from tests.conftest import OTHER_USER_ID, TEST_USER_ID

DAY = "2026-07-28"


@pytest.fixture
def no_supabase_call(monkeypatch):
    """Record the call instead of making it."""
    calls = []

    def _fake(user_id, *, supabase_url, service_role_key, timeout=10.0):
        calls.append((user_id, supabase_url, service_role_key))

    monkeypatch.setattr("app.api.delete_auth_user", _fake)
    return calls


class TestDeleteAccount:
    def test_it_removes_the_user_their_entries_and_their_sets(
        self, app, client, add, no_supabase_call
    ):
        assert add(DAY, "Barbell_Squat", 3).status_code == 201

        response = client.delete("/api/account")
        assert response.status_code == 200
        assert response.get_json() == {"deleted": True, "auth_record_removed": True}

        with app.app_context():
            assert get_user(TEST_USER_ID) is None
        # The entries are gone with the user, by cascade — no cascade handling
        # in Python anywhere in this path.
        assert client.get(f"/api/entries?date={DAY}").get_json()["entries"] == []

    def test_it_calls_supabase_with_the_service_role_key(
        self, client, no_supabase_call
    ):
        client.delete("/api/account")
        assert no_supabase_call == [
            (TEST_USER_ID, "https://test.supabase.co", "test-service-role-key")
        ]

    def test_another_users_data_survives(
        self, app, client, other_client, add, no_supabase_call
    ):
        assert add(DAY, "Barbell_Squat", 3).status_code == 201
        assert other_client.post(
            "/api/entries",
            json={"date": DAY, "exercise_id": "Pullups", "sets": [{}, {}]},
        ).status_code == 201

        client.delete("/api/account")

        with app.app_context():
            assert get_user(OTHER_USER_ID) is not None
        theirs = other_client.get(f"/api/entries?date={DAY}").get_json()["entries"]
        assert [e["exercise_id"] for e in theirs] == ["Pullups"]

    def test_it_reports_honestly_when_supabase_refuses(
        self, app, client, monkeypatch
    ):
        """Local-first ordering: the rows are gone, the auth record is not."""

        def _boom(user_id, **kwargs):
            raise AuthError("Supabase would not delete the auth record: 503")

        monkeypatch.setattr("app.api.delete_auth_user", _boom)

        response = client.delete("/api/account")
        assert response.status_code == 200
        assert response.get_json() == {"deleted": True, "auth_record_removed": False}
        with app.app_context():
            assert get_user(TEST_USER_ID) is None

    def test_it_refuses_before_touching_anything_without_a_service_key(
        self, tmp_path, add
    ):
        from app import create_app
        from app.db import get_engine
        from app.tables import metadata
        from tests.conftest import _signed_in_client, TEST_USER_EMAIL

        application = create_app(
            "testing",
            DATABASE_URL=f"sqlite:///{tmp_path / 'nokey.sqlite3'}",
            SUPABASE_SERVICE_ROLE_KEY=None,
        )
        with application.app_context():
            metadata.create_all(get_engine(application))
            local = _signed_in_client(application, TEST_USER_ID, TEST_USER_EMAIL)

            local.post(
                "/api/entries",
                json={"date": DAY, "exercise_id": "Barbell_Squat", "sets": [{}]},
            )
            response = local.delete("/api/account")
            assert response.status_code == 503

            # Nothing was touched.
            assert get_user(TEST_USER_ID) is not None
            entries = local.get(f"/api/entries?date={DAY}").get_json()["entries"]
            assert len(entries) == 1

            get_engine(application).dispose()

    def test_it_needs_a_token(self, app):
        assert app.test_client().delete("/api/account").status_code == 401
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_account.py -v`
Expected: FAIL — `DELETE /api/account` answers 405 (the URL rule does not exist), except `test_it_needs_a_token` which may also report 405.

- [ ] **Step 3: Write the endpoint**

In `app/api.py`, extend the auth import:

```python
from .services.auth import AuthError, decode_token, delete_auth_user
```

and add `delete_user` to the `from .models import (...)` list.

Add after `get_me`:

```python
@bp.delete("/account")
@require_user
def remove_account():
    """Delete the signed-in account: local rows first, then the auth record.

    **The order is deliberate.** If the Supabase call fails, the account
    survives with no data — recoverable, retryable, and the response says so.
    Supabase-first would risk the opposite: the auth record gone and the rows
    orphaned behind an account that can never sign in again to delete them.

    This is the one place Flask holds a Supabase credential. The login path
    holds none — the browser talks to GoTrue directly — but a user cannot delete
    their own auth record with the anon key, and there is no way around that.
    """
    service_key = current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        # Checked before touching anything, so a misconfigured deployment
        # refuses rather than half-deleting an account.
        return jsonify(
            {"error": "Account deletion is not configured on this server."}
        ), 503

    user_id = g.user_id
    # One statement: workout_entry and workout_set both cascade from here.
    delete_user(user_id)

    try:
        delete_auth_user(
            user_id,
            supabase_url=current_app.config.get("SUPABASE_URL") or "",
            service_role_key=service_key,
        )
    except AuthError:
        # The data is gone, which is the part the user asked for and the part
        # that matters for privacy. Say plainly that the sign-in record is not.
        return jsonify({"deleted": True, "auth_record_removed": False})

    return jsonify({"deleted": True, "auth_record_removed": True})
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_account.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api.py tests/test_account.py
git commit -m "Add in-app account deletion

Local rows first, the Supabase auth record second. If the second step
fails the account survives with no data — recoverable, retryable, and the
response reports auth_record_removed: false rather than claiming success.
The reverse order risks the auth record gone and the rows orphaned behind
an account that can never sign in again to delete them.

503 when the service-role key is unset, checked before touching anything.
This is the one place Flask holds a Supabase credential: the login path
holds none, but a user cannot delete their own auth record with the anon
key.

The call is stdlib urllib, so it adds no HTTP dependency."
```

---

> **There is no JS test runner in this project** — zero JS dependencies, no
> bundler, no Node. Tasks 9–12 are therefore verified two ways: by Python tests
> asserting what the server renders and which modules a page loads, and by
> explicit manual browser checks. The manual steps are written out in full; do
> not skip them and do not add a JS test framework to avoid them.

### Task 9: `auth.js` and the Supabase config in the page

**Files:**
- Create: `app/static/js/auth.js`
- Modify: `app/views.py:44-56` (`inject_globals`)
- Modify: `app/templates/base.html:23` (the config script, in `<head>`)
- Test: `tests/test_pages.py` (append)

**Interfaces:**
- Consumes: config keys `SUPABASE_URL`, `SUPABASE_ANON_KEY` (Task 1).
- Produces — `app/static/js/auth.js` exports:
  ```js
  export const STORAGE_KEY;                       // "bodyshop.auth"
  export function getSession();                   // {access_token, refresh_token, expires_at} | null
  export function setSession(session);            // persists; returns the stored object
  export function clearSession();
  export function accessToken();                  // string | null
  export function isSignedIn();                   // boolean
  export function isExpiring();                   // boolean; within 60s of expiry
  export async function signUp(email, password);  // -> {session|null, needsConfirmation: boolean}
  export async function signIn(email, password);  // -> session
  export async function refresh();                // -> session   (throws if it cannot)
  export async function signOut();                // always clears locally
  export async function requestPasswordReset(email, redirectTo);
  export async function updatePassword(newPassword, token);
  export function sessionFromHash();              // parses Supabase's redirect fragment
  ```
  Template global: `supabase` → `{"url": str, "anon_key": str}`, rendered as `window.BODYSHOP_SUPABASE`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pages.py`:

```python
def test_every_page_carries_the_supabase_config(client):
    """auth.js reads it off the window; it is public by design."""
    body = client.get("/").data.decode()
    assert "window.BODYSHOP_SUPABASE" in body
    assert "https://test.supabase.co" in body
    assert "test-anon-key" in body


def test_the_service_role_key_is_never_rendered(client):
    """The one Supabase credential Flask holds must never reach a browser."""
    for path in ("/", "/log", "/summary", "/calendar", "/progress", "/how-to-use"):
        assert "test-service-role-key" not in client.get(path).data.decode()
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_pages.py -k supabase -v`
Expected: `test_every_page_carries_the_supabase_config` FAILS on the first assertion; `test_the_service_role_key_is_never_rendered` passes vacuously (keep it — it is a regression guard).

- [ ] **Step 3: Expose the config to templates**

In `app/views.py`, add `current_app` usage inside `inject_globals` — it is already imported. Add to the returned dict, after `"today": date.today(),`:

```python
        # Public by design: the anon key identifies the project to GoTrue and
        # grants nothing on its own. The service-role key is deliberately absent
        # from this dict and must stay that way.
        "supabase": {
            "url": current_app.config.get("SUPABASE_URL") or "",
            "anon_key": current_app.config.get("SUPABASE_ANON_KEY") or "",
        },
```

- [ ] **Step 4: Render it into `<head>`**

In `app/templates/base.html`, after the stylesheet `<link>` and before `</head>`:

```html
  {#
    Supabase's public identifiers, read by auth.js. `tojson` escapes for a
    script context, so a key containing a quote or a `</script>` cannot break
    out. The service-role key is never in this dict — see views.inject_globals.
  #}
  <script>
    window.BODYSHOP_SUPABASE = {{ supabase | tojson }};
  </script>
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `pytest tests/test_pages.py -k supabase -v`
Expected: PASS.

- [ ] **Step 6: Write `auth.js`**

Create `app/static/js/auth.js`:

```js
/**
 * Supabase Auth, over plain `fetch`.
 *
 * **The only place in the front end that talks to Supabase**, exactly as
 * `api.js` is the only place that talks to our own API. Between them that is
 * every network call the app makes.
 *
 * No SDK: signup, the password grant, refresh, recover and update are five
 * POSTs against a documented REST API, and the zero-dependency rule is worth
 * more than the convenience. The build step stays CSS-only.
 *
 * Tokens live in `localStorage` rather than a cookie. That is what makes the
 * whole app bearer-only — no CSRF surface, and the same API a mobile client
 * will consume in Phase 10.
 */

const CONFIG = window.BODYSHOP_SUPABASE || { url: "", anon_key: "" };
const BASE = `${CONFIG.url.replace(/\/$/, "")}/auth/v1`;

/** Where the session is kept. The inline script in `base.html` reads this same
 *  literal to set `data-auth` before first paint — keep the two in step. */
export const STORAGE_KEY = "bodyshop.auth";

/** Refresh this many seconds before the access token actually expires, so a
 *  request never leaves with a token that dies in flight. */
const EXPIRY_MARGIN_SECONDS = 60;

function headers(extra = {}) {
  return {
    apikey: CONFIG.anon_key,
    "Content-Type": "application/json",
    Accept: "application/json",
    ...extra,
  };
}

/**
 * POST to GoTrue and return the parsed body, throwing its message on failure.
 * @returns {Promise<any>}
 */
async function post(path, body, extraHeaders = {}) {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: headers(extraHeaders),
    body: JSON.stringify(body),
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    // GoTrue uses `error_description`, `msg` or `message` depending on the
    // endpoint and the version. Try all three before falling back.
    const message =
      (payload && (payload.error_description || payload.msg || payload.message)) ||
      `Request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

/** The stored session, or `null`. */
export function getSession() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY)) || null;
  } catch {
    // Corrupt or partially written. Treat it as signed out rather than
    // throwing on every page load forever.
    return null;
  }
}

/**
 * Persist a GoTrue token response.
 * @param {{access_token: string, refresh_token: string, expires_in?: number}} session
 */
export function setSession(session) {
  const stored = {
    access_token: session.access_token,
    refresh_token: session.refresh_token,
    // Absolute, not relative: a stored countdown is wrong the moment the tab
    // sleeps, which is the same reason the rest timer persists a deadline.
    expires_at: Math.floor(Date.now() / 1000) + (session.expires_in || 3600),
  };
  localStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
  return stored;
}

export function clearSession() {
  localStorage.removeItem(STORAGE_KEY);
}

/** The current access token, or `null`. Does not check expiry — `api.js`
 *  handles a 401 by refreshing once, which covers both stale and revoked. */
export function accessToken() {
  const session = getSession();
  return session ? session.access_token : null;
}

export function isSignedIn() {
  return Boolean(accessToken());
}

/** True when the stored token is within the margin of expiring. */
export function isExpiring() {
  const session = getSession();
  if (!session) return false;
  return session.expires_at - EXPIRY_MARGIN_SECONDS <= Math.floor(Date.now() / 1000);
}

/**
 * Create an account.
 * @returns {Promise<{session: object|null, needsConfirmation: boolean}>}
 *   When the project requires email confirmation, GoTrue returns a user with no
 *   session — which is a success, not a failure, and the page says so.
 */
export async function signUp(email, password) {
  const payload = await post("/signup", { email, password });
  if (payload && payload.access_token) {
    return { session: setSession(payload), needsConfirmation: false };
  }
  return { session: null, needsConfirmation: true };
}

/** Sign in with the password grant. */
export async function signIn(email, password) {
  const payload = await post("/token?grant_type=password", { email, password });
  return setSession(payload);
}

/**
 * Exchange the refresh token for a new access token.
 * @throws {Error} when there is no refresh token or Supabase rejects it.
 */
export async function refresh() {
  const session = getSession();
  if (!session || !session.refresh_token) {
    throw new Error("Not signed in.");
  }
  const payload = await post("/token?grant_type=refresh_token", {
    refresh_token: session.refresh_token,
  });
  return setSession(payload);
}

/**
 * Sign out. Clears locally **whatever** Supabase says: a failed revoke must not
 * leave someone still signed in on the device in front of them.
 */
export async function signOut() {
  const token = accessToken();
  try {
    if (token) {
      await post("/logout", {}, { Authorization: `Bearer ${token}` });
    }
  } catch {
    // Deliberately swallowed. See the docstring.
  } finally {
    clearSession();
  }
}

/**
 * Send the password-reset email.
 *
 * `redirect_to` is a **query parameter** here, not a body field, and the URL it
 * names must be listed under Authentication → URL Configuration in the Supabase
 * dashboard or the link in the email silently comes back to the Site URL
 * instead.
 */
export async function requestPasswordReset(email, redirectTo) {
  const query = redirectTo ? `?redirect_to=${encodeURIComponent(redirectTo)}` : "";
  return post(`/recover${query}`, { email });
}

/** Set a new password, using the recovery token from the emailed link. */
export async function updatePassword(newPassword, token) {
  const response = await fetch(`${BASE}/user`, {
    method: "PUT",
    headers: headers({ Authorization: `Bearer ${token}` }),
    body: JSON.stringify({ password: newPassword }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(
      (payload && (payload.error_description || payload.msg || payload.message)) ||
        "Could not set the password."
    );
  }
  return payload;
}

/**
 * Read the session Supabase puts in the URL **fragment** on a redirect back.
 *
 * A fragment, not a query string, which is why this is client-side only: it
 * never reaches the server, so recovery and confirmation tokens stay out of
 * access logs. Returns `null` when there is nothing there.
 * @returns {{access_token: string, refresh_token: string, type: string}|null}
 */
export function sessionFromHash() {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const access = params.get("access_token");
  if (!access) return null;
  return {
    access_token: access,
    refresh_token: params.get("refresh_token") || "",
    expires_in: Number(params.get("expires_in") || 3600),
    type: params.get("type") || "",
  };
}
```

- [ ] **Step 7: Check it parses**

There is no bundler, so a syntax error would only appear in the browser. Check it now:

Run: `python -c "import pathlib; s=pathlib.Path('app/static/js/auth.js').read_text(); print(len(s), 'chars'); assert s.count('{') == s.count('}'), 'brace mismatch'"`

Then, properly, in a browser — start the dev server and load any page:

```bash
python run.py
```
Open `http://127.0.0.1:5000/`, open the console and run:
```js
const m = await import("/static/js/auth.js");
m.isSignedIn();   // expect: false
m.STORAGE_KEY;    // expect: "bodyshop.auth"
```
Expected: no syntax error, `false`, `"bodyshop.auth"`. Stop the server.

- [ ] **Step 8: Run the full suite**

Run: `pytest`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/static/js/auth.js app/views.py app/templates/base.html tests/test_pages.py
git commit -m "Talk to Supabase Auth over plain fetch

auth.js is the only place the front end calls Supabase, as api.js is the
only place it calls our own API. Between them that is every network call
the app makes — which amends ARCHITECTURE.md's single-fetch-site claim
rather than quietly breaking it.

No SDK: signup, the password grant, refresh, recover and update are five
POSTs against a documented REST API, and the zero-JS-dependency rule is
worth more than the convenience.

Tokens live in localStorage, and the stored value is an absolute expiry
rather than a countdown — the same reason the rest timer persists a
deadline. The recovery token arrives in the URL fragment, so it never
reaches the server and never lands in an access log.

The anon key is rendered into every page and is public by design. A test
asserts the service-role key is not."
```

---

### Task 10: `api.js` — bearer header and one silent retry

**Files:**
- Modify: `app/static/js/api.js:9-34` (the `request` wrapper only; every typed helper below it is untouched)

**Interfaces:**
- Consumes: `accessToken`, `refresh`, `clearSession` from `auth.js` (Task 9).
- Produces: no signature changes. Every existing export keeps its name, arguments and return shape — this task changes only what happens inside `request()`.

- [ ] **Step 1: Rewrite the request wrapper**

Replace lines 1–34 of `app/static/js/api.js` (the module docstring through the end of `request`):

```js
/**
 * Thin wrapper around the Body Shop JSON API.
 *
 * Every function returns parsed JSON and throws an `Error` carrying the
 * server's message when the response is not 2xx, so callers can simply
 * `try { ... } catch (err) { toast(err.message) }`.
 *
 * **The only place our own API is called.** `auth.js` is the only place
 * Supabase is. Every request from here carries the bearer token; a 401 is
 * retried exactly once behind a refresh, and then becomes a redirect to
 * `/login`.
 */

import { accessToken, clearSession, refresh } from "./auth.js";

const BASE = "/api";

/** Send the browser to sign in, remembering where it was. */
function toLogin() {
  const here = window.location.pathname + window.location.search;
  window.location.assign(`/login?next=${encodeURIComponent(here)}`);
}

function send(path, options, token) {
  return fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    },
  });
}

/**
 * Perform a request against the API.
 *
 * On a 401 this refreshes **once** and replays the request. One retry, never a
 * loop: a refresh token that is genuinely dead must not spin, and the honest
 * end of that road is the login page.
 *
 * @param {string} path - Path below `/api`, e.g. `/entries`.
 * @param {RequestInit} [options]
 * @returns {Promise<any>} Parsed JSON body.
 */
async function request(path, options = {}) {
  let response = await send(path, options, accessToken());

  if (response.status === 401) {
    try {
      const session = await refresh();
      response = await send(path, options, session.access_token);
    } catch {
      clearSession();
      toLogin();
      throw new Error("Sign in to continue.");
    }
    if (response.status === 401) {
      // The refresh succeeded and the API still says no. Nothing further to
      // try — the token is valid and simply is not allowed here.
      clearSession();
      toLogin();
      throw new Error("Sign in to continue.");
    }
  }

  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }

  if (!response.ok) {
    throw new Error((payload && payload.error) || `Request failed (${response.status})`);
  }
  return payload;
}
```

Everything from `export async function fetchExercises()` onward is unchanged.

- [ ] **Step 2: Verify no call site changed**

Run: `grep -rn "from \"./api.js\"\|from './api.js'" app/static/js/`
Expected: `calendar.js`, `log.js`, `progress.js`, `summary.js` — each importing named helpers whose signatures this task did not touch. If any of them imported `request` directly, it would need updating; confirm none does.

- [ ] **Step 3: Manual browser check — the signed-out path**

The pages this affects cannot be exercised without a browser, and there is no JS runner. Do it deliberately:

```bash
python run.py
```

1. Open `http://127.0.0.1:5000/log`, open DevTools → Application → Local Storage, and confirm there is no `bodyshop.auth` key.
2. Watch the Network tab and reload.
   Expected: `GET /api/exercises` returns 200 (public). `GET /api/exercises/recent` returns **401**, and the browser navigates to `/login?next=%2Flog`. `/login` will 404 until Task 11 — that is the correct intermediate state, and it confirms the redirect fires with the right `next`.
3. Confirm the redirect happened **once**. A loop here means the retry is not bounded.

Stop the server.

- [ ] **Step 4: Run the full suite**

Run: `pytest`
Expected: PASS. Nothing server-side changed, so this is a regression check.

- [ ] **Step 5: Commit**

```bash
git add app/static/js/api.js
git commit -m "Send the bearer token, and refresh once on a 401

Every request carries the access token. A 401 refreshes and replays the
request exactly once; if that also fails the session is cleared and the
browser goes to /login?next=<where it was>. One retry, never a loop — a
refresh token that is genuinely dead must not spin.

No exported signature changes: the four page modules call the same typed
helpers they always did."
```

---

### Task 11: The five auth pages

**Files:**
- Modify: `app/templates/base.html:25` (body class), `:109-127` (the shell), `:129-163` (dock, veil, tab bar)
- Modify: `app/views.py` (five routes)
- Create: `app/templates/login.html`, `signup.html`, `reset_password.html`, `verify.html`, `account.html`
- Modify: `app/static/css/input.css` (the `.auth-*` block and the `data-auth` rules)
- Modify: `app/static/css/styles.css` (build output — regenerated, never hand-edited)
- Test: `tests/test_pages.py` (append)

**Interfaces:**
- Consumes: `auth.js` (Task 9); `api.js` (Task 10); `DELETE /api/account`, `GET /api/me` (Tasks 6, 8).
- Produces: routes `views.login_page` (`/login`), `views.signup_page` (`/signup`), `views.reset_password_page` (`/reset-password`), `views.verify_page` (`/verify`), `views.account_page` (`/account`). `base.html` accepts a `bare` template variable, default falsey.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_pages.py`:

```python
AUTH_PAGES = [
    ("/login", b"Sign in"),
    ("/signup", b"Create an account"),
    ("/reset-password", b"Reset your password"),
    ("/verify", b"Confirming your email"),
    ("/account", b"Your account"),
]


@pytest.mark.parametrize(("path", "marker"), AUTH_PAGES)
def test_auth_pages_render(client, path, marker):
    response = client.get(path)
    assert response.status_code == 200
    assert marker in response.data


@pytest.mark.parametrize(("path", "_marker"), AUTH_PAGES)
def test_auth_pages_carry_no_chrome(client, path, _marker):
    """They are not chapters of the book, so they get no shelves and no tabs.

    This is also what keeps the chapter-ordering assertions below untouched:
    `sections` in base.html never learns about these pages.
    """
    body = client.get(path).data.decode()
    assert "shelf-stack" not in body
    assert "tab-bar" not in body
    assert "rest-dock" not in body


@pytest.mark.parametrize(("path", "_marker"), AUTH_PAGES)
def test_auth_pages_are_reachable_signed_out(app, path, _marker):
    """Shells are public — a signed-out browser must be able to load /login."""
    assert app.test_client().get(path).status_code == 200


def test_auth_pages_never_appear_as_a_shelf(client):
    """A shelf for /login would renumber the book."""
    for page in ("/calendar", "/log", "/summary", "/progress", "/how-to-use", "/"):
        body = client.get(page).data.decode()
        assert 'href="/login' not in body.replace('href="/login?next=', "")
```

Drop that last test if it proves brittle — the `/` page legitimately links to `/login` in its signed-out state after Task 12. Replace it with the narrower assertion:

```python
def test_auth_pages_never_appear_as_a_shelf(client):
    """A shelf for /login would renumber the book."""
    for page in ("/calendar", "/log", "/summary", "/progress", "/how-to-use"):
        body = client.get(page).data.decode()
        shelves = re.findall(r'class="shelf[^"]*"\s+data-nav\s+href="([^"]+)"', body)
        assert all("/login" not in href and "/account" not in href for href in shelves)
```

Use the second version. `re` is already imported at the top of `test_pages.py`.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pages.py -k auth -v`
Expected: FAIL with 404 on all five paths.

- [ ] **Step 3: Add the `bare` flag to `base.html`**

Three edits.

The body tag (line 25) becomes:

```html
<body data-page="{{ page }}" class="min-h-screen flex flex-col{{ '' if bare else ' has-tab-bar' }}">
```

The shell (lines 109–127) becomes:

```html
  <div class="shell">
    {#
      Auth pages are not chapters of the book — they have no number and never
      enter the stack, which is also what keeps `sections` above untouched and
      the chapter-ordering tests passing unchanged.
    #}
    {% if not bare %}
      <nav class="shelf-stack shelf-stack-left" aria-label="Earlier sections">
        {% for endpoint, key, label, chapter, blurb in left_shelves %}
          {{ shelf(endpoint, key, label, chapter, blurb, home=(key == 'home')) }}
        {% endfor %}
      </nav>
    {% endif %}

    <main id="main" class="shell-main">
      {% block content %}{% endblock %}
    </main>

    {% if not bare %}
      <nav class="shelf-stack" aria-label="Later sections">
        {% for endpoint, key, label, chapter, blurb in right_shelves %}
          {{ shelf(endpoint, key, label, chapter, blurb) }}
        {% endfor %}
      </nav>
    {% endif %}
  </div>
```

Wrap the rest dock (lines 129–148) and the tab bar (lines 156–163) each in `{% if not bare %}` … `{% endif %}`, and wrap the rest-timer boot script (lines 167–171) in the same, since it looks up an element that is no longer there. The page veil and the toast stay on every page.

- [ ] **Step 4: Add the routes**

Append to `app/views.py`:

```python
#: Pages outside the book. No chapter number, no shelf, no tab bar — they are
#: not sections of the product, and `sections` in base.html never learns about
#: them. All five are public shells: bearer tokens mean Flask cannot read an
#: Authorization header on a navigation, so gating happens in the page's JS.
@bp.get("/login")
def login_page():
    """Sign in. ``?next=`` carries where the browser was headed."""
    return render_template(
        "login.html", page="login", bare=True, selected_date=_requested_date()
    )


@bp.get("/signup")
def signup_page():
    """Create an account."""
    return render_template(
        "signup.html", page="signup", bare=True, selected_date=_requested_date()
    )


@bp.get("/reset-password")
def reset_password_page():
    """Both halves of the reset flow.

    Which half renders is decided client-side: Supabase sends the recovery token
    back in the URL **fragment**, which never reaches this function. That is the
    point — the token stays out of the server's access log.
    """
    return render_template(
        "reset_password.html",
        page="reset-password",
        bare=True,
        selected_date=_requested_date(),
    )


@bp.get("/verify")
def verify_page():
    """Landing page for the email confirmation link."""
    return render_template(
        "verify.html", page="verify", bare=True, selected_date=_requested_date()
    )


@bp.get("/account")
def account_page():
    """Email, sign out, and delete account.

    Deletion lives here rather than on ``/`` because ``/`` is one screen and new
    content there has to earn its height or replace something.
    """
    return render_template(
        "account.html", page="account", bare=True, selected_date=_requested_date()
    )
```

Update the module docstring's page list at `app/views.py:3-9` to name eleven pages, and delete the stale sentence "When auth arrives it becomes the signed-out half of a split (see docs/ROADMAP.md, Phase 4)" — auth has now arrived, and Task 12 implements that split.

- [ ] **Step 5: Add the CSS**

In `app/static/css/input.css`, inside the existing `@layer components` block, add:

```css
  /* Auth pages. One narrow column on the same continuous ground as everything
     else — hairline rules, no card, no shadow, per the layout invariant. */
  .auth-shell {
    @apply mx-auto flex min-h-screen w-full max-w-sm flex-col justify-center gap-6 px-6 py-12;
  }

  .auth-title {
    @apply font-serif text-3xl font-light tracking-tight text-base-content;
  }

  .auth-field {
    @apply flex flex-col gap-2;
  }

  /* 44pt clear, like every other target in the app. `.field-sm` elsewhere is a
     typographic variant, never a smaller tap target, and the same rule holds
     here. */
  .auth-input {
    @apply min-h-[44px] w-full border border-base-content/25 bg-base-100 px-3 py-2
           text-base text-base-content outline-none;
  }

  .auth-input:focus {
    @apply border-base-content/60;
  }

  /* Hairline-outlined, never filled. Red *area* means volume past target; red
     outline or text means an action. */
  .auth-submit {
    @apply min-h-[44px] w-full border border-primary bg-transparent px-4 py-2
           text-primary;
  }

  .auth-submit:disabled {
    @apply cursor-not-allowed opacity-50;
  }

  .auth-note {
    @apply text-sm text-secondary;
  }

  .auth-error {
    @apply border border-primary/40 px-3 py-2 text-sm text-primary;
  }

  /* The signed-in / signed-out split on `/`. An inline script in base.html
     stamps `data-auth` on <html> before first paint, so neither block ever
     flashes. Hand-written rather than a utility because the attribute is
     toggled at runtime and Tailwind would purge an interpolated class. */
  [data-auth-when] {
    display: none;
  }

  :root[data-auth="out"] [data-auth-when="out"],
  :root[data-auth="in"] [data-auth-when="in"] {
    display: revert;
  }
```

- [ ] **Step 6: Build the stylesheet**

The toolchain is npm-free and gitignored, so fetch it first if `tools/tailwindcss` is absent:

```bash
python tools/fetch_css_toolchain.py
tools/tailwindcss -i app/static/css/input.css -o app/static/css/styles.css --minify
```

`styles.css` is build output and is committed. Never hand-edit it.

- [ ] **Step 7: Write the five templates**

Each extends `base.html`, sets `bare=True` via its route, and loads its own inline module. `login.html`:

```html
{% extends "base.html" %}
{% block title %}Sign in — Body Shop{% endblock %}

{% block content %}
<div class="auth-shell">
  <div>
    <h1 class="auth-title">Sign in</h1>
    <p class="auth-note mt-2">Your training, on every device you use.</p>
  </div>

  <form id="signin-form" class="flex flex-col gap-4" novalidate>
    <p id="signin-error" class="auth-error" hidden></p>

    <label class="auth-field">
      <span class="type-label">Email</span>
      <input class="auth-input" type="email" name="email" autocomplete="email" required>
    </label>

    <label class="auth-field">
      <span class="type-label">Password</span>
      <input class="auth-input" type="password" name="password"
             autocomplete="current-password" required>
    </label>

    <button class="auth-submit type-label" type="submit">Sign in</button>
  </form>

  <p class="auth-note">
    <a href="/reset-password">Forgot your password?</a>
    &nbsp;·&nbsp;
    <a href="/signup">Create an account</a>
  </p>
</div>
{% endblock %}

{% block scripts %}
<script type="module">
  import { signIn } from "{{ url_for('static', filename='js/auth.js') }}";

  const form = document.getElementById("signin-form");
  const error = document.getElementById("signin-error");
  // Same-origin paths only. An open redirect here would let a crafted link
  // bounce someone off the app right after they signed in.
  const raw = new URLSearchParams(location.search).get("next") || "/summary";
  const next = raw.startsWith("/") && !raw.startsWith("//") ? raw : "/summary";

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const data = new FormData(form);
      await signIn(data.get("email"), data.get("password"));
      location.assign(next);
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
</script>
{% endblock %}
```

`signup.html`:

```html
{% extends "base.html" %}
{% block title %}Create an account — Body Shop{% endblock %}

{% block content %}
<div class="auth-shell">
  <div>
    <h1 class="auth-title">Create an account</h1>
    <p class="auth-note mt-2">Free, and your workouts are yours.</p>
  </div>

  <form id="signup-form" class="flex flex-col gap-4" novalidate>
    <p id="signup-error" class="auth-error" hidden></p>

    <label class="auth-field">
      <span class="type-label">Email</span>
      <input class="auth-input" type="email" name="email" autocomplete="email" required>
    </label>

    <label class="auth-field">
      <span class="type-label">Password</span>
      <input class="auth-input" type="password" name="password"
             autocomplete="new-password" required>
    </label>

    <button class="auth-submit type-label" type="submit">Create account</button>
  </form>

  {# Password rules, lockout and enumeration hygiene are all Supabase's, set in
     its dashboard rather than here — so this page states no rule it does not
     enforce. #}
  <p id="signup-done" class="auth-note" hidden>
    Check your email — we have sent you a link to confirm the address.
  </p>

  <p class="auth-note">Already have one? <a href="/login">Sign in</a></p>
</div>
{% endblock %}

{% block scripts %}
<script type="module">
  import { signUp } from "{{ url_for('static', filename='js/auth.js') }}";

  const form = document.getElementById("signup-form");
  const error = document.getElementById("signup-error");
  const done = document.getElementById("signup-done");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const button = form.querySelector("button");
    button.disabled = true;
    try {
      const data = new FormData(form);
      const result = await signUp(data.get("email"), data.get("password"));
      if (result.needsConfirmation) {
        // Not a failure. The project requires email confirmation, so there is
        // no session yet and the next step is in their inbox.
        form.hidden = true;
        done.hidden = false;
        return;
      }
      location.assign("/summary");
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
</script>
{% endblock %}
```

`reset_password.html` — one page, two states, chosen from the fragment:

```html
{% block content %}
<div class="auth-shell">
  <h1 class="auth-title">Reset your password</h1>

  <form id="request-form" class="flex flex-col gap-4" novalidate>
    <p id="reset-error" class="auth-error" hidden></p>
    <label class="auth-field">
      <span class="type-label">Email</span>
      <input class="auth-input" type="email" name="email" autocomplete="email" required>
    </label>
    <button class="auth-submit type-label" type="submit">Send the link</button>
  </form>

  <form id="new-password-form" class="flex flex-col gap-4" hidden novalidate>
    <label class="auth-field">
      <span class="type-label">New password</span>
      <input class="auth-input" type="password" name="password"
             autocomplete="new-password" required>
    </label>
    <button class="auth-submit type-label" type="submit">Set the password</button>
  </form>

  <p id="reset-sent" class="auth-note" hidden>
    If that address has an account, the link is on its way.
  </p>
</div>
{% endblock %}

{% block scripts %}
<script type="module">
  import { requestPasswordReset, sessionFromHash, setSession, updatePassword }
    from "{{ url_for('static', filename='js/auth.js') }}";

  const requestForm = document.getElementById("request-form");
  const newForm = document.getElementById("new-password-form");
  const error = document.getElementById("reset-error");
  const sent = document.getElementById("reset-sent");

  // Supabase returns the recovery token in the fragment, which never reached
  // the server — so which half of this page applies is a client-side question.
  const recovery = sessionFromHash();
  if (recovery && recovery.type === "recovery") {
    requestForm.hidden = true;
    newForm.hidden = false;
  }

  requestForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    try {
      const data = new FormData(requestForm);
      await requestPasswordReset(data.get("email"), `${location.origin}/reset-password`);
    } catch {
      // Deliberately not surfaced. Saying "no such account" here is the
      // enumeration leak the same message avoids.
    }
    requestForm.hidden = true;
    sent.hidden = false;
  });

  newForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const button = newForm.querySelector("button");
    button.disabled = true;
    try {
      await updatePassword(new FormData(newForm).get("password"), recovery.access_token);
      setSession(recovery);
      location.assign("/summary");
    } catch (err) {
      error.textContent = err.message;
      error.hidden = false;
      button.disabled = false;
    }
  });
</script>
{% endblock %}
```

`verify.html` — `<h1 class="auth-title">Confirming your email</h1>`, a `<p id="verify-status" class="auth-note">One moment…</p>`, and:

```html
{% block scripts %}
<script type="module">
  import { sessionFromHash, setSession } from "{{ url_for('static', filename='js/auth.js') }}";

  const status = document.getElementById("verify-status");
  const session = sessionFromHash();

  if (session) {
    setSession(session);
    status.textContent = "You are signed in. Taking you to your week…";
    location.assign("/summary");
  } else {
    status.innerHTML =
      'That link has expired or has already been used. ' +
      '<a href="/login">Sign in</a> instead.';
  }
</script>
{% endblock %}
```

`account.html` — `<h1 class="auth-title">Your account</h1>`, a `<p id="account-email" class="type-data"></p>`, a sign-out button, and a delete button behind a typed confirmation:

```html
{% block scripts %}
<script type="module">
  import { signOut } from "{{ url_for('static', filename='js/auth.js') }}";

  const email = document.getElementById("account-email");
  const out = document.getElementById("sign-out");
  const del = document.getElementById("delete-account");
  const confirmField = document.getElementById("delete-confirm");
  const status = document.getElementById("account-status");

  // Uses api.js rather than fetch directly, so it inherits the bearer header
  // and the refresh-once behaviour like every other call in the app.
  const { fetchMe, deleteAccount } =
    await import("{{ url_for('static', filename='js/api.js') }}");

  try {
    const me = await fetchMe();
    email.textContent = me.email;
  } catch {
    // api.js has already redirected to /login.
  }

  out.addEventListener("click", async () => {
    await signOut();
    location.assign("/");
  });

  // Typing the address is the confirmation. A second "are you sure" dialog is
  // one click; this is the only irreversible action in the app.
  confirmField.addEventListener("input", () => {
    del.disabled = confirmField.value.trim() !== email.textContent.trim();
  });

  del.addEventListener("click", async () => {
    del.disabled = true;
    try {
      const result = await deleteAccount();
      if (!result.auth_record_removed) {
        status.textContent =
          "Your workouts are deleted. The sign-in record could not be removed — " +
          "contact support and it will be.";
      }
      await signOut();
      location.assign("/");
    } catch (err) {
      status.textContent = err.message;
      del.disabled = false;
    }
  });
</script>
{% endblock %}
```

- [ ] **Step 8: Add the two API helpers `account.html` needs**

Append to `app/static/js/api.js`:

```js
/** The signed-in user. Confirms the token server-side rather than trusting a
 *  local decode of it. */
export async function fetchMe() {
  const data = await request("/me");
  return data.user;
}

/**
 * Delete the account and everything in it. Irreversible.
 * @returns {Promise<{deleted: boolean, auth_record_removed: boolean}>}
 *   `auth_record_removed: false` means the workouts are gone but Supabase
 *   would not remove the sign-in record — say so rather than claiming success.
 */
export async function deleteAccount() {
  return request("/account", { method: "DELETE" });
}
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `pytest tests/test_pages.py -v`
Expected: PASS, including the two pre-existing chapter-ordering tests, which must be untouched.

- [ ] **Step 10: Manual browser check — the whole flow**

This needs a real Supabase project. Put its URL, anon key and service-role key in `.env`, and in the Supabase dashboard under Authentication → URL Configuration add `http://127.0.0.1:5000/verify` and `http://127.0.0.1:5000/reset-password` to the redirect allow-list.

```bash
flask --app app upgrade-db   # NB: destructive — see Task 3
python run.py
```

Walk it: `/signup` → confirmation email → `/verify` → lands signed in on `/summary` → log a workout on `/log` → `/account` shows the address → sign out → `/login` → back in, workout still there → `/reset-password` → email → new password → signed in.

Then the part that matters: sign up a **second** account and confirm its `/summary`, `/calendar` and `/progress` are empty. `test_ownership.py` already proves this, but seeing it once against real Supabase is what confirms the token's `sub` is what the tests assume.

Finally `/account` → delete → confirm the address → signed out, and signing in again fails.

- [ ] **Step 11: Run the full suite and commit**

Run: `pytest`

```bash
git add app/templates/ app/views.py app/static/css/input.css \
        app/static/css/styles.css app/static/js/api.js tests/test_pages.py
git commit -m "Add the sign-in, sign-up, reset, verify and account pages

Five pages outside the book: no chapter number, no shelf, no tab bar, no
rest dock. base.html gains a bare flag for that, and `sections` never
learns about them — which is what leaves the chapter-ordering tests
passing unchanged.

The shells are public. Bearer tokens mean Flask cannot read an
Authorization header on a navigation, so gating is the page module's job
and the cost is one unauthenticated frame before the redirect. The benefit
is that the web app consumes the same API a mobile client will.

/reset-password serves both halves of the flow, chosen client-side:
Supabase returns the recovery token in the URL fragment, which never
reaches the server and so never lands in an access log. The request form
reports the same thing whether or not the address has an account.

Deleting an account requires typing the address. It is the only
irreversible action in the app, and it reports honestly when the workouts
are gone but Supabase would not remove the sign-in record."
```

---

### Task 12: The signed-in / signed-out split on `/`

**Files:**
- Modify: `app/templates/base.html` (the blocking `<head>` script)
- Modify: `app/templates/home.html` (the actions row only)
- Test: `tests/test_pages.py` (append)

**Interfaces:**
- Consumes: `STORAGE_KEY` from `auth.js` (Task 9); the `[data-auth-when]` CSS from Task 11.
- Produces: `<html data-auth="in">` or `data-auth="out"`, set before first paint.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_pages.py`:

```python
def test_home_carries_both_halves_of_the_auth_split(client):
    """One screen, and the signed-in state *swaps* the action rather than adding.

    Both blocks are in the markup; CSS shows one. That is what makes the split
    free of a flash and free of an API call — `/` still fetches nothing.
    """
    body = client.get("/").data.decode()
    assert 'data-auth-when="out"' in body
    assert 'data-auth-when="in"' in body


def test_the_auth_attribute_is_set_before_paint(client):
    """A blocking script in <head>, not a module: a module is deferred, and a
    deferred toggle is a visible flash of the wrong state."""
    body = client.get("/").data.decode()
    head = body.split("</head>")[0]
    assert "data-auth" in head
    assert "bodyshop.auth" in head


def test_home_still_makes_no_api_call(client):
    """The one-screen invariant's other half: `/` reads nothing."""
    body = client.get("/").data.decode()
    assert "js/api.js" not in body
    assert "js/summary.js" not in body
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_pages.py -k auth_split -v; pytest tests/test_pages.py -k before_paint -v`
Expected: both FAIL. `test_home_still_makes_no_api_call` passes already — it is a regression guard for this task.

- [ ] **Step 3: Stamp `data-auth` before first paint**

In `app/templates/base.html`, immediately after `<meta name="viewport" ...>` and **before** the stylesheet link:

```html
  {#
    Stamp the signed-in state on <html> before anything paints. Deliberately
    inline, blocking and tiny: a module script is deferred, and a deferred
    toggle is a visible flash of the wrong half of the landing page.

    The key is duplicated from auth.js's STORAGE_KEY rather than imported —
    importing would make this a module, which is exactly what it must not be.
    Keep the two literals in step.
  #}
  <script>
    (function () {
      var signedIn = false;
      try {
        signedIn = Boolean(JSON.parse(localStorage.getItem("bodyshop.auth")));
      } catch (e) {
        signedIn = false;
      }
      document.documentElement.setAttribute("data-auth", signedIn ? "in" : "out");
    })();
  </script>
```

- [ ] **Step 4: Split the actions row on `/`**

**Swap, do not add.** Replace `app/templates/home.html:110-117` — the existing `.home-actions` block — with two blocks of identical shape. Both carry one `.btn-brick` and one `.btn-ghost-line`, so the row is the same height in either state:

```html
    {#
      Two rows, one shown. The masthead is height:100vh from `lg:` and only the
      specimen may flex, so the signed-in state *swaps* the actions rather than
      adding to them — both blocks are one .btn-brick plus one .btn-ghost-line,
      which is what keeps the row's height identical either way.
    #}
    <div class="home-actions" data-auth-when="out">
      <a class="btn-brick" href="{{ url_for('views.signup_page') }}">
        Create an account
      </a>
      <a class="btn-ghost-line" href="{{ url_for('views.login_page') }}">
        Sign in
      </a>
    </div>

    <div class="home-actions" data-auth-when="in">
      <a class="btn-brick" href="{{ url_for('views.log_page', date=selected_date.isoformat()) }}">
        Log a workout
      </a>
      <a class="btn-ghost-line" href="{{ url_for('views.summary_page', date=selected_date.isoformat()) }}">
        See this week
      </a>
    </div>
```

`btn-brick` is the hairline-outlined primary — brick border, lifted-brick text, no fill. Do not introduce a filled variant for the auth actions.

Leave the `.home-follow` block below it exactly as it is. It is disabled placeholders for a later phase and has nothing to do with accounts.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/test_pages.py -v`
Expected: PASS.

- [ ] **Step 6: Verify the one-screen invariant survives**

The invariant is not something a test can assert. Check it by eye:

```bash
python run.py
```

Open `http://127.0.0.1:5000/` at a desktop width and confirm: no vertical scrollbar; the wordmark, kicker, tagline, actions and follow row are all at their normal size; only the specimen has absorbed the change. Then in DevTools run `localStorage.setItem("bodyshop.auth", '{"access_token":"x"}')` and reload. Confirm the signed-in row appears, the page is **still** exactly one screen, and there is no flash of the signed-out row on load. Then `localStorage.clear()` and reload to check the other direction.

Resize down through `lg:` and confirm the page behaves as it did before this task below that breakpoint.

- [ ] **Step 7: Run the full suite and commit**

Run: `pytest`

```bash
git add app/templates/base.html app/templates/home.html tests/test_pages.py
git commit -m "Swap the landing page's action when signed in

Both halves are in the markup and CSS shows one, so / still fetches
nothing and still runs no page module. A blocking inline script in <head>
stamps data-auth before first paint — a module script is deferred, and a
deferred toggle is a visible flash of the wrong state.

The signed-in state swaps the primary action rather than adding to it. /
is height:100vh with only the specimen allowed to flex, so a row that grew
would have to take the height from somewhere that cannot give it. Sign out
and delete account live on /account for the same reason."
```

---

### Task 13: The documentation sweep

Phase 5 reverses invariants that several docs state as rules. A doc that
contradicts the code is a bug, so this lands as part of the phase, not after it.

**Files:**
- Modify: `CLAUDE.md`, `docs/API.md`, `docs/ARCHITECTURE.md`, `docs/ROADMAP.md`, `README.md`, `CHANGELOG.md`

**Interfaces:**
- Consumes: everything Tasks 1–12 built.
- Produces: nothing executable.

- [ ] **Step 1: Update `CLAUDE.md`**

Four edits, all replacing statements that are now false.

Replace the two-tables invariant:

```markdown
- **Three tables, and every row has an owner.** `user` (the Supabase account, mirrored), `workout_entry` (the movement on a day) and its `workout_set` children. `user → workout_entry → workout_set` are both `ON DELETE CASCADE`, and [db.py](app/db.py) enables SQLite foreign keys per connection, so deleting an account is one `DELETE FROM "user"` with no cascade handling in Python.
- **`user_id` is the first positional parameter of every `models.py` function touching `workout_entry`.** Positional-and-first is the safety property, not a style choice: a call site that was not updated fails loudly as a `TypeError` instead of silently querying across all users. `_sets_for` is the one exception — every caller passes ids from an already-filtered query, and its docstring says what a new caller must do instead. [tests/test_ownership.py](tests/test_ownership.py) walks two users across every endpoint; a failure there is a data leak, so fix the query, never the test.
- **Auth is Supabase's, and Flask never sees a password.** The browser talks to GoTrue directly ([auth.js](app/static/js/auth.js)); Flask only *verifies* the bearer token, in [app/services/auth.py](app/services/auth.py), against either the shared HS256 secret or the project's JWKS depending on whether `SUPABASE_JWT_SECRET` is set. Testing config pins that secret, which is what keeps the whole suite offline. Every verification failure raises one `AuthError` and renders as one 401 — a 401 that says *why* is an oracle. The one Supabase credential Flask holds is the service-role key, used by `DELETE /api/account` and nowhere else.
- **The `user` table is a mirror, not a source of truth**, created just-in-time on the first authenticated request — there is no signup webhook, which makes `ensure_user` the only place in the app where a GET writes. It carries no `password_hash` and no `verified_at`: Supabase owns both, and a mirrored verification flag drifts invisibly until someone is wrongly let in or wrongly kept out.
- **Page shells are public; gating is the page module's job.** Flask cannot read an `Authorization` header on a navigation, so `/login`, `/signup`, `/reset-password`, `/verify` and `/account` are public and so is every chapter — `api.js` redirects to `/login?next=<path>` after one silent refresh-and-retry on a 401. The five auth pages are outside the book: `bare=True`, no chapter number, never in the shelf stack.
```

Delete the old bullet beginning "**Two append-only tables**, no `user_id`, no auth". Amend the `fetch` claim wherever it appears: `api.js` is the only place **our own API** is called; `auth.js` is the only place Supabase is.

Update the Architecture paragraph's phase list: Phase 5 is done; `/` and `/how-to-use` are still the static pages, and there are now eleven routes rather than six. Add `PyJWT[crypto]` to the runtime dependencies wherever they are named.

- [ ] **Step 2: Update `docs/API.md`**

Read it first — its payload examples are exhaustive, not illustrative, so every one of them has to stay true.

Add an **Authentication** section at the top stating: every request carries `Authorization: Bearer <supabase access token>`; tokens come from Supabase GoTrue, which the browser calls directly, so **login, signup, refresh, password reset and email verification are not Flask endpoints and are not documented here**; a missing, malformed, expired or foreign token returns `401 {"error": "Sign in to continue."}` with `WWW-Authenticate: Bearer`, and the message never varies by cause.

Mark each endpoint gated or public. Gated: `GET`/`POST /api/entries`, `DELETE /api/entries/<id>`, `GET /api/calendar`, `GET /api/summary/week`, `GET /api/progress/graph`, `GET /api/exercises/recent`, `GET /api/exercises/<id>/last-sets`. Public: `GET /api/exercises`, `GET /api/exercises/<id>`, `GET /api/summary/week/bounds`.

Document the two new endpoints with full payloads:

```
GET /api/me
200 {"user": {"id": "11111111-1111-4111-8111-111111111111",
              "email": "you@example.com"}}

DELETE /api/account
200 {"deleted": true, "auth_record_removed": true}
200 {"deleted": true, "auth_record_removed": false}   # rows gone, Supabase refused
503 {"error": "Account deletion is not configured on this server."}
```

State that `DELETE /api/entries/<id>` returns **404, not 403**, for another user's entry, and why.

- [ ] **Step 3: Update `docs/ARCHITECTURE.md`**

Add `app/services/auth.py` and `app/static/js/auth.js` to the layer-ownership table: token rules and GoTrue calls respectively, with the note that `require_user`, `g.user_id` and the 401 live in `api.py` because they touch `request` and `g`.

Amend the sentence claiming `api.js` is the only place `fetch` is called to the honest version: `api.js` is the only place *our own API* is called, `auth.js` is the only place Supabase is, and between them that is every network call the front end makes.

Update the data-model section for the `user` table and `workout_entry.user_id`, including the `idx_workout_entry_user_date` index and why it is ordered `(user_id, entry_date)`.

- [ ] **Step 4: Update `docs/ROADMAP.md`**

Add a "what shipped, and where it diverged" section to Phase 5, naming the three divergences from its own SQL sketch (UUID rather than INTEGER id; no `password_hash`; no `verified_at`) and the reason for each. Record that the suite stayed offline via the pinned HS256 secret — the cost the phase estimate had not priced in.

Close open decisions 2, 3 and 5 with what was chosen: Supabase Auth with bearer tokens; token auth and in-app deletion both satisfied; existing data wiped.

Note what Phase 5 deliberately did not build and why: Flask-Limiter and Redis, CSRF, server-side page gating, enumeration hygiene, lockout and password strength. Note that Phase 7's `body_metric` and Phase 8's `custom_exercise` inherit the FK-plus-cascade pattern and need no change to `DELETE /api/account`.

- [ ] **Step 5: Update `README.md` and `CHANGELOG.md`**

`README.md`: add the Supabase setup to the getting-started steps — create a project, copy the URL, anon key and service-role key into `.env`, and add `/verify` and `/reset-password` to the dashboard's redirect allow-list. Say plainly that `flask --app app upgrade-db` on an existing database **deletes every workout**, because revision `0005` wipes.

`CHANGELOG.md`: a Phase 5 entry covering accounts, the `user_id` sweep, the five new pages, the two new endpoints, `PyJWT[crypto]`, and the destructive migration.

- [ ] **Step 6: Check the docs against the code**

Run: `pytest`
Expected: PASS — `tests/test_migrations.py` and `tests/test_pages.py` are the parts of the suite that can catch a doc-adjacent drift.

Then reread the invariants you edited in `CLAUDE.md` against the code you actually wrote. Any statement you cannot point at a line for is a statement to delete.

- [ ] **Step 7: Commit**

```bash
git add CLAUDE.md docs/API.md docs/ARCHITECTURE.md docs/ROADMAP.md \
        README.md CHANGELOG.md
git commit -m "Document Phase 5

Reverses the no-user_id, no-auth invariant and the single-fetch-site
claim, both of which Phase 5 makes false. Adds the first-positional-
parameter rule, the mirror-table shape, the public-shell gating model and
PyJWT[crypto] as a runtime dependency.

The roadmap records where the implementation diverged from its own SQL
sketch — a UUID id, no password_hash, no verified_at, all forced by the
provider choice — and closes open decisions 2, 3 and 5.

README says plainly that upgrade-db deletes every existing workout."
```
