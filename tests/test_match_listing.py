from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from united_bot.application import TyperService
from united_bot.db import (
    MatchRepository,
    PredictionRepository,
    create_schema,
    create_session_factory,
)
from united_bot.discord_bot import format_match_listing
from united_bot.domain import Match, Score

DB_PATH = Path(__file__).resolve().parent.parent / "test_match_listing.db"


@pytest.fixture
async def service():
    for suffix in ("", "-wal", "-shm"):
        DB_PATH.with_name(DB_PATH.name + suffix).unlink(missing_ok=True)
    session_factory = create_session_factory(f"sqlite+aiosqlite:///{DB_PATH}")
    await create_schema(session_factory)
    yield TyperService(
        MatchRepository(session_factory),
        PredictionRepository(session_factory),
    )
    await session_factory.kw["bind"].dispose()
    for suffix in ("", "-wal", "-shm"):
        DB_PATH.with_name(DB_PATH.name + suffix).unlink(missing_ok=True)


def _match(
    kickoff: datetime, guild_id: int = 1, id: int | None = None, **overrides: object
) -> Match:
    values: dict[str, object] = {
        "id": id,
        "guild_id": guild_id,
        "home_team": "Everton",
        "away_team": "Manchester United",
        "competition": "Premier League",
        "kickoff_at": kickoff,
    }
    values.update(overrides)
    return Match(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_list_matches_returns_all_matches_newest_first(
    service: TyperService,
) -> None:
    base = datetime(2030, 1, 1, tzinfo=timezone.utc)
    old = await service.matches.add(_match(base - timedelta(days=30)))
    finished = await service.matches.add(
        _match(
            base - timedelta(days=15),
            home_team="Manchester United",
            away_team="Liverpool",
            competition="FA Cup",
        )
    )
    await service.matches.update(finished.finish(Score(3, 0)))
    newest = await service.matches.add(
        _match(base, home_team="Manchester United", away_team="Chelsea")
    )

    matches = await service.list_matches(1)

    assert [m.id for m in matches] == [newest.id, finished.id, old.id]
    assert all(m.guild_id == 1 for m in matches)


@pytest.mark.asyncio
async def test_list_matches_filters_by_guild(service: TyperService) -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    other_guild = _match(kickoff, guild_id=2)
    await service.matches.add(other_guild)

    matches = await service.list_matches(1)

    assert matches == []


@pytest.mark.asyncio
async def test_list_matches_returns_empty_when_no_matches(
    service: TyperService,
) -> None:
    matches = await service.list_matches(1)

    assert matches == []


def test_format_match_listing_home_match_shows_mu_first_score() -> None:
    kickoff = datetime(2030, 5, 25, 17, 0, tzinfo=timezone.utc)
    match = _match(kickoff, id=4, home_team="Manchester United", away_team="Chelsea")
    finished = match.finish(Score(3, 0))

    text = format_match_listing([finished])

    assert text == "#4 · Chelsea · 3:0 · DOM · Premier League · 25.05.2030 19:00"


def test_format_match_listing_away_match_flips_score_and_orientation() -> None:
    kickoff = datetime(2030, 1, 5, 12, 0, tzinfo=timezone.utc)
    match = _match(kickoff, id=5, competition="FA Cup")
    finished = match.finish(Score(0, 2))

    text = format_match_listing([finished])

    assert text == "#5 · Everton · 2:0 · WYJAZD · FA Cup · 05.01.2030 13:00"


def test_format_match_listing_unsettle_shows_dash_score() -> None:
    kickoff = datetime(2030, 5, 25, 17, 0, tzinfo=timezone.utc)
    match = _match(kickoff, id=7, home_team="Manchester United", away_team="Chelsea")

    text = format_match_listing([match])

    assert text == "#7 · Chelsea · - · DOM · Premier League · 25.05.2030 19:00"


def test_format_match_listing_renders_in_given_order() -> None:
    old_kickoff = datetime(2030, 1, 5, 12, 0, tzinfo=timezone.utc)
    new_kickoff = datetime(2030, 2, 5, 12, 0, tzinfo=timezone.utc)
    older = _match(old_kickoff, id=1)
    newer = _match(new_kickoff, id=2)

    # Repozytorium zwraca mecze posortowane po kickoff malejąco;
    # formatter renderuje w otrzymanej kolejności.
    text = format_match_listing([newer, older])

    lines = text.splitlines()
    assert lines[0].startswith("#2 ·")
    assert lines[1].startswith("#1 ·")


def test_format_match_listing_empty_returns_no_matches_message() -> None:
    assert format_match_listing([]) == "Brak meczów w bazie."
