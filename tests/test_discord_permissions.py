from types import SimpleNamespace

import discord
import pytest

from united_bot.discord_bot import TyperCog


class Response:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def send_message(self, message: str, **_: object) -> None:
        self.messages.append(message)


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
