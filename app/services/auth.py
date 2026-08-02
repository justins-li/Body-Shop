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
