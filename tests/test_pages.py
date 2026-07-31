"""Smoke tests for the four HTML pages."""

import pathlib
import re

import pytest

from app.exercises import DEFAULT_MUSCLE_SCHEME, MUSCLE_GROUPS, MUSCLE_SCHEMES


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        # The masthead's own class: the landing page's headline is its wordmark,
        # which appears in every page's header, so structure is the stable marker.
        ("/", b"home-masthead"),
        ("/routines", b"Something to follow"),
        ("/log", b"New entry"),
        ("/summary", b"Sets by split"),
        ("/progress", b"Where your training lives"),
        ("/how-to-use", b"How to use"),
    ],
)
def test_pages_render(client, path, marker):
    """Each marker is unique to its page — the nav links appear on all four."""
    response = client.get(path)
    assert response.status_code == 200
    assert marker in response.data


def test_home_page_needs_no_api(client):
    """`/` is static: it must not depend on a page module or the JSON API."""
    body = client.get("/").data.decode()
    assert "js/routines.js" not in body
    assert "js/summary.js" not in body


def test_home_page_body_map_is_pre_graded(client):
    """The macro's `demo` argument bakes grading into the markup, since the home
    page runs no JS to paint it."""
    body = client.get("/").data.decode()
    assert 'class="muscle is-worked"' in body
    assert "--level:" in body


def test_summary_body_map_is_not_pre_graded(client):
    """Summary passes no `demo`, so summary.js owns every region's state."""
    body = client.get("/summary").data.decode()
    assert "is-worked" not in body
    assert "--level:" not in body


def test_log_page_renders_a_picker_shell_not_the_catalog(client):
    """873 movements cannot be radio buttons: log.js fills these panels."""
    body = client.get("/log").data.decode()
    for marker in ('data-tab="recent"', 'data-tab="search"', 'data-tab="browse"',
                   'id="exercise-id"', 'id="browse-muscle"'):
        assert marker in body

    # The catalog itself must not be server-rendered.
    assert "Barbell Bench Press" not in body
    assert body.count('data-panel="') == 3


def test_log_page_renders_a_set_grid_shell(client):
    """The page ships a mount point; `setgrid.js` builds everything inside it.

    Phase 8.2 moved the header, the add/repeat buttons and the added-weight
    toggle into the component, because a routine's quick-log mounts the same
    grid into a dialog and a grid needing a server-rendered shell could not be
    the same grid in both places.
    """
    body = client.get("/log").data.decode()
    for marker in ('id="set-grid-mount"', 'id="weight-unit"'):
        assert marker in body

    # The old flat-count stepper is gone, not hidden.
    assert 'id="entry-sets"' not in body
    assert 'data-step="-1"' not in body


def test_log_page_keeps_every_submitted_field_inside_the_form(client):
    """`onSubmit` builds the entry from a `FormData`, so a control outside the
    form submits nothing.

    Phase 4.5 moved the date into the page header for density and broke every
    submit with "Pick a date first" — the field was still on screen and still
    filled in, which is what made it hard to see.
    """
    body = client.get("/log").data.decode()
    start = body.index('<form id="entry-form"')
    end = body.index("</form>", start)
    for field in ('id="entry-date"', 'id="exercise-id"', 'id="set-grid-mount"'):
        assert start < body.index(field) < end, field


def test_log_page_leads_with_recent_and_browse_and_demotes_search(client):
    """Browse is a way in; search is a fallback, so it is only an icon."""
    body = client.get("/log").data.decode()
    tabs = re.findall(r'data-tab="(\w+)"', body)
    assert tabs == ["recent", "browse", "search"]

    # The two named tabs carry visible labels; search carries a glyph and an
    # accessible name only.
    assert ">Recent</button>" in body
    assert ">Browse</button>" in body
    assert 'class="picker-tab picker-tab-icon' in body
    assert "Search all 873 movements" in body

    # Recent is still what opens.
    assert body.count('aria-selected="true"') == 1


def test_log_page_browse_offers_every_muscle_group(client):
    body = client.get("/log").data.decode()
    for muscle in MUSCLE_GROUPS:
        assert f'<option value="{muscle}">' in body


def test_summary_page_offers_every_grouping_scheme(client):
    body = client.get("/summary").data.decode()
    for scheme in MUSCLE_SCHEMES:
        assert f'<option value="{scheme.key}"' in body
        for bucket in scheme.buckets:
            # Whitespace-insensitive: the two attributes wrap in the template.
            pattern = (
                rf'data-scheme="{re.escape(scheme.key)}"\s+'
                rf'data-bucket="{re.escape(bucket.key)}"'
            )
            assert re.search(pattern, body), (scheme.key, bucket.key)

    # The default is selected server-side; summary.js re-heads the list to match.
    assert re.search(
        rf'<option value="{DEFAULT_MUSCLE_SCHEME}"[^>]*\bselected\b', body
    )


def test_summary_page_renders_each_muscle_row_once_whatever_the_scheme(client):
    """Schemes re-head the same twelve rows; duplicating them would double volume.

    Matched on the row's structure rather than its full class attribute: this
    is an assertion about how many rows exist, and pinning the utility classes
    beside them made a restyle look like a correctness failure.
    """
    body = client.get("/summary").data.decode()
    for muscle in MUSCLE_GROUPS:
        assert len(re.findall(
            rf'class="muscle-row"\s+data-muscle="{re.escape(muscle)}"', body
        )) == 1, muscle


def test_summary_page_ships_a_region_skeleton_for_the_six_subdivided_groups(client):
    body = client.get("/summary").data.decode()
    for muscle in ("chest", "shoulders", "back", "triceps", "hamstrings", "calves"):
        assert f'class="region-group" data-muscle="{muscle}"' in body
    for region in ("chest_upper", "delt_front", "delt_side", "delt_rear", "soleus"):
        assert f'data-region="{region}"' in body

    # Groups without evidence for subdivision must not appear in the panel.
    for muscle in ("biceps", "abs", "quads", "glutes", "traps", "forearms"):
        assert f'class="region-group" data-muscle="{muscle}"' not in body


def test_summary_page_states_no_region_targets(client):
    """The panel must not imply a per-region number the evidence lacks."""
    body = client.get("/summary").data.decode()
    assert "No region targets" in body


def test_summary_page_contains_every_muscle_region(client):
    body = client.get("/summary").data.decode()
    for muscle in MUSCLE_GROUPS:
        assert f'data-muscle="{muscle}"' in body


def test_front_and_back_views_show_different_muscle_groups(client):
    body = client.get("/summary").data.decode()
    # Scope to each <svg>; the breakdown list below them repeats every slug.
    front = body.split('data-view="front"')[1].split("</svg>")[0]
    back = body.split('data-view="back"')[1].split("</svg>")[0]

    front_groups = set(re.findall(r'data-muscle="(\w+)"', front))
    back_groups = set(re.findall(r'data-muscle="(\w+)"', back))

    assert front_groups == {"chest", "abs", "shoulders", "biceps", "forearms", "quads"}
    assert back_groups == {"back", "traps", "triceps", "glutes", "hamstrings", "calves"}

    # The split is the point: neither figure repeats the other's information.
    assert not front_groups & back_groups
    assert front_groups | back_groups == set(MUSCLE_GROUPS)


def test_summary_page_uses_requested_week(client):
    body = client.get("/summary?date=2026-07-28").data.decode()
    assert "Jul 27" in body and "Aug 02" in body


def test_bad_date_falls_back_to_today(client):
    assert client.get("/summary?date=nonsense").status_code == 200


def test_progress_page_ships_a_canvas_and_a_written_fallback(client):
    """The graph is drawn to a canvas, so the finding it exists to show is also
    written out — that list is the whole page before there is enough history."""
    body = client.get("/progress").data.decode()
    for marker in ('id="graph-canvas"', 'id="orphan-list"', 'id="window-select"'):
        assert marker in body

    # Nothing about the graph is server-rendered; progress.js owns all of it.
    assert "Barbell Squat" not in body


@pytest.mark.parametrize("path", ["/", "/routines", "/log", "/summary", "/progress"])
def test_every_page_ships_the_rest_timer_strip(client, path):
    """The countdown moved into `base.html` in Phase 4.5.

    It used to live on `/log` alone, which killed a rest the moment you looked
    at the routines. The strip is now shared, and `timer.js` persists a deadline
    so the count survives the navigation.
    """
    body = client.get(path).data.decode()
    for marker in ('id="rest-timer"', "data-timer-readout", "data-timer-toggle"):
        assert marker in body


def test_only_log_ships_the_rest_duration_select(client):
    """Choosing a rest length is a setup decision, so it stays beside the sets.

    It also has to appear exactly once: `timer.js` binds the first one it finds
    in the document, so a second copy would be silently dead.
    """
    assert client.get("/log").data.decode().count("data-timer-duration") == 1
    for path in ("/", "/routines", "/summary"):
        assert "data-timer-duration" not in client.get(path).data.decode()


# ---- The shelf navigation --------------------------------------------------


def test_the_current_page_is_never_a_shelf_beside_itself(client):
    """Leftmost is Home; the right stack is every section except this one."""
    for path, key in [("/", "home"), ("/how-to-use", "how"), ("/routines", "routines"),
                      ("/log", "log"), ("/summary", "summary"), ("/progress", "progress")]:
        body = client.get(path).data.decode()
        shelves = re.findall(r'class="shelf(?: shelf-home)?" data-nav\s+href="([^"?]+)', body)
        assert path not in shelves, path
        # Home leads on every page but its own.
        assert ("/" in shelves) == (key != "home"), path
        # Five sections, minus the one being read.
        assert len(shelves) == 5, (path, shelves)


def test_chapter_numbers_are_fixed_to_the_section(client):
    """A chapter that renumbers by position is not a chapter you can navigate by."""
    expected = {"/how-to-use": "01", "/routines": "02", "/log": "03",
                "/summary": "04", "/progress": "05"}
    for path in ("/", "/log", "/progress"):
        body = client.get(path).data.decode()
        marks = dict(re.findall(
            r'class="shelf" data-nav\s+href="([^"?]+)[^>]*>\s*<span class="shelf-top[^>]*>\[(\d\d)\]',
            body))
        for href, chapter in marks.items():
            assert expected[href] == chapter, (path, href, chapter)


def test_there_is_no_top_header(client):
    body = client.get("/").data.decode()
    assert "app-header" not in body
    assert 'class="shelf' in body


def _shelf_names(body, side):
    """Section names on one side, in the order they are rendered."""
    if side == "left":
        chunk = body.split("shelf-stack-left")[1].split("</nav>")[0]
    else:
        chunk = body.split('aria-label="Later sections"')[1].split("</nav>")[0]
    return re.findall(r'shelf-name">([^<]+)<', chunk)


def test_chapters_split_around_the_open_one_and_keep_their_side(client):
    """Earlier chapters stack left, later ones right — never reshuffled."""
    order = ["Home", "How to use", "Routines", "Log workout", "Weekly summary", "Graph"]
    for path, name in [("/", "Home"), ("/how-to-use", "How to use"),
                       ("/routines", "Routines"), ("/log", "Log workout"),
                       ("/summary", "Weekly summary"), ("/progress", "Graph")]:
        body = client.get(path).data.decode()
        cut = order.index(name)
        assert _shelf_names(body, "left") == order[:cut], path
        assert _shelf_names(body, "right") == order[cut + 1:], path


def test_every_shelf_carries_a_symbol(client):
    body = client.get("/log").data.decode()
    # Five shelves on /log, each with one drawn mark above its name.
    assert body.count('class="shelf-mark"') == 5
    assert body.count("<path d=") >= 5


def test_the_chapter_mark_sits_directly_above_its_name(client):
    body = client.get("/log").data.decode()
    first = body.split('class="shelf-mid"')[1]
    assert first.index("shelf-index") < first.index("shelf-name")


# ---- Theme -----------------------------------------------------------------


def test_every_page_carries_the_theme_toggle(client):
    for path in ("/", "/how-to-use", "/routines", "/log", "/summary", "/progress"):
        body = client.get(path).data.decode()
        assert 'id="theme-toggle"' in body, path
        assert "js/theme.js" in body, path


def test_the_theme_is_applied_before_the_stylesheet_loads(client):
    """A deferred script would paint one theme and then flip to the other."""
    body = client.get("/").data.decode()
    assert body.index("bodyshop:theme") < body.index("css/styles.css")
    # Blocking, not a module: `type="module"` is deferred by definition.
    head = body.split("</head>")[0]
    assert "bodyshop:theme" in head
    prepaint = head[head.index("bodyshop:theme") - 400:head.index("bodyshop:theme")]
    assert "type=\"module\"" not in prepaint


def test_both_themes_and_both_ramps_are_compiled(client):
    """The ramp inverts with the ground, so each theme needs its own values."""
    css = (pathlib.Path(__file__).parent.parent
           / "app" / "static" / "css" / "styles.css").read_text(encoding="utf-8")
    assert "bodyshop-dark" in css
    # Cream ramp (pale -> deep) and dark ramp (dim -> lit) both present.
    assert "#4f9068" in css and "#14432a" in css
    assert "#428262" in css and "#5fd98a" in css


def test_how_to_use_credits_both_leads_and_offers_contact(client):
    body = client.get("/how-to-use").data.decode()
    for name in ("Justin Li", "Owen Zhang"):
        assert name in body
    assert body.count("Lead developer") == 2
    assert "Have questions?" in body
    assert "mailto:" in body
    # Portraits degrade to initials rather than a broken image.
    assert body.count("this.remove()") == 2


# ---- Phase 6 / 6.5 shells --------------------------------------------------


def test_summary_ships_the_trainer_setup_controls(client):
    """The three controls that decide every target on the page below them."""
    body = client.get("/summary").data.decode()
    for marker in (
        'id="experience-select"',
        'id="sessions-input"',
        'id="minutes-input"',
        'id="setup-effect"',
    ):
        assert marker in body, marker


def test_summary_offers_every_experience_level(client):
    from app.training import EXPERIENCE_LEVELS

    body = client.get("/summary").data.decode()
    for level in EXPERIENCE_LEVELS:
        assert f'value="{level.key}"' in body


def test_session_inputs_carry_the_servers_own_bounds(client):
    """The markup's min/max must not drift from what `resolve_profile` clamps
    to, so they are rendered from the same constants."""
    from app.training import MAX_MINUTES, MAX_SESSIONS, MIN_MINUTES, MIN_SESSIONS

    body = client.get("/summary").data.decode()
    assert f'min="{MIN_SESSIONS}"' in body and f'max="{MAX_SESSIONS}"' in body
    assert f'min="{MIN_MINUTES}"' in body and f'max="{MAX_MINUTES}"' in body


def test_the_grid_mount_sits_inside_the_form(client):
    """`onSubmit` reads the entry off a FormData, so everything the grid builds
    has to land inside the form. This broke every submit once already, when the
    date input was moved into the page header for density."""
    body = client.get("/log").data.decode()
    form = body[body.index('id="entry-form"'): body.index("</form>")]
    for marker in ('id="entry-date"', 'id="set-grid-mount"'):
        assert marker in form, marker


# ---- First run, and the graph's new controls (Phase 6.7) -------------------


@pytest.mark.parametrize("path", ["/routines", "/log", "/summary", "/progress"])
def test_app_pages_ship_the_first_run_dialog(client, path):
    """The shell rides on base.html; `onboarding.js` decides whether to open it."""
    body = client.get(path).data.decode()
    assert 'id="first-run"' in body
    assert 'id="first-run-start"' in body
    assert 'id="first-run-skip"' in body


@pytest.mark.parametrize("path", ["/", "/how-to-use"])
def test_static_pages_never_open_the_first_run_dialog(client, path):
    """`/` and `/how-to-use` are static and must render identically for any
    visitor — `/` is also pinned to exactly one screen. The module refuses to
    open on them, and the page key it reads is what enforces it."""
    body = client.get(path).data.decode()
    page = "home" if path == "/" else "how"
    assert f'initOnboarding(document.getElementById("first-run"), "{page}")' in body


def test_first_run_offers_every_experience_level(client):
    from app.training import EXPERIENCE_LEVELS

    body = client.get("/log").data.decode()
    for level in EXPERIENCE_LEVELS:
        assert f'data-level="{level.key}"' in body


def test_first_run_dialog_starts_closed(client):
    """A `<dialog>` without `open` is display:none, so a browser with JS off —
    or a returning user — never sees it at all."""
    body = client.get("/log").data.decode()
    dialog = body[body.index('<dialog class="first-run"'):]
    assert " open" not in dialog[: dialog.index(">")]


def test_progress_ships_the_size_control(client):
    body = client.get("/progress").data.decode()
    assert 'id="size-select"' in body
    assert 'value="strength"' in body
    assert 'id="graph-key-load"' in body


def test_progress_no_longer_promises_a_graph_at_fifteen(client):
    """Phase 6.7 replaced the threshold with a count that climbs. The page must
    not still tell a new user the drawing is locked."""
    body = client.get("/progress").data.decode().lower()
    assert "graph_ready" not in body
    assert "starts at one dot" in body


# ---- Routines and the folded calendar (Phase 8) ----------------------------


def test_calendar_redirects_to_the_week_it_was_showing(client):
    """`/calendar` retired in Phase 8.3, but `?date=` links to it are the app's
    own shared state — so an old link still lands on the right week."""
    response = client.get("/calendar?date=2026-07-28")
    assert response.status_code == 301
    assert response.headers["Location"] == "/summary?date=2026-07-28"


def test_the_calendar_is_now_a_strip_on_the_summary(client):
    body = client.get("/summary").data.decode()
    for marker in ('id="calendar-grid"', 'id="calendar-toggle"', 'id="calendar-heading"'):
        assert marker in body, marker


def test_the_strip_starts_collapsed(client):
    """Seven boxes cost one row above the body map; a month would cost six."""
    body = client.get("/summary").data.decode()
    toggle = body[body.index('id="calendar-toggle"'):]
    assert 'aria-expanded="false"' in toggle[: toggle.index(">") + 1]
    assert "Show the month" in body


def test_routines_page_lists_every_routine(client):
    from app.routines import ROUTINES

    body = client.get("/routines").data.decode()
    for routine in ROUTINES:
        assert f'data-routine="{routine.key}"' in body
        assert routine.name in body


def test_routines_show_a_derived_time_estimate(client):
    """Rendered from `estimate_minutes`, so it cannot drift from the exercises."""
    from app.routines import ROUTINES

    body = client.get("/routines").data.decode()
    for routine in ROUTINES:
        assert f"~{routine.minutes} min" in body


def test_routines_page_ships_the_quick_log_dialog(client):
    body = client.get("/routines").data.decode()
    for marker in ('id="quick-log"', 'id="quick-log-grid"', 'id="quick-log-form"'):
        assert marker in body, marker


def test_the_quick_log_mounts_the_same_grid_as_the_log_page(client):
    """Phase 8.2's whole point: one implementation of what a set is.

    Both pages import `setgrid.js`, and neither server-renders a grid of its
    own — a second, simpler grid on the routines page would have been a second
    set of rules about weight modes, warm-ups and units.
    """
    routines = client.get("/routines").data.decode()
    log = client.get("/log").data.decode()
    assert "js/routines.js" in routines and "js/log.js" in log
    # Neither ships rows or a header server-side; the component owns both.
    assert 'class="set-row"' not in routines and 'class="set-row"' not in log


def test_routines_are_reachable_as_chapter_two(client):
    """Calendar's old shelf. Keeping the number meant Log, Weekly summary and
    Graph did not renumber around the change."""
    body = client.get("/log").data.decode()
    assert 'href="/routines' in body
    assert "Routines" in body
