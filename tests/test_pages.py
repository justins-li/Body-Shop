"""Smoke tests for the three HTML pages."""

import pytest


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
    for name in (b"Bench press", b"Pull ups", b"Squat"):
        assert name in body


def test_summary_page_contains_every_muscle_region(client):
    body = client.get("/summary").data.decode()
    for muscle in ("chest", "back", "biceps", "triceps", "legs"):
        assert f'data-muscle="{muscle}"' in body


def test_summary_page_uses_requested_week(client):
    body = client.get("/summary?date=2026-07-28").data.decode()
    assert "Jul 27" in body and "Aug 02" in body


def test_bad_date_falls_back_to_today(client):
    assert client.get("/summary?date=nonsense").status_code == 200
