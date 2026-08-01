/**
 * First run — ask once what kind of training week this is, then never again.
 *
 * The trainer setup (Phase 6) decides every weekly target in the app, and its
 * default is a guess about a stranger. Asking once, up front, is the difference
 * between a summary page that means something on day one and one that quietly
 * grades a beginner against an experienced lifter's volume.
 *
 * Three rules it obeys:
 *
 * **It runs on the app pages only.** `/` and `/how-to-use` are static, make no
 * API calls, and must render identically for any visitor — `/` is also pinned to
 * exactly one screen. A dialog over either would break the one property that
 * makes them worth having before auth exists. `data-page` on `<body>` is the
 * gate.
 *
 * **Answering and skipping are both answers.** Either writes the "asked" flag,
 * so the dialog is genuinely once. Skipping stores nothing else, leaving the
 * server's defaults in place — a user who does not want to be interviewed gets
 * the app, not a nag on every navigation.
 *
 * **It never blocks the page it is over.** A `<dialog>` opened non-modally would
 * be dismissible by scrolling past; opened modally it traps focus, which is what
 * a genuine one-time decision wants. `Escape` counts as skipping.
 */

import { $, loadProfile, saveProfile } from "./ui.js";

/**
 * Whether the question has been put to this browser.
 *
 * Deliberately separate from the stored profile. If it were the same key, a
 * user who skipped would be asked again on every visit, and one who cleared
 * only their preferences would never be asked again — both backwards.
 */
const ASKED_KEY = "bodyshop:onboarded";

/** Pages that are allowed to interrupt. `/` and `/how-to-use` are not. */
const APP_PAGES = new Set(["calendar", "log", "summary", "progress"]);

function hasBeenAsked() {
  try {
    return localStorage.getItem(ASKED_KEY) === "1";
  } catch {
    // Storage blocked. Treat it as asked: a dialog we can never record an
    // answer to would reappear on every single page load.
    return true;
  }
}

function markAsked() {
  try {
    localStorage.setItem(ASKED_KEY, "1");
  } catch {
    // Nothing to do — the dialog is already closed either way.
  }
}

/** Highlight the chosen level and remember it on the element. */
function selectLevel(dialog, key) {
  dialog.dataset.level = key;
  dialog.querySelectorAll(".first-run-level").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.level === key));
  });
}

/**
 * Boot the first-run dialog.
 *
 * @param {HTMLDialogElement|null} dialog - The shell from `base.html`.
 * @param {string} page - The current page's `data-page` value.
 */
export function initOnboarding(dialog, page) {
  if (!dialog || !APP_PAGES.has(page) || hasBeenAsked()) return;

  const sessions = $("#first-run-sessions", dialog);
  const minutes = $("#first-run-minutes", dialog);

  // Start on whatever the app would have used anyway, so skipping and
  // submitting-untouched land in the same place.
  const current = loadProfile();
  selectLevel(dialog, current.experience);
  sessions.value = current.sessions_per_week;
  minutes.value = current.minutes_per_session;

  dialog.querySelectorAll(".first-run-level").forEach((button) => {
    button.addEventListener("click", () => selectLevel(dialog, button.dataset.level));
  });

  // Both exits mark the question asked; only this one records an answer.
  $("#first-run-start", dialog).addEventListener("click", () => {
    saveProfile({
      experience: dialog.dataset.level,
      sessions_per_week: Number(sessions.value),
      minutes_per_session: Number(minutes.value),
    });
    markAsked();
    dialog.close();
    // The page fetched its data before this was answered, so anything graded
    // against a target is now stale. A reload is the honest fix and costs one
    // request on a page that has just opened.
    window.location.reload();
  });

  $("#first-run-skip", dialog).addEventListener("click", () => {
    markAsked();
    dialog.close();
  });

  // Escape closes a modal dialog natively; catch it so it counts as skipping
  // rather than leaving the question to reappear on the next navigation.
  dialog.addEventListener("close", markAsked);

  dialog.showModal();
}
