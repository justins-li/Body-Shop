/**
 * Log page — create workout entries and review/delete what's on a given day.
 */

import { createEntry, deleteEntry, fetchEntriesForDate } from "./api.js";
import {
  $, formatDate, renderEntries, retargetLinks, syncUrlDate, toast,
} from "./ui.js";

let selectedIso;

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
    await refreshDay();
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
  initStepper();
  retargetLinks([$("#view-summary")], selectedIso);
  await refreshDay();
}
