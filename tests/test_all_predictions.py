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
from united_bot.domain import Score

DB_PATH = Path(__file__).resolve().parent.parent / "test_all_predictions.db"


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


@pytest.mark.asyncio
async def test_list_predictions_returns_sorted_types_for_current_match(
    service: TyperService,
) -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    now = kickoff - timedelta(days=1)
    await service.add_match(
        1,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
    )
    await service.save_prediction(1, 101, Score(0, 2), now)
    await service.save_prediction(1, 102, Score(1, 1), now + timedelta(minutes=1))
    await service.save_prediction(1, 103, Score(3, 0), now + timedelta(minutes=2))

    match, predictions = await service.list_predictions(1, now + timedelta(minutes=3))

    assert match is not None
    assert [prediction.user_id for prediction in predictions] == [103, 102, 101]


@pytest.mark.asyncio
async def test_list_predictions_breaks_identical_types_by_submission_time(
    service: TyperService,
) -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    now = kickoff - timedelta(days=1)
    await service.add_match(
        1,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
    )
    await service.save_prediction(1, 101, Score(2, 0), now)
    await service.save_prediction(1, 102, Score(2, 0), now + timedelta(minutes=1))

    _, predictions = await service.list_predictions(1, now + timedelta(minutes=2))

    assert [prediction.user_id for prediction in predictions] == [101, 102]


@pytest.mark.asyncio
async def test_list_predictions_returns_no_match_outside_prediction_window(
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
    await service.save_prediction(1, 101, Score(2, 0), kickoff - timedelta(days=1))

    match, predictions = await service.list_predictions(1, kickoff + timedelta(hours=1))

    assert match is None
    assert predictions == []
