from datetime import datetime, timezone

import pytest

from united_bot.discord_bot import parse_kickoff
from united_bot.domain import DomainError


def test_parse_kickoff_uses_polish_local_time() -> None:
    parsed = parse_kickoff("2026-09-12 18:30")

    assert parsed == datetime(2026, 9, 12, 16, 30, tzinfo=timezone.utc)


def test_parse_kickoff_rejects_timezone_input() -> None:
    with pytest.raises(DomainError, match="RRRR-MM-DD GG:MM"):
        parse_kickoff("2026-09-12T18:30:00+00:00")
