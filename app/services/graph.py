"""The training graph: which movements your training is built from, and what it
has stopped feeding.

Backs ``GET /api/progress/graph`` and the canvas on ``/progress``. This module
holds the *rules* — what a window means, what makes a movement an orphan, and
which colour a node takes — while every SQL statement stays in
:mod:`app.models` and the HTTP shape stays in :mod:`app.api`.

Three decisions are worth reading before changing anything here.

**Node colour is the app's own thesis, not an invented benchmark.** A node takes
the current weekly coverage state of its primary muscle, so the graph answers
"where does my training live, and what is it feeding" with the same grading the
body map uses. Colouring against a *strength standard* — what someone your
bodyweight "should" lift — remains out: the app stores no bodyweight and has no
business ranking anyone against a population.

**Node size is either volume or your own best, and never a standard.** Phase 6.7
added the second encoding. ``sets`` is cumulative work; ``one_rep_max`` is
estimated from sets the user actually performed (:mod:`app.services.strength`),
which is arithmetic on their own log rather than a benchmark imported from
elsewhere. The honesty rule this module wrote down before the data existed still
holds and is now enforced: **a movement with no recorded load has no estimate and
must render as a hollow ring**, not a small circle. That covers bodyweight work
and every row logged before Phase 4 added the weight column.

**The orphan thresholds are opinion, and are named so they stay visible.** Same
discipline as ``REGION_NEGLECT_SHARE`` in :mod:`app.services.summary`: no study
says how long is too long between sessions, so the numbers live as constants
with docstrings rather than as literals buried in a comparison.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..exercises import get_exercise
from ..models import exercise_activity, exercise_co_occurrence, loaded_sets
from ..training import TrainerProfile
from .strength import best_from_sets
from .summary import weekly_summary

#: Windows the graph can be drawn over, as a span in days. ``all`` is unbounded.
WINDOWS: dict[str, int | None] = {"8w": 56, "6m": 182, "all": None}

#: What each window is called on screen. Defined beside the spans so the control
#: and the query cannot drift apart.
WINDOW_LABELS: dict[str, str] = {
    "8w": "8 weeks",
    "6m": "6 months",
    "all": "All time",
}

#: The window used when the request does not ask for one.
DEFAULT_WINDOW = "8w"

#: Sessions below which a movement counts as an orphan.
#:
#: Three is the point where a movement stops looking like something you tried
#: once and starts looking like part of the programme. It is a judgement, not a
#: finding — there is no literature on how often a movement must recur.
ORPHAN_MIN_SESSIONS = 3

#: Weeks of silence after which a movement counts as an orphan regardless of how
#: often it was logged before. Matches the eight-week default window, so the
#: shortest view answers "what have I dropped" without arithmetic.
ORPHAN_STALE_WEEKS = 8

#: Movements below which the drawing is still worth showing but not yet worth
#: reading as a *shape*.
#:
#: **This is no longer a gate.** Until Phase 6.7 the graph did not render at all
#: below fifteen movements: the page showed a ranked list and told you what would
#: unlock the picture. That was the wrong shape for the one visual the app has —
#: a new user met an explanation of a drawing they could not see, and the drawing
#: arrived all at once rather than growing. It now draws from the first logged
#: movement and fills in as history accumulates, which is what makes it worth
#: returning to.
#:
#: The number survives only as a note under the canvas, so a two-node picture
#: says it is early rather than pretending to be a map.
SPARSE_GRAPH_NODES = 15


def window_bounds(window: str, today: date) -> tuple[date | None, date]:
    """Resolve a window key to an inclusive ``(start, end)`` pair.

    ``start`` is ``None`` for ``all``, which the caller turns into the earliest
    date the database holds. Unknown keys fall back to the default rather than
    raising: this is a view preference arriving from a query string, and a bad
    one should show the usual graph, not an error page.
    """
    span = WINDOWS.get(window, WINDOWS[DEFAULT_WINDOW])
    if span is None:
        return None, today
    return today - timedelta(days=span - 1), today


def is_orphan(sessions: int, last_logged: date, today: date) -> bool:
    """Whether a movement has fallen out of the training.

    Either it never really entered it (fewer than ``ORPHAN_MIN_SESSIONS``
    sessions) or it has gone quiet (nothing in ``ORPHAN_STALE_WEEKS``). These
    are the nodes the graph exists to surface, so the test is deliberately
    generous — a movement is an orphan if *either* holds.
    """
    stale_before = today - timedelta(weeks=ORPHAN_STALE_WEEKS)
    return sessions < ORPHAN_MIN_SESSIONS or last_logged < stale_before


def training_graph(
    window: str = DEFAULT_WINDOW,
    today: date | None = None,
    week_starts_on: int = 1,
    profile: TrainerProfile | None = None,
) -> dict:
    """Build the graph payload for ``window``.

    Nodes are movements logged in the window, sized by the sets they carried;
    edges join movements performed on the same day, weighted by how many days
    that happened on. ``coverage`` is this week's per-muscle grade, which is
    what colours the nodes.

    ``profile`` reaches this only to be handed to :func:`weekly_summary`, and it
    has to: the node colours *are* the body map's grading, so a graph drawn
    against a different set of targets than the summary page would make the two
    pages disagree about the same week.
    """
    today = today or date.today()
    resolved = window if window in WINDOWS else DEFAULT_WINDOW
    start, end = window_bounds(resolved, today)
    # `all` still needs a lower bound for the query; the catalog predates no
    # plausible training history, so the epoch is safe and keeps one code path.
    floor = start or date(1970, 1, 1)
    activity = exercise_activity(floor, end)
    # Personal bests are read over the same window as the nodes, so "your best
    # in the last 8 weeks" is what the drawing sizes by — a lifetime best would
    # keep a movement large long after it was dropped, which is exactly the
    # signal the orphan ring exists to give.
    bests = best_from_sets(loaded_sets(floor, end))

    nodes = []
    for exercise_id, sets, sessions, last_logged in activity:
        exercise = get_exercise(exercise_id)
        if exercise is None:
            # A retired id that no migration caught. Dropping it is better than
            # drawing an unlabelled dot nobody can act on.
            continue
        best = bests.get(exercise_id)
        nodes.append(
            {
                "exercise_id": exercise_id,
                "name": exercise.name,
                # The graph colours by one muscle, so it uses the first primary
                # — the same group the picker shows first.
                "primary_muscle": exercise.primary[0] if exercise.primary else None,
                "sets": sets,
                "sessions": sessions,
                "last_logged": last_logged.isoformat(),
                "orphan": is_orphan(sessions, last_logged, today),
                # `None` when nothing this movement logged can support an
                # estimate. The client must draw a hollow ring rather than a
                # small one — an unmeasured lift is not a light lift.
                "best": best.to_dict() if best else None,
                "weight_mode": exercise.weight_mode,
            }
        )

    known = {node["exercise_id"] for node in nodes}
    edges = [
        {"source": a, "target": b, "days": days}
        for a, b, days in exercise_co_occurrence(start or date(1970, 1, 1), end)
        if a in known and b in known
    ]

    # Colour comes from the *current* week, not the window: the question the
    # graph answers is what this training is feeding now.
    week = weekly_summary(today, week_starts_on, profile)
    coverage = {
        muscle: {"state": info["state"], "intensity": info["intensity"]}
        for muscle, info in week["muscles"].items()
    }

    return {
        "window": resolved,
        "start": start.isoformat() if start else None,
        "end": end.isoformat(),
        "nodes": nodes,
        "edges": edges,
        "coverage": coverage,
        # How much of the drawing can be sized by load. Reported rather than
        # left to be counted, because it is the honest headline for the
        # strength view: "6 of 14 movements carry a recorded weight" is the
        # difference between a sparse picture and a wrong one.
        "measured": sum(1 for node in nodes if node["best"] is not None),
        # A note, not a gate. The graph draws from one node now; this only says
        # whether it is dense enough to read as a shape yet.
        "sparse": len(nodes) < SPARSE_GRAPH_NODES,
        "sparse_below": SPARSE_GRAPH_NODES,
    }
