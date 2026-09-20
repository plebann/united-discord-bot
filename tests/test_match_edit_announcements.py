from datetime import datetime, timedelta, timezone

import pytest

from united_bot.announcements import AnnouncementService
from united_bot.domain import Match


class Publisher:
    def __init__(self) -> None:
        self.messages: list[str] = []

    async def publish(self, content: str) -> None:
        self.messages.append(content)


class Announcements:
    async def was_sent(self, match_id: int, announcement_type: str) -> bool:
        return False

    async def mark_sent(self, match_id: int, announcement_type: str, sent_at: datetime) -> None:
        pass


class Predictions:
    async def list_for_match(self, match_id: int):
        return []


@pytest.mark.asyncio
async def test_edit_announcement_marks_typing_active_within_three_days() -> None:
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    previous = Match(
        1, 1, "Everton", "Manchester United", "Premier League", now + timedelta(days=10)
    )
    updated = previous.with_kickoff(now + timedelta(days=2))
    publisher = Publisher()
    service = AnnouncementService(None, None, Announcements(), publisher)  # type: ignore[arg-type]

    await service.publish_match_edited(previous, updated, now)

    assert "Zmieniono termin meczu i rozpoczęto typowanie" in publisher.messages[0]
    assert "Typowanie już aktywne!" in publisher.messages[0]


@pytest.mark.asyncio
async def test_edit_announcement_keeps_typing_scheduled_beyond_three_days() -> None:
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    previous = Match(
        1, 1, "Everton", "Manchester United", "Premier League", now + timedelta(days=2)
    )
    updated = previous.with_kickoff(now + timedelta(days=10))
    publisher = Publisher()
    service = AnnouncementService(None, None, Announcements(), publisher)  # type: ignore[arg-type]

    await service.publish_match_edited(previous, updated, now)

    assert "Zmieniono termin meczu:" in publisher.messages[0]
    assert "Typowanie rozpocznie się" in publisher.messages[0]


@pytest.mark.asyncio
async def test_match_started_announcement_closes_prediction_window() -> None:
    now = datetime(2030, 1, 1, tzinfo=timezone.utc)
    match = Match(1, 1, "Everton", "Manchester United", "Premier League", now)
    publisher = Publisher()
    service = AnnouncementService(None, Predictions(), Announcements(), publisher)  # type: ignore[arg-type]

    await service.publish_match_started(match, now)

    assert publisher.messages == [
        "Mecz rozpoczęty: Everton - Manchester United\n"
        "Rozgrywki: Premier League\n"
        "Kick-off: <t:1893456000:f>\n"
        "Typowanie zamknięte.\n\n"
        "Nikt jeszcze nie typował na mecz Everton - Manchester United."
    ]
