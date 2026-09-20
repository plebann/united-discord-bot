from datetime import datetime, timedelta, timezone

import pytest

from united_bot.application import TyperService
from united_bot.db import (
    MatchRepository,
    PredictionRepository,
    create_schema,
    create_session_factory,
)
from united_bot.domain import DomainError


@pytest.fixture
async def service(tmp_path):
    session_factory = create_session_factory(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await create_schema(session_factory)
    yield TyperService(
        MatchRepository(session_factory),
        PredictionRepository(session_factory),
    )
    await session_factory.kw["bind"].dispose()


GUILD_ID = 1
NOW = datetime(2026, 9, 12, 18, 30, tzinfo=timezone.utc)


async def _add_future_match(service: TyperService, kickoff: datetime) -> None:
    await service.add_match(
        GUILD_ID,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
        now=NOW,
    )


async def test_add_match_rejects_past_kickoff(service: TyperService) -> None:
    with pytest.raises(DomainError, match="Kickoff musi być w przyszłości."):
        await service.add_match(
            GUILD_ID,
            "Everton",
            "Manchester United",
            "Premier League",
            NOW - timedelta(minutes=1),
            now=NOW,
        )


async def test_add_match_rejects_kickoff_equal_to_now(service: TyperService) -> None:
    with pytest.raises(DomainError, match="Kickoff musi być w przyszłości."):
        await service.add_match(
            GUILD_ID,
            "Everton",
            "Manchester United",
            "Premier League",
            NOW,
            now=NOW,
        )


async def test_add_match_accepts_future_kickoff(service: TyperService) -> None:
    match = await service.add_match(
        GUILD_ID,
        "Everton",
        "Manchester United",
        "Premier League",
        NOW + timedelta(minutes=1),
        now=NOW,
    )

    assert match.kickoff_at == NOW + timedelta(minutes=1)


async def test_edit_kickoff_rejects_past_kickoff(service: TyperService) -> None:
    await _add_future_match(service, NOW + timedelta(days=2))

    with pytest.raises(DomainError, match="Nowy kickoff musi być w przyszłości."):
        await service.edit_kickoff(GUILD_ID, NOW - timedelta(hours=1), now=NOW)


async def test_edit_kickoff_rejects_kickoff_equal_to_now(service: TyperService) -> None:
    await _add_future_match(service, NOW + timedelta(days=2))

    with pytest.raises(DomainError, match="Nowy kickoff musi być w przyszłości."):
        await service.edit_kickoff(GUILD_ID, NOW, now=NOW)


async def test_edit_kickoff_accepts_future_kickoff(service: TyperService) -> None:
    await _add_future_match(service, NOW + timedelta(days=2))

    _, updated = await service.edit_kickoff(
        GUILD_ID, NOW + timedelta(days=3), now=NOW
    )

    assert updated.kickoff_at == NOW + timedelta(days=3)
