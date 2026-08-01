/**
 * Turning a page — the transition between chapters.
 *
 * The app is arranged as a book: chapters down the sides, numbered marks, a
 * chapter that keeps its side. Navigation between them was the one place that
 * did not say so. It raised a veil to cover the server round trip, and because
 * these pages render in a few milliseconds the veil was a flicker — a hint that
 * something loaded, rather than a sense of having moved.
 *
 * So the transition is now **timed rather than measured**. A leaf falls across
 * the screen, and the navigation waits for it. That is a deliberate cost: the
 * app is slower by the length of the animation, on purpose, because "instant
 * and imperceptible" and "you turned a page" are different experiences and this
 * one is a book.
 *
 * Two details make it read as a page rather than a wipe:
 *
 *   - **It hinges.** The leaf rotates about a vertical spine, from edge-on to
 *     flat, so it arrives with the foreshortening a real page has.
 *   - **It follows the shelves.** The stacks split around the open chapter, so
 *     an earlier chapter is to your left and a later one to your right. Going
 *     forward, the leaf falls from the right; going back, from the left. The
 *     gesture agrees with where the thing you clicked was standing.
 *
 * Degradation, in order of how likely it is:
 *
 *   - **Reduced motion**: no rotation and a much shorter hold. Someone who has
 *     asked for less movement has not asked to be kept waiting for it.
 *   - **Before this module loads**: the link is an ordinary `<a>` and navigates
 *     immediately. That is the whole fallback, and it is why the handler is
 *     bound rather than the links being rewritten.
 *   - **No JavaScript**: as above.
 */

/** How long the leaf takes to fall. Must match `--page-turn-ms` in input.css. */
const TURN_MS = 460;

/** The reduced-motion hold: long enough to register, short enough not to nag. */
const REDUCED_MS = 140;

/**
 * Anything longer than this and a slow navigation would look stuck rather than
 * deliberate. If the browser has not started leaving by now, something is
 * wrong and the veil should not be the thing that hides it.
 */
const MAX_HOLD_MS = 1200;

const prefersReducedMotion = () =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/**
 * Which way the book is turning.
 *
 * Read off the DOM rather than by comparing chapter numbers: `base.html`
 * already decided which stack a shelf belongs to, and asking it is one lookup
 * against a rule that lives in one place. Anything not in a stack — the bottom
 * tab bar, an in-page link — turns forward, which is the unmarked case.
 */
function directionFor(link) {
  return link.closest(".shelf-stack-left") ? "back" : "forward";
}

/**
 * Whether this click should be handled at all.
 *
 * A modified click is the user asking for a new tab or a download, and
 * swallowing it to play an animation would be taking something away.
 */
function isPlainClick(event) {
  return !(
    event.defaultPrevented
    || event.button !== 0
    || event.metaKey
    || event.ctrlKey
    || event.shiftKey
    || event.altKey
  );
}

let leaving = false;

/**
 * Turn to `href`, holding the navigation until the leaf has fallen.
 *
 * Exported because shelf clicks are not the only way to leave a page —
 * double-clicking a day on `/summary` opens `/log` for it — and a second
 * navigation that raised the veil and left immediately would tear the animation
 * down a few milliseconds in. One implementation, so every departure looks the
 * same.
 *
 * @param {string} href
 * @param {"forward"|"back"} [direction] - Which side the leaf falls from.
 */
export function turnTo(href, direction = "forward") {
  const veil = document.getElementById("page-veil");
  if (!veil) {
    window.location.assign(href);
    return;
  }
  if (leaving) return;
  leaving = true;

  veil.dataset.turn = direction;
  veil.classList.add("is-visible");

  // The wait is the point: the browser would otherwise replace the document
  // mid-animation, and the turn would be a flicker again.
  window.setTimeout(
    () => window.location.assign(href),
    Math.min(prefersReducedMotion() ? REDUCED_MS : TURN_MS, MAX_HOLD_MS),
  );
}

/**
 * Boot the page-turn transition.
 *
 * @param {HTMLElement|null} veil - `#page-veil` from `base.html`.
 */
export function initPageTurn(veil) {
  if (!veil) return;

  document.querySelectorAll("a[data-nav]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (!isPlainClick(event)) return;

      const href = link.getAttribute("href");
      if (!href || href.startsWith("#")) return;

      event.preventDefault();
      turnTo(href, directionFor(link));
    });
  });

  // Coming back through the bfcache restores a document that was mid-departure,
  // veil and all. Without this the page returns permanently covered — and the
  // guard stays latched, so the next click would do nothing at all.
  window.addEventListener("pageshow", () => {
    leaving = false;
    veil.classList.remove("is-visible");
    delete veil.dataset.turn;
  });
}
