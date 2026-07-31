/**
 * Rest timer — counts down after a set is finished.
 *
 * Entirely client-side: no schema, no endpoint, and no notification. Phase 10
 * moves the alert to a watch, where you can see it without unlocking a phone;
 * this is the logic that phase will reuse.
 *
 * The timer is a convenience, never a prescription. It counts the rest you
 * chose — it does not tell you how long to rest.
 *
 * Two things are load-bearing about how it keeps time:
 *
 * 1. **It stores a deadline, not a remaining count.** Rest continues while you
 *    look at the calendar, so the countdown has to survive a page load — and
 *    every page boots this module from `base.html`. A remaining-seconds counter
 *    would also drift, because browsers throttle `setInterval` in a backgrounded
 *    tab; recomputing from a timestamp is correct however long the tab slept.
 * 2. **The readout and the duration select need not share a page.** The strip
 *    lives in the shared header; choosing a rest length is a setup decision, so
 *    that select stays on `/log` beside the sets. This module binds whichever
 *    of the two the current page ships.
 */

const DURATIONS = [60, 90, 120, 180];
const DEFAULT_SECONDS = 120;
const KEY = "bodyshop:rest-seconds";
const UNTIL_KEY = "bodyshop:rest-until";

let handle = null;
let elements = null;

/** Storage can throw in private browsing; the timer still works, it just
 *  stops surviving navigation. */
function read(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key, value) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Nothing to do — see above.
  }
}

/** The reader's chosen rest length, defaulting to two minutes. */
function chosenSeconds() {
  const stored = Number(read(KEY));
  return DURATIONS.includes(stored) ? stored : DEFAULT_SECONDS;
}

/** Epoch milliseconds the current rest ends at, or 0 when nothing is running. */
function deadline() {
  const stored = Number(read(UNTIL_KEY));
  return Number.isFinite(stored) && stored > Date.now() ? stored : 0;
}

/** Seconds left on the clock — 0 when stopped, so the readout falls back. */
function remaining() {
  const until = deadline();
  return until ? Math.ceil((until - Date.now()) / 1000) : 0;
}

/** `m:ss`, so 90 reads as 1:30. */
function format(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function paint() {
  if (!elements) return;
  const left = remaining();
  // A stopped clock shows the length it would run for, not 0:00 — that reads
  // as "ready", where a zero reads as "finished" every time you open the app.
  elements.readout.textContent = format(left || chosenSeconds());
  elements.root.classList.toggle("is-running", left > 0);
}

function stop() {
  if (handle !== null) clearInterval(handle);
  handle = null;
  write(UNTIL_KEY, null);
  paint();
}

function tick() {
  if (remaining() <= 0) {
    stop(); // paints on its way out, so this tick is already drawn
    return;
  }
  paint();
}

/** Start, or restart, the countdown from the chosen duration. */
export function startRestTimer() {
  if (!elements) return;
  if (handle !== null) clearInterval(handle);
  write(UNTIL_KEY, String(Date.now() + chosenSeconds() * 1000));
  handle = setInterval(tick, 1000);
  paint();
}

/**
 * Wire the timer's controls.
 *
 * Returns early when the strip is missing, so a page without it can import this
 * module harmlessly.
 *
 * @param {HTMLElement} root - The `.rest-timer` strip from `base.html`.
 */
export function initRestTimer(root) {
  if (!root) return;
  elements = {
    root,
    readout: root.querySelector("[data-timer-readout]"),
    toggle: root.querySelector("[data-timer-toggle]"),
  };

  elements.toggle.addEventListener("click", () => {
    if (deadline()) stop();
    else startRestTimer();
  });

  // Queried from the document rather than the strip: on /log it sits down in
  // the form, and on every other page it does not exist at all.
  const select = document.querySelector("[data-timer-duration]");
  if (select) {
    select.value = String(chosenSeconds());
    select.addEventListener("change", () => {
      write(KEY, select.value);
      // Only re-seed a stopped clock: changing the length mid-rest should not
      // silently restart the count you are already watching.
      if (!deadline()) paint();
    });
  }

  // A rest already running when the page loaded keeps counting.
  if (deadline()) handle = setInterval(tick, 1000);
  paint();
}
