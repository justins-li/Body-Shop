#!/usr/bin/env python3
"""Regenerate ``app/data/exercises.json`` from free-exercise-db.

Body Shop's exercise catalog is vendored from `free-exercise-db
<https://github.com/yuhonas/free-exercise-db>`_ (Unlicense / public domain):
873 movements, each with two photographs showing the start and end position.

This follows the same contract as ``tools/fetch_css_toolchain.py``: the fetch is
pinned to a commit so it is reproducible, and its *output* is committed, so
running the app — in development, in CI, or on a server — never needs this
script or a network connection. Only changing the pin does.

Usage::

    python tools/build_exercise_catalog.py

The images are **not** downloaded. All 1,746 of them come to roughly 85 MB,
which does not belong in a git repository; they are served from jsDelivr at the
same pinned commit (see ``EXERCISE_IMAGE_BASE`` in ``app/config.py``).
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

#: Pinned so the catalog and the CDN images always describe the same revision.
SOURCE_COMMIT = "b0eed061e1c832b3ed815fbaa4b45b3cdc14df49"

SOURCE_URL = (
    "https://raw.githubusercontent.com/yuhonas/free-exercise-db/"
    f"{SOURCE_COMMIT}/dist/exercises.json"
)

REPO = Path(__file__).resolve().parent.parent
TARGET = REPO / "app" / "data" / "exercises.json"

#: free-exercise-db's 17 muscle slugs mapped onto Body Shop's 12 groups.
#:
#: The collapses are anatomical judgements worth stating: the three back regions
#: are one trainable group here; hip abductors are graded as glutes because the
#: gluteus medius does the work; adductors go to quads as the closest tracked
#: thigh group; and the eight neck movements are folded into traps, which is the
#: only group whose silhouette covers them.
MUSCLE_MAP: dict[str, str] = {
    "abdominals": "abs",
    "abductors": "glutes",
    "adductors": "quads",
    "biceps": "biceps",
    "calves": "calves",
    "chest": "chest",
    "forearms": "forearms",
    "glutes": "glutes",
    "hamstrings": "hamstrings",
    "lats": "back",
    "lower back": "back",
    "middle back": "back",
    "neck": "traps",
    "quadriceps": "quads",
    "shoulders": "shoulders",
    "traps": "traps",
    "triceps": "triceps",
}

#: Source records leave equipment null for 77 bodyweight-ish movements.
DEFAULT_EQUIPMENT = "none"

#: Field order in the generated file, chosen so a diff reads top-down.
FIELD_ORDER = (
    "id",
    "name",
    "primary",
    "secondary",
    "equipment",
    "category",
    "level",
    "force",
    "mechanic",
    "images",
    "instructions",
)


def map_muscles(primary: list[str], secondary: list[str]) -> tuple[list[str], list[str]]:
    """Map source muscle slugs onto Body Shop groups, primary winning ties.

    Several movements name two source regions that collapse to one group here —
    "lats" primary alongside "middle back" secondary, say. Dropping the
    duplicate from ``secondary`` matters: without it the group would be counted
    at both the primary and the secondary weight.
    """
    mapped_primary = {MUSCLE_MAP[m] for m in primary}
    mapped_secondary = {MUSCLE_MAP[m] for m in secondary} - mapped_primary
    return sorted(mapped_primary), sorted(mapped_secondary)


def convert(record: dict) -> dict:
    """Turn one free-exercise-db record into a Body Shop catalog entry."""
    primary, secondary = map_muscles(
        record.get("primaryMuscles", []), record.get("secondaryMuscles", [])
    )
    return {
        "id": record["id"],
        "name": record["name"],
        "primary": primary,
        "secondary": secondary,
        "equipment": record.get("equipment") or DEFAULT_EQUIPMENT,
        "category": record["category"],
        "level": record["level"],
        "force": record.get("force"),
        "mechanic": record.get("mechanic"),
        "images": list(record.get("images", [])),
        "instructions": list(record.get("instructions", [])),
    }


def check(entries: list[dict]) -> None:
    """Fail loudly on anything the app's loader would reject at import."""
    ids = [e["id"] for e in entries]
    duplicates = {i for i in ids if ids.count(i) > 1}
    if duplicates:
        raise SystemExit(f"Duplicate exercise ids: {sorted(duplicates)}")

    for entry in entries:
        if not entry["primary"]:
            raise SystemExit(f"{entry['id']}: no primary muscle after mapping.")
        if len(entry["images"]) != 2:
            raise SystemExit(
                f"{entry['id']}: expected 2 images, got {len(entry['images'])}. "
                "The two-frame animation on /log assumes exactly two."
            )


def fetch() -> list[dict]:
    """Download the pinned source catalog."""
    try:
        with urllib.request.urlopen(SOURCE_URL) as response:  # noqa: S310 - pinned https URL
            return json.load(response)
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            # python.org macOS builds ship without a CA bundle until their
            # bundled installer command is run once. Same trap as
            # tools/fetch_css_toolchain.py.
            sys.exit(
                "TLS certificate verification failed.\n"
                "If this is a python.org build on macOS, run:\n"
                '  "/Applications/Python 3.x/Install Certificates.command"\n'
                "or re-run this script with a Python that has a CA bundle."
            )
        raise


def main() -> None:
    print(f"Fetching free-exercise-db @ {SOURCE_COMMIT[:7]}")
    source = fetch()

    entries = sorted((convert(r) for r in source), key=lambda e: e["name"].lower())
    check(entries)

    payload = {
        "source": "https://github.com/yuhonas/free-exercise-db",
        "source_commit": SOURCE_COMMIT,
        "license": "Unlicense (public domain)",
        "exercises": [{k: e[k] for k in FIELD_ORDER} for e in entries],
    }

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")

    groups = sorted({m for e in entries for m in e["primary"] + e["secondary"]})
    print(f"  -> {TARGET.relative_to(REPO)} ({len(entries)} exercises)")
    print(f"  {len(groups)} muscle groups: {', '.join(groups)}")


if __name__ == "__main__":
    main()
