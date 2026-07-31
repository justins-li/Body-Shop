/**
 * Force-directed layout — a pure function of the graph, with no canvas, no DOM
 * and no globals. Everything that draws lives in `progress.js`.
 *
 * Hand-written rather than pulled from d3: the repository has zero JavaScript
 * dependencies and the redesign keeps it that way. A repulsion/spring/centering
 * loop is about a hundred lines and is more than enough at this scale.
 *
 * Three properties are load-bearing.
 *
 * **It is deterministic.** Positions are seeded from the exercise ids rather
 * than from `Math.random`, so the same training draws the same picture every
 * time. A graph that rearranges itself on every visit cannot become a mental
 * map, which is the only reason to draw one.
 *
 * **It runs to completion once, not per frame.** `simulate` returns final
 * positions; panning and zooming are transforms over them. The caller caches
 * the result against a hash of its input.
 *
 * **Orphans are pushed outward rather than filtered out.** They are the insight
 * the graph exists for — movements that fell out of the training — so they ring
 * the outside where they can be read, instead of being buried in the core.
 */

/** Repulsion between every pair, keeping the cloud from collapsing. */
const REPULSION = 5200;

/** Pull along an edge. Scaled by co-occurrence, so habitual pairs sit closer. */
const SPRING = 0.0016;

/**
 * Strength of the radial force that puts every node at its target radius.
 *
 * One force does both jobs: core nodes target radius 0, so it reads as
 * centering, and orphans target `ORPHAN_RADIUS`, so it reads as a ring. The
 * first version pushed orphans *away* from the origin with a negative
 * centering constant, which is unbounded — each step scaled the displacement
 * that produced it, so positions grew exponentially and the layout ran off to
 * 1e19 before the loop finished.
 */
const RADIAL = 0.02;

/** Where movements that have fallen out of the training come to rest. */
const ORPHAN_RADIUS = 300;

/** Velocity retained per step. Below 1 the simulation settles. */
const DAMPING = 0.82;

/** Enough for this many nodes to settle; the loop is run once, not per frame. */
const ITERATIONS = 320;

/**
 * Pairs closer than 8 units apart are treated as 8 apart.
 *
 * Repulsion goes as 1/d², so without a floor two nodes that land on top of
 * each other trade an effectively infinite kick and the simulation never
 * recovers. Stored squared, because that is how it is compared.
 */
const MIN_DISTANCE_SQ = 64;

/** Furthest a node may travel in one step, which bounds any remaining spike. */
const MAX_STEP = 28;

/**
 * Cooling schedule, as in any annealed force layout: displacement is scaled by
 * `alpha`, which decays geometrically so late steps only polish. Without it the
 * system keeps trading energy and never settles into one arrangement.
 */
const ALPHA_DECAY = 0.985;

/**
 * A small deterministic PRNG (mulberry32).
 * @param {number} seed
 * @returns {() => number} Successive values in [0, 1).
 */
function random(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Hash a string to a 32-bit integer (FNV-1a).
 *
 * Used both to seed the layout and to key its cache, so a change in the data is
 * a change in the seed and a stale layout cannot be served for new data.
 * @param {string} value
 */
export function hash(value) {
  let result = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) {
    result ^= value.charCodeAt(index);
    result = Math.imul(result, 0x01000193);
  }
  return result >>> 0;
}

/**
 * A stable fingerprint of the graph, for cache keys.
 *
 * Reads only what the layout depends on — which nodes exist, whether each is an
 * orphan, and the weighted edges — so re-colouring after a week's training does
 * not invalidate a perfectly good arrangement.
 * @param {{nodes: Array<object>, edges: Array<object>}} graph
 */
export function fingerprint(graph) {
  const nodes = graph.nodes
    .map((node) => `${node.exercise_id}:${node.orphan ? 1 : 0}`)
    .sort()
    .join(",");
  const edges = graph.edges
    .map((edge) => `${edge.source}>${edge.target}:${edge.days}`)
    .sort()
    .join(",");
  return `${hash(nodes)}-${hash(edges)}-${graph.nodes.length}`;
}

/**
 * Lay the graph out.
 *
 * @param {{nodes: Array<object>, edges: Array<object>}} graph
 * @param {{iterations?: number}} [options]
 * @returns {Map<string, {x: number, y: number}>} Positions in arbitrary units
 *   centred near the origin; the renderer scales them to fit.
 */
export function simulate(graph, { iterations = ITERATIONS } = {}) {
  const nodes = graph.nodes.map((node, index) => {
    // Seeded per node from its id, so adding one movement does not reshuffle
    // the rest of the picture.
    const rng = random(hash(node.exercise_id));
    const angle = rng() * Math.PI * 2;
    // Orphans start further out, which is also where they should end up —
    // starting them in the core just makes the simulation walk them outward.
    const radius = (node.orphan ? 260 : 40) + rng() * 90;
    return {
      id: node.exercise_id,
      orphan: Boolean(node.orphan),
      // The index keeps two movements with colliding hashes from starting on
      // exactly the same point, where the repulsion direction is undefined.
      x: Math.cos(angle) * radius + index * 0.01,
      y: Math.sin(angle) * radius,
      vx: 0,
      vy: 0,
    };
  });

  const byId = new Map(nodes.map((node) => [node.id, node]));
  const edges = graph.edges
    .map((edge) => ({
      a: byId.get(edge.source),
      b: byId.get(edge.target),
      weight: Math.min(edge.days, 12),
    }))
    .filter((edge) => edge.a && edge.b);

  let alpha = 1;

  for (let step = 0; step < iterations; step += 1) {
    // Repulsion: every pair. O(n²), run once, at a few hundred nodes — a
    // quadtree would be the optimisation if this ever became per-frame.
    for (let i = 0; i < nodes.length; i += 1) {
      const a = nodes[i];
      for (let j = i + 1; j < nodes.length; j += 1) {
        const b = nodes[j];
        let dx = a.x - b.x;
        let dy = a.y - b.y;
        let distanceSq = dx * dx + dy * dy;
        if (distanceSq < MIN_DISTANCE_SQ) {
          // Two nodes on the same point have no direction to separate along,
          // so give them one rather than dividing by zero.
          if (distanceSq === 0) {
            dx = 1;
            dy = 0;
          }
          distanceSq = MIN_DISTANCE_SQ;
        }
        const distance = Math.sqrt(dx * dx + dy * dy) || 1;
        const force = REPULSION / distanceSq;
        const fx = (dx / distance) * force;
        const fy = (dy / distance) * force;
        a.vx += fx;
        a.vy += fy;
        b.vx -= fx;
        b.vy -= fy;
      }
    }

    // Springs: a pair trained together often is pulled tighter.
    for (const edge of edges) {
      const dx = edge.b.x - edge.a.x;
      const dy = edge.b.y - edge.a.y;
      const pull = SPRING * edge.weight;
      edge.a.vx += dx * pull;
      edge.a.vy += dy * pull;
      edge.b.vx -= dx * pull;
      edge.b.vy -= dy * pull;
    }

    for (const node of nodes) {
      // One radial force, two behaviours: the core targets the origin, the
      // orphans target a ring around it. Both are restoring forces, so both
      // are bounded — which the earlier outward push was not.
      const distance = Math.hypot(node.x, node.y) || 1;
      const target = node.orphan ? ORPHAN_RADIUS : 0;
      const pull = (distance - target) * RADIAL;
      node.vx -= (node.x / distance) * pull;
      node.vy -= (node.y / distance) * pull;

      node.vx *= DAMPING;
      node.vy *= DAMPING;

      const speed = Math.hypot(node.vx, node.vy);
      if (speed > MAX_STEP) {
        node.vx = (node.vx / speed) * MAX_STEP;
        node.vy = (node.vy / speed) * MAX_STEP;
      }

      node.x += node.vx * alpha;
      node.y += node.vy * alpha;
    }

    alpha *= ALPHA_DECAY;
  }

  return new Map(nodes.map((node) => [node.id, { x: node.x, y: node.y }]));
}

/**
 * The bounding box of a position map, for fitting the drawing to a viewport.
 * @param {Map<string, {x: number, y: number}>} positions
 */
export function bounds(positions) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const { x, y } of positions.values()) {
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  }
  // An empty graph has no box; hand back a unit square so callers can divide.
  if (!Number.isFinite(minX)) return { minX: 0, minY: 0, maxX: 1, maxY: 1 };
  return { minX, minY, maxX, maxY };
}
