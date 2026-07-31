/**
 * Weekly summary page — paints the body map and the per-muscle breakdown.
 *
 * Colour is a volume scale, not a yes/no: light green at one set deepening to
 * dark green at the group's weekly target, then light-to-dark red once the
 * target is passed. The server does the grading — each group arrives with a
 * `state` (`rest` | `trained` | `over`) and an `intensity` from 0 to 1 within
 * that state's ramp. All this module does is hand those to CSS.
 *
 * Set counts arrive fractional: a movement's primary muscles take the whole
 * set and its secondary muscles half, so `12.5 / 20` is a normal reading.
 *
 * The "inside the muscle" panel is the exception to all of the above: regions
 * are a *distribution*, never a grade. They take no target, no `--level` and
 * none of the ramp's colours — see `renderRegions` and docs/VOLUME_SCIENCE.md.
 */

import { fetchWeeklySummary } from "./api.js";
import {
  $, addDays, formatDate, formatSets, loadProfile, renderEntries, retargetLinks,
  saveProfile, syncUrlDate, toast,
} from "./ui.js";
import { initWeekStrip, setWeekStripDate } from "./weekstrip.js";

let anchorIso; // Any date inside the week being displayed.

/** `{scheme: [{key, label, muscles}, ...]}`, defined once in app/exercises.py. */
let schemeBuckets = {};

/** The chosen grouping. A view over the same rows — never a filter. */
let activeScheme;

/** The last week's per-muscle payload, so re-heading the list costs no request. */
let lastMuscles = null;

/**
 * Where the chosen split is remembered.
 *
 * Not in the URL: `?date=` is shared state that every page honours, while this
 * is a reading preference that should follow the reader rather than the link.
 */
const SCHEME_KEY = "bodyshop:summary-scheme";

/**
 * Apply a group's grade to one element: `--level` drives the colour mix, and
 * the classes pick which ramp CSS mixes along.
 */
function applyGrade(element, info) {
  element.style.setProperty("--level", info ? info.intensity : 0);
  element.classList.toggle("is-worked", Boolean(info && info.worked));
  element.classList.toggle("is-over", Boolean(info && info.state === "over"));
}

/** Describe a group's weekly volume for the region's tooltip. */
function describe(info, fallbackLabel) {
  if (!info) return fallbackLabel;
  if (!info.worked) return `${info.label}: no sets this week (target ${info.target})`;

  const sets = `${formatSets(info.sets)} of ${info.target} sets`;
  const detail = info.exercises.join(", ");
  return info.state === "over"
    ? `${info.label}: ${sets} — ${formatSets(info.over)} over target (${detail})`
    : `${info.label}: ${sets} (${detail})`;
}

/** Shade every SVG region according to its group's weekly volume. */
function paintBody(muscles) {
  document.querySelectorAll(".muscle").forEach((region) => {
    const info = muscles[region.dataset.muscle];
    applyGrade(region, info);

    const title = region.querySelector("title");
    if (title) title.textContent = describe(info, region.dataset.muscle);
  });

  // Arms the staggered head-to-toe sweep in CSS. Set after the grades so the
  // delays apply to this transition rather than to the page's first paint,
  // which would hold an already-grey map grey for another half second.
  document.querySelectorAll(".body-muscles").forEach((group) => {
    group.classList.add("is-graded");
  });
}

/** Fill the breakdown list, each bar scaled against its target. */
function renderBreakdown(muscles) {
  document.querySelectorAll(".muscle-row").forEach((row) => {
    const info = muscles[row.dataset.muscle];
    if (!info) return;
    applyGrade(row, info);

    // The bar tops out at the target; overshoot shows as colour, not length.
    const progress = Math.min(1, info.sets / info.target);
    row.querySelector(".muscle-bar-fill").style.width = `${progress * 100}%`;
    row.querySelector(".muscle-sets").textContent =
      `${formatSets(info.sets)} / ${info.target}`;
    row.title = describe(info, row.dataset.muscle);
  });

  renderBucketTotals(muscles);
}

/**
 * Total each visible bucket.
 *
 * Sets only — no bucket target. Summing twelve targets into a "push target"
 * would put a number on screen that nobody has studied, which is the same
 * reason regions are not graded (docs/VOLUME_SCIENCE.md).
 */
function renderBucketTotals(muscles) {
  (schemeBuckets[activeScheme] || []).forEach((bucket) => {
    const heading = document.querySelector(
      `.muscle-bucket[data-scheme="${activeScheme}"][data-bucket="${bucket.key}"]`,
    );
    if (!heading) return;

    const sets = bucket.muscles.reduce(
      (total, muscle) => total + (muscles[muscle] ? muscles[muscle].sets : 0), 0,
    );
    heading.querySelector(".muscle-bucket-sets").textContent =
      sets ? `${formatSets(sets)} sets` : "nothing logged";
  });
}

/**
 * Re-head the breakdown into `key`.
 *
 * Nodes are *moved* rather than given a CSS `order`, so the reading order a
 * screen reader follows matches the order on screen. Every scheme files all
 * twelve rows, so nothing can be hidden by switching view — only regrouped.
 */
function applyScheme(key) {
  const buckets = schemeBuckets[key];
  if (!buckets) return;
  activeScheme = key;

  const list = $("#muscle-list");
  const rows = new Map(
    Array.from(list.querySelectorAll(".muscle-row")).map((row) => [row.dataset.muscle, row]),
  );

  document.querySelectorAll(".muscle-bucket").forEach((heading) => {
    heading.hidden = heading.dataset.scheme !== key;
  });

  buckets.forEach((bucket) => {
    const heading = list.querySelector(
      `.muscle-bucket[data-scheme="${key}"][data-bucket="${bucket.key}"]`,
    );
    if (heading) list.append(heading);
    bucket.muscles.forEach((muscle) => {
      const row = rows.get(muscle);
      if (row) list.append(row);
    });
  });

  // Park the other schemes' headings at the end. They are hidden either way,
  // but leaving them in front would make one of them `:first-child` and give
  // the first visible heading a rule above it.
  list.querySelectorAll(".muscle-bucket[hidden]").forEach((h) => list.append(h));

  const select = $("#scheme-select");
  select.value = key;
  $("#scheme-note").textContent = select.selectedOptions[0]?.dataset.note || "";

  try {
    localStorage.setItem(SCHEME_KEY, key);
  } catch {
    // Private browsing, or storage disabled. The choice just won't persist.
  }
}

function onSchemeChange(event) {
  applyScheme(event.target.value);
  // The week already loaded; the new headings just need totalling. No refetch —
  // switching view is not new data.
  if (lastMuscles) renderBucketTotals(lastMuscles);
}

/**
 * Fill the "inside the muscle" panel: where each subdivided group's work landed.
 *
 * Regions are **not** graded. They get no target, no `--level` and none of the
 * volume ramp's colours, because no evidence establishes how many sets a muscle
 * head needs (docs/VOLUME_SCIENCE.md). The bar length is the region's share of
 * the volume the server could place inside the group, and the only judgement
 * shown is `neglected`, which the server decides.
 */
/**
 * Say which sets the bars below are a share *of*, and why it can be fewer than
 * the group's total.
 *
 * Always the same shape — "based on …" — because the two cases differ only in
 * whether every set could be placed, and phrasing them differently made them
 * look like unrelated readings.
 */
function setBasis(element, info) {
  const total = formatSets(info.sets);
  const placed = formatSets(info.region_sets);
  const missed = formatSets(info.sets - info.region_sets);

  if (!info.worked) {
    element.textContent = "not trained this week";
    element.title = "";
  } else if (!info.region_sets) {
    element.textContent = "no split to show";
    element.title =
      `All ${total} sets came from movements that do not favour one region of `
      + "this group, so there is nothing to divide up.";
  } else if (info.region_sets < info.sets) {
    element.textContent = `based on ${placed} of ${total} sets`;
    element.title =
      `${missed} of this group's ${total} sets came from movements that do not `
      + "favour one region — a deadlift trains the back without telling you "
      + "lats or mid back — so they count for the group but not for a bar here.";
  } else {
    element.textContent = `based on all ${total} sets`;
    element.title = `Every one of this group's ${total} sets favoured a region.`;
  }
}

function renderRegions(muscles) {
  document.querySelectorAll(".region-group").forEach((group) => {
    const info = muscles[group.dataset.muscle];
    if (!info) return;

    setBasis(group.querySelector('[data-role="basis"]'), info);

    const byRegion = new Map(info.regions.map((r) => [r.region, r]));
    group.querySelectorAll(".region-bar").forEach((bar) => {
      const region = byRegion.get(bar.dataset.region);
      if (!region) return;

      bar.querySelector(".region-bar-fill").style.width = `${region.share * 100}%`;
      bar.querySelector(".region-bar-value").textContent =
        info.region_sets ? `${Math.round(region.share * 100)}%` : "—";
      bar.classList.toggle("is-neglected", region.neglected);
      bar.title = region.neglected
        ? `${region.label}: ${formatSets(region.sets)} sets — thin next to the rest of this group`
        : `${region.label}: ${formatSets(region.sets)} sets`;
    });
  });
}

/**
 * One readout cell: a figure over the thing it counts.
 *
 * `over` marks the only cell allowed the ramp's colour — it reports the same
 * fact the map is already showing in red, so tinting it agrees with the map
 * rather than inventing a second scale.
 */
function readoutCell(value, label, { over = false } = {}) {
  const cell = document.createElement("div");
  cell.className = `readout-cell${over ? " is-over" : ""}`;

  const figure = document.createElement("dd");
  figure.className = "readout-value";
  figure.textContent = value;

  const name = document.createElement("dt");
  name.className = "readout-label type-label";
  name.textContent = label;

  // <dt> before <dd> in the DOM, so the pair reads correctly; CSS puts the
  // figure on top.
  cell.append(name, figure);
  return cell;
}

function renderHeader(summary) {
  const start = formatDate(summary.week_start, { month: "short", day: "numeric" });
  const end = formatDate(summary.week_end, { month: "short", day: "numeric", year: "numeric" });
  $("#week-label").textContent = `${start} – ${end}`;

  const worked = summary.muscles_worked.length;
  const total = Object.keys(summary.muscles).length;
  const thin = summary.regions_neglected.length;

  const meta = $("#week-meta");
  meta.textContent = "";
  meta.append(
    readoutCell(summary.total_sets, "Sets"),
    readoutCell(`${worked}/${total}`, "Trained"),
    readoutCell(summary.muscles_at_target.length, "At target"),
    summary.muscles_over.length
      ? readoutCell(summary.muscles_over.length, "Over", { over: true })
      : readoutCell(thin, thin === 1 ? "Region thin" : "Regions thin"),
  );
}

// ---- Trainer setup (Phase 6) ----------------------------------------------

/**
 * Read the three controls into the shape `ui.js` stores and `api.js` sends.
 *
 * Deliberately unvalidated beyond `Number`: `resolve_profile` on the server
 * clamps to the same bounds the inputs carry, and duplicating that here would
 * be a second implementation of one rule.
 */
function readSetup() {
  return {
    experience: $("#experience-select").value,
    sessions_per_week: Number($("#sessions-input").value),
    minutes_per_session: Number($("#minutes-input").value),
  };
}

/** Put a stored setup back into the controls on first paint. */
function fillSetup(profile) {
  $("#experience-select").value = profile.experience;
  $("#sessions-input").value = profile.sessions_per_week;
  $("#minutes-input").value = profile.minutes_per_session;
  renderBlurb();
}

function renderBlurb() {
  const option = $("#experience-select").selectedOptions[0];
  $("#experience-blurb").textContent = (option && option.dataset.blurb) || " ";
}

/**
 * Say what the setup resolved to, in words.
 *
 * **One number per size of group, never a range** — printing "aim for 10–20"
 * would invite reading the top of it as the goal, which is the product-voice
 * rule in docs/VOLUME_SCIENCE.md §4. And the two figures come from the server's
 * own `targets`, not from re-applying the multiplier here, so the sentence
 * cannot disagree with the bars underneath it.
 */
function renderSetupEffect(profile) {
  const large = profile.targets.chest;
  const small = profile.targets.abs;

  $("#setup-summary").textContent =
    `${profile.sessions_per_week} × ${profile.minutes_per_session} min`;

  const reason = profile.limited_by === "plan"
    ? "Your week is what is setting these — more time, or another session, "
      + "raises them until they reach what your experience asks for."
    : "Your experience level is what is setting these; the time you have "
      + "covers them.";

  $("#setup-effect").textContent =
    `Large groups are covered at ${large} sets a week, small ones at ${small}. `
    + reason;
}

async function onSetupChange() {
  saveProfile(readSetup());
  renderBlurb();
  // Targets are graded server-side, so a new setup is a new request rather than
  // a re-render: the states, the ramp positions and the readouts all move with
  // it, and recomputing any of them here would be a second grader.
  await load();
}

async function load() {
  try {
    const summary = await fetchWeeklySummary(anchorIso);
    lastMuscles = summary.muscles;
    // Echoed back by the server, so the controls settle on what was actually
    // used — a value clamped out of range corrects itself on screen instead of
    // sitting there disagreeing with the bars it produced.
    if (summary.profile) {
      fillSetup(summary.profile);
      renderSetupEffect(summary.profile);
    }
    renderHeader(summary);
    paintBody(summary.muscles);
    renderBreakdown(summary.muscles);
    renderRegions(summary.muscles);
    renderEntries($("#week-entries"), summary.entries, {
      showDate: true,
      emptyMessage: "No workouts logged this week yet.",
    });
  } catch (err) {
    toast(err.message, "error");
  }
}

/**
 * Move the page to `iso` — the one place the anchor date changes.
 *
 * Stepping a week and clicking a day in the calendar strip are the same act,
 * so they go through here: `?date=` is shared state every page honours, and the
 * strip has to re-anchor with the summary or the two disagree about which week
 * is on screen.
 */
async function goToDate(iso) {
  anchorIso = iso;
  syncUrlDate(anchorIso);
  retargetLinks(
    Array.from(document.querySelectorAll(".nav-link, .tab-link, .shelf")), anchorIso,
  );
  await Promise.all([load(), setWeekStripDate(anchorIso)]);
}

function shiftWeek(days) {
  goToDate(addDays(anchorIso, days));
}

/** The stored split, if it is still one the server offers. */
function storedScheme() {
  try {
    const stored = localStorage.getItem(SCHEME_KEY);
    return stored && schemeBuckets[stored] ? stored : null;
  } catch {
    return null;
  }
}

/**
 * Boot the summary page.
 * @param {string} initialIso - Any date inside the week to show.
 * @param {Object} buckets - Grouping schemes from `app/exercises.py`, keyed by
 *   scheme: `{push_pull_legs: [{key, label, muscles}, ...], ...}`.
 */
export async function initSummary(initialIso, buckets = {}) {
  anchorIso = initialIso;
  schemeBuckets = buckets;
  $("#prev-week").addEventListener("click", () => shiftWeek(-7));
  $("#next-week").addEventListener("click", () => shiftWeek(7));
  $("#scheme-select").addEventListener("change", onSchemeChange);

  // Fill the setup controls *before* the first fetch, so the request carries
  // the stored profile rather than the markup's defaults and the page never
  // paints one set of targets and then replaces it with another.
  fillSetup(loadProfile());
  ["#experience-select", "#sessions-input", "#minutes-input"].forEach((selector) => {
    $(selector).addEventListener("change", onSetupChange);
  });

  applyScheme(storedScheme() || $("#scheme-select").value);
  await load();
  // After the week, not before: the strip is a supporting reading and the body
  // map is what the page is for, so it does not delay the thing being read.
  await initWeekStrip(anchorIso, goToDate);
}
