import pytest

from united_bot.discord_bot import _acknowledge_announcement


class Followup:
    def __init__(self) -> None:
        self.messages: list[tuple[str, bool]] = []

    async def send(self, content: str, *, ephemeral: bool) -> None:
        self.messages.append((content, ephemeral))


class Response:
    def is_done(self) -> bool:
        return True


@pytest.mark.asyncio
async def test_announcement_commands_finish_deferred_interaction() -> None:
    followup = Followup()
    interaction = type(
        "Interaction",
        (),
        {"response": Response(), "followup": followup},
    )()

    await _acknowledge_announcement(interaction)

    assert followup.messages == [("Ogłoszenie zostało opublikowane.", True)]
