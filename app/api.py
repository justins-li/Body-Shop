"""JSON API consumed by the front-end JavaScript.

All endpoints are namespaced under ``/api`` and return JSON.  Errors use the
shape ``{"error": "message"}`` with an appropriate status code.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, jsonify, request

from .exercises import all_exercises, get_exercise
from .models import (
    ValidationError,
    add_entry,
    delete_entry,
    list_entries,
    parse_date,
    recent_exercise_usage,
    sets_by_date,
)
from .services.summary import weekly_summary
from .services.weeks import month_bounds, week_bounds

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
    """Create a workout entry from a JSON or form-encoded body."""
    payload = request.get_json(silent=True) or request.form
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
    """Weekly muscle-coverage summary for the week containing ``date``."""
    day = _query_date("date")
    return jsonify(weekly_summary(day, _week_start()))


@bp.get("/summary/week/bounds")
def get_week_bounds():
    """Return the start/end dates of the week containing ``date``."""
    start, end = week_bounds(_query_date("date"), _week_start())
    return jsonify({"week_start": start.isoformat(), "week_end": end.isoformat()})
