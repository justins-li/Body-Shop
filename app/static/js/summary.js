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

/** Fill the "sets by muscle group" list, each bar scaled against its target. */
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

/**
 * Boot the summary page.
 * @param {string} initialIso - Any date inside the week to show.
 */
export async function initSummary(initialIso) {
  anchorIso = initialIso;
  $("#prev-week").addEventListener("click", () => shiftWeek(-7));
  $("#next-week").addEventListener("click", () => shiftWeek(7));
  await load();
}
