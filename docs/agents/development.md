# Development guide

Read this before editing Python source or tests.

## Conventions

- Use Python 3.12 and `from __future__ import annotations` in every module.
- Define domain values as frozen dataclasses; validate them in `__post_init__`
  and raise Polish `DomainError` messages.
- Keep datetimes timezone-aware: persist UTC and convert
  `Europe/Warsaw` input at the edge.
- Give time-dependent application methods `now: datetime | None = None`,
  defaulting to `utc_now()`, so tests pin time.
- Keep user-facing text in Polish and identifiers in English.
- Use ruff's `E`, `F`, and `I` rules with a 100-character line limit.

## Boundaries

- Domain and rules are pure: no I/O, Discord, SQLAlchemy, or repositories.
- Application use cases orchestrate repositories and domain values; no Discord
  types enter this layer.
- New operational business rules belong in `rules.py`; domain values and
  scoring belong in `domain.py`.
- Discord maps errors to ephemeral messages. New admin commands retain both
  the configured-channel check and `_require_admin`.

## Validation

Run these non-interactive PowerShell commands from the repository root:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\ruff.exe format --check <touched-files>
```

For an interactive setup, follow `README.md`. Tests use an in-temp-file SQLite
database; domain tests are synchronous and application tests pin `now`.

## Feature flow

1. Record changed business rules in `docs/discord-bot-domain-rules-v1.md`.
2. Add a failing behavior test.
3. Implement inward from `domain.py` or `application.py`.
4. Expose the behavior through Discord only when users need it.
5. Run the validation commands.

Do not rewrite settled behavior. Extend frozen domain dataclasses through
methods such as `with_*` or `finish`.

## Discord interactions

- Defer an interaction before database or Discord I/O. For private replies,
  defer with `ephemeral=True` and send through `followup`.
- Keep `discord.Intents(guilds=True)`; it is required for the optional VAR
  role gate to resolve guild member roles.
- Let discord.py queue rate-limited sends; scheduled work uses
  `discord.ext.tasks.loop`, waits for readiness, and catches each cycle's
  errors.
- Synchronize slash commands only at startup. Broadcasts use the announcement
  publisher; replies for one user are ephemeral.

## Known deltas

- `PREDICTION_OPEN_DAYS` is present in `.env.example`, while the three-day
  window remains hard-coded.
- Startup uses `create_all`; Alembic remains the reference for future row
  shape changes.
- The architecture document names APScheduler and httpx; the MVP uses
  `tasks.loop` and no HTTP client.
