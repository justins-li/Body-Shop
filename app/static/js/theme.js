/**
 * Light/dark switching.
 *
 * The *applying* half of this does not live here — it runs as a blocking inline
 * script in `base.html`'s head, because a module is deferred and would let one
 * theme paint before the other replaced it. This module only owns the control:
 * reading the current state, flipping it, and remembering the choice.
 *
 * Remembering matters more than it looks. Until a choice is made the system
 * preference decides, which is the right default; once someone picks, that
 * has to survive a reload, so the two states are stored explicitly rather than
 * as "not the system value".
 */

const STORAGE_KEY = "bodyshop:theme";
const DARK = "bodyshop-dark";
const LIGHT = "bodyshop";

/** Ground colour per theme, so the browser chrome matches the page. */
const THEME_COLOR = { [DARK]: "#0d1014", [LIGHT]: "#faf4eb" };

const isDark = () => document.documentElement.dataset.theme === DARK;

/**
 * Point the document at a theme and record the choice.
 * @param {boolean} dark
 */
function apply(dark) {
  const root = document.documentElement;
  const theme = dark ? DARK : LIGHT;

  root.dataset.theme = theme;
  // Tells the browser which way to render form controls and scrollbars; without
  // it a dark page keeps light native widgets.
  root.style.colorScheme = dark ? "dark" : "light";

  const meta = document.getElementById("theme-color");
  if (meta) meta.setAttribute("content", THEME_COLOR[theme]);

  try {
    localStorage.setItem(STORAGE_KEY, dark ? "dark" : "light");
  } catch {
    // Private browsing, or storage disabled. The choice just won't persist.
  }
}

/** Sync the button's label and pressed state to the document. */
function sync(button) {
  const dark = isDark();
  button.setAttribute("aria-pressed", String(dark));
  const label = button.querySelector("[data-theme-label]");
  if (label) label.textContent = dark ? "Dark" : "Light";
}

/**
 * Wire the toggle.
 * @param {HTMLElement} button
 */
export function initThemeToggle(button) {
  if (!button) return;
  sync(button);

  button.addEventListener("click", () => {
    apply(!isDark());
    sync(button);
  });

  // Follow the system while the reader has expressed no preference of their own.
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  media.addEventListener("change", (event) => {
    let stored = null;
    try {
      stored = localStorage.getItem(STORAGE_KEY);
    } catch {
      stored = null;
    }
    if (stored) return;
    apply(event.matches);
    sync(button);
  });
}
