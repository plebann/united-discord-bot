from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum


class MatchStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    FINISHED = "FINISHED"


class ResultType(StrEnum):
    HOME_WIN = "HOME_WIN"
    DRAW = "DRAW"
    AWAY_WIN = "AWAY_WIN"


class DomainError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class Score:
    home: int
    away: int

    def __post_init__(self) -> None:
        if self.home < 0 or self.away < 0:
            raise DomainError("Liczba goli nie może być ujemna.")

    @classmethod
    def parse(cls, value: str) -> Score:
        parts = value.strip().split(":")
        if len(parts) != 2:
            raise DomainError("Wynik musi mieć format gole_gospodarzy:gole_gości, np. 3:0.")
        try:
            return cls(int(parts[0]), int(parts[1]))
        except ValueError as exc:
            raise DomainError("Liczby goli muszą być całkowite.") from exc


def result_type(score: Score) -> ResultType:
    if score.home > score.away:
        return ResultType.HOME_WIN
    if score.home < score.away:
        return ResultType.AWAY_WIN
    return ResultType.DRAW


def calculate_prediction_points(actual: Score, predicted: Score) -> int:
    if actual == predicted:
        return 5

    correct_result = result_type(actual) == result_type(predicted)
    correct_goal_count = actual.home == predicted.home or actual.away == predicted.away

    if correct_result:
        return 3 if correct_goal_count else 2
    return 1 if correct_goal_count else 0


@dataclass(frozen=True, slots=True)
class Match:
    id: int | None
    guild_id: int
    home_team: str
    away_team: str
    competition: str
    kickoff_at: datetime
    status: MatchStatus = MatchStatus.SCHEDULED
    final_score: Score | None = None

    def __post_init__(self) -> None:
        kickoff = self.kickoff_at
        if kickoff.tzinfo is None:
            raise DomainError("Kickoff musi zawierać strefę czasową.")
        if self.home_team.strip() == "" or self.away_team.strip() == "":
            raise DomainError("Drużyny nie mogą być puste.")
        if self.competition.strip() == "":
            raise DomainError("Rozgrywki nie mogą być puste.")
        if self.status == MatchStatus.FINISHED and self.final_score is None:
            raise DomainError("Zakończony mecz musi mieć wynik.")

    @property
    def prediction_opens_at(self) -> datetime:
        return self.kickoff_at - timedelta(days=3)

    def can_predict(self, now: datetime) -> bool:
        if now.tzinfo is None:
            raise DomainError("Bieżący czas musi zawierać strefę czasową.")
        return (
            self.status == MatchStatus.SCHEDULED
            and self.prediction_opens_at <= now < self.kickoff_at
        )

    def with_kickoff(self, kickoff_at: datetime) -> Match:
        if self.status == MatchStatus.FINISHED:
            raise DomainError("Nie można zmienić kickoffu rozliczonego meczu.")
        return Match(
            id=self.id,
            guild_id=self.guild_id,
            home_team=self.home_team,
            away_team=self.away_team,
            competition=self.competition,
            kickoff_at=kickoff_at,
            status=self.status,
            final_score=self.final_score,
        )

    def finish(self, score: Score) -> Match:
        if self.status == MatchStatus.FINISHED:
            raise DomainError("Mecz ma już wprowadzony wynik.")
        return Match(
            id=self.id,
            guild_id=self.guild_id,
            home_team=self.home_team,
            away_team=self.away_team,
            competition=self.competition,
            kickoff_at=self.kickoff_at,
            status=MatchStatus.FINISHED,
            final_score=score,
        )


@dataclass(frozen=True, slots=True)
class Prediction:
    match_id: int
    user_id: int
    score: Score
    points: int | None = None
    submitted_at: datetime | None = None
    updated_at: datetime | None = None


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def prediction_listing_key(prediction: Prediction) -> tuple[int, int, int, int, bool, datetime]:
    score = prediction.score
    if score.home > score.away:
        group, goal_difference, winner_goals, loser_goals = (
            0,
            score.home - score.away,
            score.home,
            score.away,
        )
    elif score.home < score.away:
        group, goal_difference, winner_goals, loser_goals = (
            2,
            score.away - score.home,
            score.away,
            score.home,
        )
    else:
        group, goal_difference, winner_goals, loser_goals = (
            1,
            0,
            score.home + score.away,
            0,
        )
    submitted_at = prediction.submitted_at
    return (
        group,
        -goal_difference,
        -winner_goals,
        -loser_goals,
        submitted_at is None,
        submitted_at or _EPOCH,
    )


def sort_predictions_for_listing(predictions: list[Prediction]) -> list[Prediction]:
    return sorted(predictions, key=prediction_listing_key)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
