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
 *   size   — cumulative non-warmup sets in the window.
 *   colour — the *current* weekly coverage of the movement's main muscle,
 *            straight from the same grading the body map uses. There is no
 *            invented benchmark here: the app stores no bodyweight and computes
 *            no 1RM, and pre-Phase-4 history has null weights, so anything
 *            strength-relative would be a guess. That is Phase 7's to add.
 *   edge   — the two movements were logged on the same day; opacity rises with
 *            how many days that happened on.
 *   outside — logged fewer than three times, or not in eight weeks.
 */

import { fetchTrainingGraph } from "./api.js";
import { bounds, fingerprint, simulate } from "./layout.js";
import { $, formatDate, toast } from "./ui.js";

let anchorIso;
let graph = null;
let positions = null;

/** Canvas transform: world units → CSS pixels. */
let scale = 1;
let offsetX = 0;
let offsetY = 0;

let selectedId = null;

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

/** Resolve the ramp to a colour, mirroring `.muscle` in input.css. */
function nodeColour(node) {
  const info = graph.coverage[node.primary_muscle];
  if (!info || info.state === "rest") return css("--color-rest");

  const level = Math.max(0, Math.min(1, info.intensity));
  const [min, max] = info.state === "over"
    ? [css("--color-over-min"), css("--color-over-max")]
    : [css("--color-train-min"), css("--color-train-max")];
  return `color-mix(in srgb, ${max} ${level * 100}%, ${min})`;
}

/** Sets → radius, on a square-root scale so area tracks volume. */
function nodeRadius(node, maxSets) {
  const share = maxSets > 0 ? Math.sqrt(node.sets / maxSets) : 0;
  return MIN_RADIUS + share * (MAX_RADIUS - MIN_RADIUS);
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

  const maxSets = graph.nodes.reduce((most, node) => Math.max(most, node.sets), 0);
  const maxDays = graph.edges.reduce((most, edge) => Math.max(most, edge.days), 1);
  const brick = css("--color-primary");
  const bone = css("--color-base-content");

  // Edges first, so nodes sit on top of them.
  context.lineWidth = 1;
  for (const edge of graph.edges) {
    const a = positions.get(edge.source);
    const b = positions.get(edge.target);
    if (!a || !b) continue;
    const from = toScreen(a);
    const to = toScreen(b);
    const strength = 0.12 + 0.5 * (edge.days / maxDays);
    context.strokeStyle = `color-mix(in srgb, ${brick} ${strength * 100}%, transparent)`;
    context.beginPath();
    context.moveTo(from.x, from.y);
    context.lineTo(to.x, to.y);
    context.stroke();
  }

  for (const node of graph.nodes) {
    const point = positions.get(node.exercise_id);
    if (!point) continue;
    const { x, y } = toScreen(point);
    const radius = nodeRadius(node, maxSets);

    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);

    if (node.orphan) {
      // A hollow ring: logged, but not currently part of the training. Reading
      // it as absence rather than as a quantity is the whole point.
      context.fillStyle = css("--color-base-200");
      context.fill();
      context.strokeStyle = `color-mix(in srgb, ${bone} 45%, transparent)`;
      context.lineWidth = 1.25;
      context.stroke();
    } else {
      context.fillStyle = nodeColour(node);
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
  const maxSets = graph.nodes.reduce((most, node) => Math.max(most, node.sets), 0);
  let best = null;
  let bestDistance = Infinity;

  for (const node of graph.nodes) {
    const point = positions.get(node.exercise_id);
    if (!point) continue;
    const screen = toScreen(point);
    const distance = Math.hypot(screen.x - x, screen.y - y);
    const reach = Math.max(nodeRadius(node, maxSets), TAP_SLOP);
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

  panel.append(name, meta, note);
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
  selectNode(null);

  if (!graph.graph_ready) {
    // Degrade honestly rather than drawing a dozen dots and calling it a graph.
    positions = null;
    $("#graph-legend").hidden = true;
    setStatus(
      `${graph.nodes.length} of ${graph.min_nodes} movements — the graph draws once `
      + "you have logged a few more. The list below works already.",
    );
    draw();
    return;
  }

  const key = fingerprint(graph);
  if (!layouts.has(key)) layouts.set(key, simulate(graph));
  positions = layouts.get(key);

  $("#graph-legend").hidden = false;
  setStatus("");
  fitToView();
  draw();
}

/**
 * Boot the progress page.
 * @param {string} initialIso - Anchors the window and the colouring week.
 */
export async function initProgress(initialIso) {
  anchorIso = initialIso;

  $("#window-select").addEventListener("change", load);
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
