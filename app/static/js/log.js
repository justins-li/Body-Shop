/**
 * Log page — pick a movement from the catalog, record sets, review the day.
 *
 * The catalog is 873 movements, so the picker is the page. It fetches
 * `/api/exercises` once (the light shape: no instructions, no images) and
 * filters it locally through three access paths, which serve different moments:
 *
 *   Recent — the default, and the 90% path. Most people cycle through 10–20
 *            movements, so history beats search almost every time.
 *   Search — substring match over name, equipment, muscles and category.
 *   Browse — muscle group then equipment, for finding something new.
 *
 * Only the *selected* exercise costs a second request, for its instructions and
 * the two photographs the card animates between.
 */

import {
  createEntry, deleteEntry, fetchEntriesForDate, fetchExerciseDetail,
  fetchExercises, fetchRecentExercises,
} from "./api.js";
import {
  $, formatDate, renderEntries, retargetLinks, syncUrlDate, toast,
} from "./ui.js";

let selectedIso;
let catalog = [];
let byId = new Map();
let selectedId = null;

/** Most results anyone scans before retyping; keeps the DOM small. */
const MAX_RESULTS = 40;

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

// ---- Searching ------------------------------------------------------------

/**
 * Rank the catalog against `query`.
 *
 * Every whitespace-separated token must match, so tokens narrow rather than
 * widen. Name matches outrank matches on equipment or muscle, and a name that
 * *starts* with the query outranks one that merely contains it.
 */
function search(query) {
  const tokens = query.toLowerCase().split(/\s+/).filter(Boolean)
    .map((token) => ALIASES[token] || token);
  if (!tokens.length) return [];

  const scored = [];
  for (const exercise of catalog) {
    if (!tokens.every((token) => exercise._haystack.includes(token))) continue;

    const name = exercise.name.toLowerCase();
    const phrase = tokens.join(" ");
    const score = name.startsWith(phrase) ? 0 : name.includes(phrase) ? 1 : 2;
    scored.push({ exercise, score });
  }

  scored.sort((a, b) => a.score - b.score || a.exercise.name.localeCompare(b.exercise.name));
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

  try {
    renderChosen(await fetchExerciseDetail(id));
  } catch (err) {
    // The pick still stands; only its illustration failed.
    const exercise = byId.get(id);
    if (exercise) renderChosen({ ...exercise, images: [], instructions: [] });
    toast(err.message, "error");
  }
}

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
    const recent = await fetchRecentExercises();
    renderResults(
      $("#recent-results"), recent,
      "Nothing logged yet — search or browse to find your first movement.",
    );
  } catch (err) {
    toast(err.message, "error");
  }
}

/** Fill the equipment dropdown from whatever the chosen muscle actually has. */
function renderBrowse() {
  const muscle = $("#browse-muscle").value;
  const equipmentSelect = $("#browse-equipment");
  const forMuscle = catalog.filter((e) => e.muscles.includes(muscle));

  const available = [...new Set(forMuscle.map((e) => e.equipment))].sort();
  const previous = equipmentSelect.value;
  equipmentSelect.textContent = "";
  equipmentSelect.append(new Option("Any", ""));
  available.forEach((item) => equipmentSelect.append(new Option(titleCase(item), item)));
  equipmentSelect.value = available.includes(previous) ? previous : "";

  const equipment = equipmentSelect.value;
  const matches = forMuscle
    .filter((e) => !equipment || e.equipment === equipment)
    // Primary first: the movements that actually train the chosen group.
    .sort((a, b) =>
      Number(b.primary.includes(muscle)) - Number(a.primary.includes(muscle))
      || a.name.localeCompare(b.name))
    .slice(0, MAX_RESULTS);

  renderResults($("#browse-results"), matches, "No movements match that combination.");
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
  $("#entries-date").textContent = formatDate(selectedIso, {
    month: "short",
    day: "numeric",
  });

  try {
    const entries = await fetchEntriesForDate(selectedIso);
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

function onDateChange(event) {
  selectedIso = event.target.value;
  if (!selectedIso) return;
  syncUrlDate(selectedIso);
  retargetLinks([$("#view-summary")], selectedIso);
  refreshDay();
}

async function onSubmit(event) {
  event.preventDefault();
  showError("");

  const form = event.currentTarget;
  const data = new FormData(form);
  const sets = Number(data.get("sets"));

  if (!data.get("date")) return showError("Pick a date first.");
  if (!data.get("exercise_id")) return showError("Choose an exercise.");
  if (!Number.isInteger(sets) || sets < 1) return showError("Sets must be a whole number of 1 or more.");

  try {
    const entry = await createEntry({
      date: data.get("date"),
      exercise_id: data.get("exercise_id"),
      sets,
    });
    toast(`Logged ${entry.sets} × ${entry.exercise_name}.`);
    await Promise.all([refreshDay(), loadRecent()]);
  } catch (err) {
    showError(err.message);
  }
}

/** Wire the +/− buttons around the sets input. */
function initStepper() {
  const input = $("#entry-sets");
  document.querySelectorAll("[data-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = Number(input.value || 0) + Number(button.dataset.step);
      input.value = String(Math.min(100, Math.max(1, next)));
    });
  });
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
  $("#browse-muscle").addEventListener("change", renderBrowse);
  $("#browse-equipment").addEventListener("change", renderBrowse);
  document.querySelectorAll("[data-tab]").forEach((tab) => {
    tab.addEventListener("click", () => showTab(tab.dataset.tab));
  });
  initStepper();
  retargetLinks([$("#view-summary")], selectedIso);

  try {
    catalog = await fetchExercises();
    catalog.forEach((exercise) => {
      exercise._haystack = haystack(exercise);
    });
    byId = new Map(catalog.map((exercise) => [exercise.id, exercise]));
    renderBrowse();
  } catch (err) {
    toast(err.message, "error");
  }

  await Promise.all([refreshDay(), loadRecent()]);
}
