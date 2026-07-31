"""HTML page routes.

Six pages, numbered as chapters by the shelf navigation in ``base.html``:

* ``/``            — home: what the app is, and the way in
* ``/how-to-use``  — the explainer: the idea, and what the colours mean
* ``/routines``    — suggested sessions, each with a one-tap log (Phase 8.1)
* ``/log``         — input form for date / exercise / sets
* ``/summary``     — the week: body map, trainer setup, and the calendar strip
* ``/progress``    — the training graph (Phase 4.5)

``/calendar`` was a seventh until Phase 8.3 folded it into ``/summary``; it
survives as a redirect so shared ``?date=`` links still land on the right week.

Pages are server-rendered shells; the dynamic parts are filled in by the
JavaScript modules in ``app/static/js`` talking to the JSON API. ``/`` and
``/how-to-use`` are the exceptions — static, reading nothing. ``/`` is the one
page that renders identically for a visitor and a user. When auth arrives it
becomes the signed-out half of a split (see docs/ROADMAP.md, Phase 5); the
calendar already lives at its own URL so that change stays additive.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, redirect, render_template, request, url_for

from .exercises import (
    DEFAULT_MUSCLE_SCHEME,
    MUSCLE_GROUPS,
    MUSCLE_LABELS,
    MUSCLE_REGIONS,
    MUSCLE_SCHEMES,
    MUSCLE_TARGETS,
    REGION_LABELS,
    all_exercises,
    scheme_map,
)
from .models import parse_date
from .routines import all_routines
from .services.graph import DEFAULT_WINDOW as DEFAULT_GRAPH_WINDOW
from .services.graph import WINDOW_LABELS as GRAPH_WINDOW_LABELS
from .services.weeks import week_bounds
from .training import (
    DEFAULT_PROFILE,
    MAX_MINUTES,
    MAX_SESSIONS,
    MIN_MINUTES,
    MIN_SESSIONS,
    level_options,
)

bp = Blueprint("views", __name__)


@bp.app_context_processor
def inject_globals() -> dict:
    """Expose muscle metadata and today's date to every template."""
    return {
        "muscle_groups": MUSCLE_GROUPS,
        "muscle_labels": MUSCLE_LABELS,
        # The trainer setup's vocabulary, needed by *every* page rather than
        # only /summary: the first-run dialog lives in base.html, and it has to
        # offer the same three levels the settings control does.
        **_trainer_setup_context(),
        # The *baseline* targets, which is all a server-rendered shell can know:
        # the trainer setup lives in the browser until Phase 5 gives it a user
        # row to sit on, so `summary.js` overwrites these once it has fetched
        # the week. They are here so the skeleton reads as numbers rather than
        # blanks before that lands.
        "muscle_targets": MUSCLE_TARGETS,
        # Only six groups are subdivided, and regions carry no target — see
        # docs/VOLUME_SCIENCE.md.
        "muscle_regions": MUSCLE_REGIONS,
        "region_labels": REGION_LABELS,
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


@bp.get("/how-to-use")
def how_page():
    """Chapter 01 — purpose, the sequence, and what the colours mean.

    Static, like ``/``. This is the explainer that used to sit below the landing
    page; once ``/`` became a single screen it needed a chapter of its own,
    which is also what makes it a shelf rather than a scroll.
    """
    return render_template("how.html", page="how", selected_date=_requested_date())


@bp.get("/routines")
def routines_page():
    """Suggested routines — Phase 8.1.

    Server-rendered in full: routines are static server data, so there is
    nothing to wait for. Only the *chosen* routine costs a request, for the
    photographs and instructions its exercises carry.
    """
    return render_template(
        "routines.html",
        page="routines",
        selected_date=_requested_date(),
        routines=all_routines(),
    )


@bp.get("/calendar")
def calendar_page():
    """Retired in Phase 8.3 — redirects to the weekly summary.

    A whole chapter for a month grid was more room than the feature earned: it
    answered "what did I do that day", which the summary's own entry list
    already answers for the week you are reading. The grid itself survives as a
    strip on ``/summary`` that expands to a month and collapses again.

    This route stays as a redirect rather than a 404 because ``?date=`` links to
    it are the app's own shared state, and every page honours it — so an old
    link still lands on the right week.
    """
    return redirect(
        url_for("views.summary_page", date=_requested_date().isoformat()), code=301
    )


@bp.get("/log")
def log_page():
    """Workout input form plus the list of entries for the chosen day.

    The catalog is **not** passed to the template. At 873 movements the old
    radio list is neither renderable nor usable, so ``log.js`` fetches
    ``/api/exercises`` once and drives the picker client-side.
    """
    day = _requested_date()
    return render_template(
        "log.html",
        page="log",
        selected_date=day,
        exercise_count=len(all_exercises()),
    )


def _trainer_setup_context() -> dict:
    """Template context for the trainer-setup control (Phase 6).

    The bounds travel with the options so the markup's ``min``/``max`` cannot
    drift from what :func:`app.training.resolve_profile` will clamp to.
    """
    return {
        "experience_levels": level_options(),
        "default_profile": DEFAULT_PROFILE.to_dict(),
        "session_bounds": {
            "min_sessions": MIN_SESSIONS,
            "max_sessions": MAX_SESSIONS,
            "min_minutes": MIN_MINUTES,
            "max_minutes": MAX_MINUTES,
        },
    }


@bp.get("/progress")
def progress_page():
    """The training graph.

    A shell only: ``progress.js`` fetches ``/api/progress/graph`` and draws to a
    canvas. Nothing here is server-rendered, because there is nothing to render
    without the data — and the page says so rather than showing an empty frame.
    """
    day = _requested_date()
    return render_template(
        "progress.html",
        page="progress",
        selected_date=day,
        windows=GRAPH_WINDOW_LABELS,
        default_window=DEFAULT_GRAPH_WINDOW,
    )


@bp.get("/summary")
def summary_page():
    """Weekly summary with the body map.

    The breakdown's grouping schemes are passed as data rather than baked into
    the JS: ``summary.js`` re-heads the same twelve rows against whichever the
    reader picks, so both halves have to agree on one definition.
    """
    day = _requested_date()
    start, end = week_bounds(day, current_app.config.get("WEEK_STARTS_ON", 1))
    return render_template(
        "summary.html",
        page="summary",
        selected_date=day,
        week_start=start,
        week_end=end,
        muscle_schemes=MUSCLE_SCHEMES,
        default_scheme=DEFAULT_MUSCLE_SCHEME,
        scheme_buckets=scheme_map(),
    )
