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
from united_bot.discord_bot import UserTyperCog
from united_bot.domain import Score


class Response:
    def __init__(self) -> None:
        self.deferred: list[bool] = []

    async def defer(self, *, ephemeral: bool) -> None:
        self.deferred.append(ephemeral)

    def is_done(self) -> bool:
        return bool(self.deferred)


class Followup:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool) -> None:
        self.messages.append((content, ephemeral))


class Interaction:
    def __init__(self, guild_id: int) -> None:
        self.guild_id = guild_id
        self.response = Response()
        self.followup = Followup()


class DisplayNames:
    def __init__(self, names: dict[int, str]) -> None:
        self.names = names

    async def resolve(self, guild_id: int, user_ids: list[int]) -> dict[int, str]:
        del guild_id
        return {user_id: self.names[user_id] for user_id in user_ids if user_id in self.names}


@pytest.fixture
async def service(tmp_path: Path):
    session_factory = create_session_factory(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await create_schema(session_factory)
    yield TyperService(
        MatchRepository(session_factory),
        PredictionRepository(session_factory),
    )
    await session_factory.kw["bind"].dispose()


async def add_match(
    service: TyperService,
    guild_id: int,
    kickoff: datetime,
) -> None:
    await service.add_match(
        guild_id,
        "Everton",
        "Manchester United",
        "Premier League",
        kickoff,
        now=kickoff - timedelta(days=4),
    )


async def invoke_classification(
    service: TyperService,
    interaction: Interaction,
    names: dict[int, str] | None = None,
) -> None:
    cog = UserTyperCog(service, DisplayNames(names or {}))
    await cog.classification.callback(cog, interaction)


@pytest.mark.asyncio
async def test_classification_command_shows_ranked_guild_history_privately(
    service: TyperService,
) -> None:
    first_kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    await add_match(service, 1, first_kickoff)
    await service.save_prediction(1, 101, Score(2, 1), first_kickoff - timedelta(days=1))
    await service.save_prediction(1, 102, Score(2, 1), first_kickoff - timedelta(days=1))
    await service.save_prediction(1, 103, Score(2, 0), first_kickoff - timedelta(days=1))
    await service.save_prediction(1, 104, Score(2, 0), first_kickoff - timedelta(days=1))
    await service.save_prediction(1, 105, Score(2, 0), first_kickoff - timedelta(days=1))
    await service.finish_match(1, Score(2, 1), first_kickoff + timedelta(hours=2))

    second_kickoff = first_kickoff + timedelta(days=7)
    await add_match(service, 1, second_kickoff)
    await service.save_prediction(1, 103, Score(0, 0), second_kickoff - timedelta(days=1))
    await service.finish_match(1, Score(1, 1), second_kickoff + timedelta(hours=2))

    open_kickoff = second_kickoff + timedelta(days=7)
    await add_match(service, 1, open_kickoff)
    await service.save_prediction(1, 105, Score(3, 0), open_kickoff - timedelta(days=1))

    other_guild_kickoff = datetime(2030, 2, 1, tzinfo=timezone.utc)
    await add_match(service, 2, other_guild_kickoff)
    await service.save_prediction(2, 999, Score(2, 1), other_guild_kickoff - timedelta(days=1))
    await service.finish_match(2, Score(2, 1), other_guild_kickoff + timedelta(hours=2))

    interaction = Interaction(guild_id=1)
    await invoke_classification(
        service,
        interaction,
        {
            101: "Adam",
            102: "adam",
            103: "Beata",
            104: "Celina",
        },
    )

    assert interaction.response.deferred == [True]
    assert interaction.followup.messages == [
        (
            "1. Adam — 5 pkt · 1 dokładne trafienia · 1 typy\n"
            "1. adam — 5 pkt · 1 dokładne trafienia · 1 typy\n"
            "3. Beata — 5 pkt · 0 dokładne trafienia · 2 typy\n"
            "4. Celina — 3 pkt · 0 dokładne trafienia · 1 typy\n"
            "5. Użytkownik 105 — 3 pkt · 0 dokładne trafienia · 2 typy",
            True,
        )
    ]


@pytest.mark.asyncio
async def test_classification_command_reports_empty_guild_privately(
    service: TyperService,
) -> None:
    interaction = Interaction(guild_id=1)

    await invoke_classification(service, interaction)

    assert interaction.response.deferred == [True]
    assert interaction.followup.messages == [("Nikt jeszcze nie typował.", True)]


@pytest.mark.asyncio
async def test_classification_command_sends_every_row_when_response_is_long(
    service: TyperService,
) -> None:
    kickoff = datetime(2030, 1, 1, tzinfo=timezone.utc)
    await add_match(service, 1, kickoff)
    for user_id in range(1000, 1080):
        await service.save_prediction(1, user_id, Score(2, 1), kickoff - timedelta(days=1))

    interaction = Interaction(guild_id=1)
    await invoke_classification(service, interaction)

    assert len(interaction.followup.messages) > 1
    assert all(ephemeral for _, ephemeral in interaction.followup.messages)
    rows = "\n".join(content for content, _ in interaction.followup.messages).splitlines()
    assert len(rows) == 80
    assert rows[0].startswith("1. Użytkownik 1000 — 0 pkt")
    assert rows[-1].startswith("1. Użytkownik 1079 — 0 pkt")
