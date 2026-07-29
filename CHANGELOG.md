# Changelog

All notable changes to Body Shop are documented here. This project follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] — 2026-07-28

First functional release.

### Added

- **Calendar page** (`/`) — month grid with a dot on every day that has logged
  sets, a side panel showing that day's entries, arrow-key day navigation and a
  "jump to today" shortcut.
- **Log page** (`/log`) — date picker, exercise selector (bench press, pull ups,
  squat) with the muscle groups each movement trains, a set stepper, and inline
  deletion of the day's entries.
- **Weekly summary page** (`/summary`) — front and back body outlines that fill
  red for every muscle group trained at least one set that week, a per-group set
  breakdown, and week-by-week navigation.
- JSON API under `/api` covering exercises, entries, calendar totals and the
  weekly summary — see [docs/API.md](docs/API.md).
- SQLite persistence with a `flask --app app init-db` reset command; the database
  is created automatically on first run.
- pytest suite covering week maths, muscle-coverage aggregation, every API
  endpoint and all three pages.
- GitHub Actions CI running the suite on Python 3.10–3.13.
