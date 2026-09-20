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
from united_bot.discord_bot import format_all_predictions
from united_bot.domain import Match, Prediction, Score

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
async def test_list_predictions_returns_live_match_after_kickoff(
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

    assert match is not None
    assert [prediction.user_id for prediction in predictions] == [101]


@pytest.mark.asyncio
async def test_list_predictions_prefers_live_match_over_open_window_match(
    service: TyperService,
) -> None:
    live_kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc) - timedelta(hours=1)
    future_kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc) + timedelta(days=2)
    await service.add_match(
        1,
        "Manchester United",
        "Liverpool",
        "Premier League",
        future_kickoff,
    )
    await service.save_prediction(1, 201, Score(1, 1), future_kickoff - timedelta(days=2))
    await service.add_match(
        1,
        "Everton",
        "Manchester United",
        "Premier League",
        live_kickoff,
    )
    await service.save_prediction(1, 101, Score(2, 0), live_kickoff - timedelta(hours=2))

    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    match, predictions = await service.list_predictions(1, now)

    assert match is not None
    assert match.kickoff_at == live_kickoff
    assert [prediction.user_id for prediction in predictions] == [101]


@pytest.mark.asyncio
async def test_list_predictions_returns_no_match_when_none_active(
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

    match, predictions = await service.list_predictions(1, kickoff - timedelta(days=10))

    assert match is None
    assert predictions == []


def _match_with_kickoff(kickoff_at: datetime) -> Match:
    return Match(
        id=7,
        guild_id=1,
        home_team="Everton",
        away_team="Manchester United",
        competition="Premier League",
        kickoff_at=kickoff_at,
    )


def _prediction(user_id: int) -> Prediction:
    return Prediction(match_id=7, user_id=user_id, score=Score(3, 0), submitted_at=None)


def test_format_all_predictions_prefixes_live_match_header() -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    message = format_all_predictions(
        _match_with_kickoff(kickoff),
        [_prediction(101)],
        now=kickoff + timedelta(hours=1),
    )

    assert (
        message == "\u26bd Mecz Everton - Manchester United trwa — typowanie zamknięte.\n"
        "Typy na mecz Everton - Manchester United\n\n\U0001f535 Wygrana gospodarzy\n"
        "1. <@101> — 3:0"
    )


def test_format_all_predictions_prefixes_header_on_empty_listing() -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    message = format_all_predictions(
        _match_with_kickoff(kickoff),
        [],
        now=kickoff + timedelta(hours=1),
    )

    assert (
        message == "\u26bd Mecz Everton - Manchester United trwa — typowanie zamknięte.\n"
        "Nikt jeszcze nie typował na mecz Everton - Manchester United."
    )


def test_format_all_predictions_has_no_header_for_open_window_match() -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    message = format_all_predictions(
        _match_with_kickoff(kickoff),
        [_prediction(101)],
        now=kickoff - timedelta(days=1),
    )

    assert (
        message == "Typy na mecz Everton - Manchester United\n\n\U0001f535 Wygrana gospodarzy\n"
        "1. <@101> — 3:0"
    )
