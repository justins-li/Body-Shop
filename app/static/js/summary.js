/**
 * Weekly summary page — paints the body map and the per-muscle breakdown.
 *
 * Colour is a volume scale, not a yes/no: light green at one set deepening to
 * dark green at the group's weekly target, then light-to-dark red once the
 * target is passed. The server does the grading — each group arrives with a
 * `state` (`rest` | `trained` | `over`) and an `intensity` from 0 to 1 within
 * that state's ramp. All this module does is hand those to CSS.
 */

import { fetchWeeklySummary } from "./api.js";
import { $, addDays, formatDate, renderEntries, retargetLinks, syncUrlDate, toast } from "./ui.js";

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

  const sets = `${info.sets} of ${info.target} sets`;
  const detail = info.exercises.join(", ");
  return info.state === "over"
    ? `${info.label}: ${sets} — ${info.over} over target (${detail})`
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
    row.querySelector(".muscle-sets").textContent = `${info.sets} / ${info.target}`;
    row.title = describe(info, row.dataset.muscle);
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
  $("#week-meta").textContent = parts.join(" · ");
}

async function load() {
  try {
    const summary = await fetchWeeklySummary(anchorIso);
    renderHeader(summary);
    paintBody(summary.muscles);
    renderBreakdown(summary.muscles);
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
