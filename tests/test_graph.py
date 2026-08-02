"""The training graph behind ``/progress``.

Two things carry the risk here, and they are what these tests are about:

* **The warm-up rule has to reach the graph.** Warm-ups count nowhere else, so
  a movement logged only as a warm-up must not become a node — and, crucially,
  must not pull an edge toward a node that does not exist.
* **The orphan thresholds are opinion.** They are asserted directly so that
  changing one is a deliberate edit to a test rather than a silent drift in
  what the page claims.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.exercises import MUSCLE_GROUPS
from conftest import TEST_USER_ID
from app.services.graph import (
    DEFAULT_WINDOW,
    SPARSE_GRAPH_NODES,
    ORPHAN_MIN_SESSIONS,
    ORPHAN_STALE_WEEKS,
    WINDOWS,
    is_orphan,
    training_graph,
    window_bounds,
)

TODAY = date(2026, 7, 30)


def iso(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


# ---- Pure rules ------------------------------------------------------------


def test_window_bounds_span_the_named_period():
    start, end = window_bounds("8w", TODAY)
    assert end == TODAY
    # Inclusive of both ends, so eight weeks is 56 days counting today.
    assert (end - start).days == WINDOWS["8w"] - 1


def test_all_time_has_no_start():
    start, end = window_bounds("all", TODAY)
    assert start is None and end == TODAY


def test_unknown_window_falls_back_rather_than_raising():
    """It arrives from a view control; a bad preference should show the usual
    view, not an error."""
    assert window_bounds("nonsense", TODAY) == window_bounds(DEFAULT_WINDOW, TODAY)


def test_a_movement_logged_rarely_is_an_orphan():
    assert is_orphan(ORPHAN_MIN_SESSIONS - 1, TODAY, TODAY)
    assert not is_orphan(ORPHAN_MIN_SESSIONS, TODAY, TODAY)


def test_a_movement_gone_quiet_is_an_orphan_however_often_it_was_logged():
    stale = TODAY - timedelta(weeks=ORPHAN_STALE_WEEKS, days=1)
    assert is_orphan(50, stale, TODAY)


# ---- Through the database --------------------------------------------------


def test_nodes_carry_volume_sessions_and_recency(app, add):
    add(iso(1), "Barbell_Squat", 3)
    add(iso(3), "Barbell_Squat", 2)

    with app.app_context():
        graph = training_graph(TEST_USER_ID, "8w", TODAY)

    node = next(n for n in graph["nodes"] if n["exercise_id"] == "Barbell_Squat")
    assert node["sets"] == 5
    assert node["sessions"] == 2
    assert node["last_logged"] == iso(1)
    assert node["primary_muscle"] == "quads"


def test_warmup_only_entries_never_become_nodes(app, add):
    """Warm-ups count nowhere else in the app, and this is nowhere else."""
    add(iso(1), "Barbell_Squat", [{"set_type": "warmup"}, {"set_type": "warmup"}])
    add(iso(1), "Barbell_Bench_Press_-_Medium_Grip", 3)

    with app.app_context():
        graph = training_graph(TEST_USER_ID, "8w", TODAY)

    assert [n["exercise_id"] for n in graph["nodes"]] == [
        "Barbell_Bench_Press_-_Medium_Grip"
    ]


def test_edges_only_ever_join_movements_that_are_nodes(app, add):
    """A warm-up-only movement must not leave a dangling edge behind.

    This is the failure the shared `_counted_sessions` subquery exists to
    prevent: nodes and edges are filtered by the same rule, once.
    """
    add(iso(1), "Barbell_Squat", [{"set_type": "warmup"}])
    add(iso(1), "Barbell_Bench_Press_-_Medium_Grip", 3)
    add(iso(1), "Barbell_Deadlift", 3)

    with app.app_context():
        graph = training_graph(TEST_USER_ID, "8w", TODAY)

    known = {n["exercise_id"] for n in graph["nodes"]}
    assert known == {"Barbell_Bench_Press_-_Medium_Grip", "Barbell_Deadlift"}
    for edge in graph["edges"]:
        assert edge["source"] in known and edge["target"] in known


def test_an_edge_counts_the_days_two_movements_shared(app, add):
    for day in (1, 3, 5):
        add(iso(day), "Barbell_Squat", 2)
        add(iso(day), "Romanian_Deadlift", 2)
    # A day only one of them appeared must not raise the count.
    add(iso(7), "Barbell_Squat", 2)

    with app.app_context():
        graph = training_graph(TEST_USER_ID, "8w", TODAY)

    edge = next(
        e for e in graph["edges"]
        if {e["source"], e["target"]} == {"Barbell_Squat", "Romanian_Deadlift"}
    )
    assert edge["days"] == 3


def test_each_pair_appears_once_and_nothing_links_to_itself(app, add):
    add(iso(1), "Barbell_Squat", 2)
    add(iso(1), "Romanian_Deadlift", 2)
    add(iso(1), "Leg_Press", 2)

    with app.app_context():
        graph = training_graph(TEST_USER_ID, "8w", TODAY)

    pairs = [frozenset((e["source"], e["target"])) for e in graph["edges"]]
    assert len(pairs) == len(set(pairs)) == 3
    assert all(len(pair) == 2 for pair in pairs)


def test_the_window_excludes_older_training(app, add):
    add(iso(3), "Barbell_Squat", 3)
    add(iso(120), "Barbell_Deadlift", 3)

    with app.app_context():
        recent = training_graph(TEST_USER_ID, "8w", TODAY)
        everything = training_graph(TEST_USER_ID, "all", TODAY)

    assert {n["exercise_id"] for n in recent["nodes"]} == {"Barbell_Squat"}
    assert {n["exercise_id"] for n in everything["nodes"]} == {
        "Barbell_Squat",
        "Barbell_Deadlift",
    }


def test_colour_comes_from_the_current_week_not_the_window(app, add):
    """Nodes are graded by what the training is feeding *now*, which is the same
    reading the body map gives."""
    add(iso(1), "Barbell_Squat", 3)

    with app.app_context():
        graph = training_graph(TEST_USER_ID, "all", TODAY)

    assert set(graph["coverage"]) == set(MUSCLE_GROUPS)
    assert graph["coverage"]["quads"]["state"] == "trained"
    # A group nothing touched this week must not be dressed as trained. Biceps,
    # not calves — the squat carries calves as a secondary, at half weight.
    assert graph["coverage"]["biceps"]["state"] == "rest"


def test_a_thin_history_still_draws_and_says_it_is_early(app, add):
    """Phase 6.7 removed the gate. One movement is a drawing of one movement.

    The old behaviour hid the canvas below fifteen nodes, which meant a new user
    met an explanation of a picture they could not see. `sparse` is now a note,
    not a switch — the nodes come back either way.
    """
    add(iso(1), "Barbell_Squat", 3)

    with app.app_context():
        graph = training_graph(TEST_USER_ID, "8w", TODAY)

    assert len(graph["nodes"]) == 1
    assert graph["sparse"] is True
    assert graph["sparse_below"] == SPARSE_GRAPH_NODES
    assert "graph_ready" not in graph


@pytest.mark.parametrize("window", list(WINDOWS))
def test_every_window_is_servable(app, add, window):
    add(iso(1), "Barbell_Squat", 3)
    with app.app_context():
        assert training_graph(TEST_USER_ID, window, TODAY)["window"] == window


# ---- Personal bests on the nodes (Phase 6.7) -------------------------------


def test_a_node_carries_the_best_its_sets_support(app, add):
    add(iso(3), "Barbell_Squat", [
        {"weight": 100, "reps": 5},
        {"weight": 110, "reps": 1},
    ])

    with app.app_context():
        node = training_graph(TEST_USER_ID, "8w", TODAY)["nodes"][0]

    # 100 x 5 estimates to ~117, which beats the 110 single.
    assert node["best"]["one_rep_max"] == 116.7
    assert node["best"]["weight"] == 100.0
    assert node["best"]["reps"] == 5


def test_a_movement_with_no_load_has_no_best(app, add):
    """The rule this module wrote down before the data existed: an unmeasured
    lift renders as a hollow ring, never as a small node."""
    add(iso(3), "Pullups", 4)

    with app.app_context():
        node = training_graph(TEST_USER_ID, "8w", TODAY)["nodes"][0]

    assert node["best"] is None
    # The client uses this to say *why* there is no number.
    assert node["weight_mode"] == "bodyweight"


def test_warm_ups_never_become_a_personal_best(app, add):
    """On movements where the warm-up is the heaviest thing logged, counting it
    would routinely beat the real work. It is excluded here as everywhere."""
    add(iso(3), "Barbell_Squat", [
        {"weight": 200, "reps": 1, "set_type": "warmup"},
        {"weight": 100, "reps": 5},
    ])

    with app.app_context():
        node = training_graph(TEST_USER_ID, "8w", TODAY)["nodes"][0]

    assert node["best"]["weight"] == 100.0


def test_measured_counts_the_sizeable_nodes(app, add):
    """The headline for the strength view: a canvas of rings should explain
    itself rather than look broken."""
    add(iso(3), "Barbell_Squat", [{"weight": 100, "reps": 5}])
    add(iso(3), "Pullups", 3)

    with app.app_context():
        graph = training_graph(TEST_USER_ID, "8w", TODAY)

    assert len(graph["nodes"]) == 2
    assert graph["measured"] == 1


def test_bests_are_scoped_to_the_window(app, add):
    """"Your best in this window", not a lifetime best — a lifetime figure would
    keep a movement large long after it was dropped, which is the opposite of
    what the orphan ring is for."""
    add(iso(200), "Barbell_Squat", [{"weight": 200, "reps": 1}])
    add(iso(3), "Barbell_Squat", [{"weight": 100, "reps": 5}])

    with app.app_context():
        recent = training_graph(TEST_USER_ID, "8w", TODAY)["nodes"][0]
        lifetime = training_graph(TEST_USER_ID, "all", TODAY)["nodes"][0]

    assert recent["best"]["weight"] == 100.0
    assert lifetime["best"]["weight"] == 200.0


def test_the_graph_draws_from_a_single_movement(app, add):
    """Phase 6.7 removed the gate outright. There is no node count at which the
    drawing appears — it starts at one and fills in."""
    add(iso(1), "Barbell_Squat", 1)

    with app.app_context():
        graph = training_graph(TEST_USER_ID, "8w", TODAY)

    assert len(graph["nodes"]) == 1
    assert graph["sparse"] is True


def test_an_empty_window_is_the_only_case_with_no_nodes(app):
    with app.app_context():
        graph = training_graph(TEST_USER_ID, "8w", TODAY)
    assert graph["nodes"] == []
    assert graph["measured"] == 0
    assert graph["sparse"] is True
