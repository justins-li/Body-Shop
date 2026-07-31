/**
 * Routines page — a session to follow, and a one-tap way to log each movement.
 *
 * Phase 8.1. The app could always tell you what your week *was*; a new user's
 * first screen was still an empty picker over 873 movements. A routine is the
 * answer to "what do I actually do today", and every movement in one carries a
 * log button so following it does not mean retyping it into `/log` afterwards.
 *
 * **The quick log is not a lesser log.** It mounts `setgrid.js` — the same
 * component `/log` mounts — so a set recorded from a routine obeys every rule a
 * set recorded on the log page does: weight modes and their plate hints, the
 * added-weight toggle for bodyweight movements, the RPE gate, warm-ups, the
 * kg/lb preference, the rest timer. What differs is the *framing*: the movement
 * is already chosen, and the grid opens with the routine's prescribed number of
 * sets rather than however many you did last time.
 *
 * The routine's prescription is placed as **placeholders, not values**, exactly
 * as last session's numbers are on `/log`. A routine saying "4 × 6-8" is a
 * suggestion about what to do, and recording it as though it happened before it
 * has is the one thing a training log must never do.
 */

import { createEntry, fetchRoutine } from "./api.js";
import { $, retargetLinks, syncUrlDate, toast } from "./ui.js";
import { createSetGrid } from "./setgrid.js";

let selectedIso;

/** The routine on screen, hydrated. */
let routine = null;

/** The movement the quick-log dialog is currently pointed at. */
let logging = null;

/** The shared set grid, mounted once into the dialog and re-pointed per use. */
let grid = null;

/** Routines already fetched, so re-opening one costs nothing. */
const cache = new Map();

// ---- The routine's exercises ----------------------------------------------

/** A muscle badge; `strong` marks a primary (full-weight) group. */
function badge(label, strong) {
  const el = document.createElement("span");
  el.className = `muscle-badge${strong ? " is-primary" : ""}`;
  el.textContent = label;
  return el;
}

/**
 * One movement in the routine: its frames, what to do, and the log button.
 *
 * The two photographs are the catalog's own start and end position, stacked and
 * cross-faded in CSS — the same treatment `/log` gives the chosen movement, so
 * the two pages illustrate a lift identically.
 */
function exerciseCard(item, index) {
  const card = document.createElement("article");
  card.className = "routine-exercise";

  const frames = document.createElement("div");
  frames.className = "exercise-frames routine-exercise-frames";
  (item.images || []).forEach((src, frame) => {
    const img = document.createElement("img");
    img.className = "exercise-frame";
    img.src = src;
    img.alt = `${item.name}, ${frame === 0 ? "start" : "end"} position`;
    img.loading = "lazy";
    // A broken CDN must not leave a torn card behind.
    img.addEventListener("error", () => frames.remove(), { once: true });
    frames.append(img);
  });

  const body = document.createElement("div");
  body.className = "routine-exercise-body";

  const head = document.createElement("p");
  head.className = "routine-exercise-head";
  const order = document.createElement("span");
  order.className = "routine-exercise-order type-data";
  order.textContent = String(index + 1);
  const name = document.createElement("span");
  name.className = "routine-exercise-name";
  name.textContent = item.name;
  head.append(order, name);

  const dose = document.createElement("p");
  dose.className = "routine-exercise-dose type-data";
  dose.textContent = `${item.sets} × ${item.reps}`;

  const muscles = document.createElement("p");
  muscles.className = "exercise-chosen-muscles";
  muscles.append(...item.primary.map((m) => badge(m, true)));
  muscles.append(...item.secondary.map((m) => badge(m, false)));

  const note = document.createElement("p");
  note.className = "routine-exercise-note";
  note.textContent = item.note;

  body.append(head, dose, muscles, note);

  // Say so rather than letting a stretch quietly grade as zero on the map —
  // the same disclosure `/log` makes on the chosen movement.
  if (!item.counts_toward_volume) {
    const zero = document.createElement("p");
    zero.className = "exercise-chosen-note";
    zero.textContent = "Logged, but not counted toward weekly muscle volume.";
    body.append(zero);
  }

  if (item.instructions && item.instructions.length) {
    const how = document.createElement("details");
    how.className = "routine-how";
    const summary = document.createElement("summary");
    summary.className = "type-label";
    summary.textContent = "How to do it";
    const steps = document.createElement("ol");
    steps.className = "exercise-steps";
    item.instructions.forEach((step) => {
      const li = document.createElement("li");
      li.textContent = step;
      steps.append(li);
    });
    how.append(summary, steps);
    body.append(how);
  }

  const log = document.createElement("button");
  log.type = "button";
  log.className = "btn-brick routine-log";
  log.textContent = "Log this";
  log.addEventListener("click", () => openQuickLog(item));
  body.append(log);

  card.append(frames, body);
  return card;
}

function renderRoutine() {
  const panel = $("#routine-detail");
  panel.hidden = false;
  $("#routine-detail-heading").textContent = routine.name;
  $("#routine-detail-meta").textContent =
    `~${routine.minutes} min · ${routine.total_sets} sets`;

  const list = $("#routine-exercises");
  list.textContent = "";
  routine.exercises.forEach((item, index) => list.append(exerciseCard(item, index)));
}

async function selectRoutine(key) {
  document.querySelectorAll(".routine-card").forEach((card) => {
    card.setAttribute("aria-pressed", String(card.dataset.routine === key));
  });

  try {
    if (!cache.has(key)) cache.set(key, await fetchRoutine(key));
    routine = cache.get(key);
  } catch (err) {
    toast(err.message, "error");
    return;
  }
  renderRoutine();
  $("#routine-detail").scrollIntoView({ behavior: "smooth", block: "start" });
}

// ---- Quick log -------------------------------------------------------------

function showQuickError(message) {
  const box = $("#quick-log-error");
  box.textContent = message;
  box.hidden = !message;
}

/**
 * Open the dialog against one movement.
 *
 * The grid opens with the routine's set count, and the reps as a **placeholder**
 * on every row — a suggestion to aim at, not a value. An untouched row still
 * saves as NULL, so following a routine loosely records what you did rather than
 * what it told you to do.
 */
function openQuickLog(item) {
  logging = item;
  showQuickError("");
  $("#quick-log-name").textContent = item.name;
  $("#quick-log-date").value = selectedIso;

  // `reps` is free text on a routine ("8-10", "max", "30 sec"), so only a bare
  // number is worth offering as a placeholder — the rest would not parse into
  // the field anyway, and a half-parsed "30" from "30 sec" would be a lie.
  const suggestedReps = /^\d+$/.test(item.reps) ? Number(item.reps) : null;
  grid.setMovement({
    weightMode: item.weight_mode,
    previousSets: Array.from({ length: item.sets }, () => ({ reps: suggestedReps })),
    count: item.sets,
  });
  grid.setPrefillNote(`This routine asks for ${item.sets} × ${item.reps}.`);

  $("#quick-log").showModal();
}

async function onQuickSubmit(event) {
  event.preventDefault();
  showQuickError("");
  if (!logging) return;

  const iso = $("#quick-log-date").value;
  if (!iso) return showQuickError("Pick a date first.");

  const sets = grid.values();
  if (!sets.length) return showQuickError("Add at least one set.");

  try {
    const entry = await createEntry({
      date: iso,
      exercise_id: logging.exercise_id,
      sets,
    });
    $("#quick-log").close();
    toast(`Logged ${entry.set_count} × ${entry.exercise_name}.`);
  } catch (err) {
    showQuickError(err.message);
  }
}

// ---- Boot ------------------------------------------------------------------

/** Every page honours `?date=`, so navigating away keeps the day being viewed. */
function retargetNav(iso) {
  retargetLinks(
    Array.from(document.querySelectorAll(".nav-link, .tab-link, .shelf")), iso,
  );
}

/**
 * Boot the routines page.
 * @param {string} initialIso - The day a quick log defaults to (`YYYY-MM-DD`).
 */
export async function initRoutines(initialIso) {
  selectedIso = initialIso;

  document.querySelectorAll(".routine-card").forEach((card) => {
    card.addEventListener("click", () => selectRoutine(card.dataset.routine));
  });

  // Mounted once. Re-pointing it per movement is cheaper than rebuilding it,
  // and it keeps one grid's worth of listeners on the page rather than one per
  // exercise card.
  grid = createSetGrid($("#quick-log-grid"), { onError: showQuickError });

  $("#quick-log-form").addEventListener("submit", onQuickSubmit);
  $("#quick-log-close").addEventListener("click", () => $("#quick-log").close());
  $("#quick-log-date").addEventListener("change", (event) => {
    if (!event.target.value) return;
    selectedIso = event.target.value;
    syncUrlDate(selectedIso);
    retargetNav(selectedIso);
  });

  retargetNav(selectedIso);
}
