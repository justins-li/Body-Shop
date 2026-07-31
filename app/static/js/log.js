/**
 * Log page — pick a movement from the catalog, record sets, review the day.
 *
 * The catalog is 873 movements, so the picker is the page. It fetches
 * `/api/exercises` once (the light shape: no instructions, no images) and
 * filters it locally through three access paths, in deliberate order of
 * prominence:
 *
 *   Recent — the default, and the 90% path. Most people cycle through 10–20
 *            movements, so history beats search almost every time.
 *   Browse — muscle group then equipment. The way you *shop* for a movement,
 *            and the path a new user has to succeed on, so it is a full tab.
 *   Search — behind an icon. It is the fallback for when you already know the
 *            name, which is the narrower case, and giving it equal billing
 *            invited typing at a catalog nobody has memorised.
 *
 * Every list is ordered by the same three keys, most significant first: whether
 * the movement trains the chosen muscle *primarily*, how often **you** have
 * logged it, then `rank` — the server's "common lifts first" ordering (see
 * `STAPLE_EXERCISE_IDS` in app/exercises.py). Alphabetical is the last resort,
 * never the first: it used to open chest with "Alternating Floor Press".
 *
 * Only the *selected* exercise costs a second request, for its instructions and
 * the two photographs the card animates between.
 */

import {
  createEntry, deleteEntry, fetchEntriesForDate, fetchExerciseDetail,
  fetchExercises, fetchLastSets, fetchRecentExercises,
} from "./api.js";
import {
  $, formatDate, loadUnit, renderEntries, retargetLinks, saveUnit,
  syncUrlDate, toast,
} from "./ui.js";
import { createSetGrid } from "./setgrid.js";
import { startRestTimer } from "./timer.js";

let selectedIso;
let catalog = [];
let byId = new Map();
let selectedId = null;

/** The reader's display unit. Weight is kilograms everywhere else. */
let unit = loadUnit();

/**
 * The shared set grid (Phase 8.2), mounted into the form.
 *
 * Everything about *what a set is* — weight modes, added weight, the RPE gate,
 * plate hints, repeat, the rest timer — lives in `setgrid.js` and is identical
 * here and in a routine's quick-log. This page's job is choosing the movement
 * and the day.
 */
let grid = null;

/** muscle slug → its movements, pre-sorted. Built once, after the one fetch. */
let byMuscle = new Map();

/** muscle slug → the equipment values that muscle actually has. */
let equipmentByMuscle = new Map();

/** exercise id → times logged, from `/api/exercises/recent`. */
let personalUses = new Map();

/** Whether browse is showing its whole list rather than the first page. */
let browseExpanded = false;

/** Most results anyone scans before retyping; keeps the DOM small. */
const MAX_RESULTS = 40;

/**
 * How many recents to *fetch*. Only `RECENT_SHOWN` are listed; the rest are
 * kept for their `uses` counts, which rank browse and search. One request
 * either way, so ask for the wider history.
 */
const RECENT_FETCHED = 50;
const RECENT_SHOWN = 12;

/**
 * Gym shorthand the catalog's own words don't cover, so "incl db bench" finds
 * "Dumbbell Incline Bench Press".
 */
const ALIASES = {
  db: "dumbbell",
  bb: "barbell",
  kb: "kettlebell",
  ez: "e-z curl bar",
  bw: "body only",
  ohp: "shoulder press",
  rdl: "romanian deadlift",
};

const MUSCLE_LABELS = {
  chest: "Chest", abs: "Abs", shoulders: "Shoulders", biceps: "Biceps",
  forearms: "Forearms", quads: "Quads", back: "Back", traps: "Traps",
  triceps: "Triceps", glutes: "Glutes", hamstrings: "Hamstrings", calves: "Calves",
};

const titleCase = (value) => value.charAt(0).toUpperCase() + value.slice(1);

/** Everything a search query is matched against, lower-cased once at load. */
function haystack(exercise) {
  return [
    exercise.name,
    exercise.equipment,
    exercise.category,
    ...exercise.muscles.map((m) => MUSCLE_LABELS[m] || m),
  ].join(" ").toLowerCase();
}

// ---- Ordering --------------------------------------------------------------

/** Times the user has logged this movement — 0 if never. */
const uses = (exercise) => personalUses.get(exercise.id) || 0;

/**
 * Index the catalog by muscle group, so browsing is a lookup rather than a scan.
 *
 * Each list is sorted once, here, by primary-first then `rank` then name — every
 * key that does not depend on history. `uses` is applied at render time
 * instead, because the recents request can land after this runs and because a
 * stable sort over an already-ranked list preserves the rest of the order.
 */
function buildIndexes() {
  byMuscle = new Map();
  equipmentByMuscle = new Map();

  for (const exercise of catalog) {
    for (const muscle of exercise.muscles) {
      if (!byMuscle.has(muscle)) byMuscle.set(muscle, []);
      byMuscle.get(muscle).push(exercise);
    }
  }

  for (const [muscle, exercises] of byMuscle) {
    exercises.sort((a, b) =>
      Number(!a.primary.includes(muscle)) - Number(!b.primary.includes(muscle))
      || a.rank - b.rank
      || a.name.localeCompare(b.name));
    equipmentByMuscle.set(muscle, [...new Set(exercises.map((e) => e.equipment))].sort());
  }
}

/**
 * Re-order a muscle's pre-sorted list to put the user's own movements first.
 *
 * `Array.prototype.sort` is stable, and the input is already ordered by rank
 * and name, so comparing only these two tiers leaves everything else intact.
 */
function personalFirst(exercises, muscle) {
  const tier = (e) => Number(!e.primary.includes(muscle)) * 2 + Number(uses(e) === 0);
  return [...exercises].sort((a, b) => tier(a) - tier(b));
}

// ---- Searching ------------------------------------------------------------

/**
 * Rank the catalog against `query`.
 *
 * Every whitespace-separated token must match, so tokens narrow rather than
 * widen. Name matches outrank matches on equipment or muscle, and a name that
 * *starts* with the query outranks one that merely contains it. Within a tier
 * it is your own history first, then the catalog's `rank` — so "press" leads
 * with the bench press rather than the Anti-Gravity Press.
 */
function search(query) {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean)
    .map((token) => ALIASES[token] || token);
  if (!tokens.length) return [];

  const phrase = tokens.join(" ");
  const scored = [];
  for (const exercise of catalog) {
    if (!tokens.every((token) => exercise._haystack.includes(token))) continue;

    const name = exercise.name.toLowerCase();
    const score = name.startsWith(phrase) ? 0 : name.includes(phrase) ? 1 : 2;
    scored.push({ exercise, score });
  }

  scored.sort((a, b) =>
    a.score - b.score
    || uses(b.exercise) - uses(a.exercise)
    || a.exercise.rank - b.exercise.rank
    || a.exercise.name.localeCompare(b.exercise.name));
  return scored.slice(0, MAX_RESULTS).map((s) => s.exercise);
}

// ---- Rendering ------------------------------------------------------------

/** A muscle badge; `strong` marks a primary (full-weight) group. */
function badge(muscle, strong) {
  const el = document.createElement("span");
  el.className = `muscle-badge${strong ? " is-primary" : ""}`;
  el.textContent = MUSCLE_LABELS[muscle] || muscle;
  return el;
}

/** One selectable row in a results list. */
function resultRow(exercise) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = "picker-result";
  row.dataset.id = exercise.id;
  row.setAttribute("aria-pressed", String(exercise.id === selectedId));

  const name = document.createElement("span");
  name.className = "picker-result-name";
  name.textContent = exercise.name;

  const meta = document.createElement("span");
  meta.className = "picker-result-meta";
  meta.append(...exercise.primary.map((m) => badge(m, true)));
  meta.append(...exercise.secondary.map((m) => badge(m, false)));

  const equipment = document.createElement("span");
  equipment.className = "picker-result-equipment";
  equipment.textContent = titleCase(exercise.equipment);
  meta.append(equipment);

  row.append(name, meta);
  row.addEventListener("click", () => selectExercise(exercise.id));
  return row;
}

/** Fill a results container, or show why it is empty. */
function renderResults(container, exercises, emptyMessage) {
  container.textContent = "";
  if (!exercises.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = emptyMessage;
    container.append(empty);
    return;
  }
  exercises.forEach((exercise) => container.append(resultRow(exercise)));
}

/**
 * Render the chosen movement: its two frames, muscles and instructions.
 *
 * The frames are the dataset's start and end position. Stacking them and
 * cross-fading in CSS turns the pair into a short loop of the movement — see
 * `.exercise-frame` in input.css, which also honours `prefers-reduced-motion`.
 */
function renderChosen(detail) {
  const panel = $("#exercise-chosen");
  panel.textContent = "";
  panel.hidden = false;

  const card = document.createElement("div");
  card.className = "exercise-chosen-card";

  const frames = document.createElement("div");
  frames.className = "exercise-frames";
  detail.images.forEach((src, index) => {
    const img = document.createElement("img");
    img.className = "exercise-frame";
    img.src = src;
    img.alt = `${detail.name}, ${index === 0 ? "start" : "end"} position`;
    img.loading = "lazy";
    // A broken CDN must not leave a torn card behind.
    img.addEventListener("error", () => frames.remove(), { once: true });
    frames.append(img);
  });

  const body = document.createElement("div");
  body.className = "exercise-chosen-body";

  const name = document.createElement("p");
  name.className = "exercise-chosen-name";
  name.textContent = detail.name;

  const muscles = document.createElement("p");
  muscles.className = "exercise-chosen-muscles";
  muscles.append(...detail.primary.map((m) => badge(m, true)));
  muscles.append(...detail.secondary.map((m) => badge(m, false)));

  body.append(name, muscles);

  // Say so rather than letting a stretch quietly grade as zero on the map.
  if (!detail.counts_toward_volume) {
    const note = document.createElement("p");
    note.className = "exercise-chosen-note";
    note.textContent =
      `${titleCase(detail.category)} — logged, but not counted toward weekly muscle volume.`;
    body.append(note);
  }

  if (detail.instructions.length) {
    const steps = document.createElement("ol");
    steps.className = "exercise-steps";
    detail.instructions.forEach((step) => {
      const li = document.createElement("li");
      li.textContent = step;
      steps.append(li);
    });
    body.append(steps);
  }

  card.append(frames, body);
  panel.append(card);
}

// ---- Selection ------------------------------------------------------------

async function selectExercise(id) {
  selectedId = id;
  $("#exercise-id").value = id;
  showError("");

  document.querySelectorAll(".picker-result").forEach((row) => {
    row.setAttribute("aria-pressed", String(row.dataset.id === id));
  });

  await Promise.all([renderChosenFor(id), loadPreviousSets(id)]);
}

/** Render the chosen movement's card, falling back to the light shape. */
async function renderChosenFor(id) {
  try {
    renderChosen(await fetchExerciseDetail(id));
  } catch (err) {
    // The pick still stands; only its illustration failed.
    const exercise = byId.get(id);
    if (exercise) renderChosen({ ...exercise, images: [], instructions: [] });
    toast(err.message, "error");
  }
}

/**
 * Prefill the grid from the last time this movement was logged.
 *
 * A failure here is not worth a toast — the grid still works, it just starts
 * empty — so it degrades to no placeholders rather than an error.
 */
async function loadPreviousSets(id) {
  let previousSets = [];
  let note = "";
  try {
    const data = await fetchLastSets(id);
    previousSets = data.sets || [];
    if (data.date) {
      note = `Greyed values are what you did on ${formatDate(data.date, {
        month: "short", day: "numeric",
      })}.`;
    }
  } catch {
    // Not worth a toast: the grid still works, it just starts with no
    // placeholders rather than with an error over it.
    previousSets = [];
  }

  // The grid takes it from here — the mode off the catalog payload already in
  // memory, and the rest (added weight, the RPE column) decided from history.
  grid.setMovement({
    weightMode: byId.get(id)?.weight_mode,
    previousSets,
  });
  grid.setPrefillNote(note);
}

// ---- The set grid ---------------------------------------------------------
//
// Phase 8.2 moved every line of this into `setgrid.js`, because routines gave
// the app a second place to record a set and a simpler grid there would have
// been a second set of rules about weight modes, warm-ups and units. What is
// left here is mounting it and reading it back.


// ---- Panels ---------------------------------------------------------------

function showTab(name) {
  document.querySelectorAll("[data-tab]").forEach((tab) => {
    tab.setAttribute("aria-selected", String(tab.dataset.tab === name));
  });
  document.querySelectorAll("[data-panel]").forEach((panel) => {
    panel.hidden = panel.dataset.panel !== name;
  });
  if (name === "search") $("#exercise-search").focus();
}

async function loadRecent() {
  try {
    const recent = await fetchRecentExercises(RECENT_FETCHED);
    personalUses = new Map(recent.map((e) => [e.id, e.uses || 0]));
    renderResults(
      $("#recent-results"), recent.slice(0, RECENT_SHOWN),
      "Nothing logged yet — browse by muscle group to find your first movement.",
    );
    // A first-time user has nothing to be shown, so start them where the
    // catalog is actually navigable rather than on an empty list.
    if (!recent.length) showTab("browse");
    // Browse may have rendered before these counts existed.
    if (byMuscle.size) renderBrowse({ keepPage: true });
  } catch (err) {
    toast(err.message, "error");
  }
}

/**
 * Fill the browse panel: equipment options for the chosen muscle, then its
 * movements in ranked order.
 *
 * The list is capped at `MAX_RESULTS` with the rest one click away. The cap used
 * to be a silent truncation of an alphabetical list, which put pushups (70th of
 * 147 for chest) out of reach of browsing altogether.
 *
 * @param {{keepPage?: boolean}} [options] - Keep an expanded list expanded;
 *   changing a filter collapses it back to the first page.
 */
function renderBrowse({ keepPage = false } = {}) {
  const muscle = $("#browse-muscle").value;
  const equipmentSelect = $("#browse-equipment");
  if (!keepPage) browseExpanded = false;

  const available = equipmentByMuscle.get(muscle) || [];
  const previous = equipmentSelect.value;
  equipmentSelect.textContent = "";
  equipmentSelect.append(new Option("Any", ""));
  available.forEach((item) => equipmentSelect.append(new Option(titleCase(item), item)));
  equipmentSelect.value = available.includes(previous) ? previous : "";

  const equipment = equipmentSelect.value;
  const matches = personalFirst(byMuscle.get(muscle) || [], muscle)
    .filter((e) => !equipment || e.equipment === equipment);
  const shown = browseExpanded ? matches : matches.slice(0, MAX_RESULTS);

  renderResults($("#browse-results"), shown, "No movements match that combination.");
  renderBrowseNote(shown.length, matches.length);
}

/** Say how much of the list is showing, and offer the rest. */
function renderBrowseNote(shownCount, totalCount) {
  const note = $("#browse-note");
  note.textContent = "";
  note.hidden = totalCount === 0;
  if (!totalCount) return;

  const label = document.createElement("span");
  label.textContent = shownCount < totalCount
    ? `Showing ${shownCount} of ${totalCount} — most common first.`
    : `All ${totalCount} — most common first.`;
  note.append(label);

  if (shownCount < totalCount) {
    const more = document.createElement("button");
    more.type = "button";
    more.className = "picker-more";
    more.textContent = `Show all ${totalCount}`;
    more.addEventListener("click", () => {
      browseExpanded = true;
      renderBrowse({ keepPage: true });
    });
    note.append(more);
  }
}

function onSearchInput(event) {
  const query = event.target.value.trim();
  if (!query) {
    $("#search-results").textContent = "";
    return;
  }
  renderResults($("#search-results"), search(query), `No movements match “${query}”.`);
}

// ---- Day panel and form ---------------------------------------------------

async function refreshDay() {
  const panel = $("#day-entries");
  const total = $("#entries-total");
  $("#entries-date").textContent = formatDate(selectedIso, {
    month: "short",
    day: "numeric",
  });

  try {
    const entries = await fetchEntriesForDate(selectedIso);
    // Warm-ups are already out of `set_count`, so this is the week's reading.
    const sets = entries.reduce((sum, entry) => sum + entry.set_count, 0);
    total.textContent = sets ? `${sets} ${sets === 1 ? "set" : "sets"}` : "";
    renderEntries(panel, entries, {
      emptyMessage: "Nothing logged for this day yet — add your first set.",
      onDelete: removeEntry,
    });
  } catch (err) {
    toast(err.message, "error");
  }
}

async function removeEntry(id) {
  try {
    await deleteEntry(id);
    toast("Entry deleted.");
    await refreshDay();
  } catch (err) {
    toast(err.message, "error");
  }
}

function showError(message) {
  const box = $("#form-error");
  box.textContent = message;
  box.hidden = !message;
}

/** Every page honours `?date=`, so navigating away keeps the day being edited. */
function retargetNav(iso) {
  retargetLinks(
    Array.from(document.querySelectorAll(".nav-link, .tab-link")), iso,
  );
}

function onDateChange(event) {
  selectedIso = event.target.value;
  if (!selectedIso) return;
  syncUrlDate(selectedIso);
  retargetNav(selectedIso);
  refreshDay();
}

async function onSubmit(event) {
  event.preventDefault();
  showError("");

  const form = event.currentTarget;
  const data = new FormData(form);
  const sets = grid.values();

  if (!data.get("date")) return showError("Pick a date first.");
  if (!data.get("exercise_id")) return showError("Choose an exercise.");
  if (!sets.length) return showError("Add at least one set.");

  try {
    const entry = await createEntry({
      date: data.get("date"),
      exercise_id: data.get("exercise_id"),
      sets,
    });
    toast(`Logged ${entry.set_count} × ${entry.exercise_name}.`);
    startRestTimer();
    await Promise.all([refreshDay(), loadRecent(), loadPreviousSets(entry.exercise_id)]);
  } catch (err) {
    showError(err.message);
  }
}

/**
 * Boot the log page.
 * @param {string} initialIso - Date pre-filled in the form (`YYYY-MM-DD`).
 */
export async function initLog(initialIso) {
  selectedIso = initialIso;
  $("#entry-date").addEventListener("change", onDateChange);
  $("#entry-form").addEventListener("submit", onSubmit);
  $("#exercise-search").addEventListener("input", onSearchInput);
  $("#browse-muscle").addEventListener("change", () => renderBrowse());
  $("#browse-equipment").addEventListener("change", () => renderBrowse());
  document.querySelectorAll("[data-tab]").forEach((tab) => {
    tab.addEventListener("click", () => showTab(tab.dataset.tab));
  });

  // The grid builds its own markup, including the header and the added-weight
  // toggle — see setgrid.js. Mounted before the catalog lands so the page has
  // its shape immediately.
  grid = createSetGrid($("#set-grid-mount"), { onError: showError });

  const unitSelect = $("#weight-unit");
  unitSelect.value = unit;
  unitSelect.addEventListener("change", () => {
    unit = unitSelect.value;
    saveUnit(unit);
    // Placeholders, aria-labels and the plate hint's bar re-read in the new
    // unit. Typed values are deliberately left alone: they are what the user
    // just entered, and silently converting them under the cursor is worse than
    // a mixed grid.
    grid.setUnit(unit);
  });

  // The timer is booted from base.html — it runs on every page now, so binding
  // it again here would double up its listeners.
  retargetNav(selectedIso);

  try {
    catalog = await fetchExercises();
    catalog.forEach((exercise) => {
      exercise._haystack = haystack(exercise);
    });
    byId = new Map(catalog.map((exercise) => [exercise.id, exercise]));
    buildIndexes();
    renderBrowse();
  } catch (err) {
    toast(err.message, "error");
  }

  await Promise.all([refreshDay(), loadRecent()]);
}
