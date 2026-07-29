/**
 * Weekly summary page — paints the body map and the per-muscle breakdown.
 *
 * A muscle group turns red (`.is-worked`) as soon as the week contains at
 * least one set of an exercise that targets it, which is exactly what the
 * server reports in `summary.muscles[<group>].worked`.
 */

import { fetchWeeklySummary } from "./api.js";
import { $, addDays, formatDate, renderEntries, retargetLinks, syncUrlDate, toast } from "./ui.js";

let anchorIso; // Any date inside the week being displayed.

/** Colour every SVG region belonging to a worked muscle group. */
function paintBody(muscles) {
  document.querySelectorAll(".muscle").forEach((region) => {
    const info = muscles[region.dataset.muscle];
    const worked = Boolean(info && info.worked);
    region.classList.toggle("is-worked", worked);

    const label = info ? info.label : region.dataset.muscle;
    const title = region.querySelector("title");
    if (title) {
      title.textContent = worked
        ? `${label}: ${info.sets} sets (${info.exercises.join(", ")})`
        : `${label}: no sets this week`;
    }
  });
}

/** Fill the "sets by muscle group" list, scaled against the busiest group. */
function renderBreakdown(muscles) {
  const counts = Object.values(muscles).map((m) => m.sets);
  const max = Math.max(1, ...counts);

  document.querySelectorAll(".muscle-row").forEach((row) => {
    const info = muscles[row.dataset.muscle];
    if (!info) return;
    row.classList.toggle("is-worked", info.worked);
    row.querySelector(".muscle-bar-fill").style.width = `${(info.sets / max) * 100}%`;
    row.querySelector(".muscle-sets").textContent =
      `${info.sets} ${info.sets === 1 ? "set" : "sets"}`;
  });
}

function renderHeader(summary) {
  const start = formatDate(summary.week_start, { month: "short", day: "numeric" });
  const end = formatDate(summary.week_end, { month: "short", day: "numeric", year: "numeric" });
  $("#week-label").textContent = `${start} – ${end}`;

  const worked = summary.muscles_worked.length;
  const total = Object.keys(summary.muscles).length;
  $("#week-meta").textContent =
    `${summary.total_sets} sets · ${worked} of ${total} muscle groups trained`;
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
