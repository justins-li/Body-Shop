-- Body Shop database schema.
-- Applied by `flask --app app init-db` (see app/db.py).

DROP TABLE IF EXISTS workout_entry;

CREATE TABLE workout_entry (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date  TEXT    NOT NULL,              -- ISO-8601 date, e.g. 2026-07-28
    exercise_id TEXT    NOT NULL,              -- slug from app/exercises.py
    sets        INTEGER NOT NULL CHECK (sets > 0),
    created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_workout_entry_date ON workout_entry (entry_date);
