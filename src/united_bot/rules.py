from __future__ import annotations

from datetime import datetime

from .domain import DomainError, Match


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
