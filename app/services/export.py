"""Turn a user's log into CSV.

Pure: it takes entries and returns text. No SQL, no Flask, no request context —
so the cases that matter (nulls, warm-ups, ordering, escaping) are testable
without a client, and the *SQL only in models.py* rule needs no exception.

**One row per set, warm-ups included.** Excluding warm-ups is a *grading* rule:
it keeps them off the muscle map, where counting them would inflate the week.
An export is the raw record of what happened, and dropping a set from it would
misstate the session.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date

from ..models import WorkoutEntry

#: The header row, in order.
#:
#: ``weight_kg`` names its unit on purpose. Kilograms are what is stored and
#: what is exported; ``kg``/``lb`` is a display preference that lives only in
#: ``app/static/js/ui.js``, and a file someone keeps for years must not be
#: ambiguous about which one it holds.
EXPORT_COLUMNS: tuple[str, ...] = (
    "entry_id",
    "date",
    "exercise_id",
    "exercise",
    "set_number",
    "set_type",
    "weight_kg",
    "reps",
    "rpe",
)


def _cell(value: object) -> str:
    """Render one value.

    ``None`` is an empty cell and ``0`` is ``0``. The two are different facts —
    "I added no weight" against "I did not write it down" — and a falsy check
    would collapse them, which is the bug the ``is None`` guards elsewhere in
    the app exist to prevent.
    """
    return "" if value is None else str(value)


def entries_to_csv(entries: Iterable[WorkoutEntry]) -> str:
    """Render ``entries`` and their sets as CSV text.

    Sorted oldest first, then by entry, then by set number. ``list_entries``
    returns newest first because that is what a day panel wants; a file someone
    opens in a spreadsheet reads forwards.
    """
    buffer = io.StringIO()
    # Explicit terminator: csv.writer defaults to CRLF, and a file that reads
    # cleanly everywhere is worth more here than strict RFC 4180.
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(EXPORT_COLUMNS)

    for entry in sorted(entries, key=lambda item: (item.entry_date, item.id)):
        for row in sorted(entry.set_rows, key=lambda item: item.set_index):
            writer.writerow(
                [
                    entry.id,
                    entry.entry_date.isoformat(),
                    entry.exercise_id,
                    entry.exercise_name,
                    row.set_index,
                    row.set_type,
                    _cell(row.weight),
                    _cell(row.reps),
                    _cell(row.rpe),
                ]
            )

    return buffer.getvalue()


def export_filename(day: date) -> str:
    """Filename for a download taken on ``day``."""
    return f"bodyshop-export-{day.isoformat()}.csv"
