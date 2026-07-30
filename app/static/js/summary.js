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
  $, addDays, formatDate, formatSets, renderEntries, retargetLinks, syncUrlDate, toast,
} from "./ui.js";

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
function renderRegions(muscles) {
  document.querySelectorAll(".region-group").forEach((group) => {
    const info = muscles[group.dataset.muscle];
    if (!info) return;

    const attributed = group.querySelector('[data-role="attributed"]');
    if (!info.worked) {
      attributed.textContent = "not trained";
    } else if (!info.region_sets) {
      // Trained, but by movements with no defensible emphasis inside the group.
      attributed.textContent = "no placed sets";
    } else if (info.region_sets < info.sets) {
      attributed.textContent =
        `${formatSets(info.region_sets)} of ${formatSets(info.sets)} sets placed`;
    } else {
      attributed.textContent = `${formatSets(info.sets)} sets`;
    }

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

function renderHeader(summary) {
  const start = formatDate(summary.week_start, { month: "short", day: "numeric" });
  const end = formatDate(summary.week_end, { month: "short", day: "numeric", year: "numeric" });
  $("#week-label").textContent = `${start} – ${end}`;

  const worked = summary.muscles_worked.length;
  const total = Object.keys(summary.muscles).length;
  const parts = [
    `${summary.total_sets} sets`,
    `${worked} of ${total} muscle groups trained`,
    `${summary.muscles_at_target.length} at target`,
  ];
  if (summary.muscles_over.length) {
    parts.push(`${summary.muscles_over.length} over`);
  }
  if (summary.regions_neglected.length) {
    const count = summary.regions_neglected.length;
    parts.push(`${count} region${count === 1 ? "" : "s"} left thin`);
  }
  $("#week-meta").textContent = parts.join(" · ");
}

async function load() {
  try {
    const summary = await fetchWeeklySummary(anchorIso);
    lastMuscles = summary.muscles;
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

function shiftWeek(days) {
  anchorIso = addDays(anchorIso, days);
  syncUrlDate(anchorIso);
  retargetLinks(Array.from(document.querySelectorAll(".nav-link")), anchorIso);
  load();
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
  applyScheme(storedScheme() || $("#scheme-select").value);
  await load();
}
