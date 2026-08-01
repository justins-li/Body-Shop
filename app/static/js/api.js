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

/**
 * The whole catalog in its light shape — no instructions, no images.
 *
 * Fetched once per page load and filtered client-side; at 873 movements that
 * is ~35 KB gzipped, which beats a round trip per keystroke.
 * @returns {Promise<Array>}
 */
export async function fetchExercises() {
  const data = await request("/exercises");
  return data.exercises;
}

/**
 * Recently logged exercises, most recent first, each carrying `uses` — how many
 * times it has been logged. The picker ranks browse and search by that count,
 * so it asks for more than it lists.
 * Reads entry history, so it cannot come from the catalog payload.
 */
export async function fetchRecentExercises(limit = 12) {
  const data = await request(`/exercises/recent?limit=${limit}`);
  return data.exercises;
}

/** One exercise in full: instructions and absolute image URLs. */
export async function fetchExerciseDetail(id) {
  const data = await request(`/exercises/${encodeURIComponent(id)}`);
  return data.exercise;
}

/**
 * List entries for a single ISO date.
 * @param {string} isoDate - `YYYY-MM-DD`
 */
export async function fetchEntriesForDate(isoDate) {
  const data = await request(`/entries?date=${encodeURIComponent(isoDate)}`);
  return data.entries;
}

/** List entries in an inclusive ISO date range. */
export async function fetchEntriesInRange(startIso, endIso) {
  const query = `start=${encodeURIComponent(startIso)}&end=${encodeURIComponent(endIso)}`;
  const data = await request(`/entries?${query}`);
  return data.entries;
}

/**
 * Create an entry.
 * @param {{date: string, exercise_id: string, sets: Array<object>}} entry
 *   `sets` is an array of `{weight?, reps?, rpe?, set_type?}` — weight in
 *   **kilograms**, which is the only unit that crosses the wire. Three bare
 *   sets are `[{}, {}, {}]`.
 */
export async function createEntry(entry) {
  const data = await request("/entries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  return data.entry;
}

/**
 * The sets from the last session of a movement — what the grid prefills from.
 * @returns {Promise<{date: string|null, sets: Array<object>}>}
 */
export async function fetchLastSets(id) {
  return request(`/exercises/${encodeURIComponent(id)}/last-sets`);
}

/** Delete an entry by id. */
export async function deleteEntry(id) {
  return request(`/entries/${id}`, { method: "DELETE" });
}

/**
 * Total sets per day for a month.
 * @returns {Promise<Record<string, number>>} `{ "2026-07-28": 6, ... }`
 */
export async function fetchMonth(year, month) {
  const data = await request(`/calendar?year=${year}&month=${month}`);
  return data.days;
}

/** Weekly muscle-coverage summary for the week containing `isoDate`. */
export async function fetchWeeklySummary(isoDate) {
  return request(`/summary/week?date=${encodeURIComponent(isoDate)}`);
}

/**
 * The training graph: movements as nodes, same-day pairings as edges.
 * @param {"8w"|"6m"|"all"} window
 * @param {string} isoDate - Anchors both the window and the colouring week.
 */
export async function fetchTrainingGraph(window, isoDate) {
  const query = `window=${encodeURIComponent(window)}&date=${encodeURIComponent(isoDate)}`;
  return request(`/progress/graph?${query}`);
}

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
