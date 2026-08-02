/**
 * Shared DOM helpers: date formatting, toasts, and entry-list rendering.
 * Imported by every page module so the three pages look and behave alike.
 */

/** @param {string} selector @returns {HTMLElement|null} */
export const $ = (selector, root = document) => root.querySelector(selector);

/** Format `YYYY-MM-DD` as e.g. "Tuesday, Jul 28". */
export function formatDate(isoDate, options = { weekday: "long", month: "short", day: "numeric" }) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day).toLocaleDateString(undefined, options);
}

/** Today's date as `YYYY-MM-DD` in the browser's local timezone. */
export function todayIso() {
  return toIso(new Date());
}

/** Convert a `Date` to `YYYY-MM-DD` without UTC drift. */
export function toIso(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

/** Parse `YYYY-MM-DD` into a local-midnight `Date`. */
export function fromIso(isoDate) {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}

/** Return a new ISO date `days` away from `isoDate`. */
export function addDays(isoDate, days) {
  const date = fromIso(isoDate);
  date.setDate(date.getDate() + days);
  return toIso(date);
}

/**
 * Render a weighted set count: `12.5`, but `12` rather than `12.0`.
 *
 * Secondary muscles count half a set, so per-group totals are fractional.
 * Mirrors `format_sets` in `app/exercises.py`.
 */
export function formatSets(value) {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

/**
 * Weight is stored in kilograms and displayed in whichever unit the reader
 * picked. Conversion happens only here, at the UI boundary — the column, the
 * API and every Phase 7 aggregate are kilograms throughout.
 */
export const WEIGHT_UNITS = ["kg", "lb"];

const LB_PER_KG = 2.2046226218;
const UNIT_KEY = "bodyshop:weight-unit";

/** The reader's chosen unit, defaulting to kg. */
export function loadUnit() {
  const stored = localStorage.getItem(UNIT_KEY);
  return WEIGHT_UNITS.includes(stored) ? stored : "kg";
}

/** Remember the reader's unit choice. Ignores anything not in `WEIGHT_UNITS`. */
export function saveUnit(unit) {
  if (WEIGHT_UNITS.includes(unit)) localStorage.setItem(UNIT_KEY, unit);
}

/**
 * The trainer setup — Phase 6, given a home on the user row in the Phase 5
 * carryover.
 *
 * **The server owns this. What is stored here is a cache of its answer**, so
 * that `loadProfile()` can stay synchronous: `setgrid.js` decides whether to
 * draw the RPE column while it is building markup, and making that await a
 * fetch means the column flickers in after the grid has already painted.
 *
 * Nothing writes this cache except `api.js`, from a payload that carried a
 * resolved profile. Treating it as a store is what this change ended — a second
 * device would go on grading you against whatever that browser last chose.
 *
 * **The client never computes a target from it.** The server sends back the
 * targets it graded against (`profile.targets` on the weekly summary), and
 * deriving them here as well would be two implementations of one rule.
 */
const PROFILE_KEY = "bodyshop:trainer-profile";

/** What a browser with no stored choice sends — the server's own default. */
const DEFAULT_PROFILE = {
  experience: "experienced",
  sessions_per_week: 5,
  minutes_per_session: 75,
};

/** The stored trainer setup, or the default. Never throws. */
export function loadProfile() {
  try {
    const stored = JSON.parse(localStorage.getItem(PROFILE_KEY) || "null");
    if (!stored || typeof stored !== "object") return { ...DEFAULT_PROFILE };
    return {
      experience: stored.experience || DEFAULT_PROFILE.experience,
      sessions_per_week:
        Number(stored.sessions_per_week) || DEFAULT_PROFILE.sessions_per_week,
      minutes_per_session:
        Number(stored.minutes_per_session) || DEFAULT_PROFILE.minutes_per_session,
    };
  } catch {
    // Private browsing, storage disabled, or a value from an older shape.
    return { ...DEFAULT_PROFILE };
  }
}

/**
 * Remember the server's resolved profile. Silently does nothing if storage is
 * blocked — the setup is on the account either way, and the next response
 * carries it again.
 */
export function cacheProfile(profile) {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(profile));
  } catch {
    // The cache just won't persist; the next response carries it again.
  }
}

/** A displayed value in `unit` → kilograms, for sending to the API. */
export function toKg(value, unit) {
  return unit === "lb" ? value / LB_PER_KG : value;
}

/** Kilograms → a value in `unit`, for display. */
export function fromKg(value, unit) {
  return unit === "lb" ? value * LB_PER_KG : value;
}

/**
 * Render a weight for reading: `60`, `62.5`, and `""` when it was not recorded.
 *
 * Rounds to one decimal like `formatSets`, which is also what makes the lb
 * round trip read cleanly — 135 lb stored as 61.23kg comes back as `135`, not
 * `134.99998`.
 */
export function formatWeight(kg, unit = loadUnit()) {
  if (kg === null || kg === undefined) return "";
  const value = Math.round(fromKg(kg, unit) * 10) / 10;
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

/**
 * How each `weight_mode` presents its weight — Phase 6.5.
 *
 * The rule that produces the mode is the server's (`EQUIPMENT_WEIGHT_MODES` in
 * `app/exercises.py`); what a mode is *called* is presentation, so it lives
 * here beside the other display vocabulary, the way `SET_TYPE_LABELS` does in
 * `log.js`.
 *
 * - `label` heads the weight column in the set grid.
 * - `note` is the one line under it saying what the number means.
 * - `prefix` marks the value where the bare number would mislead: a weighted
 *   pull-up's `20` is twenty kilos *added*, not twenty kilos lifted, and the
 *   two must not read alike in a list of entries.
 */
export const WEIGHT_MODE_DISPLAY = {
  barbell: { label: "Weight", note: "Total on the bar, bar included.", prefix: "" },
  ez_bar: { label: "Weight", note: "Total on the EZ bar, bar included.", prefix: "" },
  dumbbell: { label: "Weight", note: "Per dumbbell, not the pair.", prefix: "" },
  kettlebell: { label: "Weight", note: "Per bell.", prefix: "" },
  stack: { label: "Weight", note: "The stack setting, as marked on the machine.", prefix: "" },
  bodyweight: {
    label: "Added",
    note: "Bodyweight — leave blank unless you added weight.",
    prefix: "+",
  },
  implement: { label: "Weight", note: "Whatever the implement is marked as.", prefix: "" },
  // No weight column at all — see `unweighted` in app/exercises.py. The note
  // still speaks, because a missing column with no explanation reads as a bug.
  unweighted: { label: "", note: "No weight to record — just sets and time.", prefix: "" },
};

/** The display rules for a mode, falling back to a plain weight column. */
export function weightModeDisplay(mode) {
  return WEIGHT_MODE_DISPLAY[mode] || WEIGHT_MODE_DISPLAY.implement;
}

/**
 * One set as a short line: `100kg × 5 @8.5`, degrading as fields are missing.
 * Returns `""` for a set that recorded nothing, so callers can skip it.
 *
 * `mode` is the entry's `weight_mode`. It only changes the weight's prefix —
 * `+20kg × 8` for a weighted pull-up — but that prefix is load-bearing: the
 * same stored number means "lifted" for a barbell and "hung off a belt" here.
 */
export function describeSet(set, unit = loadUnit(), mode = "implement") {
  const parts = [];
  if (set.weight !== null && set.weight !== undefined) {
    // A bodyweight set recorded as 0 added weight is just a bodyweight set;
    // "+0kg" is noise, and dropping it lets the reps carry the line.
    const bare = weightModeDisplay(mode).prefix === "+" && set.weight === 0;
    if (!bare) {
      parts.push(
        `${weightModeDisplay(mode).prefix}${formatWeight(set.weight, unit)}${unit}`,
      );
    }
  }
  if (set.reps !== null && set.reps !== undefined) {
    parts.push(parts.length ? `× ${set.reps}` : `${set.reps} reps`);
  }
  if (set.rpe !== null && set.rpe !== undefined) parts.push(`@${set.rpe}`);
  // Say which sets the count left out. Without this a warm-up reads as a
  // working set: an entry of one working set plus one warm-up shows "1 set"
  // above two identical lines, which looks like a bug in the count.
  if (parts.length && set.set_type && set.set_type !== "normal") {
    parts.push(`(${set.set_type})`);
  }
  return parts.join(" ");
}

/** Update `?date=` in the address bar without reloading the page. */
export function syncUrlDate(isoDate) {
  const url = new URL(window.location.href);
  url.searchParams.set("date", isoDate);
  window.history.replaceState({}, "", url);
}

/** Point every `href` on the given elements at `?date=isoDate`. */
export function retargetLinks(elements, isoDate) {
  elements.filter(Boolean).forEach((el) => {
    const url = new URL(el.getAttribute("href"), window.location.origin);
    url.searchParams.set("date", isoDate);
    el.setAttribute("href", `${url.pathname}${url.search}`);
  });
}

let toastTimer;
/**
 * Show a transient message at the bottom of the screen.
 * @param {string} message
 * @param {"info"|"error"} [tone]
 */
export function toast(message, tone = "info") {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("is-error", tone === "error");
  el.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("is-visible"), 2600);
}

/**
 * Render a list of entries into `container`.
 *
 * @param {HTMLElement} container
 * @param {Array<object>} entries      Entry objects from the API.
 * @param {object}  [opts]
 * @param {string}  [opts.emptyMessage]
 * @param {boolean} [opts.showDate]    Prefix each row with its date.
 * @param {(id:number)=>void} [opts.onDelete] Adds a delete button per row.
 */
export function renderEntries(container, entries, opts = {}) {
  const { emptyMessage = "Nothing logged yet.", showDate = false, onDelete } = opts;
  container.textContent = "";

  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = emptyMessage;
    container.append(empty);
    return;
  }

  for (const entry of entries) {
    const row = document.createElement("article");
    row.className = "entry";

    const main = document.createElement("div");
    main.className = "entry-main";

    const name = document.createElement("div");
    name.className = "entry-name";
    name.textContent = entry.exercise_name;

    const meta = document.createElement("div");
    meta.className = "entry-meta";
    const muscles = entry.muscles.join(" · ");
    meta.textContent = showDate ? `${formatDate(entry.date, { month: "short", day: "numeric" })} — ${muscles}` : muscles;

    main.append(name, meta);

    // A line of "100kg × 5" per set, when there is anything to say. Entries
    // logged as a bare count stay a single line, exactly as before. The entry
    // carries its own `weight_mode`, so a weighted pull-up reads "+20kg × 8"
    // without this having to consult the catalog.
    const detail = entry.sets
      .map((set) => describeSet(set, loadUnit(), entry.weight_mode))
      .filter(Boolean);
    if (detail.length) {
      const performed = document.createElement("div");
      performed.className = "entry-performed";
      performed.textContent = detail.join(" · ");
      main.append(performed);
    }

    const sets = document.createElement("span");
    sets.className = "entry-sets";
    sets.textContent = `${entry.set_count} ${entry.set_count === 1 ? "set" : "sets"}`;

    row.append(main, sets);

    if (onDelete) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "entry-delete";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Delete ${entry.set_count} sets of ${entry.exercise_name}`);
      remove.addEventListener("click", () => onDelete(entry.id));
      row.append(remove);
    }

    container.append(row);
  }
}
