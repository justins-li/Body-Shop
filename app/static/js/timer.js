/**
 * Rest timer — counts down after a set is saved.
 *
 * Entirely client-side: no schema, no endpoint, and no notification. Phase 10
 * moves the alert to a watch, where you can see it without unlocking a phone;
 * this is the logic that phase will reuse.
 *
 * The timer is a convenience, never a prescription. It counts the rest you
 * chose — it does not tell you how long to rest.
 */

const DURATIONS = [60, 90, 120, 180];
const DEFAULT_SECONDS = 120;
const KEY = "bodyshop:rest-seconds";

let handle = null;
let remaining = 0;
let elements = null;

/** The reader's chosen rest length, defaulting to two minutes. */
function chosenSeconds() {
  const stored = Number(localStorage.getItem(KEY));
  return DURATIONS.includes(stored) ? stored : DEFAULT_SECONDS;
}

/** `m:ss`, so 90 reads as 1:30. */
function format(seconds) {
  const minutes = Math.floor(seconds / 60);
  return `${minutes}:${String(seconds % 60).padStart(2, "0")}`;
}

function paint() {
  elements.readout.textContent = format(Math.max(0, remaining));
  elements.root.classList.toggle("is-running", handle !== null);
}

function stop() {
  if (handle !== null) clearInterval(handle);
  handle = null;
  paint();
}

function tick() {
  remaining -= 1;
  if (remaining <= 0) {
    remaining = 0;
    stop();
  }
  paint();
}

/** Start, or restart, the countdown from the chosen duration. */
export function startRestTimer() {
  if (!elements) return;
  if (handle !== null) clearInterval(handle);
  remaining = chosenSeconds();
  handle = setInterval(tick, 1000);
  paint();
}

/**
 * Wire the timer's controls.
 *
 * Returns early when the container is missing, so a page without the shell —
 * every page but `/log` — can import this module harmlessly.
 *
 * @param {HTMLElement} root - The `.rest-timer` container.
 */
export function initRestTimer(root) {
  if (!root) return;
  elements = {
    root,
    readout: root.querySelector("[data-timer-readout]"),
    select: root.querySelector("[data-timer-duration]"),
    toggle: root.querySelector("[data-timer-toggle]"),
  };

  elements.select.value = String(chosenSeconds());
  elements.select.addEventListener("change", () => {
    localStorage.setItem(KEY, elements.select.value);
    // Only re-seed a stopped clock: changing the length mid-rest should not
    // silently restart the count you are already watching.
    if (handle === null) {
      remaining = chosenSeconds();
      paint();
    }
  });
  elements.toggle.addEventListener("click", () => {
    if (handle !== null) stop();
    else startRestTimer();
  });

  remaining = chosenSeconds();
  paint();
}
