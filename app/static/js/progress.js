/**
 * Progress page — draws the training graph to a canvas.
 *
 * Layout is `layout.js`, which is a pure function and knows nothing about
 * drawing. This module owns the canvas, the gestures and the panel.
 *
 * Why a canvas rather than SVG or DOM nodes: at a few hundred movements with
 * every pairing drawn, a node per element is hundreds of layout objects
 * re-composited on every pan. One canvas is a single element, and panning is a
 * transform rather than a reflow.
 *
 * What the marks mean, and what they deliberately do not:
 *
 *   size   — either cumulative non-warmup sets, or your best estimated 1RM,
 *            depending on the Size-by control. **Not a strength standard.**
 *            The estimate is arithmetic on sets you logged yourself; nothing
 *            here compares you to anyone, because the app stores no bodyweight
 *            and has no business ranking people. A movement with no recorded
 *            load has no estimate and draws as a hollow ring — an unmeasured
 *            lift is not a light one.
 *   colour — the *current* weekly coverage of the movement's main muscle,
 *            straight from the same grading the body map uses.
 *   edge   — the two movements were logged on the same day; opacity rises with
 *            how many days that happened on.
 *   outside — logged fewer than three times, or not in eight weeks.
 *
 * **The graph draws from the first logged movement.** Until Phase 6.7 it was
 * hidden below fifteen, which meant a new user met a description of a picture
 * they could not see, and the picture then arrived all at once. It now starts
 * as one dot and fills in, which is the only way it becomes something to come
 * back to.
 */

import { fetchTrainingGraph } from "./api.js";
import { bounds, fingerprint, simulate } from "./layout.js";
import { $, formatDate, formatWeight, loadUnit, toast } from "./ui.js";

let anchorIso;
let graph = null;
let positions = null;

/** Canvas transform: world units → CSS pixels. */
let scale = 1;
let offsetX = 0;
let offsetY = 0;

let selectedId = null;

/**
 * What node size is measuring: `"volume"` (sets) or `"strength"` (your best).
 *
 * A reading preference, so it lives in `localStorage` beside the summary
 * page's split rather than in `?date=`, which is shared state every page
 * honours. It never reaches the API — both numbers are already in the payload,
 * so switching view costs no request and, crucially, no re-simulation: the
 * layout fingerprint deliberately ignores size for the same reason it ignores
 * colour. A drawing that rearranged itself when you asked a different question
 * of it could not become a mental map.
 */
const SIZE_KEY = "bodyshop:graph-size";
const SIZE_MODES = ["volume", "strength"];
let sizeMode = "volume";

/** Node radius in CSS pixels, before zoom. */
const MIN_RADIUS = 3;
const MAX_RADIUS = 13;

/** Zoom limits — far enough out to see the whole cloud, in to read one cluster. */
const MIN_SCALE = 0.35;
const MAX_SCALE = 4;

/** How close a tap has to land, in CSS pixels, to count as hitting a node. */
const TAP_SLOP = 14;

/**
 * Cached layouts, keyed by a fingerprint of the graph.
 *
 * The simulation is a few hundred iterations over every pair, so it runs when
 * the data changes and never on a re-render. Switching window and switching
 * back is free, and re-colouring after a workout does not move anything.
 */
const layouts = new Map();

const css = (name) =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/**
 * The theme's colours as numbers, read once per load.
 *
 * Parsed to RGB rather than handed to the canvas as `color-mix(...)` strings:
 * the ramp has to be *interpolated* here to build gradients, and a canvas
 * cannot mix a colour it was given as text. Doing the arithmetic in JS also
 * drops a dependency on canvas-side `color-mix` support.
 */
let theme = null;

/** `#rgb`, `#rrggbb` or an `rgb()` string → `{r, g, b}`. */
function parseColour(value) {
  const text = value.trim();
  if (text.startsWith("#")) {
    const hex = text.slice(1);
    const full = hex.length === 3 ? [...hex].map((c) => c + c).join("") : hex;
    return {
      r: parseInt(full.slice(0, 2), 16),
      g: parseInt(full.slice(2, 4), 16),
      b: parseInt(full.slice(4, 6), 16),
    };
  }
  const [r, g, b] = text.match(/[\d.]+/g).map(Number);
  return { r, g, b };
}

const mix = (a, b, t) => ({
  r: a.r + (b.r - a.r) * t,
  g: a.g + (b.g - a.g) * t,
  b: a.b + (b.b - a.b) * t,
});

const rgba = (c, alpha = 1) =>
  `rgba(${Math.round(c.r)}, ${Math.round(c.g)}, ${Math.round(c.b)}, ${alpha})`;

function readTheme() {
  theme = {
    rest: parseColour(css("--color-rest")),
    trainMin: parseColour(css("--color-train-min")),
    trainMax: parseColour(css("--color-train-max")),
    overMin: parseColour(css("--color-over-min")),
    overMax: parseColour(css("--color-over-max")),
    ground: parseColour(css("--color-base-200")),
    bone: parseColour(css("--color-base-content")),
    brick: parseColour(css("--color-primary")),
  };
}

/** Resolve the ramp to an `{r, g, b}`, mirroring `.muscle` in input.css. */
function nodeColour(node) {
  const info = graph.coverage[node.primary_muscle];
  if (!info || info.state === "rest") return theme.rest;

  const level = Math.max(0, Math.min(1, info.intensity));
  return info.state === "over"
    ? mix(theme.overMin, theme.overMax, level)
    : mix(theme.trainMin, theme.trainMax, level);
}

/**
 * What a node's size is measuring, or `null` when it cannot be measured.
 *
 * `null` is the important return. Under `strength` a movement with no recorded
 * load — bodyweight work, anything logged as a bare count, every row from
 * before Phase 4 added the weight column — has no estimate, and the drawing
 * says so with a hollow ring rather than a small circle. Sizing it at zero
 * would claim it is light, which is a different and false statement.
 */
function nodeMetric(node) {
  if (sizeMode === "strength") return node.best ? node.best.one_rep_max : null;
  return node.sets;
}

/** The largest measurable value on the canvas, for scaling everything else. */
function maxMetric() {
  return graph.nodes.reduce((most, node) => {
    const value = nodeMetric(node);
    return value === null ? most : Math.max(most, value);
  }, 0);
}

/**
 * Metric → radius, on a square-root scale so *area* tracks the quantity.
 *
 * An unmeasurable node takes the minimum radius, which is only ever drawn as a
 * ring — see `draw`.
 */
function nodeRadius(node, max) {
  const value = nodeMetric(node);
  if (value === null) return MIN_RADIUS;
  const share = max > 0 ? Math.sqrt(value / max) : 0;
  return MIN_RADIUS + share * (MAX_RADIUS - MIN_RADIUS);
}

// ---- The lit field ---------------------------------------------------------

/**
 * The glow layer: every node casts light in its own ramp colour.
 *
 * This is the only "background" the page has, and it is **made of the data**.
 * A decorative gradient was not an option — the redesign brief rules out
 * gradient backgrounds and blurred colour blobs outright, and the volume ramp
 * has to stay the most saturated thing on screen. Light emitted *by* the ramp
 * does not compete with it; it is the same reading, spread. Where training is
 * dense the field warms toward that muscle's coverage colour, so a page of
 * over-target work reads hot before a single node is examined.
 *
 * **Rendered once, in world units, then blitted.** Pan and zoom are a transform
 * over the layout, so the lit field does not change with them — redrawing a few
 * hundred large radial gradients per frame would not hold 60fps, and one
 * `drawImage` does. Its softness is why the low resolution costs nothing: there
 * is no edge in it to look pixelated.
 */
let glow = null;

/** Pixels per world unit in the glow layer. Low on purpose — it is all blur. */
const GLOW_RESOLUTION = 0.75;

/** Cap, so a sprawling all-time graph cannot allocate an enormous bitmap. */
const GLOW_MAX_PX = 1100;

/** How far a node's light reaches, in world units. */
const GLOW_MIN_REACH = 34;
const GLOW_MAX_REACH = 118;

/**
 * Peak alpha of a single node's light. Additive, so they build where dense.
 *
 * Kept low, and with a fast falloff below: at 0.5 with a gentle curve the
 * field turned milky and the nodes lost contrast against the haze they were
 * casting, which is the opposite of the point. This should read as atmosphere,
 * never as fog.
 */
const GLOW_ALPHA = 0.36;

function buildGlow() {
  const box = bounds(positions);
  const pad = GLOW_MAX_REACH;
  const worldW = box.maxX - box.minX + pad * 2;
  const worldH = box.maxY - box.minY + pad * 2;

  const resolution = Math.min(
    GLOW_RESOLUTION,
    GLOW_MAX_PX / Math.max(worldW, worldH),
  );
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(worldW * resolution));
  canvas.height = Math.max(1, Math.round(worldH * resolution));

  const context = canvas.getContext("2d");
  // Additive: two nearby movements light the space between them more than
  // either does alone, which is what makes a training block read as a region
  // rather than as a handful of dots.
  context.globalCompositeOperation = "lighter";
  context.scale(resolution, resolution);
  context.translate(-box.minX + pad, -box.minY + pad);

  const maxSets = graph.nodes.reduce((most, n) => Math.max(most, n.sets), 0);

  for (const node of graph.nodes) {
    const point = positions.get(node.exercise_id);
    if (!point) continue;

    const share = maxSets > 0 ? Math.sqrt(node.sets / maxSets) : 0;
    const reach = GLOW_MIN_REACH + share * (GLOW_MAX_REACH - GLOW_MIN_REACH);
    // An orphan is not lighting anything — it fell out of the training — so it
    // casts a cold, faint bone light instead of a coverage colour.
    const colour = node.orphan ? theme.bone : nodeColour(node);
    const peak = node.orphan ? GLOW_ALPHA * 0.22 : GLOW_ALPHA;

    const gradient = context.createRadialGradient(
      point.x, point.y, 0, point.x, point.y, reach,
    );
    gradient.addColorStop(0, rgba(colour, peak));
    gradient.addColorStop(0.3, rgba(colour, peak * 0.22));
    gradient.addColorStop(1, rgba(colour, 0));

    context.fillStyle = gradient;
    context.beginPath();
    context.arc(point.x, point.y, reach, 0, Math.PI * 2);
    context.fill();
  }

  glow = { canvas, minX: box.minX - pad, minY: box.minY - pad, worldW, worldH };
}

// ---- Drawing ---------------------------------------------------------------

function canvasSize() {
  const canvas = $("#graph-canvas");
  return { width: canvas.clientWidth, height: canvas.clientHeight };
}

/** Fit the laid-out cloud into the canvas, once, after a layout or a resize. */
function fitToView() {
  const { width, height } = canvasSize();
  const box = bounds(positions);
  const spanX = Math.max(1, box.maxX - box.minX);
  const spanY = Math.max(1, box.maxY - box.minY);
  const padding = MAX_RADIUS * 2 + 8;

  scale = Math.min(
    (width - padding * 2) / spanX,
    (height - padding * 2) / spanY,
  );
  scale = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale));

  const midX = (box.minX + box.maxX) / 2;
  const midY = (box.minY + box.maxY) / 2;
  offsetX = width / 2 - midX * scale;
  offsetY = height / 2 - midY * scale;
}

const toScreen = (point) => ({
  x: point.x * scale + offsetX,
  y: point.y * scale + offsetY,
});

function draw() {
  const canvas = $("#graph-canvas");
  const context = canvas.getContext("2d");
  const { width, height } = canvasSize();
  const ratio = window.devicePixelRatio || 1;

  // Back the canvas at device resolution but keep drawing in CSS pixels, so
  // marks are crisp on a phone without every coordinate carrying the ratio.
  if (canvas.width !== Math.round(width * ratio)) {
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  if (!graph || !positions) return;

  const max = maxMetric();
  const maxDays = graph.edges.reduce((most, edge) => Math.max(most, edge.days), 1);
  const bone = rgba(theme.bone);

  // The lit field, underneath everything. One blit of a bitmap built in world
  // units, so panning costs the same whatever the graph contains.
  if (glow) {
    const origin = toScreen({ x: glow.minX, y: glow.minY });
    context.drawImage(
      glow.canvas,
      origin.x, origin.y,
      glow.worldW * scale, glow.worldH * scale,
    );
  }

  // Edges next, so nodes sit on top of them.
  context.lineWidth = 1;
  for (const edge of graph.edges) {
    const a = positions.get(edge.source);
    const b = positions.get(edge.target);
    if (!a || !b) continue;
    const from = toScreen(a);
    const to = toScreen(b);
    // Opacity is the co-occurrence count; the hue is the two movements it
    // joins, blended. A uniform brick web said nothing about what it connected,
    // and at this density that is most of the drawing. Blended once when the
    // data lands, not per frame — a gradient per edge per frame is what would
    // cost the frame rate here.
    const strength = 0.14 + 0.52 * (edge.days / maxDays);
    context.strokeStyle = rgba(edge._colour || theme.brick, strength);
    context.beginPath();
    context.moveTo(from.x, from.y);
    context.lineTo(to.x, to.y);
    context.stroke();
  }

  for (const node of graph.nodes) {
    const point = positions.get(node.exercise_id);
    if (!point) continue;
    const { x, y } = toScreen(point);
    const radius = nodeRadius(node, max);
    // Under the strength view, a movement whose sets carry no load cannot be
    // sized. That is a different fact from an orphan, so it gets a different
    // ring — in the muscle's own coverage colour, so you can still read what it
    // feeds — but it is emphatically not filled. `graph.py` wrote this rule
    // down before the data to break it existed.
    const unmeasured = nodeMetric(node) === null;

    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);

    if (node.orphan) {
      // A hollow ring: logged, but not currently part of the training. Reading
      // it as absence rather than as a quantity is the whole point.
      context.fillStyle = rgba(theme.ground);
      context.fill();
      context.strokeStyle = rgba(theme.bone, 0.45);
      context.lineWidth = 1.25;
      context.stroke();
    } else if (unmeasured) {
      context.fillStyle = rgba(theme.ground);
      context.fill();
      context.strokeStyle = rgba(nodeColour(node), 0.75);
      context.lineWidth = 1.5;
      context.stroke();
    } else {
      // Lit from up and to the left rather than filled flat, so a node reads as
      // a body catching light on the field it is casting. The bright stop is
      // the node's own ramp colour pushed toward white; the far stop is the
      // colour itself, so the encoding is unchanged — only its shading is.
      const colour = nodeColour(node);
      const sphere = context.createRadialGradient(
        x - radius * 0.38, y - radius * 0.42, radius * 0.12,
        x, y, radius,
      );
      sphere.addColorStop(0, rgba(mix(colour, { r: 255, g: 255, b: 255 }, 0.42)));
      sphere.addColorStop(0.55, rgba(colour));
      sphere.addColorStop(1, rgba(mix(colour, theme.ground, 0.3)));
      context.fillStyle = sphere;
      context.fill();

      // The same redundant cue the body map carries: past-target is a hue flip
      // at nearly equal brightness, so it also takes a bone outline and does
      // not rely on telling green from red.
      const state = graph.coverage[node.primary_muscle];
      if (state && state.state === "over") {
        context.strokeStyle = bone;
        context.lineWidth = 1.75;
        context.stroke();
      }
    }

    if (node.exercise_id === selectedId) {
      context.beginPath();
      context.arc(x, y, radius + 4, 0, Math.PI * 2);
      context.strokeStyle = bone;
      context.lineWidth = 1.5;
      context.stroke();
    }
  }
}

// ---- Interaction -----------------------------------------------------------

/** The node under a point, or null. Nearest within `TAP_SLOP`, not first hit. */
function nodeAt(x, y) {
  if (!graph || !positions) return null;
  const max = maxMetric();
  let best = null;
  let bestDistance = Infinity;

  for (const node of graph.nodes) {
    const point = positions.get(node.exercise_id);
    if (!point) continue;
    const screen = toScreen(point);
    const distance = Math.hypot(screen.x - x, screen.y - y);
    const reach = Math.max(nodeRadius(node, max), TAP_SLOP);
    if (distance < reach && distance < bestDistance) {
      best = node;
      bestDistance = distance;
    }
  }
  return best;
}

/** Fill the detail panel for a movement, or clear it. */
function showPanel(node) {
  const panel = $("#graph-panel");
  panel.textContent = "";
  panel.hidden = !node;
  if (!node) return;

  const name = document.createElement("p");
  name.className = "graph-panel-name";
  name.textContent = node.name;

  const meta = document.createElement("p");
  meta.className = "graph-panel-meta type-data";
  const parts = [
    `${node.sets} ${node.sets === 1 ? "set" : "sets"}`,
    `${node.sessions} ${node.sessions === 1 ? "session" : "sessions"}`,
    `last ${formatDate(node.last_logged, { month: "short", day: "numeric" })}`,
  ];
  meta.textContent = parts.join("  ·  ");

  const coverage = graph.coverage[node.primary_muscle];
  const note = document.createElement("p");
  note.className = "graph-panel-note";
  // Names the muscle and this week's reading for it — the same fact the body
  // map shows, so the two pages cannot say different things.
  note.textContent = coverage
    ? `Mainly ${node.primary_muscle}, ${describeState(coverage.state)} this week.`
    : `Mainly ${node.primary_muscle}.`;

  panel.append(name, meta, note, bestLine(node));
}

/**
 * The personal-best line: the estimate, and the set it came from.
 *
 * **It always shows its working.** An estimate printed alone is indistinguishable
 * from a measurement, and this one is neither measured nor a benchmark — it is
 * Epley's formula on a set the user typed in. Naming that set is what keeps the
 * number checkable, and "est." is not decoration.
 */
function bestLine(node) {
  const line = document.createElement("p");
  line.className = "graph-panel-best type-data";
  const unit = loadUnit();

  if (!node.best) {
    line.classList.add("is-unmeasured");
    // Say *why* there is nothing, since the two reasons want different actions.
    line.textContent = node.weight_mode === "bodyweight"
      ? "No load recorded — bodyweight movement."
      : "No load recorded on these sets.";
    return line;
  }

  const { one_rep_max: estimate, weight, reps, achieved_on: on } = node.best;
  const load = `${formatWeight(weight, unit)}${unit}`;
  const when = formatDate(on, { month: "short", day: "numeric" });
  // A logged single is not an estimate — it is the lift — so it is not
  // dressed up as one.
  line.textContent = reps === 1
    ? `Best single ${load} on ${when}`
    : `Est. 1RM ${formatWeight(estimate, unit)}${unit} — from ${load} × ${reps} on ${when}`;
  return line;
}

/** The coverage states in the product's own words — never "optimal". */
function describeState(state) {
  if (state === "over") return "past its target";
  if (state === "trained") return "in range";
  return "untrained";
}

function selectNode(node) {
  selectedId = node ? node.exercise_id : null;
  showPanel(node);
  draw();
}

/**
 * Pan, pinch and tap on one pointer-event handler.
 *
 * Pointer events cover mouse, touch and pen in one path, which is what keeps
 * this short enough to hand-write. A gesture only counts as a tap if it barely
 * moved, so dragging across a node does not open its panel.
 */
function bindGestures() {
  const canvas = $("#graph-canvas");
  const active = new Map();
  let pinchDistance = 0;
  let moved = 0;

  const centre = () => {
    const points = [...active.values()];
    const sum = points.reduce((a, p) => ({ x: a.x + p.x, y: a.y + p.y }), { x: 0, y: 0 });
    return { x: sum.x / points.length, y: sum.y / points.length };
  };

  canvas.addEventListener("pointerdown", (event) => {
    canvas.setPointerCapture(event.pointerId);
    active.set(event.pointerId, { x: event.offsetX, y: event.offsetY });
    moved = 0;
    if (active.size === 2) {
      const [a, b] = [...active.values()];
      pinchDistance = Math.hypot(a.x - b.x, a.y - b.y);
    }
  });

  canvas.addEventListener("pointermove", (event) => {
    const previous = active.get(event.pointerId);
    if (!previous) return;
    const next = { x: event.offsetX, y: event.offsetY };

    if (active.size === 1) {
      offsetX += next.x - previous.x;
      offsetY += next.y - previous.y;
      moved += Math.hypot(next.x - previous.x, next.y - previous.y);
    }
    active.set(event.pointerId, next);

    if (active.size === 2) {
      const [a, b] = [...active.values()];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      if (pinchDistance > 0) {
        const focus = centre();
        zoomAt(focus.x, focus.y, distance / pinchDistance);
      }
      pinchDistance = distance;
      moved += TAP_SLOP; // a pinch is never a tap
    }
    draw();
  });

  const release = (event) => {
    const point = active.get(event.pointerId);
    active.delete(event.pointerId);
    if (active.size < 2) pinchDistance = 0;
    if (point && moved < 6) selectNode(nodeAt(point.x, point.y));
  };
  canvas.addEventListener("pointerup", release);
  canvas.addEventListener("pointercancel", (event) => active.delete(event.pointerId));

  // Trackpad and mouse wheel zoom, anchored under the cursor.
  canvas.addEventListener("wheel", (event) => {
    event.preventDefault();
    zoomAt(event.offsetX, event.offsetY, Math.exp(-event.deltaY * 0.002));
    draw();
  }, { passive: false });
}

/** Zoom by `factor` about a point, keeping what is under it in place. */
function zoomAt(x, y, factor) {
  const next = Math.max(MIN_SCALE, Math.min(MAX_SCALE, scale * factor));
  const applied = next / scale;
  offsetX = x - (x - offsetX) * applied;
  offsetY = y - (y - offsetY) * applied;
  scale = next;
}

// ---- The written half ------------------------------------------------------

/**
 * List the movements that have fallen out.
 *
 * This is not a caption for the canvas — it is the same finding in words, and
 * it is the whole page when there is not enough history to draw a graph.
 */
function renderOrphans() {
  const list = $("#orphan-list");
  const basis = $("#orphan-basis");
  list.textContent = "";

  const orphans = graph.nodes
    .filter((node) => node.orphan)
    .sort((a, b) => a.last_logged.localeCompare(b.last_logged));

  basis.textContent = orphans.length
    ? `${orphans.length} of ${graph.nodes.length}`
    : "";

  if (!orphans.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = graph.nodes.length
      ? "Nothing has been dropped in this window — every movement here is still in rotation."
      : "Nothing logged in this window yet.";
    list.append(empty);
    return;
  }

  for (const node of orphans) {
    const row = document.createElement("article");
    row.className = "entry";

    const main = document.createElement("div");
    main.className = "entry-main";

    const name = document.createElement("div");
    name.className = "entry-name";
    name.textContent = node.name;

    const meta = document.createElement("div");
    meta.className = "entry-meta";
    meta.textContent = `${node.primary_muscle} · last logged `
      + formatDate(node.last_logged, { month: "short", day: "numeric" });

    main.append(name, meta);

    const count = document.createElement("span");
    count.className = "entry-sets";
    count.textContent = `${node.sessions}×`;

    row.append(main, count);
    list.append(row);
  }
}

// ---- Loading ---------------------------------------------------------------

function setStatus(message) {
  const status = $("#graph-status");
  status.textContent = message || "";
  status.hidden = !message;
}

async function load() {
  const window_ = $("#window-select").value;
  setStatus("Loading…");

  try {
    graph = await fetchTrainingGraph(window_, anchorIso);
  } catch (err) {
    setStatus("Could not load the graph.");
    toast(err.message, "error");
    return;
  }

  renderOrphans();
  // Clear the selection *without* drawing. Every draw below reads state
  // derived from the graph that has just arrived — edge colours, the glow
  // layer — so nothing may paint until that state has been rebuilt for it.
  selectedId = null;
  showPanel(null);

  // Nothing at all is the one case with no drawing to make. Everything above
  // zero draws: one node is a dot, and the point of Phase 6.7 is that it grows
  // from there rather than switching on at a threshold.
  if (!graph.nodes.length) {
    positions = null;
    glow = null;
    $("#graph-legend").hidden = true;
    setStatus("Nothing logged in this window yet — log a workout and it starts here.");
    draw();
    return;
  }

  const key = fingerprint(graph);
  if (!layouts.has(key)) layouts.set(key, simulate(graph));
  positions = layouts.get(key);

  // Each edge takes the blend of the two movements it joins, resolved once
  // here. Per frame this would be the most expensive thing on the canvas.
  const colours = new Map(
    graph.nodes.map((node) => [
      node.exercise_id,
      node.orphan ? theme.bone : nodeColour(node),
    ]),
  );
  for (const edge of graph.edges) {
    edge._colour = mix(
      colours.get(edge.source) || theme.brick,
      colours.get(edge.target) || theme.brick,
      0.5,
    );
  }

  buildGlow();

  $("#graph-legend").hidden = false;
  setStatus(graphNote());
  fitToView();
  draw();
}

/**
 * The line under the canvas: how far along the drawing is, in its own terms.
 *
 * This replaced the threshold. A count that climbs is a reason to come back; a
 * gate that says "not yet" is a reason not to. Under the strength view it says
 * how much of the picture is actually sized by load, because a canvas of rings
 * should explain itself rather than look broken.
 */
function graphNote() {
  const total = graph.nodes.length;

  if (sizeMode === "strength") {
    if (!graph.measured) {
      return `No weights recorded in this window, so nothing can be sized by load — `
        + "every movement is drawn as a ring. Log a weight and reps and they fill in.";
    }
    if (graph.measured < total) {
      return `${graph.measured} of ${total} movements sized by your best lift; `
        + "the rings are the ones with no weight recorded.";
    }
    return `All ${total} movements sized by your best lift in this window.`;
  }

  return graph.sparse
    ? `${total} ${total === 1 ? "movement" : "movements"} so far — the shape fills in `
      + `as you log more, and reads as a map from about ${graph.sparse_below}.`
    : `${total} movements, sized by the sets they carried.`;
}

/** Keep the legend describing what size currently means. */
function renderSizeKey() {
  const strength = sizeMode === "strength";
  $("#graph-size-key").textContent = strength
    ? "size is your best lift"
    : "size is sets logged";
  // The ring key is nonsense under the volume view, where nothing is unsized.
  $("#graph-key-load").hidden = !strength;
}

/** Switch what size means. No refetch and no re-simulation — see `sizeMode`. */
function onSizeChange(event) {
  sizeMode = SIZE_MODES.includes(event.target.value) ? event.target.value : "volume";
  try {
    localStorage.setItem(SIZE_KEY, sizeMode);
  } catch {
    // Private browsing. The choice holds for this page view.
  }
  renderSizeKey();
  if (graph && graph.nodes.length) setStatus(graphNote());
  // The selected movement's panel names its best, which is unchanged — but the
  // ring under it may have just appeared or gone, so re-read it.
  draw();
}

/** The stored size mode, if it is still one the page offers. */
function storedSizeMode() {
  try {
    const stored = localStorage.getItem(SIZE_KEY);
    return SIZE_MODES.includes(stored) ? stored : "volume";
  } catch {
    return "volume";
  }
}

/**
 * Boot the progress page.
 * @param {string} initialIso - Anchors the window and the colouring week.
 */
export async function initProgress(initialIso) {
  anchorIso = initialIso;
  readTheme();

  $("#window-select").addEventListener("change", load);

  // Both numbers already ride on the payload, so this is a re-draw rather than
  // a request — and never a re-simulation, so the arrangement holds still while
  // you switch between the two questions.
  sizeMode = storedSizeMode();
  const sizeSelect = $("#size-select");
  sizeSelect.value = sizeMode;
  sizeSelect.addEventListener("change", onSizeChange);
  renderSizeKey();

  bindGestures();

  // Refit on resize rather than re-simulating: the arrangement is in world
  // units and only the mapping to pixels changed.
  let resizeHandle;
  window.addEventListener("resize", () => {
    clearTimeout(resizeHandle);
    resizeHandle = setTimeout(() => {
      if (positions) fitToView();
      draw();
    }, 120);
  });

  await load();
}
