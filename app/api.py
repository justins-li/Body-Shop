"""JSON API consumed by the front-end JavaScript.

All endpoints are namespaced under ``/api`` and return JSON.  Errors use the
shape ``{"error": "message"}`` with an appropriate status code.
"""

from __future__ import annotations

import functools
from datetime import date

from flask import Blueprint, current_app, g, jsonify, request

from .exercises import all_exercises, get_exercise
from .routines import all_routines, get_routine
from .models import (
    delete_user,
    ensure_user,
    get_trainer_setup,
    get_user,
    set_trainer_setup,
    ValidationError,
    add_entry,
    delete_entry,
    last_sets_for_exercise,
    list_entries,
    parse_date,
    recent_exercise_usage,
    sets_by_date,
)
from .services.auth import AuthError, decode_token, delete_auth_user
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


def _user_profile() -> TrainerProfile:
    """The signed-in account's trainer setup.

    The Phase 5 carryover: this used to read three query parameters, because
    Phase 6 shipped before there was a user row to hang the setup off. There is
    one now, and it is the only source — a client cannot override the targets it
    is graded against, so the summary and the graph cannot be made to disagree
    about one week.

    An account that has never chosen resolves to the default profile, which is
    the pre-Phase-6 grading exactly. ``resolve_profile`` clamps and falls back
    rather than raising, so a value stored before a bound was tuned shows the
    usual targets rather than blanking the page.
    """
    stored = get_trainer_setup(g.user_id) or {}
    return resolve_profile(
        stored.get("experience"),
        stored.get("sessions_per_week"),
        stored.get("minutes_per_session"),
    )


def _unauthorised():
    """The one 401 this app produces.

    ``WWW-Authenticate: Bearer`` is what lets api.js tell this apart from a
    validation 400 without parsing prose. The body says the same thing for every
    cause — expired, forged, wrong project — because a 401 that distinguishes
    them is a small oracle and no client needs the distinction.
    """
    response = jsonify({"error": "Sign in to continue."})
    response.headers["WWW-Authenticate"] = "Bearer"
    return response, 401


def require_user(view):
    """Verify the bearer token, mirror the user, and set ``g.user_id``.

    The Flask glue for :mod:`app.services.auth`, and it lives here rather than
    there because it touches ``request``, ``g`` and ``current_app`` — which the
    layer rule calls HTTP.

    Note that this **writes** on a GET: ``ensure_user`` provisions the mirror row
    on first contact, since Supabase sends no signup webhook.
    """

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return _unauthorised()

        try:
            claims = decode_token(
                token.strip(),
                supabase_url=current_app.config.get("SUPABASE_URL") or "",
                jwt_secret=current_app.config.get("SUPABASE_JWT_SECRET"),
            )
        except AuthError:
            return _unauthorised()

        ensure_user(claims.sub, claims.email)
        g.user_id = claims.sub
        return view(*args, **kwargs)

    return wrapped


# Public, deliberately. The catalog and the routines are public-domain data
# that ship in the repo, and week bounds are arithmetic over a query parameter;
# gating any of them would leave /login unable to render.
@bp.get("/exercises")
def get_exercises():
    """The whole catalog, in its light shape.

    Instructions and images are omitted — they quadruple the payload, and the
    picker filters the catalog client-side, so it wants the smallest thing it
    can search over. ``/api/exercises/<id>`` serves the rest on demand.
    """
    return jsonify({"exercises": [e.to_dict() for e in all_exercises()]})


@bp.get("/exercises/recent")
@require_user
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
            for exercise_id, uses in recent_exercise_usage(g.user_id, limit)
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
@require_user
def get_last_sets(exercise_id: str):
    """The sets from the most recent session of this movement.

    Backs the ``/log`` grid's prefill. Returns ``{"date": null, "sets": []}``
    when the movement has never been logged, which the page renders as empty
    placeholders rather than an error.
    """
    if get_exercise(exercise_id) is None:
        return jsonify({"error": f"Unknown exercise: {exercise_id!r}."}), 404

    day, sets = last_sets_for_exercise(g.user_id, exercise_id)
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
@require_user
def get_entries():
    """List entries, optionally filtered by ``date`` or ``start``/``end``."""
    if "date" in request.args:
        day = _query_date("date")
        start = end = day
    else:
        start = parse_date(request.args["start"], field="start") if "start" in request.args else None
        end = parse_date(request.args["end"], field="end") if "end" in request.args else None

    entries = list_entries(g.user_id, start, end)
    return jsonify({"entries": [entry.to_dict() for entry in entries]})


@bp.post("/entries")
@require_user
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
        g.user_id,
        payload.get("date"),
        payload.get("exercise_id"),
        payload.get("sets"),
    )
    return jsonify({"entry": entry.to_dict()}), 201


@bp.delete("/entries/<int:entry_id>")
@require_user
def remove_entry(entry_id: int):
    """Delete a workout entry by id."""
    if not delete_entry(g.user_id, entry_id):
        return jsonify({"error": "Entry not found."}), 404
    return jsonify({"deleted": entry_id})


@bp.get("/calendar")
@require_user
def get_calendar():
    """Return ``{iso_date: total_sets}`` for a month (``year``/``month`` args)."""
    today = date.today()
    year = request.args.get("year", type=int) or today.year
    month = request.args.get("month", type=int) or today.month
    if not 1 <= month <= 12:
        return jsonify({"error": "'month' must be between 1 and 12."}), 400

    start, end = month_bounds(year, month)
    return jsonify({"year": year, "month": month, "days": sets_by_date(g.user_id, start, end)})


@bp.get("/summary/week")
@require_user
def get_weekly_summary():
    """Weekly muscle-coverage summary for the week containing ``date``.

    Targets come from the account's stored trainer setup — see
    ``GET /api/profile``. The resolved profile comes back in the payload, so the
    page renders the targets it was graded against rather than deriving its own.
    """
    day = _query_date("date")
    return jsonify(weekly_summary(g.user_id, day, _week_start(), _user_profile()))


@bp.get("/progress/graph")
@require_user
def get_progress_graph():
    """The training graph: movements as nodes, same-day pairings as edges.

    ``window`` is ``8w`` (default), ``6m`` or ``all``. An unrecognised value
    falls back to the default rather than 400-ing — it arrives from a view
    control, and the honest response to a bad view preference is the usual view.
    Read-only, and the one endpoint Phase 4.5 added.
    """
    return jsonify(
        training_graph(
            g.user_id,
            request.args.get("window", DEFAULT_WINDOW),
            _query_date("date"),
            _week_start(),
            _user_profile(),
        )
    )


@bp.get("/summary/week/bounds")
def get_week_bounds():
    """Return the start/end dates of the week containing ``date``."""
    start, end = week_bounds(_query_date("date"), _week_start())
    return jsonify({"week_start": start.isoformat(), "week_end": end.isoformat()})


@bp.get("/me")
@require_user
def get_me():
    """The signed-in user.

    Exists so the client can confirm a token server-side rather than trusting
    its own decode of it. The mirror row is guaranteed present by the time this
    runs — ``require_user`` provisioned it.
    """
    return jsonify({"user": get_user(g.user_id)})


@bp.get("/profile")
@require_user
def get_profile():
    """The account's trainer setup, resolved, with its targets.

    ``configured`` says whether the account has ever chosen one. It is a fact
    about storage rather than about training, which is why it rides beside the
    profile instead of inside it — ``TrainerProfile`` describes a week's targets
    and has no business knowing where its inputs came from. The first-run dialog
    is the one reader: an account that has answered is never asked again, on any
    device.
    """
    configured = get_trainer_setup(g.user_id) is not None
    return jsonify({"profile": _user_profile().to_dict(), "configured": configured})


@bp.put("/profile")
@require_user
def put_profile():
    """Store the account's trainer setup.

    **Clamps rather than 400s**, for the reason the query string did: these
    arrive from a settings control, and the honest response to an out-of-range
    number is the nearest one that works. The *resolved* values are what get
    stored, so the column can never hold a setup the app would refuse to use,
    and the echoed profile is what the controls settle on — a value corrected on
    the way in corrects itself on screen rather than sitting there disagreeing
    with the bars it produced.
    """
    body = request.get_json(silent=True) or {}
    profile = resolve_profile(
        body.get("experience"),
        body.get("sessions_per_week"),
        body.get("minutes_per_session"),
    )
    set_trainer_setup(
        g.user_id,
        profile.experience.key,
        profile.plan.sessions_per_week,
        profile.plan.minutes_per_session,
    )
    return jsonify({"profile": profile.to_dict(), "configured": True})


@bp.delete("/account")
@require_user
def remove_account():
    """Delete the signed-in account: local rows first, then the auth record.

    **The order is deliberate.** If the Supabase call fails, the account
    survives with no data — recoverable, retryable, and the response says so.
    Supabase-first would risk the opposite: the auth record gone and the rows
    orphaned behind an account that can never sign in again to delete them.

    This is the one place Flask holds a Supabase credential. The login path
    holds none — the browser talks to GoTrue directly — but a user cannot delete
    their own auth record with the anon key, and there is no way around that.
    """
    service_key = current_app.config.get("SUPABASE_SERVICE_ROLE_KEY")
    if not service_key:
        # Checked before touching anything, so a misconfigured deployment
        # refuses rather than half-deleting an account.
        return jsonify(
            {"error": "Account deletion is not configured on this server."}
        ), 503

    user_id = g.user_id
    # One statement: workout_entry and workout_set both cascade from here.
    delete_user(user_id)

    try:
        delete_auth_user(
            user_id,
            supabase_url=current_app.config.get("SUPABASE_URL") or "",
            service_role_key=service_key,
        )
    except AuthError:
        # The data is gone, which is the part the user asked for and the part
        # that matters for privacy. Say plainly that the sign-in record is not.
        return jsonify({"deleted": True, "auth_record_removed": False})

    return jsonify({"deleted": True, "auth_record_removed": True})
