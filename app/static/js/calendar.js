/**
 * Calendar page — month grid of logged workouts.
 *
 * Renders whole weeks (Monday-first) for the visible month, dots any day with
 * at least one logged set, and shows that day's entries in the side panel.
 */

import { fetchEntriesForDate, fetchMonth } from "./api.js";
import {
  $, addDays, formatDate, fromIso, renderEntries, retargetLinks, syncUrlDate, toIso, toast, todayIso,
} from "./ui.js";

/** Days of the visible month keyed by ISO date -> total sets. */
let monthTotals = {};
let selectedIso;
let cursor; // Date positioned on the 1st of the visible month.

/**
 * Sets that fill a day cell's bar to full height.
 *
 * A **fixed** reference rather than the month's own busiest day: scaling to the
 * maximum in view would redraw the same week at a different height depending on
 * what else happened that month, so two months could not be compared. Days past
 * it clamp, which costs nothing — the reading is "how big was this session",
 * and everything above a very hard one reads the same anyway.
 */
const FULL_DAY_SETS = 24;

/** Build the weeks (Monday-first) covering the month containing `date`. */
function monthGrid(date) {
  const first = new Date(date.getFullYear(), date.getMonth(), 1);
  const start = new Date(first);
  start.setDate(first.getDate() - ((first.getDay() + 6) % 7)); // back to Monday

  const last = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  const end = new Date(last);
  end.setDate(last.getDate() + (7 - ((last.getDay() + 6) % 7) - 1)); // fwd to Sunday

  const days = [];
  for (const day = new Date(start); day <= end; day.setDate(day.getDate() + 1)) {
    days.push(new Date(day));
  }
  return days;
}

function renderMonthLabel() {
  $("#calendar-heading").textContent = cursor.toLocaleDateString(undefined, {
    month: "long",
    year: "numeric",
  });
}

function renderGrid() {
  const container = $("#calendar-days");
  container.textContent = "";
  const today = todayIso();

  for (const day of monthGrid(cursor)) {
    const iso = toIso(day);
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "day-cell";
    cell.dataset.date = iso;
    cell.setAttribute("role", "gridcell");

    if (day.getMonth() !== cursor.getMonth()) cell.classList.add("is-outside");
    if (iso === today) cell.classList.add("is-today");
    if (iso === selectedIso) {
      cell.classList.add("is-selected");
      cell.setAttribute("aria-current", "date");
    }

    const total = monthTotals[iso] || 0;
    if (total > 0) cell.classList.add("has-entries");

    const number = document.createElement("span");
    number.className = "day-num";
    number.textContent = String(day.getDate());

    const bar = document.createElement("span");
    bar.className = "day-bar";
    bar.style.setProperty("--volume", Math.min(1, total / FULL_DAY_SETS));

    cell.append(bar, number);
    cell.setAttribute(
      "aria-label",
      `${formatDate(iso)}${total ? `, ${total} sets logged` : ", nothing logged"}`
    );
    cell.addEventListener("click", () => selectDay(iso));
    container.append(cell);
  }
}

async function loadMonth() {
  try {
    monthTotals = await fetchMonth(cursor.getFullYear(), cursor.getMonth() + 1);
  } catch (err) {
    monthTotals = {};
    toast(err.message, "error");
  }
  renderMonthLabel();
  renderGrid();
}

async function loadDay() {
  const heading = $("#day-heading");
  const panel = $("#day-entries");
  const total = $("#day-total");
  heading.textContent = formatDate(selectedIso);
  total.textContent = "";

  try {
    const entries = await fetchEntriesForDate(selectedIso);
    // Warm-ups are already out of `set_count`, so this matches the bar above.
    const sets = entries.reduce((sum, entry) => sum + entry.set_count, 0);
    total.textContent = sets ? `${sets} ${sets === 1 ? "set" : "sets"}` : "";
    renderEntries(panel, entries, {
      emptyMessage: "No workouts logged on this day yet.",
    });
  } catch (err) {
    panel.textContent = "";
    toast(err.message, "error");
  }
}

async function selectDay(iso) {
  selectedIso = iso;
  syncUrlDate(iso);
  retargetLinks([$("#log-for-day"), $("#week-for-day")], iso);

  const cursorChanged =
    fromIso(iso).getMonth() !== cursor.getMonth() ||
    fromIso(iso).getFullYear() !== cursor.getFullYear();
  if (cursorChanged) {
    cursor = new Date(fromIso(iso).getFullYear(), fromIso(iso).getMonth(), 1);
    await loadMonth();
  } else {
    renderGrid();
  }
  await loadDay();
}

function shiftMonth(delta) {
  cursor = new Date(cursor.getFullYear(), cursor.getMonth() + delta, 1);
  loadMonth();
}

/**
 * Boot the calendar page.
 * @param {string} initialIso - Date selected on first render (`YYYY-MM-DD`).
 */
export async function initCalendar(initialIso) {
  selectedIso = initialIso;
  cursor = new Date(fromIso(initialIso).getFullYear(), fromIso(initialIso).getMonth(), 1);

  $("#prev-month").addEventListener("click", () => shiftMonth(-1));
  $("#next-month").addEventListener("click", () => shiftMonth(1));
  $("#today-btn").addEventListener("click", () => selectDay(todayIso()));

  document.addEventListener("keydown", (event) => {
    if (event.target.matches("input, textarea")) return;
    if (event.key === "ArrowLeft") selectDay(addDays(selectedIso, -1));
    if (event.key === "ArrowRight") selectDay(addDays(selectedIso, 1));
  });

  retargetLinks([$("#log-for-day"), $("#week-for-day")], selectedIso);
  await loadMonth();
  await loadDay();
}
