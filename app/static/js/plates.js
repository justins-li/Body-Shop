/**
 * Plate calculator — what to load per side to reach a target weight.
 *
 * A pure function of the target, the bar and the unit. No storage, no API, and
 * no opinion about what you should be lifting: it reports what makes the number
 * you already typed.
 */

/** Plates a normal gym actually stocks, heaviest first, per unit. */
const PLATES = {
  kg: [25, 20, 15, 10, 5, 2.5, 1.25],
  lb: [45, 35, 25, 10, 5, 2.5],
};

/** The bar most racks have, in each unit. */
export const DEFAULT_BAR = { kg: 20, lb: 45 };

/**
 * The bar each barbell weight mode is loaded on, per unit.
 *
 * Keyed by the server's `weight_mode` (see `EQUIPMENT_WEIGHT_MODES` in
 * `app/exercises.py`). Only the two modes that *have* a bar appear: a movement
 * whose mode is missing here gets no plate breakdown at all, which is the whole
 * point of Phase 6.5 — a cable stack has no bar, and printing "20kg bar + …"
 * under a pulldown was arithmetic about equipment that is not in the room.
 *
 * The kg and lb figures are not conversions of each other (45lb is 20.4kg).
 * Gyms stock one bar or the other, so each unit names the bar that unit's gym
 * actually has, exactly as `DEFAULT_BAR` always did.
 */
export const BAR_WEIGHTS = {
  barbell: { kg: 20, lb: 45 },
  ez_bar: { kg: 10, lb: 25 },
};

/**
 * The bar for a weight mode, or `null` when that mode has no bar.
 *
 * `null` is the answer for dumbbells, stacks, bodyweight and implements, and
 * callers must render nothing rather than falling back to a barbell.
 *
 * @param {string} mode - A `weight_mode` from the API.
 * @param {"kg"|"lb"} unit
 * @returns {number|null}
 */
export function barFor(mode, unit) {
  const bar = BAR_WEIGHTS[mode];
  return bar && bar[unit] !== undefined ? bar[unit] : null;
}

/**
 * Plates for **one side** of the bar.
 *
 * @param {number} target - Total weight, in `unit`.
 * @param {number} bar - Bar weight, in `unit`.
 * @param {"kg"|"lb"} unit
 * @returns {{plates: number[], remainder: number}} `remainder` is what the
 *   stocked plates cannot make — non-zero for, say, 61kg on a 20kg bar. It is
 *   reported rather than rounded away, because rounding would quietly claim a
 *   loadout that does not exist.
 */
export function platesFor(target, bar, unit) {
  const perSide = (target - bar) / 2;
  if (!Number.isFinite(perSide) || perSide <= 0) return { plates: [], remainder: 0 };
  // Refuse an unknown unit rather than quietly handing back kilo plates
  // labelled as something else — a wrong loadout is worse than no hint.
  const stock = PLATES[unit];
  if (!stock) return { plates: [], remainder: 0 };

  const plates = [];
  let left = perSide;
  for (const plate of stock) {
    // The epsilon keeps 2.5 from being rejected by float dust at 2.4999999996.
    while (left >= plate - 1e-9) {
      plates.push(plate);
      left -= plate;
    }
  }
  // Two decimal places: float subtraction leaves 1e-15 dust otherwise.
  return { plates, remainder: Math.round(left * 100) / 100 };
}

/**
 * The same thing as a line to read: `20kg bar + 25 / 20 / 1.25 per side`.
 *
 * Returns `""` when the bar alone is the answer or the target is unreachable,
 * so callers can render nothing rather than an empty hint.
 */
export function describePlates(target, bar, unit) {
  const { plates, remainder } = platesFor(target, bar, unit);
  if (!plates.length) return "";
  const line = `${bar}${unit} bar + ${plates.join(" / ")} per side`;
  return remainder > 0 ? `${line} (${remainder}${unit} short)` : line;
}
