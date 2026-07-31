/**
 * The set grid — one implementation, mounted by every surface that logs a set.
 *
 * Phase 8.2. This used to live inside `log.js`, which was fine while `/log` was
 * the only way to record anything. Routines added a second entrance, and a
 * "quick log" that reimplemented a simpler grid would have been a second set of
 * rules about weight modes, warm-ups and units — the exact divergence this
 * codebase keeps one copy of everything to avoid. The two entrances differ in
 * what they are *for*, not in what a set is.
 *
 * Everything the grid knows how to do comes with it:
 *
 *   - **Weight modes** (Phase 6.5). The column's name, whether a plate
 *     breakdown makes sense, and whether a weight is asked for at all, all
 *     follow the movement's equipment.
 *   - **Added weight.** Body-only movements hide the field behind a toggle, and
 *     the field is *removed from the DOM* rather than hidden, because a hidden
 *     input still submits.
 *   - **The RPE gate** (Phase 6). Shown on the advanced trainer setup, or
 *     whenever the last session of this movement already recorded one — a
 *     column you have been filling never disappears under you.
 *   - **Repeat**, **plate hints**, and starting the rest timer when a row is
 *     finished.
 *
 * It owns its own markup. The header used to be server-rendered so the column
 * names survived with no script, but the rows never did, so that bought a
 * header over nothing — and it cannot be true of a grid mounted into a dialog.
 */

import { formatWeight, loadProfile, loadUnit, toKg, weightModeDisplay } from "./ui.js";
import { barFor, describePlates } from "./plates.js";
import { startRestTimer } from "./timer.js";

const SET_TYPES = ["normal", "warmup", "drop", "failure"];
const SET_TYPE_LABELS = {
  normal: "Working", warmup: "Warm-up", drop: "Drop", failure: "To failure",
};

/** An entry cannot hold more sets than the API accepts. */
export const MAX_SETS = 100;

/**
 * Mount a set grid into `root`.
 *
 * @param {HTMLElement} root - Emptied and filled with the grid's own markup.
 * @param {object} [options]
 * @param {(message: string) => void} [options.onError] - Where to report "too
 *   many sets". Defaults to doing nothing, since a dialog may have nowhere.
 * @returns {object} The grid's handle — see the methods at the bottom.
 */
export function createSetGrid(root, { onError = () => {} } = {}) {
  let unit = loadUnit();
  let weightMode = "implement";
  let addedWeight = false;
  let showRpe = loadProfile().experience === "advanced";
  let previousSets = [];
  /** Whether a movement has been chosen — the note stays quiet until one is. */
  let mounted = false;

  root.textContent = "";
  root.classList.add("set-grid-root");

  const note = document.createElement("p");
  note.className = "picker-note m-0 mb-2";
  note.hidden = true;

  const toggleWrap = document.createElement("label");
  toggleWrap.className = "added-weight-toggle";
  toggleWrap.hidden = true;
  const toggleBox = document.createElement("input");
  toggleBox.type = "checkbox";
  toggleBox.className = "added-weight-box";
  const toggleName = document.createElement("span");
  toggleName.className = "type-label";
  toggleName.textContent = "Added weight";
  const toggleHint = document.createElement("span");
  toggleHint.className = "text-secondary text-sm";
  toggleHint.textContent = "belt, vest or dumbbell";
  toggleWrap.append(toggleBox, toggleName, toggleHint);

  const head = document.createElement("div");
  head.className = "set-grid-head type-label text-secondary";
  head.setAttribute("aria-hidden", "true");
  const headIndex = document.createElement("span");
  headIndex.textContent = "#";
  const headWeight = document.createElement("span");
  headWeight.textContent = "Weight";
  const headReps = document.createElement("span");
  headReps.textContent = "Reps";
  head.append(headIndex, headWeight, headReps, document.createElement("span"));

  const grid = document.createElement("div");
  grid.className = "grid gap-2 set-grid";

  const actions = document.createElement("div");
  actions.className = "flex flex-wrap items-center gap-3 mt-3";
  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.className = "step-key";
  addButton.textContent = "+ Add set";
  const repeatButton = document.createElement("button");
  repeatButton.type = "button";
  repeatButton.className = "step-key";
  repeatButton.textContent = "⧉ Repeat set";
  const prefill = document.createElement("p");
  prefill.className = "picker-note m-0";
  prefill.hidden = true;
  actions.append(addButton, repeatButton, prefill);

  root.append(note, toggleWrap, head, grid, actions);

  // ---- Rows ---------------------------------------------------------------

  /** Whether the weight column exists for the movement in hand. */
  const weightVisible = () => weightMode !== "bodyweight" || addedWeight;

  function numberField(className, label, attrs) {
    const field = document.createElement("input");
    field.type = "number";
    field.className = `field field-sm type-data ${className}`;
    field.setAttribute("aria-label", label);
    field.inputMode = attrs.inputmode;
    if (attrs.step) field.step = attrs.step;
    if (attrs.min) field.min = attrs.min;
    if (attrs.max) field.max = attrs.max;
    // Overwriting a prefilled weight is one tap rather than a careful drag over
    // three digits — which matters when this is done between sets.
    field.addEventListener("focus", () => field.select());
    return field;
  }

  /** A second-tier control with its own mono micro-label welded to it. */
  function subField(areaClass, label, control) {
    const wrap = document.createElement("span");
    wrap.className = `set-sub ${areaClass}`;
    const tag = document.createElement("span");
    tag.className = "type-label text-secondary";
    tag.setAttribute("aria-hidden", "true");
    tag.textContent = label;
    wrap.append(tag, control);
    return wrap;
  }

  /**
   * Build one row.
   *
   * `previous` becomes **placeholders**; `values` becomes real values. The
   * distinction is the whole reason repeating a set is a separate control
   * rather than a stronger placeholder: an untouched row must save as NULL
   * rather than silently re-logging weights nobody lifted today.
   */
  function setRow(index, previous, values = null) {
    const row = document.createElement("div");
    row.className = "set-row";
    row.dataset.index = String(index);
    row.classList.toggle("no-weight", !weightVisible());
    row.classList.toggle("no-rpe", !showRpe);

    const number = document.createElement("span");
    number.className = "set-row-index";
    number.textContent = String(index);

    const display = weightModeDisplay(weightMode);
    const weight = numberField(
      "set-weight",
      `Set ${index} ${display.label.toLowerCase()} in ${unit}`,
      { step: "any", min: "0", inputmode: "decimal" },
    );
    if (previous && previous.weight !== null && previous.weight !== undefined) {
      weight.placeholder = formatWeight(previous.weight, unit);
    }

    const reps = numberField("set-reps", `Set ${index} reps`, {
      min: "1", max: "1000", inputmode: "numeric",
    });
    if (previous && previous.reps !== null && previous.reps !== undefined) {
      reps.placeholder = String(previous.reps);
    }

    const rpe = numberField("set-rpe", `Set ${index} RPE`, {
      min: "1", max: "10", step: "0.5", inputmode: "decimal",
    });

    const type = document.createElement("select");
    type.className = "field field-sm set-type";
    type.setAttribute("aria-label", `Set ${index} type`);
    SET_TYPES.forEach((value) => type.append(new Option(SET_TYPE_LABELS[value], value)));
    if (previous && previous.set_type) type.value = previous.set_type;
    type.addEventListener("change", () => {
      row.classList.toggle("is-warmup", type.value === "warmup");
    });
    row.classList.toggle("is-warmup", type.value === "warmup");

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "set-row-remove";
    remove.textContent = "×";
    remove.setAttribute("aria-label", `Remove set ${index}`);
    remove.addEventListener("click", () => {
      row.remove();
      renumber();
    });

    // What to load to make the number just typed — **only when there is a bar**.
    // `barFor` returns null for dumbbells, stacks, bodyweight and implements,
    // and the hint is then never written: telling someone their 45kg pulldown is
    // "a 20kg bar plus 12.5 per side" is arithmetic about equipment that is not
    // in the room.
    const bar = barFor(weightMode, unit);
    const hint = document.createElement("span");
    hint.className = "plate-hint";
    const updateHint = () => {
      hint.textContent = bar === null || weight.value.trim() === ""
        ? ""
        : describePlates(Number(weight.value), bar, unit);
    };
    weight.addEventListener("input", updateHint);

    // Rest happens *between* sets, but the entry is one POST at the end — so
    // leaving a row you have filled in is the earliest honest signal that a set
    // just finished. The containment check keeps it from firing as focus moves
    // from weight to reps inside the same row.
    row.addEventListener("focusout", (event) => {
      if (row.contains(event.relatedTarget)) return;
      if (rowHasData(row)) startRestTimer();
    });

    // Fields the movement or the setup does not call for are left **out of the
    // DOM**: `values()` reads the grid back through these nodes, and a hidden
    // input still carries its value.
    row.append(number);
    if (weightVisible()) row.append(weight);
    row.append(reps, remove);
    if (showRpe) row.append(subField("set-sub-rpe", "RPE", rpe));
    row.append(subField("set-sub-type", "Type", type), hint);

    if (values) applyRowValues(row, values);
    return row;
  }

  /** Fill a row with real values, dispatching so derived state recomputes. */
  function applyRowValues(row, values) {
    const set = (selector, value) => {
      const field = row.querySelector(selector);
      if (!field || value === undefined || value === null) return;
      field.value = value;
      if (selector === ".set-weight") field.dispatchEvent(new Event("input"));
    };
    set(".set-weight", values.weight);
    set(".set-reps", values.reps);
    set(".set-rpe", values.rpe);
    if (values.set_type) {
      const type = row.querySelector(".set-type");
      if (type) {
        type.value = values.set_type;
        type.dispatchEvent(new Event("change"));
      }
    }
  }

  /**
   * What a row holds, in display units.
   *
   * `fallback` decides what an empty box is worth, and the two callers want
   * opposite answers. **Repeating** falls back to the placeholder, so the first
   * tap on a freshly-opened movement copies last session. **Rebuilding** does
   * not: promoting a suggestion to a value because a checkbox moved would log
   * weights nobody lifted.
   */
  function rowValues(row, { fallback = true } = {}) {
    const read = (selector) => {
      const field = row.querySelector(selector);
      if (!field) return null;
      const typed = field.value.trim();
      if (typed !== "") return typed;
      return fallback ? field.placeholder || null : null;
    };
    return {
      weight: read(".set-weight"),
      reps: read(".set-reps"),
      rpe: read(".set-rpe"),
      set_type: row.querySelector(".set-type")?.value || "normal",
    };
  }

  /** Whether a row records anything yet — a blank row is not a finished set. */
  function rowHasData(row) {
    return ["set-weight", "set-reps", "set-rpe"].some(
      (field) => (row.querySelector(`.${field}`)?.value ?? "").trim() !== "",
    );
  }

  const rows = () => [...grid.querySelectorAll(".set-row")];

  /** Keep the visible numbering contiguous after a removal. */
  function renumber() {
    const current = rows();
    current.forEach((row, position) => {
      const index = position + 1;
      row.dataset.index = String(index);
      row.querySelector(".set-row-index").textContent = String(index);
      row.querySelector(".set-row-remove")
        .setAttribute("aria-label", `Remove set ${index}`);
    });
    // Never leave the grid empty: an entry needs at least one set.
    if (!current.length) addRow();
  }

  function addRow(values = null) {
    const index = grid.children.length + 1;
    if (index > MAX_SETS) {
      onError(`An entry can hold at most ${MAX_SETS} sets.`);
      return;
    }
    // Reaching for another row means the one above it is done — the other end
    // of the same signal as the row's own `focusout`.
    const last = grid.lastElementChild;
    if (last && rowHasData(last)) startRestTimer();
    grid.append(setRow(index, previousSets[index - 1], values));
  }

  /** Repeat the set just entered, falling back to last session's placeholders. */
  function repeatLast() {
    const last = grid.lastElementChild;
    addRow(last ? rowValues(last) : null);
  }

  /** Rebuild from scratch. `rows` overrides the count; `keep` restores values. */
  function render({ count = null, keep = null } = {}) {
    grid.textContent = "";
    const total = Math.max(1, Math.min(count ?? previousSets.length, MAX_SETS));
    for (let index = 1; index <= total; index += 1) {
      const row = setRow(index, previousSets[index - 1]);
      if (keep && keep[index - 1]) applyRowValues(row, keep[index - 1]);
      grid.append(row);
    }
    renderHead();
  }

  /** Rebuild in place, preserving the rows and the values actually typed. */
  function rebuild() {
    const current = rows();
    render({
      count: current.length,
      keep: current.map((row) => rowValues(row, { fallback: false })),
    });
  }

  /** Head the grid for the movement in hand. */
  function renderHead() {
    const display = weightModeDisplay(weightMode);
    head.classList.toggle("no-weight", !weightVisible());
    head.classList.toggle("no-rpe", !showRpe);
    headWeight.textContent = display.label;

    note.hidden = !mounted;
    note.textContent = mounted ? display.note : "";

    toggleWrap.hidden = !(mounted && weightMode === "bodyweight");
    toggleBox.checked = addedWeight;
  }

  addButton.addEventListener("click", () => addRow());
  repeatButton.addEventListener("click", repeatLast);
  toggleBox.addEventListener("change", (event) => {
    addedWeight = event.target.checked;
    rebuild();
  });

  render();

  return {
    /** The mount element, for callers that need to hide or reveal it. */
    element: root,

    /**
     * Point the grid at a movement.
     *
     * @param {object} options
     * @param {string} options.weightMode - From the exercise payload.
     * @param {Array}  [options.previousSets] - Last session's sets, as placeholders.
     * @param {number} [options.count] - Rows to open with. Defaults to however
     *   many were logged last time, which is what `/log` wants; a routine passes
     *   its own prescribed set count instead.
     * @param {string} [options.note] - Extra line under the mode's own.
     */
    setMovement({ weightMode: mode, previousSets: previous = [], count = null }) {
      mounted = true;
      weightMode = mode || "implement";
      previousSets = previous;
      // A fresh movement starts as itself, then history has its say: if you
      // logged this with weight on a belt, the field opens ticked, and if you
      // have been recording RPE it stays available whatever the setup says.
      // Both are the same rule — never take away a column you were filling.
      const recorded = (field) =>
        previousSets.some((set) => set[field] !== null && set[field] !== undefined);
      addedWeight = weightMode === "bodyweight" && recorded("weight");
      showRpe = loadProfile().experience === "advanced" || recorded("rpe");
      render({ count });
    },

    /** Say where the placeholders came from, or hide the line. */
    setPrefillNote(message) {
      prefill.hidden = !message;
      prefill.textContent = message || "";
    },

    /** Re-read in a new display unit, keeping typed values untouched. */
    setUnit(next) {
      unit = next;
      rebuild();
    },

    /**
     * The grid in the API's shape.
     *
     * A blank field becomes `null`, not `0` — "not recorded" and "zero" are
     * different facts. A field the row does not carry reads `null` for the same
     * reason. Weight converts to kilograms here, the only unit the API takes.
     */
    values() {
      const raw = (row, selector) =>
        (row.querySelector(selector)?.value ?? "").trim();
      return rows().map((row) => {
        const rawWeight = raw(row, ".set-weight");
        const rawReps = raw(row, ".set-reps");
        const rawRpe = raw(row, ".set-rpe");
        return {
          weight: rawWeight === "" ? null : toKg(Number(rawWeight), unit),
          reps: rawReps === "" ? null : Number(rawReps),
          rpe: rawRpe === "" ? null : Number(rawRpe),
          set_type: row.querySelector(".set-type").value,
        };
      });
    },

    /** Whether anything at all has been typed — for a quick-log's guard. */
    hasAnyData() {
      return rows().some(rowHasData);
    },

    addRow,
    repeatLast,
  };
}
