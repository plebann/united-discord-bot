from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from united_bot.announcements import AnnouncementService
from united_bot.application import TyperService
from united_bot.db import (
    AnnouncementRepository,
    MatchRepository,
    PredictionRepository,
    create_schema,
    create_session_factory,
)
from united_bot.domain import Score

DB_PATH = Path(__file__).resolve().parent.parent / "test_match_started_listings.db"


class RecordingPublisher:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def publish(self, content: str) -> None:
        self.messages.append(content)


class FakeNameResolver:
    def __init__(self, names: dict[int, str]) -> None:
        self.names = names
        self.calls = 0

    async def resolve(self, guild_id: int, user_ids: list[int]) -> dict[int, str]:
        self.calls += 1
        return {user_id: name for user_id, name in self.names.items() if user_id in user_ids}


@pytest.fixture
async def started_env():
    for suffix in ("", "-wal", "-shm"):
        DB_PATH.with_name(DB_PATH.name + suffix).unlink(missing_ok=True)
    session_factory = create_session_factory(f"sqlite+aiosqlite:///{DB_PATH}")
    await create_schema(session_factory)
    matches = MatchRepository(session_factory)
    predictions = PredictionRepository(session_factory)
    publisher = RecordingPublisher()
    resolver = FakeNameResolver({})
    service = AnnouncementService(
        matches,
        predictions,
        AnnouncementRepository(session_factory),
        publisher,
        resolver,
    )
    typer = TyperService(matches, predictions)
    yield service, typer, publisher, resolver
    await session_factory.kw["bind"].dispose()
    for suffix in ("", "-wal", "-shm"):
        DB_PATH.with_name(DB_PATH.name + suffix).unlink(missing_ok=True)


async def seed_started_match(typer: TyperService, kickoff: datetime) -> None:
    await typer.add_match(
        1,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
    )


@pytest.mark.asyncio
async def test_match_started_announcement_lists_types_with_resolved_names(started_env):
    service, typer, publisher, resolver = started_env
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    now = kickoff - timedelta(days=1)
    await seed_started_match(typer, kickoff)
    await typer.save_prediction(1, 101, Score(0, 2), now)
    await typer.save_prediction(1, 102, Score(1, 1), now + timedelta(minutes=1))
    await typer.save_prediction(1, 103, Score(3, 0), now + timedelta(minutes=2))
    resolver.names = {101: "Kowalski", 103: "Nowak"}

    match, _ = await typer.list_predictions(1, now + timedelta(minutes=3))
    assert match is not None
    await service.publish_match_started(match, kickoff)

    assert len(publisher.messages) == 1
    listing_lines = [
        "Typy na mecz Everton - Manchester United",
        "",
        "\U0001f535 Wygrana gospodarzy",
        "1. Nowak — 3:0",
        "",
        "\u26aa Remis",
        "1. <@102> — 1:1",
        "",
        "\U0001f534 Wygrana gości",
        "1. Kowalski — 0:2",
    ]
    assert "\n".join(listing_lines) in publisher.messages[0]
    assert "Mecz rozpoczęty: Everton - Manchester United" in publisher.messages[0]
    assert "<@101>" not in publisher.messages[0]
    assert "<@103>" not in publisher.messages[0]


@pytest.mark.asyncio
async def test_match_started_announcement_reports_no_types_and_skips_name_lookup(started_env):
    service, typer, publisher, resolver = started_env
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    await seed_started_match(typer, kickoff)

    match, _ = await typer.list_predictions(1, kickoff - timedelta(days=1))
    assert match is not None
    await service.publish_match_started(match, kickoff)

    assert len(publisher.messages) == 1
    assert "Nikt jeszcze nie typował na mecz Everton - Manchester United." in publisher.messages[0]
    assert resolver.calls == 0


@pytest.mark.asyncio
async def test_match_started_announcement_is_published_once_per_match(started_env):
    service, typer, publisher, resolver = started_env
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    now = kickoff - timedelta(days=1)
    await seed_started_match(typer, kickoff)
    await typer.save_prediction(1, 101, Score(2, 0), now)
    resolver.names = {101: "Kowalski"}

    match, _ = await typer.list_predictions(1, now + timedelta(minutes=1))
    assert match is not None
    await service.publish_match_started(match, kickoff)
    await service.publish_match_started(match, kickoff + timedelta(minutes=5))

    assert len(publisher.messages) == 1
    assert resolver.calls == 1


@pytest.mark.asyncio
async def test_match_started_announcement_falls_back_to_mentions_without_resolver(
    started_env,
):
    service, typer, publisher, _ = started_env
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    now = kickoff - timedelta(days=1)
    await seed_started_match(typer, kickoff)
    await typer.save_prediction(1, 101, Score(2, 0), now)
    service.display_names = None

    match, _ = await typer.list_predictions(1, now + timedelta(minutes=1))
    assert match is not None
    await service.publish_match_started(match, kickoff)

    assert "1. <@101> — 2:0" in publisher.messages[0]
