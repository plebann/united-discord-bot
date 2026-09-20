# AGENTS.md

Development rules for LLM agents working on this repository. This file is an index;
details live in the linked docs and in the code itself.

## Project overview

`united-discord-bot` is a Discord bot (python) for predicting Manchester United match
results: adding matches, submitting predictions (`/typ 3:1`) from 3 days before
kickoff, editing predictions until kickoff, manual settlement with the 5/3/1/0
scoring model, and channel announcements.

- Accepted architecture: `docs/discord-bot-architecture-python-sqlite-v2.md`
  (modular monolith, hexagonal / ports-and-adapters).
- Domain rules (scoring, prediction windows, terminology):
  `docs/discord-bot-domain-rules-v1.md`.
- User-facing commands, setup, and configuration: `README.md`.

## Where things live

Layered composition; dependencies point inward only
(`discord_bot` → `application` → `domain`, `db` ↔ `domain`).

- `src/united_bot/domain.py` — pure domain: frozen dataclasses (`Match`, `Prediction`,
  `Score`), enums, `calculate_prediction_points`, `DomainError`. No I/O, no
  discord, no SQLAlchemy. New business rules go here first.
- `src/united_bot/application.py` — use cases (`TyperService`). Orchestrates
  repositories and the domain; owns cross-cutting flow (e.g. which match is
  "current"). No Discord types.
- `src/united_bot/db.py` — adapters: SQLAlchemy rows, `create_schema`, and
  repository classes that map rows ↔ domain.
- `src/united_bot/announcements.py` — announcement use cases against the
  `AnnouncementPublisher` protocol; idempotent via an announcements table
  (`was_sent` / `mark_sent` / `_publish_once`).
- `src/united_bot/discord_bot.py` — the Discord adapter: cogs, slash commands,
  channel check, kickoff parsing, bot wiring, the 5-minute announcement loop.
- `src/united_bot/main.py` — composition root: env loading, session factory,
  service wiring, `bot.start`.
- `tests/` — one file per behaviour area, named after the behaviour
  (`test_domain.py`, `test_kickoff_format.py`, `test_channel_check.py`, …).

## Code conventions (derived from the current code)

- Python 3.12, `from __future__ import annotations` in every module.
- Domain values are frozen dataclasses with validation in `__post_init__`;
  violations raise `DomainError` (a `ValueError`) with a Polish user-facing message.
- All datetimes are timezone-aware: UTC in the database, kickoff entered in
  `Europe/Warsaw` and converted at the edge (`parse_kickoff`). Never store or pass
  naive datetimes.
- Application methods accept an optional `now: datetime | None = None` (defaulting
  to `utc_now()`) so tests can pin time. Follow this pattern for any new time-based
  behaviour.
- The adapter layer maps exceptions to ephemeral user messages
  (`_send_command_error`, per-command `except` blocks); domain errors must never
  leak as stack traces into Discord.
- Admin commands check `manage_guild` or `administrator` via `_require_admin`;
  every command is additionally restricted to `CHANNEL_ID` by
  `configured_channel_check`. Keep both when adding admin commands.
- User-facing text is Polish; identifiers are English.
- Style is enforced by ruff (`E`, `F`, `I`, line length 100) configured in
  `pyproject.toml`: run `ruff check .` (and `ruff format` when touching a file)
  before committing.

## Commands

Full setup is in `README.md`; the essentials:

```powershell
py -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
ruff check .          # style gate
pytest                # full suite (asyncio_mode=auto)
```

The database is SQLite (WAL, `busy_timeout=5s`). Runtime schema is created with
`Base.metadata.create_all` at startup; Alembic migrations exist for reference and
for any future migration — add a migration under `migrations/versions/` when you
change row shapes so both paths stay in sync.

Tests use an in-temp-file SQLite database per test (see the `service` fixture in
`tests/test_previous_prediction.py`). Domain tests stay synchronous and pure;
application tests pin `now` instead of sleeping.

## How to develop new features

Order of work, one slice at a time:

1. If the feature changes a business rule, first record it in
   `docs/discord-bot-domain-rules-v1.md` (or a successor versioned doc).
2. Add a failing test for the behaviour — domain-level if it is pure logic,
   application-level with pinned `now` if it is flow.
3. Implement in `domain.py` / `application.py`. No Discord or SQLAlchemy types
   may appear outside their layers.
4. Expose it through the Discord adapter only if the user needs it: slash command
   in a cog, error mapping to an ephemeral message, admin check where applicable.
5. Run `ruff check .` and `pytest`; both must pass.

Do not delete or rewrite settled behaviours while adding new ones; extend the
frozen dataclasses via new methods (`with_*`, `finish` style) rather than mutating
state.

## Discord API discipline

Facts about the platform that are easy to get wrong (see
<https://docs.discord.com/developers/topics/rate-limits> and
<https://docs.discord.com/developers/interactions/receiving-and-responding>):

- An interaction gets a 3-second window for its initial response. Call
  `interaction.response.defer()` immediately when the handler does any I/O
  (database writes, publishing announcements), then answer via `followup.send`.
- Never do blocking or long-running work before deferring; a missed window
  surfaces to the user as "Interaction failed".
- discord.py's rate-limit manager queues requests automatically — do not add your
  own retry loops or sleep-based backoff around `channel.send` / API calls.
- Slash commands are per-guild state on Discord: sync once at startup (the
  `setup_hook` does this). Do not call `tree.sync()` from handlers or on a loop.
- Keep intents minimal; the bot runs with `Intents.none()`. Any new privileged
  intent is a deliberate, documented decision (and requires review in the
  Developer Portal).
- Long-lived scheduled work belongs in `discord.ext.tasks.loop` with a
  `before_loop` that waits for readiness, wrapped in try/except so one bad cycle
  cannot kill the loop (see `poll_announcements`).
- Replies meant for one user use `ephemeral=True`; anything broadcast goes
  through the announcement publisher into `CHANNEL_ID`.

## Known deltas from the architecture doc

Documented here so agents don't "fix" them silently:

- `PREDICTION_OPEN_DAYS` exists in `.env.example` but the 3-day prediction window
  is currently hard-coded (`domain.Match.prediction_opens_at`, `db.py`).
- Startup uses `create_all`, not Alembic migrations.
- The architecture doc lists APScheduler and httpx; the current MVP uses
  `tasks.loop` and no HTTP client yet. Adopt the doc's choices only when that
  feature actually lands.
