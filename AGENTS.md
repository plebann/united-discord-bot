# Agent guide

`united-discord-bot` is a Python Discord bot for predicting Manchester United
match results.

## Map

Dependencies point inward: `discord_bot` → `application` → `domain`;
`db` maps persistent rows to domain values.

- `src/united_bot/domain.py` — pure values, scoring, and domain errors.
- `src/united_bot/rules.py` — pure operational rules.
- `src/united_bot/application.py` — use cases and repository orchestration.
- `src/united_bot/db.py` — SQLAlchemy adapters and repositories.
- `src/united_bot/discord_bot.py` — Discord commands and scheduled work.
- `src/united_bot/main.py` — composition root.
- `tests/` — behavior-focused tests.

## Read before changing

- **Development:** Before editing Python source or tests, read
  `docs/agents/development.md` for conventions, validation, layer boundaries,
  Discord interaction rules, and known deltas.
- **Domain:** Before changing business language or behavior, read
  `docs/agents/domain.md`.
- **Architecture:** Before changing module dependencies or adapters, read
  `docs/discord-bot-architecture-python-sqlite-v2.md`.
- **Commands and configuration:** Before changing user-facing setup or
  configuration, read `README.md`.

## Agent skills

### Issue tracker

Issues and specs are local Markdown files under `.scratch/`. See
`docs/agents/issue-tracker.md`.

### Triage labels

The default five canonical triage roles are used as local issue statuses. See
`docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repo; domain vocabulary lives in `CONTEXT.md`. See
`docs/agents/domain.md`.
