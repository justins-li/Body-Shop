# Phase 5 — Secure user login

Design spec for [ROADMAP.md](../../ROADMAP.md)'s Phase 5. Written before
implementation; divergences get folded back into the roadmap's phase section when
the work lands.

**Depends on:** Phase 3 (Alembic, and a real database to hold accounts), Phase 1
(the login and signup pages get styled once).

**Why now:** it is the last thing between the app and Phase 6. Deploying an
unauthenticated logger to the internet means one shared training history for
everyone who finds the URL, and `delete_entry` is currently global — any visitor
could delete any row by guessing an integer.

---

## Decisions this spec settles

Three of the roadmap's open decisions gate this phase. All three are now answered.

### Open decision 3 — auth: self-hosted or provider? **Supabase Auth, bearer tokens.**

Confirmed as the roadmap recommended. The database is already Supabase (there is a
live `DATABASE_URL` in `.env`), Phase 10 requires token auth and mobile SDKs, and
most of the roadmap's requirements table — password hashing, email verification and
reset flows, login rate limiting, enumeration-identical responses — exists only to
support the self-hosted option and becomes the provider's problem otherwise.

**One cost the roadmap's "roughly halves the phase" estimate did not price in:** the
entire test suite runs offline against a per-test SQLite file, and `create_app`
opens no connections. Putting an external issuer in the middle of every
authenticated test would end that. It is bought back under *Verifying a token*
below — the suite mints its own HS256 tokens in-process and never reaches the
network.

### Open decision 2 (remaining halves) — mobile. **Both satisfied.**

Token auth: yes, bearer tokens, no cookies anywhere. In-app account deletion: yes,
`DELETE /api/account`, specced below rather than deferred to Phase 10. Whichever
mobile route eventually wins, neither has to be retrofitted.

### Open decision 5 — existing data. **Wipe.**

Revision `0005` deletes every existing `workout_set` and `workout_entry` row before
adding the column. The local database holds development rows; a seed-account
backfill would carry them into the multi-user world as one account's history and
leave a permanent "who is user 1" question behind it.

**This is irreversible and it is the destructive step of the phase.** The revision
says so in its docstring, and `downgrade()` cannot restore what it deleted — it can
only put the column back.

---

## Identity model

Supabase owns credentials. We keep a **mirror row**, because `user_id` has to be a
real foreign key on both dialects and SQLite has no `auth.users` table to point at.

```python
user = sa.Table(
    "user",
    metadata,
    # The Supabase auth.users id — the JWT's `sub`. Not minted here.
    sa.Column("id", sa.Uuid(as_uuid=False), primary_key=True),
    sa.Column("email", sa.Text, nullable=False, unique=True),
    sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("CURRENT_TIMESTAMP"),
    ),
)
```

**This diverges from the roadmap's SQL sketch on three points, all forced by the
provider choice.** That sketch assumed self-hosting:

| Roadmap | Here | Why |
| --- | --- | --- |
| `id INTEGER PRIMARY KEY` | `Uuid(as_uuid=False)` | It is not our id. It is `auth.users.id`, which is a UUID. |
| `password_hash TEXT NOT NULL` | absent | Supabase holds it. A local copy is a credential we chose not to own. |
| `verified_at TEXT` | absent | Supabase's `email_confirmed_at` is the truth. A mirrored copy drifts, and the drift is invisible until someone is wrongly let in or wrongly kept out. |

Phase 4's Uuid finding applies unchanged: `as_uuid=False` stores 32-char hex and
returns the hyphenated 36-char form, so compare with `uuid.UUID(...)` rather than
string equality. The `sub` claim already arrives hyphenated.

The table is named `user`, which is reserved in Postgres. SQLAlchemy quotes
identifiers automatically in both dialects and there is no raw SQL outside
`conftest.py`'s `TRUNCATE`, so this is safe — but it is why the name must never be
interpolated into a string query.

### Just-in-time provisioning

There is no signup webhook. The mirror row is created on the **first authenticated
request** carrying a `sub` we have not seen:

```
require_user:
    claims = decode_token(bearer)
    models.ensure_user(claims.sub, claims.email)
    g.user_id = claims.sub
```

`ensure_user` inserts and swallows `IntegrityError` on conflict, which is portable
across both dialects — `on_conflict_do_nothing()` is spelled differently per
dialect and would break the one-query-layer rule. Two concurrent first requests
therefore race safely. If the stored email differs from the claim, it is updated;
Supabase is the source of truth for it.

**This is the only place in the app where a GET request writes.** Worth knowing
before anyone adds a read-replica or wonders why a summary request opened a
transaction.

---

## Migration `0005`

```
delete from workout_set
delete from workout_entry            # the wipe — both dialects
create table "user"
batch_alter_table("workout_entry"):
    add column user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE
create index idx_workout_entry_user_date on workout_entry (user_id, entry_date)
```

**`batch_alter_table` unconditionally, not branched by dialect.** It rebuilds the
table under SQLite and emits a plain `ALTER` under Postgres, so this is one code
path rather than the two that `0003` and `0004` needed. Phase 3's `CAST` trap does
not bite here: `cast_for_batch_migrate` only fires when a column's type *changes*,
and nothing here changes type. The table is empty by the time batch mode runs
regardless, which is also what makes the `NOT NULL` legal without a default on
Postgres.

The roadmap's warning stands and is the reason batch mode is used at all: SQLite
refuses to `ADD COLUMN` when the column is `NOT NULL` with no default, and refuses
again when it carries a `REFERENCES` clause with a non-NULL default. Both rules
apply to an empty table, so wiping first does not rescue a plain `ALTER`.

**The revision carries its own frozen copy of `NAMING_CONVENTION`** rather than
importing it from `app/tables.py` — the rule revision `0002` established, for the
same reason: a migration that imports a constant does different things depending on
when it runs. Batch mode needs the convention passed explicitly or SQLite's rebuilt
constraints come out unnamed. The foreign key lands as
`fk_workout_entry_user_id_user`.

`downgrade()` drops the index, drops the column, drops the table. It does not
restore the wiped rows and says so.

### Cascade

`user → workout_entry → workout_set` are both `ON DELETE CASCADE`, and
[app/db.py](../../../app/db.py) already enables SQLite foreign keys per connection.
Deleting an account is therefore one `DELETE FROM "user"`, with no cascade handling
in Python — the same property `delete_entry` has relied on since Phase 4.

Phase 7's `body_metric` and Phase 8's `custom_exercise` inherit the pattern: FK to
`"user"(id)` with `ON DELETE CASCADE`, and account deletion keeps working with no
change to the endpoint.

---

## Verifying a token (`app/services/auth.py`, new)

Pure, Flask-free, and therefore directly testable:

```
decode_token(raw: str) -> Claims(sub: str, email: str)

    key source:
        HS256  against SUPABASE_JWT_SECRET, when it is set
        ES256/RS256 against the project's JWKS, otherwise (cached in-process)

    always verified:
        signature
        exp
        aud == "authenticated"
        iss == f"{SUPABASE_URL}/auth/v1"
        sub present and non-empty
```

Both key types, behind one resolver, because Supabase projects differ by age:
newer ones default to asymmetric signing keys served from
`/auth/v1/.well-known/jwks.json`, while legacy projects use the shared HS256 JWT
secret. Committing to one means the app either cannot verify a token at all or
needs a stubbed HTTP endpoint in the test suite. The resolver is roughly thirty
lines and removes the guess.

Testing config pins `SUPABASE_JWT_SECRET`, so the suite always takes the HS256
branch and mints tokens in-process. **No test reaches the network.**

Failure modes all raise one `AuthError`, which `api.py` renders as `401` — never a
different status or message per cause. A 401 that distinguishes "expired" from
"forged" is a small oracle, and nothing in the client needs the distinction.

New dependency: `PyJWT[crypto]` (the extra pulls `cryptography`, which the
asymmetric branch needs).

### Where the Flask glue lives

`require_user`, `g.user_id` and the 401 response live in `app/api.py`, not in
`services/`. They touch `request` and `g`, which is HTTP, and the layer rule is
`api.py` (HTTP) → `services/` (rules) → `models.py` (SQL). `services/auth.py`
holds only the token rules. Views need none of it — page shells are public.

The 401 body is `{"error": "Sign in to continue."}` with
`WWW-Authenticate: Bearer`, so `api.js` can distinguish it from a validation 400
without parsing prose.

---

## The `user_id` sweep (`app/models.py`)

**Every function that touches `workout_entry` takes `user_id` as its first
positional parameter.** Positional-and-first is the safety property, not a style
choice: a call site that was not updated fails loudly as a `TypeError` instead of
silently querying across all users.

| Function | Change |
| --- | --- |
| `add_entry` | `user_id` first; written into the insert |
| `get_entry` | `WHERE id = :id AND user_id = :user_id` |
| `list_entries` | `WHERE user_id = :user_id` |
| `delete_entry` | `WHERE id = :id AND user_id = :user_id` |
| `recent_exercise_usage` | `WHERE user_id = :user_id` |
| `last_sets_for_exercise` | `WHERE user_id = :user_id` — already joins back through `workout_entry` |
| `_counted_sessions` | `WHERE user_id = :user_id` |
| `exercise_activity` | via `_counted_sessions` and its own clause |
| `exercise_co_occurrence` | via `_counted_sessions` |
| `sets_by_date` | `WHERE user_id = :user_id` |

New: `ensure_user(user_id, email)`, `get_user(user_id)`, `delete_user(user_id)`.

**`delete_entry` returns `False` for another user's row**, so the API answers 404 —
identical to a row that does not exist. Returning 403 would confirm the id is real,
which is the IDOR wearing a politeness mask.

**`_sets_for(entry_ids)` keeps its signature** and does *not* filter by user. Its
only callers pass ids that came out of an already-filtered query, so the join would
be redundant. It gains a comment saying exactly that, and saying that a new caller
which sources entry ids any other way must join back through `workout_entry` —
which is the roadmap's "same IDOR wearing a different hat".

`services/summary.py`, `services/graph.py` and `services/weeks.py` thread `user_id`
through. None of their rules change.

---

## API (`app/api.py`, `docs/API.md`)

Every existing endpoint that reads or writes entries gains `@require_user` and
passes `g.user_id`: `GET/POST /api/entries`, `DELETE /api/entries/<id>`,
`GET /api/calendar`, `GET /api/summary/week`, `GET /api/progress/graph`,
`GET /api/exercises/recent`, `GET /api/exercises/<id>/last-sets`.

**Left public:** `GET /api/exercises`, `GET /api/exercises/<id>` and
`GET /api/summary/week/bounds`. The catalog is public-domain data that ships in the
repo, and the week-bounds endpoint is pure calendar arithmetic over a query
parameter. Gating them would buy nothing and would make the login page unable to
render anything.

Two new endpoints:

```
GET    /api/me       -> {"user": {"id": ..., "email": ...}}
DELETE /api/account  -> {"deleted": true}
```

`GET /api/me` exists so the client can confirm a token server-side rather than
trusting its own decode of it.

**Login, signup, refresh, password reset and email verification are not Flask
endpoints.** They are Supabase's, called directly by the browser — see below.

---

## Account deletion

`DELETE /api/account`:

1. Refuse with `503` if `SUPABASE_SERVICE_ROLE_KEY` is unset, before touching
   anything.
2. `DELETE FROM "user" WHERE id = :user_id` — cascades every entry and set. Commit.
3. `DELETE {SUPABASE_URL}/auth/v1/admin/users/{sub}` with the service-role key.

**This is the one place Flask holds a Supabase key**, which qualifies the "Flask
never holds a Supabase credential" property that follows from the login-path
decision. The login path holds none; deletion needs the admin key, and there is no
way around that — a user cannot delete their own auth record with an anon key.

The call uses stdlib `urllib.request`, so it adds no HTTP dependency.

**Local-first ordering is deliberate.** If step 3 fails, the account survives with
no data: recoverable, retryable, and the response says so honestly. Supabase-first
would risk the opposite — the auth record gone, the rows orphaned behind an account
that can never sign in again to delete them.

Apple's Guideline 5.1.1(v) is what eventually *requires* this, but a launched app
holding emails and training history needs it as ordinary privacy hygiene, which is
why it is here rather than in Phase 10.

---

## Front end

### `app/static/js/auth.js` (new)

The token store plus plain-`fetch` calls to Supabase GoTrue — signup, password
grant, refresh, recover, verify. **No SDK**, so the zero-JS-dependency rule holds;
these are four `POST`s against a documented REST API.

Tokens live in `localStorage`: access token, refresh token, and the access token's
expiry. The anon key is embedded in the page from config and is public by design.

**This is a second place `fetch` is called**, which contradicts
`ARCHITECTURE.md`'s "`api.js` is the only place `fetch` is called". The doc gets
amended rather than the rule quietly broken — the honest statement is that `api.js`
is the only place *our own API* is called, and `auth.js` is the only place
Supabase is.

### `api.js`

`request()` attaches `Authorization: Bearer <access>`. On a 401 it makes **one**
silent refresh-and-retry attempt; if that also fails it clears the store and
redirects to `/login?next=<current path>`. One retry, not a loop — a refresh token
that is genuinely dead must not spin.

### Pages

New, all outside the book: `/login`, `/signup`, `/reset-password`, `/verify`,
`/account`.

`base.html` gains a `bare` flag suppressing the shelves, the tab bar and the rest
dock. These pages get **no chapter number and never appear in the shelf stack** —
they are not sections of the product, and `sections` in `base.html` is untouched,
so `tests/test_pages.py`'s two chapter-ordering assertions keep passing unchanged.

`/reset-password` serves both halves of the flow: a request form, and — when
Supabase redirects back with a recovery token in the URL fragment — a new-password
form. `/verify` is the landing page for the confirmation link.

Supabase configuration this implies, recorded because it is not in the repo: the
project's Site URL and additional redirect URLs must include `/verify` and
`/reset-password`, and the email templates point at them.

### The signed-out / signed-in split on `/`

A blocking inline script in `<head>` sets `data-auth="in"|"out"` on
`<html>` before first paint, and CSS shows one of two blocks. No flash, no JS
module, and `/` stays static in the sense that matters — it makes no API call.

**Signed-in swaps the primary action rather than adding to it.** `/` is one screen
and only the specimen may flex; new content has to earn its height or replace
something. That is also why sign-out and delete-account live on `/account` instead
of being bolted onto the landing page.

---

## Config (`app/config.py`, `.env.example`)

| Setting | Env | Notes |
| --- | --- | --- |
| `SUPABASE_URL` | `BODYSHOP_SUPABASE_URL` | Project URL; also derives the expected `iss` and the JWKS path |
| `SUPABASE_ANON_KEY` | `BODYSHOP_SUPABASE_ANON_KEY` | Public by design; rendered into the page |
| `SUPABASE_JWT_SECRET` | `BODYSHOP_SUPABASE_JWT_SECRET` | Optional. Set → HS256; unset → JWKS |
| `SUPABASE_SERVICE_ROLE_KEY` | `BODYSHOP_SUPABASE_SERVICE_ROLE_KEY` | Secret. Account deletion only |

`config.validate()` gains production checks for `SUPABASE_URL`, `SUPABASE_ANON_KEY`
and `SUPABASE_SERVICE_ROLE_KEY`. It runs against the *resolved* config in
`create_app`, exactly as the existing checks do, so `instance/config.py` can satisfy
them and cannot bypass them. `SUPABASE_JWT_SECRET` is **not** required — its absence
is a valid configuration meaning "use JWKS".

Testing config pins `SUPABASE_URL`, `SUPABASE_ANON_KEY` and a fixed
`SUPABASE_JWT_SECRET`.

---

## What this phase deliberately does not build

**Flask-Limiter and Redis.** The roadmap's requirements table lists rate limiting on
login and password reset — those are Supabase's endpoints now, and Supabase rate
limits them. Our own API is bearer-only with no credential to brute-force against
it. The Redis question also belongs to Phase 6, which has not chosen a host.

**CSRF.** Dissolved by the token choice, as the roadmap predicted. There are no
cookies anywhere in the app, `Authorization` headers are not sent cross-origin by a
browser unprompted, and `POST /api/entries` has been JSON-only since Phase 4.

**Server-side page gating.** Follows from bearer tokens: Flask cannot read a header
the browser does not send on a navigation. Shells stay public and their JS module
redirects on 401. The cost is one unauthenticated frame before the redirect, and
the benefit is that the web app consumes the same API a mobile client will.

**Enumeration hygiene, lockout, password strength.** All Supabase's, all
configurable in its dashboard rather than in this repo.

---

## Tests

`client` becomes a `FlaskClient` subclass injecting a default `Authorization`
header for a fixed test user, so the existing suite needs no per-call edits. The
`add` fixture is unchanged for the same reason. Postgres `TRUNCATE` gains `"user"`.

| File | Covers |
| --- | --- |
| `test_auth.py` (new) | `decode_token`: valid, expired, wrong secret, wrong `aud`, wrong `iss`, missing `sub`, malformed, missing header, non-Bearer scheme. JIT provisioning, including a second request not duplicating the row, and an email change updating it. |
| `test_ownership.py` (new) | Two users, exhaustively. Each sees only their own entries, calendar, weekly summary, graph, recents and last-sets. `DELETE /api/entries/<id>` across users returns 404 **and leaves the row intact**. |
| `test_account.py` (new) | `DELETE /api/account` removes the user, their entries and their sets; another user's data survives; 503 when the service key is unset, with nothing deleted. |
| `test_pages.py` | The five new pages render; they carry no shelves and no tab bar; the existing chapter-order and form-field assertions still pass. |
| `test_config.py` | Production `validate()` on each new required key. |
| `test_migrations.py` | Unchanged — it autogenerates a diff and will fail if `0005` and `tables.py` disagree. |

`test_ownership.py` is the file that proves the sweep. The roadmap's warning is
that one missed `WHERE` clause is a data leak, and a table of endpoints in one test
file is what makes a missed one visible.

---

## Docs to update in the same commit

- **`CLAUDE.md`** — the no-`user_id`/no-auth invariant is reversed; add the
  first-positional-parameter rule, the mirror-table shape, the two `fetch` sites,
  and `PyJWT[crypto]` as a runtime dependency.
- **`docs/API.md`** — an auth section, `401` on every gated endpoint, the two new
  endpoints, and the note that login/signup/reset are not Flask routes.
- **`docs/ARCHITECTURE.md`** — the layer-ownership table gains `services/auth.py`
  and `static/js/auth.js`; the `fetch` sentence is amended.
- **`docs/ROADMAP.md`** — Phase 5 gets its "what shipped, and where it diverged"
  section; open decisions 2, 3 and 5 close.
- **`.env.example`**, **`README.md`**, **`CHANGELOG.md`**.

---

## Explicitly out of scope

Per-user preferences (the kg/lb setting stays in `localStorage` — moving it to the
`user` table is a Phase 7 nicety), OAuth providers, magic links, multi-factor auth,
soft-delete tombstones (Phase 10), and any change to grading, the volume ramp or
the body map. This phase adds a `WHERE` clause to every query and five pages; it
changes nothing about what the app *says*.
