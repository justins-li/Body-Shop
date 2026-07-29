/**
 * Thin wrapper around the Body Shop JSON API.
 *
 * Every function returns parsed JSON and throws an `Error` carrying the
 * server's message when the response is not 2xx, so callers can simply
 * `try { ... } catch (err) { toast(err.message) }`.
 */

const BASE = "/api";

/**
 * Perform a request against the API.
 * @param {string} path - Path below `/api`, e.g. `/entries`.
 * @param {RequestInit} [options]
 * @returns {Promise<any>} Parsed JSON body.
 */
async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });

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

/** @returns {Promise<Array>} The exercise catalog. */
export async function fetchExercises() {
  const data = await request("/exercises");
  return data.exercises;
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
 * @param {{date: string, exercise_id: string, sets: number}} entry
 */
export async function createEntry(entry) {
  const data = await request("/entries", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(entry),
  });
  return data.entry;
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
