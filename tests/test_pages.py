"""Smoke tests for the four HTML pages."""

import re

import pytest

from app.exercises import DEFAULT_MUSCLE_SCHEME, MUSCLE_GROUPS, MUSCLE_SCHEMES


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/", b"Every set."),
        ("/calendar", b"What you trained"),
        ("/log", b"New entry"),
        ("/summary", b"Sets by split"),
        ("/progress", b"Where your training lives"),
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
    assert "js/calendar.js" not in body
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
    """Rows are built by log.js; the page ships the container and the controls."""
    body = client.get("/log").data.decode()
    for marker in ('id="set-grid"', 'id="add-set"', 'id="weight-unit"'):
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
    for field in ('id="entry-date"', 'id="exercise-id"', 'id="set-grid"'):
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


@pytest.mark.parametrize("path", ["/", "/calendar", "/log", "/summary", "/progress"])
def test_every_page_ships_the_rest_timer_strip(client, path):
    """The countdown moved into `base.html` in Phase 4.5.

    It used to live on `/log` alone, which killed a rest the moment you looked
    at the calendar. The strip is now shared, and `timer.js` persists a deadline
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
    for path in ("/", "/calendar", "/summary"):
        assert "data-timer-duration" not in client.get(path).data.decode()
