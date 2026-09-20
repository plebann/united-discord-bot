from datetime import datetime, timedelta, timezone

import pytest

from united_bot.application import TyperService
from united_bot.db import (
    MatchRepository,
    PredictionRepository,
    create_schema,
    create_session_factory,
)
from united_bot.domain import DomainError, Score


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
LATER = NOW + timedelta(hours=2)

UNRESOLVED_MESSAGE = (
    "Mecz Everton - Manchester United nie został jeszcze rozliczony. "
    "Zamknij go przed dodaniem kolejnego spotkania."
)


async def _add_match(
    service: TyperService,
    kickoff: datetime,
    home_team: str = "Everton",
    away_team: str = "Manchester United",
    now: datetime | None = None,
) -> None:
    await service.add_match(
        GUILD_ID,
        home_team,
        away_team,
        "Premier League",
        kickoff,
        now=now or NOW,
    )


async def test_add_match_rejects_when_future_match_exists(service: TyperService) -> None:
    await _add_match(service, NOW + timedelta(days=1))

    with pytest.raises(DomainError, match="nie został jeszcze rozliczony"):
        await _add_match(service, NOW + timedelta(days=2))


async def test_add_match_rejects_when_started_unsettled_match_exists(service: TyperService) -> None:
    await _add_match(service, NOW + timedelta(hours=1), now=NOW)

    with pytest.raises(DomainError, match="nie został jeszcze rozliczony"):
        await _add_match(service, NOW + timedelta(days=3), now=LATER)


async def test_add_match_unresolved_error_message_is_exact(service: TyperService) -> None:
    await _add_match(service, NOW + timedelta(days=1))

    with pytest.raises(DomainError) as excinfo:
        await _add_match(service, NOW + timedelta(days=2))

    assert str(excinfo.value) == UNRESOLVED_MESSAGE


async def test_add_match_accepts_after_settling_existing(service: TyperService) -> None:
    await _add_match(service, NOW + timedelta(hours=1), now=NOW)
    await service.finish_match(GUILD_ID, Score(1, 0), now=LATER)

    match = await service.add_match(
        GUILD_ID,
        "Everton",
        "Manchester United",
        "Premier League",
        LATER + timedelta(days=1),
        now=LATER,
    )

    assert match.kickoff_at == LATER + timedelta(days=1)


async def test_man_utd_check_runs_before_unresolved_check(service: TyperService) -> None:
    await _add_match(service, NOW + timedelta(days=1))

    with pytest.raises(DomainError, match="Mecz musi obejmować Manchester United."):
        await _add_match(
            service,
            NOW + timedelta(days=2),
            home_team="Everton",
            away_team="Liverpool",
        )
