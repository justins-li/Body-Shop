/**
 * The calendar, folded into the weekly summary.
 *
 * Phase 8.3. `/calendar` was a whole chapter for a month grid, and it answered
 * "what did I do that day" — which the summary's own entry list already answers
 * for the week you are reading. What was worth keeping is the *shape of a
 * month*: which days you trained, and how hard, at a glance.
 *
 * So it collapses. The strip shows **this week's seven boxes** by default,
 * costing one row above the body map, and expands to the surrounding month on
 * request. Both states are the same cell, the same volume bar and the same
 * fixed reference — expanding changes how many are drawn, never what one means.
 *
 * Clicking a day moves the whole page to that date, because `?date=` is shared
 * state every page honours: the week being summarised, the week the graph
 * colours against, and the day `/log` opens on are all one choice.
 */

import { fetchMonth } from "./api.js";
import {
  $, addDays, formatDate, fromIso, toIso, toast, todayIso,
} from "./ui.js";

/**
 * Sets that fill a day cell's bar to full height.
 *
 * A **fixed** reference rather than the range's own busiest day: scaling to the
 * maximum in view would redraw the same week at a different height depending on
 * what else was in the month, so the week strip and the expanded month could
 * not be compared — and they are the same cells. Days past it clamp, which
 * costs nothing: the reading is "how big was this session", and everything
 * above a very hard one reads the same anyway.
 */
const FULL_DAY_SETS = 24;

/** Where the expanded/collapsed choice is remembered. A reading preference. */
const EXPANDED_KEY = "bodyshop:calendar-expanded";

let anchorIso;
let expanded = false;
let onPick = () => {};

/** ISO date → total sets, for whatever range is currently drawn. */
let totals = {};

function storedExpanded() {
  try {
    return localStorage.getItem(EXPANDED_KEY) === "1";
  } catch {
    return false;
  }
}

function rememberExpanded() {
  try {
    localStorage.setItem(EXPANDED_KEY, expanded ? "1" : "0");
  } catch {
    // Private browsing; the choice holds for this page view.
  }
}

/** The seven days of the week containing `iso`, Monday first. */
function weekDays(iso) {
  const date = fromIso(iso);
  const monday = addDays(iso, -((date.getDay() + 6) % 7));
  return Array.from({ length: 7 }, (_, offset) => addDays(monday, offset));
}

/** Whole weeks (Monday-first) covering the month containing `iso`. */
function monthDays(iso) {
  const date = fromIso(iso);
  const first = new Date(date.getFullYear(), date.getMonth(), 1);
  const start = addDays(toIso(first), -((first.getDay() + 6) % 7));
  const last = new Date(date.getFullYear(), date.getMonth() + 1, 0);
  const end = addDays(toIso(last), 7 - ((last.getDay() + 6) % 7) - 1);

  const days = [];
  for (let day = start; day <= end; day = addDays(day, 1)) days.push(day);
  return days;
}

function dayCell(iso, { outside = false } = {}) {
  const cell = document.createElement("button");
  cell.type = "button";
  cell.className = "day-cell";
  cell.dataset.date = iso;
  cell.setAttribute("role", "gridcell");

  if (outside) cell.classList.add("is-outside");
  if (iso === todayIso()) cell.classList.add("is-today");
  if (iso === anchorIso) {
    cell.classList.add("is-selected");
    cell.setAttribute("aria-current", "date");
  }

  const total = totals[iso] || 0;
  if (total > 0) cell.classList.add("has-entries");

  const bar = document.createElement("span");
  bar.className = "day-bar";
  bar.style.setProperty("--volume", Math.min(1, total / FULL_DAY_SETS));

  const number = document.createElement("span");
  number.className = "day-num";
  number.textContent = String(fromIso(iso).getDate());

  cell.append(bar, number);
  cell.setAttribute(
    "aria-label",
    `${formatDate(iso)}${total ? `, ${total} sets logged` : ", nothing logged"}`,
  );
  cell.addEventListener("click", () => onPick(iso));
  return cell;
}

function render() {
  const grid = $("#calendar-grid");
  const heading = $("#calendar-heading");
  const toggle = $("#calendar-toggle");
  const month = fromIso(anchorIso).getMonth();

  grid.textContent = "";
  grid.classList.toggle("is-month", expanded);

  const days = expanded ? monthDays(anchorIso) : weekDays(anchorIso);
  days.forEach((iso) => {
    grid.append(dayCell(iso, { outside: expanded && fromIso(iso).getMonth() !== month }));
  });

  heading.textContent = expanded
    ? fromIso(anchorIso).toLocaleDateString(undefined, { month: "long", year: "numeric" })
    : "This week";
  toggle.textContent = expanded ? "Show the week" : "Show the month";
  toggle.setAttribute("aria-expanded", String(expanded));
}

/**
 * Fetch whatever the current view needs.
 *
 * Always the whole month, even when only a week is drawn: it is one request
 * either way, and it means expanding is instant rather than a second wait for
 * data the server already had in hand.
 */
async function load() {
  const date = fromIso(anchorIso);
  try {
    totals = await fetchMonth(date.getFullYear(), date.getMonth() + 1);
  } catch (err) {
    totals = {};
    toast(err.message, "error");
  }
  render();
}

/**
 * Boot the calendar strip.
 *
 * @param {string} initialIso - The day the page is anchored to.
 * @param {(iso: string) => void} onSelect - Called when a day is clicked.
 */
export async function initWeekStrip(initialIso, onSelect) {
  anchorIso = initialIso;
  onPick = onSelect;
  expanded = storedExpanded();

  $("#calendar-toggle").addEventListener("click", () => {
    expanded = !expanded;
    rememberExpanded();
    // No refetch: the month's totals are already in hand.
    render();
  });

  await load();
}

/**
 * Re-anchor the strip, e.g. when the summary page steps a week.
 *
 * Refetches only when the month changed — stepping inside one month is a
 * re-render of data already held.
 */
export async function setWeekStripDate(iso) {
  const before = fromIso(anchorIso);
  const after = fromIso(iso);
  anchorIso = iso;
  if (before.getMonth() !== after.getMonth() || before.getFullYear() !== after.getFullYear()) {
    await load();
  } else {
    render();
  }
}
