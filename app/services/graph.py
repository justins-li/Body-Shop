"""The training graph: which movements your training is built from, and what it
has stopped feeding.

Backs ``GET /api/progress/graph`` and the canvas on ``/progress``. This module
holds the *rules* — what a window means, what makes a movement an orphan, and
which colour a node takes — while every SQL statement stays in
:mod:`app.models` and the HTTP shape stays in :mod:`app.api`.

Two decisions are worth reading before changing anything here.

**Node colour is the app's own thesis, not an invented benchmark.** A node takes
the current weekly coverage state of its primary muscle, so the graph answers
"where does my training live, and what is it feeding" with the same grading the
body map uses. Colouring by estimated 1RM against a strength standard was
considered and belongs to Phase 7: the app stores no bodyweight, computes no
1RM, and pre-Phase-4 history has ``NULL`` weights, so every mark would be a
guess. When that lands, a lift with no benchmark must render as a hollow ring
rather than a number nobody measured.

**The orphan thresholds are opinion, and are named so they stay visible.** Same
discipline as ``REGION_NEGLECT_SHARE`` in :mod:`app.services.summary`: no study
says how long is too long between sessions, so the numbers live as constants
with docstrings rather than as literals buried in a comparison.
"""

from __future__ import annotations

from datetime import date, timedelta

from ..exercises import get_exercise
from ..models import exercise_activity, exercise_co_occurrence
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

#: Below this many movements a force-directed graph says nothing — a dozen dots
#: and their edges is a list with extra steps. ``/progress`` shows a ranked list
#: instead and says what unlocks the graph.
MIN_GRAPH_NODES = 15


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
    user_id: str,
    window: str = DEFAULT_WINDOW,
    today: date | None = None,
    week_starts_on: int = 1,
) -> dict:
    """Build the graph payload for ``window``.

    Nodes are movements logged in the window, sized by the sets they carried;
    edges join movements performed on the same day, weighted by how many days
    that happened on. ``coverage`` is this week's per-muscle grade, which is
    what colours the nodes.
    """
    today = today or date.today()
    resolved = window if window in WINDOWS else DEFAULT_WINDOW
    start, end = window_bounds(resolved, today)
    # `all` still needs a lower bound for the query; the catalog predates no
    # plausible training history, so the epoch is safe and keeps one code path.
    activity = exercise_activity(user_id, start or date(1970, 1, 1), end)

    nodes = []
    for exercise_id, sets, sessions, last_logged in activity:
        exercise = get_exercise(exercise_id)
        if exercise is None:
            # A retired id that no migration caught. Dropping it is better than
            # drawing an unlabelled dot nobody can act on.
            continue
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
            }
        )

    known = {node["exercise_id"] for node in nodes}
    edges = [
        {"source": a, "target": b, "days": days}
        for a, b, days in exercise_co_occurrence(
            user_id, start or date(1970, 1, 1), end
        )
        if a in known and b in known
    ]

    # Colour comes from the *current* week, not the window: the question the
    # graph answers is what this training is feeding now.
    week = weekly_summary(user_id, today, week_starts_on)
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
        # Said plainly rather than left for the client to infer, so both the
        # canvas and any later consumer agree on when the graph is meaningful.
        "graph_ready": len(nodes) >= MIN_GRAPH_NODES,
        "min_nodes": MIN_GRAPH_NODES,
    }
