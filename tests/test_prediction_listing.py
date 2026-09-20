from datetime import datetime, timedelta, timezone

from united_bot.domain import Prediction, Score, sort_predictions_for_listing

T0 = datetime(2026, 9, 12, 18, 30, tzinfo=timezone.utc)


def pred(user_id: int, score: str, offset_seconds: int = 0) -> Prediction:
    return Prediction(
        match_id=1,
        user_id=user_id,
        score=Score.parse(score),
        submitted_at=T0 + timedelta(seconds=offset_seconds),
    )


def ids(predictions: list[Prediction]) -> list[int]:
    return [prediction.user_id for prediction in predictions]


def test_empty_list_stays_empty() -> None:
    assert sort_predictions_for_listing([]) == []


def test_groups_home_wins_then_draws_then_away_wins() -> None:
    home_win = pred(1, "3:0")
    draw = pred(2, "1:1")
    away_win = pred(3, "0:2")

    ordered = sort_predictions_for_listing([away_win, draw, home_win])

    assert ids(ordered) == [1, 2, 3]


def test_home_wins_sorted_by_goal_difference_then_winner_goals() -> None:
    big_diff = pred(1, "3:0")  # diff 3
    diff_a = pred(2, "4:2")  # diff 2, winner 4
    diff_b = pred(3, "2:0")  # diff 2, winner 2

    ordered = sort_predictions_for_listing([diff_b, diff_a, big_diff])

    assert ids(ordered) == [1, 2, 3]


def test_draws_sorted_by_total_goals_descending() -> None:
    total_4 = pred(1, "2:2")
    total_2 = pred(2, "1:1")
    total_0 = pred(3, "0:0")

    ordered = sort_predictions_for_listing([total_0, total_2, total_4])

    assert ids(ordered) == [1, 2, 3]


def test_away_wins_sorted_by_goal_difference_then_winner_goals() -> None:
    big_diff = pred(1, "0:4")  # diff 4
    diff_a = pred(2, "1:3")  # diff 2, winner 3
    diff_b = pred(3, "0:2")  # diff 2, winner 2

    ordered = sort_predictions_for_listing([diff_b, diff_a, big_diff])

    assert ids(ordered) == [1, 2, 3]


def test_identical_types_tie_break_on_submission_time() -> None:
    first = pred(1, "2:0", offset_seconds=0)
    second = pred(2, "2:0", offset_seconds=10)

    ordered = sort_predictions_for_listing([second, first])

    assert ids(ordered) == [1, 2]
