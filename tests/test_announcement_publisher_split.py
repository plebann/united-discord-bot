import pytest

from united_bot.discord_bot import DiscordAnnouncementPublisher


class FakeChannel:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, content: str) -> None:
        self.sent.append(content)


class FakeBot:
    def __init__(self, channel: FakeChannel) -> None:
        self._channel = channel

    def get_channel(self, channel_id: int):
        return self._channel


@pytest.mark.asyncio
async def test_publisher_splits_long_announcement_into_follow_ups(monkeypatch):
    monkeypatch.setenv("CHANNEL_ID", "42")
    channel = FakeChannel()
    publisher = DiscordAnnouncementPublisher()
    publisher.bot = FakeBot(channel)

    content = "Mecz rozpoczęty\n" + "\n".join(f"linia {i}" for i in range(400))
    await publisher.publish(content)

    assert len(channel.sent) > 1
    assert all(len(chunk) <= 1900 for chunk in channel.sent)
    assert "\n".join(channel.sent) == content


@pytest.mark.asyncio
async def test_publisher_sends_short_announcement_as_single_message(monkeypatch):
    monkeypatch.setenv("CHANNEL_ID", "42")
    channel = FakeChannel()
    publisher = DiscordAnnouncementPublisher()
    publisher.bot = FakeBot(channel)

    content = "Mecz rozpoczęty\nTypowanie zamknięte."
    await publisher.publish(content)

    assert channel.sent == [content]
