from types import SimpleNamespace

import pytest

from united_bot.discord_bot import (
    CHANNEL_CONFIGURATION_ERROR,
    ChannelCheckFailure,
    configured_channel_check,
)


def test_channel_check_accepts_configured_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHANNEL_ID", "123")

    assert configured_channel_check(
        SimpleNamespace(guild=object(), channel_id=123)
    )


def test_channel_check_rejects_other_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHANNEL_ID", "123")

    with pytest.raises(ChannelCheckFailure, match="123"):
        configured_channel_check(SimpleNamespace(guild=object(), channel_id=456))


def test_channel_check_rejects_direct_messages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHANNEL_ID", "123")

    with pytest.raises(ChannelCheckFailure, match="tylko na skonfigurowanym kanale"):
        configured_channel_check(SimpleNamespace(guild=None, channel_id=None))


def test_channel_check_rejects_missing_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CHANNEL_ID", raising=False)

    with pytest.raises(ChannelCheckFailure, match="nie ma skonfigurowanego"):
        configured_channel_check(SimpleNamespace(guild=object(), channel_id=123))


def test_channel_configuration_message_is_stable() -> None:
    assert "kanału dla komend" in CHANNEL_CONFIGURATION_ERROR
