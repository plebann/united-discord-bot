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
from united_bot.domain import DomainError, Score


@pytest.fixture
async def service(tmp_path: Path):
    session_factory = create_session_factory(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await create_schema(session_factory)
    yield TyperService(
        MatchRepository(session_factory),
        PredictionRepository(session_factory),
    )
    await session_factory.kw["bind"].dispose()


@pytest.mark.asyncio
async def test_my_prediction_hides_settled_prediction_history_when_no_match_is_active(
    service: TyperService,
) -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    await service.add_match(
        1,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
    )
    await service.save_prediction(1, 42, Score(2, 1), kickoff - timedelta(days=1))
    await service.finish_match(1, Score(2, 0), kickoff + timedelta(hours=2))

    result = await service.get_prediction(1, 42, kickoff + timedelta(days=1))

    assert result.active_match is None
    assert result.prediction is None


@pytest.mark.asyncio
async def test_my_prediction_returns_no_prediction_when_user_has_never_typed(
    service: TyperService,
) -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    await service.add_match(
        1,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
    )
    await service.finish_match(1, Score(2, 0), kickoff + timedelta(hours=2))

    result = await service.get_prediction(1, 42, kickoff + timedelta(days=1))

    assert result.active_match is None
    assert result.prediction is None


@pytest.mark.asyncio
async def test_my_prediction_returns_no_history_for_never_typed_user_with_open_match(
    service: TyperService,
) -> None:
    kickoff = datetime(2030, 1, 3, tzinfo=timezone.utc)
    await service.add_match(
        1,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
    )

    result = await service.get_prediction(1, 42, kickoff - timedelta(days=1))

    assert result.active_match is not None
    assert result.active_match.match.id is not None
    assert result.prediction is None


@pytest.mark.asyncio
async def test_prediction_reports_expired_window_after_kickoff(
    service: TyperService,
) -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    await service.add_match(
        1,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
    )

    error_message = "Czas typowania dla meczu Everton - Manchester United minął."
    with pytest.raises(DomainError, match=error_message):
        await service.save_prediction(
            1,
            42,
            Score(2, 1),
            kickoff + timedelta(hours=1),
        )


@pytest.mark.asyncio
async def test_my_prediction_returns_ongoing_match_without_previous_type(
    service: TyperService,
) -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    match = await service.add_match(
        1,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
    )

    result = await service.get_prediction(1, 42, kickoff + timedelta(hours=1))

    assert result.active_match is not None
    assert result.active_match.match.id == match.id
    assert result.active_match.in_progress
    assert result.prediction is None
