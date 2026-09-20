from datetime import datetime, timedelta, timezone

import pytest

from united_bot.domain import (
    DomainError,
    Match,
    Score,
    calculate_prediction_points,
)


def score(value: str) -> Score:
    return Score.parse(value)


@pytest.mark.parametrize(
    ("actual", "predicted", "expected"),
    [
        ("4:1", "4:1", 5),
        ("4:1", "4:0", 3),
        ("4:1", "2:1", 3),
        ("4:1", "4:4", 1),
        ("4:1", "2:2", 0),
        ("0:0", "0:1", 1),
        ("0:0", "1:0", 1),
        ("2:2", "1:2", 1),
    ],
)
def test_calculate_prediction_points(actual: str, predicted: str, expected: int) -> None:
    assert calculate_prediction_points(score(actual), score(predicted)) == expected


def test_score_rejects_negative_values() -> None:
    with pytest.raises(DomainError):
        Score.parse("-1:0")


def test_prediction_window_opens_three_days_before_kickoff() -> None:
    kickoff = datetime(2026, 9, 12, 18, 30, tzinfo=timezone.utc)
    match = Match(1, 1, "Everton", "Manchester United", "Premier League", kickoff)

    assert not match.can_predict(kickoff - timedelta(days=3, seconds=1))
    assert match.can_predict(kickoff - timedelta(days=3))
    assert not match.can_predict(kickoff)


def test_finished_match_cannot_change_kickoff() -> None:
    kickoff = datetime(2026, 9, 12, 18, 30, tzinfo=timezone.utc)
    finished = Match(1, 1, "Everton", "Manchester United", "Premier League", kickoff)
    match = finished.finish(score("1:0"))

    with pytest.raises(DomainError):
        match.with_kickoff(kickoff + timedelta(days=1))
