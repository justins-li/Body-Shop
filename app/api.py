"""JSON API consumed by the front-end JavaScript.

All endpoints are namespaced under ``/api`` and return JSON.  Errors use the
shape ``{"error": "message"}`` with an appropriate status code.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, jsonify, request

from .exercises import all_exercises, get_exercise
from .routines import all_routines, get_routine
from .models import (
    ValidationError,
    add_entry,
    delete_entry,
    last_sets_for_exercise,
    list_entries,
    parse_date,
    recent_exercise_usage,
    sets_by_date,
)
from .services.graph import DEFAULT_WINDOW, training_graph
from .services.summary import weekly_summary
from .services.weeks import month_bounds, week_bounds
from .training import TrainerProfile, resolve_profile

bp = Blueprint("api", __name__, url_prefix="/api")


@bp.errorhandler(ValidationError)
def _handle_validation_error(exc: ValidationError):
    return jsonify({"error": str(exc)}), 400


def _week_start() -> int:
    return int(current_app.config.get("WEEK_STARTS_ON", 1))


def _query_date(name: str, default: date | None = None) -> date:
    raw = request.args.get(name)
    if not raw:
        return default if default is not None else date.today()
    return parse_date(raw, field=name)


def _image_base() -> str:
    return str(current_app.config.get("EXERCISE_IMAGE_BASE", ""))


def _query_profile() -> TrainerProfile:
    """Read the trainer setup off the query string.

    Phase 5 moves this onto the user row; until there is a user, the choice is a
    client preference and arrives with the request. Bad values fall back to the
    default rather than 400-ing — same reasoning as ``window`` on the graph
    endpoint. A stale ``localStorage`` key should show the usual targets, not
    blank the summary page.
    """
    return resolve_profile(
        request.args.get("experience"),
        request.args.get("sessions"),
        request.args.get("minutes"),
    )


@bp.get("/exercises")
def get_exercises():
    """The whole catalog, in its light shape.

    Instructions and images are omitted — they quadruple the payload, and the
    picker filters the catalog client-side, so it wants the smallest thing it
    can search over. ``/api/exercises/<id>`` serves the rest on demand.
    """
    return jsonify({"exercises": [e.to_dict() for e in all_exercises()]})


@bp.get("/exercises/recent")
def get_recent_exercises():
    """Recently logged exercises, most recent first — the picker's default view.

    Unlike search and browse this reads entry history, so it cannot be done
    client-side from the catalog payload. Each entry carries ``uses``, the number
    of times it has been logged, which the picker folds into the ordering of
    search and browse as well: your own history outranks the catalog's own idea
    of what is popular.
    """
    limit = request.args.get("limit", type=int) or 12
    limit = max(1, min(limit, 50))

    exercises = [
        {**exercise.to_dict(), "uses": uses}
        for exercise, uses in (
            (get_exercise(exercise_id), uses)
            for exercise_id, uses in recent_exercise_usage(limit)
        )
        if exercise is not None
    ]
    return jsonify({"exercises": exercises})


@bp.get("/exercises/<exercise_id>")
def get_exercise_detail(exercise_id: str):
    """One exercise in full: instructions plus absolute image URLs."""
    exercise = get_exercise(exercise_id)
    if exercise is None:
        return jsonify({"error": f"Unknown exercise: {exercise_id!r}."}), 404
    return jsonify({"exercise": exercise.to_detail_dict(_image_base())})


@bp.get("/exercises/<exercise_id>/last-sets")
def get_last_sets(exercise_id: str):
    """The sets from the most recent session of this movement.

    Backs the ``/log`` grid's prefill. Returns ``{"date": null, "sets": []}``
    when the movement has never been logged, which the page renders as empty
    placeholders rather than an error.
    """
    if get_exercise(exercise_id) is None:
        return jsonify({"error": f"Unknown exercise: {exercise_id!r}."}), 404

    day, sets = last_sets_for_exercise(exercise_id)
    return jsonify(
        {
            "date": day.isoformat() if day else None,
            "sets": [row.to_dict() for row in sets],
        }
    )


@bp.get("/routines")
def get_routines():
    """Every suggested routine, without its exercises' images or instructions.

    The **light** shape, for the same reason ``/api/exercises`` has one: the
    listing needs a name, a focus and a time estimate, and hydrating five
    routines' worth of photographs to render five cards is most of a megabyte
    nobody looked at.
    """
    return jsonify(
        {
            "routines": [
                {
                    key: value
                    for key, value in routine.to_dict().items()
                    if key != "exercises"
                }
                for routine in all_routines()
            ]
        }
    )


@bp.get("/routines/<key>")
def get_routine_detail(key: str):
    """One routine with its exercises hydrated — images, instructions and all.

    One request rather than one per movement: the page shows every exercise at
    once, so six round trips would be six chances to render half a routine.
    """
    routine = get_routine(key)
    if routine is None:
        return jsonify({"error": f"Unknown routine: {key!r}."}), 404

    base = _image_base()
    payload = routine.to_dict()
    for item in payload["exercises"]:
        exercise = get_exercise(item["exercise_id"])
        detail = exercise.to_detail_dict(base)
        item["images"] = detail["images"]
        item["instructions"] = detail["instructions"]
    return jsonify({"routine": payload})


@bp.get("/entries")
def get_entries():
    """List entries, optionally filtered by ``date`` or ``start``/``end``."""
    if "date" in request.args:
        day = _query_date("date")
        start = end = day
    else:
        start = parse_date(request.args["start"], field="start") if "start" in request.args else None
        end = parse_date(request.args["end"], field="end") if "end" in request.args else None

    entries = list_entries(start, end)
    return jsonify({"entries": [entry.to_dict() for entry in entries]})


@bp.post("/entries")
def create_entry():
    """Create a workout entry and its sets from a JSON body.

    ``sets`` is an **array of set objects**, not a count. Three bare sets are
    ``[{}, {}, {}]``. The integer form Phase 3 accepted is gone: there were no
    external consumers before Phase 6 deploys, and this was the last cheap
    moment to make the break.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        raise ValidationError("A JSON body is required.")

    entry = add_entry(
        payload.get("date"),
        payload.get("exercise_id"),
        payload.get("sets"),
    )
    return jsonify({"entry": entry.to_dict()}), 201


@bp.delete("/entries/<int:entry_id>")
def remove_entry(entry_id: int):
    """Delete a workout entry by id."""
    if not delete_entry(entry_id):
        return jsonify({"error": "Entry not found."}), 404
    return jsonify({"deleted": entry_id})


@bp.get("/calendar")
def get_calendar():
    """Return ``{iso_date: total_sets}`` for a month (``year``/``month`` args)."""
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month
    if not 1 <= month <= 12:
        return jsonify({"error": "'month' must be between 1 and 12."}), 400

    start, end = month_bounds(year, month)
    return jsonify({"year": year, "month": month, "days": sets_by_date(start, end)})


@bp.get("/summary/week")
def get_weekly_summary():
    """Weekly muscle-coverage summary for the week containing ``date``.

    ``experience``, ``sessions`` and ``minutes`` carry the Phase 6 trainer setup
    and decide what each group's target is. The resolved profile comes back in
    the payload, so the page renders the targets it was graded against.
    """
    day = _query_date("date")
    return jsonify(weekly_summary(day, _week_start(), _query_profile()))


@bp.get("/progress/graph")
def get_progress_graph():
    """The training graph: movements as nodes, same-day pairings as edges.

    ``window`` is ``8w`` (default), ``6m`` or ``all``. An unrecognised value
    falls back to the default rather than 400-ing — it arrives from a view
    control, and the honest response to a bad view preference is the usual view.
    Read-only, and the one endpoint Phase 4.5 added.
    """
    return jsonify(
        training_graph(
            request.args.get("window", DEFAULT_WINDOW),
            _query_date("date"),
            _week_start(),
            _query_profile(),
        )
    )


@bp.get("/summary/week/bounds")
def get_week_bounds():
    """Return the start/end dates of the week containing ``date``."""
    start, end = week_bounds(_query_date("date"), _week_start())
    return jsonify({"week_start": start.isoformat(), "week_end": end.isoformat()})
