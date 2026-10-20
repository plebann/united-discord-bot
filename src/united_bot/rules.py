from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from .domain import (
    DomainError,
    Match,
    MatchStatus,
    RankedTyperStatistics,
    TyperStatistics,
)


def select_active_match(
    in_progress: Match | None,
    open_window: Match | None,
) -> tuple[Match, bool] | None:
    """Choose the active match: live unresolved first, then open window."""
    if in_progress is not None:
        return in_progress, True
    if open_window is not None:
        return open_window, False
    return None


def ensure_deletable(match: Match) -> None:
    if match.status is not MatchStatus.SCHEDULED:
        raise DomainError("Nie można usunąć rozliczonego meczu.")


def ensure_man_utd_involvement(home_team: str, away_team: str) -> None:
    if "manchester united" not in {home_team.strip().lower(), away_team.strip().lower()}:
        raise DomainError("Mecz musi obejmować Manchester United.")


def ensure_kickoff_in_future(
    kickoff_at: datetime,
    now: datetime,
    message: str = "Kickoff musi być w przyszłości.",
) -> None:
    if kickoff_at.tzinfo is None or now.tzinfo is None:
        raise DomainError("Kickoff i bieżący czas muszą zawierać strefę czasową.")
    if not kickoff_at > now:
        raise DomainError(message)


def ensure_no_other_unresolved(existing: Match | None) -> None:
    if existing is not None:
        raise DomainError(
            f"Mecz {existing.home_team} - {existing.away_team} nie został jeszcze rozliczony. "
            f"Zamknij go przed dodaniem kolejnego spotkania."
        )


def rank_typer_statistics(
    statistics: Iterable[TyperStatistics],
    display_user: Callable[[int], str],
) -> tuple[RankedTyperStatistics, ...]:
    named_statistics = [(row, display_user(row.user_id)) for row in statistics]
    ordered = sorted(
        named_statistics,
        key=lambda item: (
            -item[0].points,
            -item[0].exact_hits,
            item[0].prediction_count,
            item[1].casefold(),
            item[0].user_id,
        ),
    )

    ranked = []
    previous_result: tuple[int, int, int] | None = None
    rank = 0
    for index, (row, display_name) in enumerate(ordered, start=1):
        result = (row.points, row.exact_hits, row.prediction_count)
        if result != previous_result:
            rank = index
            previous_result = result
        ranked.append(
            RankedTyperStatistics(
                rank=rank,
                user_id=row.user_id,
                display_name=display_name,
                points=row.points,
                exact_hits=row.exact_hits,
                prediction_count=row.prediction_count,
            )
        )
    return tuple(ranked)
