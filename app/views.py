"""HTML page routes.

Eleven pages. Six are chapters of the book, numbered 00–05 and reachable from
the shelves:

* ``/``           — home: what the app is, and the way in
* ``/how-to-use`` — the idea, and what the colours mean
* ``/calendar``   — month calendar of logged workouts
* ``/log``        — input form for date / exercise / sets
* ``/summary``    — weekly summary with the muscle-coverage body map
* ``/progress``   — the training graph (Phase 4.5)

Five are outside it, rendered with ``bare=True`` so they carry no shelves, no
tab bar and no rest dock: ``/login``, ``/signup``, ``/reset-password``,
``/verify`` and ``/account``.

Pages are server-rendered shells; the dynamic parts are filled in by the
JavaScript modules in ``app/static/js`` talking to the JSON API. ``/`` and
``/how-to-use`` are the exceptions — static, reading nothing.

**Every shell is public, including the chapters.** Bearer tokens live in
``localStorage``, and a browser does not send an ``Authorization`` header on a
navigation, so Flask cannot gate a page render. The page's JS module redirects
to ``/login`` when the API answers 401 (see ``static/js/api.js``). ``/`` renders
a signed-in and a signed-out half and shows one, chosen before first paint.
"""

from __future__ import annotations

from datetime import date

from flask import Blueprint, current_app, render_template, request

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
from .services.graph import DEFAULT_WINDOW as DEFAULT_GRAPH_WINDOW
from .services.graph import WINDOW_LABELS as GRAPH_WINDOW_LABELS
from .services.weeks import week_bounds

bp = Blueprint("views", __name__)


@bp.app_context_processor
def inject_globals() -> dict:
    """Expose muscle metadata and today's date to every template."""
    return {
        "muscle_groups": MUSCLE_GROUPS,
        "muscle_labels": MUSCLE_LABELS,
        "muscle_targets": MUSCLE_TARGETS,
        # Only six groups are subdivided, and regions carry no target — see
        # docs/VOLUME_SCIENCE.md.
        "muscle_regions": MUSCLE_REGIONS,
        "region_labels": REGION_LABELS,
        "today": date.today(),
        # Public by design: the anon key identifies the project to GoTrue and
        # grants nothing on its own. The service-role key is deliberately absent
        # from this dict and must stay that way.
        "supabase": {
            "url": current_app.config.get("SUPABASE_URL") or "",
            "anon_key": current_app.config.get("SUPABASE_ANON_KEY") or "",
        },
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


#: Pages outside the book. No chapter number, no shelf, no tab bar — they are
#: not sections of the product, and `sections` in base.html never learns about
#: them. All five are public shells: bearer tokens mean Flask cannot read an
#: Authorization header on a navigation, so gating happens in the page's JS.
@bp.get("/login")
def login_page():
    """Sign in. ``?next=`` carries where the browser was headed."""
    return render_template(
        "login.html", page="login", bare=True, selected_date=_requested_date()
    )


@bp.get("/signup")
def signup_page():
    """Create an account."""
    return render_template(
        "signup.html", page="signup", bare=True, selected_date=_requested_date()
    )


@bp.get("/reset-password")
def reset_password_page():
    """Both halves of the reset flow.

    Which half renders is decided client-side: Supabase sends the recovery token
    back in the URL **fragment**, which never reaches this function. That is the
    point — the token stays out of the server's access log.
    """
    return render_template(
        "reset_password.html",
        page="reset-password",
        bare=True,
        selected_date=_requested_date(),
    )


@bp.get("/verify")
def verify_page():
    """Landing page for the email confirmation link."""
    return render_template(
        "verify.html", page="verify", bare=True, selected_date=_requested_date()
    )


@bp.get("/account")
def account_page():
    """Email, sign out, and delete account.

    Deletion lives here rather than on ``/`` because ``/`` is one screen and new
    content there has to earn its height or replace something.
    """
    return render_template(
        "account.html", page="account", bare=True, selected_date=_requested_date()
    )
