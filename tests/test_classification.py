from __future__ import annotations

from united_bot.domain import TyperStatistics
from united_bot.rules import rank_typer_statistics


def test_rank_typer_statistics_applies_stable_full_ties_and_competition_ranks() -> None:
    statistics = (
        TyperStatistics(user_id=30, points=3, exact_hits=0, prediction_count=1),
        TyperStatistics(user_id=20, points=5, exact_hits=1, prediction_count=2),
        TyperStatistics(user_id=10, points=5, exact_hits=1, prediction_count=2),
        TyperStatistics(user_id=40, points=5, exact_hits=0, prediction_count=1),
        TyperStatistics(user_id=50, points=5, exact_hits=0, prediction_count=3),
    )
    names = {
        10: "adam",
        20: "Adam",
        30: "Celina",
        40: "Beata",
        50: "Dorota",
    }

    ranked = rank_typer_statistics(statistics, names.__getitem__)

    assert [
        (
            row.rank,
            row.user_id,
            row.display_name,
            row.points,
            row.exact_hits,
            row.prediction_count,
        )
        for row in ranked
    ] == [
        (1, 10, "adam", 5, 1, 2),
        (1, 20, "Adam", 5, 1, 2),
        (3, 40, "Beata", 5, 0, 1),
        (4, 50, "Dorota", 5, 0, 3),
        (5, 30, "Celina", 3, 0, 1),
    ]
