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

/**
 * Refuse to talk to a Supabase we have not been told about.
 *
 * Unconfigured, `CONFIG.url` is `""` and `BASE` becomes the *relative* path
 * `/auth/v1` — so every sign-up posts to our own Flask server, which has no
 * such route and answers **404**. That points the reader at Flask, which is the
 * one place the bug is not. It cost a real debugging session; anyone who clones
 * this repo without a `.env` hits it, and so does a deploy with a missing
 * environment variable.
 *
 * Called from the request helpers rather than at module load: a module-level
 * throw would take `base.html`'s boot script down with it and break pages that
 * need no Supabase at all.
 */
function requireConfig() {
  if (!CONFIG.url || !CONFIG.anon_key) {
    throw new Error(
      "Supabase is not configured. Set BODYSHOP_SUPABASE_URL and " +
        "BODYSHOP_SUPABASE_ANON_KEY in .env, then restart the server — the " +
        "config is read once at start-up."
    );
  }
}

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

/** Pull GoTrue's message out of a response body, whichever field it used. */
function messageFrom(payload, status) {
  return (
    (payload && (payload.error_description || payload.msg || payload.message)) ||
    `Request failed (${status})`
  );
}

/**
 * POST to GoTrue and return the parsed body, throwing its message on failure.
 * @returns {Promise<any>}
 */
async function post(path, body, extraHeaders = {}) {
  requireConfig();
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
    throw new Error(messageFrom(payload, response.status));
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
  requireConfig();
  const response = await fetch(`${BASE}/user`, {
    method: "PUT",
    headers: headers({ Authorization: `Bearer ${token}` }),
    body: JSON.stringify({ password: newPassword }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(messageFrom(payload, response.status));
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
