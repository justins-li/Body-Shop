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

    const sets = document.createElement("span");
    sets.className = "entry-sets";
    sets.textContent = `${entry.sets} ${entry.sets === 1 ? "set" : "sets"}`;

    row.append(main, sets);

    if (onDelete) {
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "entry-delete";
      remove.textContent = "×";
      remove.setAttribute("aria-label", `Delete ${entry.sets} sets of ${entry.exercise_name}`);
      remove.addEventListener("click", () => onDelete(entry.id));
      row.append(remove);
    }

    container.append(row);
  }
}
