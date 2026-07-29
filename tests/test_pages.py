"""Smoke tests for the three HTML pages."""

import re

import pytest

from app.exercises import MUSCLE_GROUPS


@pytest.mark.parametrize(
    ("path", "marker"),
    [
        ("/", b"Calendar"),
        ("/log", b"Log a workout"),
        ("/summary", b"Weekly summary"),
    ],
)
def test_pages_render(client, path, marker):
    response = client.get(path)
    assert response.status_code == 200
    assert marker in response.data


def test_log_page_lists_every_exercise(client):
    body = client.get("/log").data
    for name in (b"Bench press", b"Pull ups", b"Squat", b"Sit ups"):
        assert name in body


def test_summary_page_contains_every_muscle_region(client):
    body = client.get("/summary").data.decode()
    for muscle in MUSCLE_GROUPS:
        assert f'data-muscle="{muscle}"' in body


def test_front_and_back_views_show_different_muscle_groups(client):
    body = client.get("/summary").data.decode()
    # Scope to each <svg>; the breakdown list below them repeats every slug.
    front = body.split('data-view="front"')[1].split("</svg>")[0]
    back = body.split('data-view="back"')[1].split("</svg>")[0]

    assert set(re.findall(r'data-muscle="(\w+)"', front)) == {
        "chest",
        "abs",
        "biceps",
        "quads",
    }
    assert set(re.findall(r'data-muscle="(\w+)"', back)) == {
        "back",
        "triceps",
        "hamstrings",
    }


def test_summary_page_uses_requested_week(client):
    body = client.get("/summary?date=2026-07-28").data.decode()
    assert "Jul 27" in body and "Aug 02" in body


def test_bad_date_falls_back_to_today(client):
    assert client.get("/summary?date=nonsense").status_code == 200
