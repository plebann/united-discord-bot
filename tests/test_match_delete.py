from __future__ import annotations

import shutil
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from united_bot.application import TyperService
from united_bot.db import (
    AnnouncementRepository,
    MatchRepository,
    PredictionRepository,
    create_schema,
    create_session_factory,
)
from united_bot.domain import DomainError, Prediction, Score

# NOTE: uses a self-managed scratch dir instead of pytest's `tmp_path`. In
# sandboxed Windows hosts pytest's own basetemp/tmp_path setup raises
# PermissionError during session cleanup (affecting every tmp_path test), so
# the SQLite temp file lives under a per-test workspace path we control.
SCRATCH_ROOT = Path(__file__).parent.parent / ".test_scratch"


@pytest.fixture
async def factory():
    base = SCRATCH_ROOT / uuid.uuid4().hex
    base.mkdir(parents=True)
    session_factory = create_session_factory(f"sqlite+aiosqlite:///{base / 'test.db'}")
    await create_schema(session_factory)
    yield session_factory
    await session_factory.kw["bind"].dispose()
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture
async def service(factory) -> TyperService:
    return TyperService(MatchRepository(factory), PredictionRepository(factory))


@pytest.fixture
async def predictions(factory) -> PredictionRepository:
    return PredictionRepository(factory)


@pytest.fixture
async def announcements(factory) -> AnnouncementRepository:
    return AnnouncementRepository(factory)


GUILD_ID = 1
NOW = datetime(2026, 9, 12, 18, 30, tzinfo=timezone.utc)
LATER = NOW + timedelta(hours=2)

NOT_FOUND_MESSAGE_7 = "Nie znaleziono meczu o identyfikatorze #7."
FINISHED_MESSAGE = "Nie można usunąć rozliczonego meczu."


async def _add_match(service: TyperService, kickoff: datetime, now: datetime = NOW) -> int:
    match = await service.add_match(
        GUILD_ID,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
        now=now,
    )
    return match.id


async def test_delete_match_removes_match_predictions_and_announcements(
    service: TyperService,
    predictions: PredictionRepository,
    announcements: AnnouncementRepository,
) -> None:
    match_id = await _add_match(service, NOW + timedelta(days=2))
    await predictions.upsert(
        Prediction(match_id=match_id, user_id=42, score=Score(2, 1), updated_at=NOW)
    )
    await announcements.mark_sent(match_id, "MATCH_CONFIGURED", NOW)
    assert await announcements.was_sent(match_id, "MATCH_CONFIGURED") is True

    deleted = await service.delete_match(GUILD_ID, match_id)

    assert deleted.id == match_id
    assert await service.list_matches(GUILD_ID) == []
    assert await predictions.get(match_id, 42) is None
    assert await predictions.list_for_match(match_id) == []
    assert await announcements.was_sent(match_id, "MATCH_CONFIGURED") is False


async def test_delete_match_rejects_unknown_id_with_exact_message(
    service: TyperService,
) -> None:
    with pytest.raises(LookupError) as excinfo:
        await service.delete_match(GUILD_ID, 7)

    assert str(excinfo.value) == NOT_FOUND_MESSAGE_7


async def test_delete_match_second_call_raises_not_found(service: TyperService) -> None:
    match_id = await _add_match(service, NOW + timedelta(days=2))
    await service.delete_match(GUILD_ID, match_id)

    with pytest.raises(LookupError) as excinfo:
        await service.delete_match(GUILD_ID, match_id)

    assert str(excinfo.value) == f"Nie znaleziono meczu o identyfikatorze #{match_id}."


async def test_delete_match_rejects_finished_match_with_exact_message(
    service: TyperService,
) -> None:
    match_id = await _add_match(service, NOW + timedelta(hours=1))
    await service.finish_match(GUILD_ID, Score(1, 0), now=LATER)

    with pytest.raises(DomainError) as excinfo:
        await service.delete_match(GUILD_ID, match_id)

    assert str(excinfo.value) == FINISHED_MESSAGE

    matches = await service.list_matches(GUILD_ID)
    assert len(matches) == 1
    assert matches[0].id == match_id


async def test_delete_match_rejects_finished_match_from_other_guild(
    service: TyperService,
) -> None:
    match_id = await _add_match(service, NOW + timedelta(hours=1))
    await service.finish_match(GUILD_ID, Score(1, 0), now=LATER)

    with pytest.raises(LookupError):
        await service.delete_match(GUILD_ID + 1, match_id)


async def test_delete_match_accepts_started_unsettled_match(service: TyperService) -> None:
    match_id = await _add_match(service, NOW + timedelta(hours=1))

    deleted = await service.delete_match(GUILD_ID, match_id)

    assert deleted.id == match_id
    assert await service.list_matches(GUILD_ID) == []


async def test_add_match_allowed_after_deletion(service: TyperService) -> None:
    match_id = await _add_match(service, NOW + timedelta(days=2))
    await service.delete_match(GUILD_ID, match_id)

    match = await service.add_match(
        GUILD_ID,
        "Everton",
        "Manchester United",
        "Premier League",
        NOW + timedelta(days=3),
        now=NOW,
    )

    assert match.kickoff_at == NOW + timedelta(days=3)
