"""The CSV export — the "get your data out" half of the privacy obligation.

The writer is pure, so everything interesting about it is tested here without a
client: nulls, warm-ups, ordering and escaping. The endpoint's own tests live at
the foot of the file, and the two-user leak check lives in
tests/test_ownership.py, where a failure is read as a data leak rather than as a
formatting bug.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from app.models import WorkoutEntry, WorkoutSet
from app.services.export import EXPORT_COLUMNS, entries_to_csv, export_filename


def _set(index, **kwargs):
    """A WorkoutSet with everything unrecorded unless named."""
    fields = {"weight": None, "reps": None, "rpe": None, "set_type": "normal"}
    fields.update(kwargs)
    return WorkoutSet(id=f"id{index}", set_index=index, **fields)


def _rows(text):
    """Parse CSV text back into a list of dict rows."""
    return list(csv.DictReader(io.StringIO(text)))


class TestTheWriter:
    def test_the_header_names_every_column_in_order(self):
        text = entries_to_csv([])
        assert text.splitlines()[0] == ",".join(EXPORT_COLUMNS)

    def test_an_empty_log_is_a_header_and_nothing_else(self):
        """Not an error, and not an empty file: the columns are the answer."""
        assert entries_to_csv([]).strip().count("\n") == 0

    def test_one_row_per_set(self):
        entry = WorkoutEntry(
            id=41,
            entry_date=date(2026, 8, 1),
            exercise_id="Barbell_Squat",
            set_rows=(_set(1, weight=100.0, reps=5), _set(2, weight=100.0, reps=5)),
        )
        rows = _rows(entries_to_csv([entry]))
        assert len(rows) == 2
        assert [r["set_number"] for r in rows] == ["1", "2"]
        assert {r["entry_id"] for r in rows} == {"41"}

    def test_warmups_are_exported_and_named(self):
        """This is the raw record, not the graded week.

        Excluding warm-ups is a *grading* rule — it keeps them off the muscle
        map, where counting them would inflate the week. An export that dropped
        them would be lying about what happened in the gym.
        """
        entry = WorkoutEntry(
            id=41,
            entry_date=date(2026, 8, 1),
            exercise_id="Barbell_Squat",
            set_rows=(_set(1, set_type="warmup"), _set(2)),
        )
        rows = _rows(entries_to_csv([entry]))
        assert [r["set_type"] for r in rows] == ["warmup", "normal"]

    def test_unrecorded_values_are_empty_cells(self):
        entry = WorkoutEntry(
            id=1,
            entry_date=date(2026, 8, 1),
            exercise_id="Sit-Up",
            set_rows=(_set(1, reps=15),),
        )
        row = _rows(entries_to_csv([entry]))[0]
        assert row["weight_kg"] == ""
        assert row["rpe"] == ""
        assert row["reps"] == "15"

    def test_zero_is_not_blank(self):
        """`0` and "not recorded" are different facts.

        A bodyweight movement legitimately logs 0 kg added. Rendering that as an
        empty cell would erase the difference between "I added nothing" and "I
        did not write it down".
        """
        entry = WorkoutEntry(
            id=1,
            entry_date=date(2026, 8, 1),
            exercise_id="Pullups",
            set_rows=(_set(1, weight=0.0, reps=0, rpe=0.0),),
        )
        row = _rows(entries_to_csv([entry]))[0]
        assert row["weight_kg"] == "0.0"
        assert row["reps"] == "0"
        assert row["rpe"] == "0.0"

    def test_the_exercise_name_is_resolved_from_the_catalog(self):
        entry = WorkoutEntry(
            id=1,
            entry_date=date(2026, 8, 1),
            exercise_id="Barbell_Squat",
            set_rows=(_set(1),),
        )
        row = _rows(entries_to_csv([entry]))[0]
        assert row["exercise_id"] == "Barbell_Squat"
        assert row["exercise"] == "Barbell Squat"

    def test_it_reads_in_log_order_oldest_first(self):
        """list_entries returns newest first; a file people keep reads forwards."""
        older = WorkoutEntry(
            id=1, entry_date=date(2026, 7, 1), exercise_id="Sit-Up",
            set_rows=(_set(1),),
        )
        newer = WorkoutEntry(
            id=2, entry_date=date(2026, 8, 1), exercise_id="Sit-Up",
            set_rows=(_set(1),),
        )
        rows = _rows(entries_to_csv([newer, older]))
        assert [r["date"] for r in rows] == ["2026-07-01", "2026-08-01"]

    def test_sets_are_ordered_within_an_entry(self):
        entry = WorkoutEntry(
            id=1,
            entry_date=date(2026, 8, 1),
            exercise_id="Sit-Up",
            set_rows=(_set(3), _set(1), _set(2)),
        )
        rows = _rows(entries_to_csv([entry]))
        assert [r["set_number"] for r in rows] == ["1", "2", "3"]

    def test_a_comma_in_a_name_does_not_break_the_file(self):
        """The catalog really contains these — "Rowing, Stationary" and four
        other cardio machines. This asserts we did not hand-roll a join."""
        entry = WorkoutEntry(
            id=1,
            entry_date=date(2026, 8, 1),
            exercise_id="Rowing_Stationary",
            set_rows=(_set(1),),
        )
        rows = _rows(entries_to_csv([entry]))
        assert len(rows) == 1
        assert rows[0]["exercise"] == "Rowing, Stationary"

    def test_dates_are_iso_strings(self):
        entry = WorkoutEntry(
            id=1, entry_date=date(2026, 8, 1), exercise_id="Sit-Up",
            set_rows=(_set(1),),
        )
        assert _rows(entries_to_csv([entry]))[0]["date"] == "2026-08-01"

    def test_an_entry_with_no_sets_contributes_no_rows(self):
        entry = WorkoutEntry(
            id=1, entry_date=date(2026, 8, 1), exercise_id="Sit-Up", set_rows=()
        )
        assert _rows(entries_to_csv([entry])) == []


class TestTheFilename:
    def test_it_carries_the_date(self):
        assert export_filename(date(2026, 8, 3)) == "bodyshop-export-2026-08-03.csv"
