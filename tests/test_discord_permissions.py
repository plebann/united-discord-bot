from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import discord
import pytest

from united_bot.discord_bot import TyperCog
from united_bot.domain import Match


class Response:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.deferred = False

    async def send_message(self, message: str, **_: object) -> None:
        self.messages.append(message)

    async def defer(self, **_: object) -> None:
        self.deferred = True


class Followup:
    def __init__(self) -> None:
        self.chunks: list[str] = []

    async def send(self, content: str, **_: object) -> None:
        self.chunks.append(content)


class StubService:
    async def list_matches(self, guild_id: int):
        return [
            Match(
                id=1,
                guild_id=guild_id,
                home_team="Manchester United",
                away_team="Chelsea",
                competition="Premier League",
                kickoff_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
            )
        ]


@pytest.mark.asyncio
async def test_manage_server_permission_from_interaction_is_accepted() -> None:
    interaction_permissions = discord.Permissions.none()
    interaction_permissions.manage_guild = True
    user_permissions = discord.Permissions.none()
    response = Response()
    interaction = SimpleNamespace(
        guild=object(),
        permissions=interaction_permissions,
        user=SimpleNamespace(guild_permissions=user_permissions),
        response=response,
    )

    assert await TyperCog(object(), object())._require_admin(interaction) is True
    assert response.messages == []


@pytest.mark.asyncio
async def test_list_matches_sends_listing_chunks_for_admin() -> None:
    followup = Followup()
    response = Response()
    interaction = SimpleNamespace(
        guild=object(),
        guild_id=42,
        permissions=discord.Permissions.all(),
        response=response,
        followup=followup,
    )
    cog = TyperCog(StubService(), object())

    await cog.list_matches.callback(cog, interaction)

    assert response.deferred is True
    assert len(followup.chunks) >= 1
    assert any("#1 · Chelsea" in chunk for chunk in followup.chunks)


@pytest.mark.asyncio
async def test_list_matches_denied_for_non_admin() -> None:
    followup = Followup()
    response = Response()
    interaction = SimpleNamespace(
        guild=object(),
        guild_id=42,
        permissions=discord.Permissions.none(),
        response=response,
        followup=followup,
    )
    cog = TyperCog(object(), object())

    await cog.list_matches.callback(cog, interaction)

    # Non-admin gets a message, no deferred listing
    assert len(response.messages) == 1
    assert followup.chunks == []
