# Phase 5 carryover — the trainer setup's home

Design spec for [ROADMAP.md](../../ROADMAP.md)'s item 1. Written before
implementation; divergences get folded back into the roadmap when the work lands.

**Depends on:** Phase 5 (the `user` row this hangs off), Phase 6 (the setup
itself). Both shipped.

**Why now:** Phase 6 shipped ahead of Phase 5 and needed somewhere per-user to
live before there was a user, so the trainer setup became a `localStorage`
preference sent with every request. Phase 5 landed the user row and did not move
it. Until it moves, the setup is per-browser rather than per-account: signing in
on a second device grades you against a stranger's default targets, and clearing
site data resets them. Phase 7 puts real accounts on more than one device, so
this goes first.

**Scope:** a column, a default, a migration, and one endpoint to write it. The
grading model does not change — `training.py`'s arithmetic is untouched, and no
number in [VOLUME_SCIENCE.md](../../VOLUME_SCIENCE.md) moves.

---

## Decisions this spec settles

### Where the setup lives. **Three nullable columns on `user`.**

```python
sa.Column("experience", sa.Text, nullable=True),
sa.Column("sessions_per_week", sa.Integer, nullable=True),
sa.Column("minutes_per_session", sa.Integer, nullable=True),
```

Nullable, and **all three NULL means "never chosen"** rather than "chose the
defaults". That distinction is load-bearing twice over: it is what the first-run
dialog reads to decide whether this account has already answered, and it is what
lets `DEFAULT_EXPERIENCE` / `REFERENCE_PLAN` keep meaning *today's* default
instead of being frozen into every row at backfill time.

It also maps straight onto code that already exists. `resolve_profile` was
written to take three possibly-absent, possibly-garbage values and fall back per
input — that is exactly a row of NULLs, so no new fallback logic is needed
anywhere.

**No CHECK constraints.** `resolve_profile` clamps on the way in, so the database
can only ever receive an in-range value. A check duplicating `MIN_SESSIONS` /
`MAX_MINUTES` would add a migration to every future tuning of what are documented
as conventions, and a check on `experience` would have to be rewritten to add a
fourth level. The clamp is the enforcement; the column is storage.

### How it is written. **`PUT /api/profile`; the query parameters go.**

One endpoint owns the setup. `/api/summary/week` and `/api/progress/graph` stop
reading `experience`/`sessions`/`minutes` and resolve from the user row instead.

The alternative — keeping the parameters as a per-request override on top of the
stored row — preserves every existing client call verbatim and was rejected for
leaving two sources of truth. A stale client could then grade a week against
something other than the account's setup, and the resulting disagreement would be
invisible: both answers render correctly, they just describe different weeks.

The roadmap predicted "the API shape does not change". That was not quite right —
something has to write the column — but the *payloads* are unchanged. `profile`
still comes back on the weekly summary, in the same shape, echoed beside the
grading it produced.

### How the client reads it. **Server truth, `localStorage` as a read-through cache.**

The key survives, demoted. `loadProfile()` stays synchronous, which is what
`setgrid.js` needs: it decides whether to draw the RPE column while building
markup, and making that await a fetch means the column flickers in on `/log`
after the grid has already painted.

So the server is authoritative and the cache is written from server payloads
only, never as an independent store. A second device corrects itself on the first
response that carries a profile.

### First run. **Both gates: the account's setup, or the local flag.**

The dialog opens only when the account has no stored setup **and** this browser
has not been asked. Skipping still writes nothing to the server, so NULL stays
honest; it writes the local flag, so the skipper is not nagged on the browser
where they skipped. A user who set up on their phone is never interviewed again
on their laptop.

---

## The layers

### `app/tables.py` and `migrations/versions/0006_trainer_setup_on_user.py`

The three columns above, added to the `user` table's metadata and to a revision in
the same commit — `tests/test_migrations.py` compares the two with Alembic's own
autogenerate diff and fails when they disagree.

`op.add_column` three times; `op.drop_column` three times to reverse. No
`batch_alter_table` is needed: adding a nullable column with no constraint is the
one `ALTER` SQLite supports natively, and batch mode would rebuild the table for
no reason. Nothing is destructive and nothing is backfilled — existing accounts
land on NULL, which is the correct reading of "this account has never chosen".

### `app/models.py`

Two functions, both with `user_id` as the first positional parameter, per the
standing rule that a call site which was not updated must fail as a `TypeError`
rather than silently querying across users.

```python
def get_trainer_setup(user_id: str) -> dict | None:
    """The stored setup, or ``None`` if this account has never chosen one."""

def set_trainer_setup(
    user_id: str, experience: str, sessions_per_week: int, minutes_per_session: int
) -> None:
    """Store the setup. The row exists — ``ensure_user`` guaranteed it."""
```

`get_trainer_setup` returns `None` when all three columns are NULL and a dict of
the three raw values otherwise. Returning `None` rather than a dict of `None`s is
what makes "never chosen" a single check at the call site instead of three.

`get_user` and `/me` keep their shape. The setup is not identity, and widening
`/me` would make every consumer of it re-render when a target changes.

### `app/training.py`

**No behaviour changes.** `resolve_profile` already treats every input as
untrusted and falls back rather than raising; NULL columns are the same case as
absent query parameters. The module docstring's closing paragraph — "No ownership
yet… until then the choice is a client preference sent with the request" — becomes
false with this change and gets rewritten.

`TrainerProfile` deliberately does **not** learn whether it came from a stored row.
"Configured" is a fact about storage, not about training, and putting it here
would mean every `DEFAULT_PROFILE` consumer carrying a flag it has no use for.

### `app/api.py`

`_query_profile()` becomes `_user_profile()`:

```python
def _user_profile() -> TrainerProfile:
    stored = get_trainer_setup(g.user_id) or {}
    return resolve_profile(
        stored.get("experience"),
        stored.get("sessions_per_week"),
        stored.get("minutes_per_session"),
    )
```

Two endpoints, both `@require_user`:

```
GET /api/profile
→ {"profile": {…TrainerProfile.to_dict()…}, "configured": false}

PUT /api/profile   {"experience": "beginner", "sessions_per_week": 3,
                    "minutes_per_session": 45}
→ {"profile": {…}, "configured": true}
```

`PUT` runs the body through `resolve_profile` and stores the **resolved** values,
then echoes them. It clamps rather than returning 400, for the reason the query
string did: these arrive from a settings control, and the honest response to an
out-of-range number is the nearest one that works. Storing the resolved value
rather than the submitted one means the column can never hold something the app
would refuse to use, and the client's controls settle on what was actually stored
— `summary.js` already renders from the echo for exactly this reason.

`configured` is `true` after any `PUT`, since a `PUT` is a choice.

`/summary/week` and `/progress/graph` swap `_query_profile()` for `_user_profile()`
and their docstrings lose the paragraph about the three query parameters.

### `app/static/js/ui.js`

`PROFILE_KEY` stays and its docstring says what it now is: a cache of the server's
answer, never a store. `saveProfile` becomes `cacheProfile` — same body, honest
name. `profileQuery` is deleted; nothing sends the setup on a query string any
more.

`loadProfile()` is unchanged, including its defaults: a browser that has not yet
heard from the server renders the same thing the server would resolve for an
unconfigured account, so the pre-fetch paint is never wrong in a way the fetch
then corrects.

### `app/static/js/api.js`

Loses the `profileQuery` import; gains two functions and one responsibility.

```js
export async function fetchProfile()        // GET  /api/profile
export async function saveProfile(profile)  // PUT  /api/profile
```

Both call `cacheProfile` on the resolved profile in the response, and so does
`fetchWeeklySummary`, which already carries one. Caching here rather than in each
page module is what makes the cache impossible to forget: `api.js` is the only
place our own API is called, so every payload that carries a profile passes
through exactly one function that stores it.

`fetchTrainingGraph` drops its profile parameters. The graph payload carries no
`profile` of its own, so it refreshes no cache — it is a reader.

### `app/static/js/summary.js`

`onSetupChange` becomes a write: `await saveProfile(readSetup())`, then `load()`.
The reload is not optional and is not new — targets are graded server-side, so a
new setup has always meant a new request rather than a re-render.

`initSummary` keeps filling the controls from `loadProfile()` before the first
fetch, so the page paints the cached setup rather than the markup's defaults, and
the echo corrects it if the cache was stale.

A failed `PUT` toasts and leaves the controls where the user put them, like every
other write on the page.

### `app/static/js/log.js`

Awaits `fetchProfile()` during boot, before mounting the set grid. On a browser
with a cold cache the RPE gate would otherwise read the default and draw the wrong
columns for an advanced lifter. It is one small request on a page that already
makes two, and it warms the cache for `setgrid.js`, which stays entirely unchanged.

### `app/static/js/onboarding.js`

`initOnboarding` becomes `async`. The order matters:

1. Local flag set → return immediately. **No request.** A browser that has already
   been asked must not pay for a fetch on every navigation.
2. Otherwise `fetchProfile()`. `configured: true` → mark asked, return. The
   account has answered; this browser now knows.
3. Otherwise open the dialog.

"Start" writes through `saveProfile` (the API one) and then reloads, as it does
today. "Skip" and `Escape` write the local flag only — the server stays NULL, so
another device still gets asked, which is right: nobody has answered yet.

If the fetch fails — offline, or signed out — treat it as unconfigured and fall
back to the local flag alone. A dialog is not worth an error, and the page under
it is already handling its own 401 through `api.js`.

---

## Testing

- **`tests/test_api.py`** — the six existing cases that pass the setup on the query
  string become `PUT`-then-read. One asserts the clamp: `PUT` a nonsense
  experience and 400 sessions, read back the resolved values, confirm the stored
  row holds the clamped numbers rather than the submitted ones.
- **`tests/test_ownership.py`** — `/api/profile` joins the walk. Two users, two
  different setups; each `GET` returns its own, and one user's `PUT` never moves
  the other's targets. A failure here is a data leak.
- **`tests/test_models.py`** — `get_trainer_setup` returns `None` for a fresh
  account and a dict after `set_trainer_setup`; a second `set_trainer_setup`
  overwrites rather than accumulating.
- **`tests/test_migrations.py`** — covers the schema by construction, no new test.
  The Postgres CI job round-trips `0006` both ways.
- **`tests/test_summary.py` / `test_graph.py`** — unchanged. They construct
  profiles directly and never went through the query string.

Everything stays offline. Nothing here touches Supabase.

---

## Documentation to update in the same commit

- **[API.md](../../API.md)** — `GET`/`PUT /api/profile` with exhaustive payloads;
  remove the three query parameters from `GET /api/summary/week` and
  `GET /api/progress/graph`; the endpoint table gains two bearer rows.
- **[ARCHITECTURE.md](../../ARCHITECTURE.md)** — the `user` table's columns, and
  the trainer-setup section's "no user row yet" framing.
- **[ROADMAP.md](../../ROADMAP.md)** — item 1 is done; the "Current state"
  paragraph loses the carryover, and Phase 7 becomes the top of the list.
- **[CLAUDE.md](../../../CLAUDE.md)** — the invariant beginning "The trainer setup
  has no user row yet, so it travels on the query string" is rewritten to describe
  the column, the cache and the two endpoints; the Architecture section's "Phase 6
  shipped ahead of Phase 5… that is the one open carryover" sentence goes.

## Out of scope

- Migrating anyone's existing `localStorage` setup onto their account. A
  one-time upload on first sign-in would silently overwrite an account's real
  setup from whichever browser happened to load first. Existing users re-answer
  once, through a control that is already on the page.
- The weight unit (`kg`/`lb`) and the summary's split scheme. Both are also
  `localStorage`, and both are genuinely display preferences — they change what
  you read, not what you are graded against. They stay per-browser.
- Any change to targets, multipliers, or the grading model.
