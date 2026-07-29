"""HTML page routes.

Four pages:

* ``/``         — home: what the app is, and the way in
* ``/calendar`` — month calendar of logged workouts
* ``/log``      — input form for date / exercise / sets
* ``/summary``  — weekly summary with the muscle-coverage body map

Pages are server-rendered shells; the dynamic parts are filled in by the
JavaScript modules in ``app/static/js`` talking to the JSON API. ``/`` is the
exception — it is static, reads nothing, and is the one page that renders
identically for a visitor and a user. When auth arrives it becomes the
signed-out half of a split (see docs/ROADMAP.md, Phase 4); the calendar already
lives at its own URL so that change stays additive.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, render_template, request

from .exercises import MUSCLE_GROUPS, MUSCLE_LABELS, MUSCLE_TARGETS, all_exercises
from .models import parse_date
from .services.weeks import week_bounds

bp = Blueprint("views", __name__)


@bp.app_context_processor
def inject_globals() -> dict:
    """Expose muscle metadata and today's date to every template."""
    return {
        "muscle_groups": MUSCLE_GROUPS,
        "muscle_labels": MUSCLE_LABELS,
        "muscle_targets": MUSCLE_TARGETS,
        "today": date.today(),
    }


def _requested_date() -> date:
    """Read an optional ``?date=YYYY-MM-DD`` query arg, defaulting to today."""
    raw = request.args.get("date")
    if not raw:
        return date.today()
    try:
        return parse_date(raw)
    except ValueError:
        return date.today()


@bp.get("/")
def home_page():
    """Landing page. Static — no API calls, no JS module."""
    day = _requested_date()
    return render_template(
        "home.html",
        page="home",
        selected_date=day,
        exercise_count=len(all_exercises()),
    )


@bp.get("/calendar")
def calendar_page():
    """Month calendar. Clicking a day shows what was logged that day."""
    day = _requested_date()
    return render_template(
        "calendar.html",
        page="calendar",
        selected_date=day,
        week_starts_on=current_app.config.get("WEEK_STARTS_ON", 1),
    )


@bp.get("/log")
def log_page():
    """Workout input form plus the list of entries for the chosen day."""
    day = _requested_date()
    return render_template(
        "log.html",
        page="log",
        selected_date=day,
        exercises=all_exercises(),
    )


@bp.get("/summary")
def summary_page():
    """Weekly summary with the body map."""
    day = _requested_date()
    start, end = week_bounds(day, current_app.config.get("WEEK_STARTS_ON", 1))
    return render_template(
        "summary.html",
        page="summary",
        selected_date=day,
        week_start=start,
        week_end=end,
    )
