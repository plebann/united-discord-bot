from datetime import datetime, timedelta, timezone

from united_bot.domain import Match
from united_bot.rules import select_active_match

KICKOFF = datetime(2030, 1, 1, tzinfo=timezone.utc)


def match(kickoff_at: datetime = KICKOFF) -> Match:
    return Match(
        id=1,
        guild_id=1,
        home_team="Manchester United",
        away_team="Everton",
        competition="Premier League",
        kickoff_at=kickoff_at,
    )


def test_select_active_match_prefers_in_progress() -> None:
    in_progress = match(KICKOFF - timedelta(hours=1))
    open_window = match(KICKOFF + timedelta(days=1))

    assert select_active_match(in_progress, open_window) == (in_progress, True)


def test_select_active_match_uses_open_window_when_no_match_is_in_progress() -> None:
    open_window = match()

    assert select_active_match(None, open_window) == (open_window, False)


def test_select_active_match_returns_none_when_neither_match_exists() -> None:
    assert select_active_match(None, None) is None
