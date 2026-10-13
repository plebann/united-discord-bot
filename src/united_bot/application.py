from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .db import MatchRepository, PredictionRepository
from .domain import (
    DomainError,
    Match,
    Prediction,
    Score,
    sort_predictions_for_listing,
    utc_now,
)
from .rules import (
    ensure_deletable,
    ensure_kickoff_in_future,
    ensure_man_utd_involvement,
    ensure_no_other_unresolved,
    select_active_match,
)


@dataclass(frozen=True, slots=True)
class ActiveMatch:
    match: Match
    in_progress: bool


@dataclass(frozen=True, slots=True)
class ActivePrediction:
    active_match: ActiveMatch | None
    prediction: Prediction | None


class TyperService:
    def __init__(
        self,
        matches: MatchRepository,
        predictions: PredictionRepository,
    ) -> None:
        self.matches = matches
        self.predictions = predictions

    async def add_match(
        self,
        guild_id: int,
        home_team: str,
        away_team: str,
        competition: str,
        kickoff_at: datetime,
        now: datetime | None = None,
    ) -> Match:
        current_time = now or utc_now()
        ensure_man_utd_involvement(home_team, away_team)
        ensure_kickoff_in_future(kickoff_at, current_time)
        existing = await self.matches.get_next_scheduled(guild_id)
        ensure_no_other_unresolved(existing)
        return await self.matches.add(
            Match(
                id=None,
                guild_id=guild_id,
                home_team=home_team.strip(),
                away_team=away_team.strip(),
                competition=competition.strip(),
                kickoff_at=kickoff_at,
            )
        )

    async def edit_kickoff(
        self,
        guild_id: int,
        kickoff_at: datetime,
        now: datetime | None = None,
    ) -> tuple[Match, Match]:
        current_time = now or utc_now()
        ensure_kickoff_in_future(
            kickoff_at, current_time, message="Nowy kickoff musi być w przyszłości."
        )
        match = await self.matches.get_next_scheduled(guild_id)
        if match is None:
            raise LookupError("Nie znaleziono nierozliczonego meczu.")
        if match.kickoff_at == kickoff_at:
            raise DomainError("Termin meczu nie został zmieniony.")
        return match, await self.matches.update(match.with_kickoff(kickoff_at))

    async def active_match(
        self,
        guild_id: int,
        now: datetime | None = None,
    ) -> ActiveMatch | None:
        current_time = now or utc_now()
        selected = select_active_match(
            await self.matches.get_in_progress(guild_id, current_time),
            await self.matches.get_current(guild_id, current_time),
        )
        if selected is None:
            return None
        match, in_progress = selected
        return ActiveMatch(match=match, in_progress=in_progress)

    async def save_prediction(
        self,
        guild_id: int,
        user_id: int,
        score: Score,
        now: datetime | None = None,
    ) -> tuple[Match, Prediction, Prediction | None]:
        current_time = now or utc_now()
        active = await self.active_match(guild_id, current_time)
        if active is None:
            raise DomainError("Nie ma teraz aktywnego meczu do typowania.")
        if active.in_progress:
            raise DomainError(
                f"Czas typowania dla meczu {active.match.home_team} - "
                f"{active.match.away_team} minął."
            )
        previous_prediction = await self.predictions.get(active.match.id, user_id)
        prediction = await self.predictions.upsert(
            Prediction(
                match_id=active.match.id,
                user_id=user_id,
                score=score,
                updated_at=current_time,
            )
        )
        return active.match, prediction, previous_prediction

    async def get_prediction(
        self,
        guild_id: int,
        user_id: int,
        now: datetime | None = None,
    ) -> ActivePrediction:
        active = await self.active_match(guild_id, now)
        if active is None:
            return ActivePrediction(active_match=None, prediction=None)
        return ActivePrediction(
            active_match=active,
            prediction=await self.predictions.get(active.match.id, user_id),
        )

    async def list_predictions(
        self,
        guild_id: int,
        now: datetime | None = None,
    ) -> tuple[ActiveMatch | None, list[Prediction]]:
        active = await self.active_match(guild_id, now)
        if active is None:
            return None, []
        predictions = await self.predictions.list_for_match(active.match.id)
        return active, sort_predictions_for_listing(predictions)

    async def list_matches(self, guild_id: int) -> list[Match]:
        return await self.matches.list_all(guild_id)

    async def delete_match(self, guild_id: int, match_id: int) -> Match:
        match = await self.matches.get(match_id, guild_id)
        if match is None:
            raise LookupError(f"Nie znaleziono meczu o identyfikatorze #{match_id}.")
        ensure_deletable(match)
        return await self.matches.delete(match_id, guild_id)

    async def finish_match(
        self,
        guild_id: int,
        score: Score,
        now: datetime | None = None,
    ) -> tuple[Match, list[Prediction]]:
        current_time = now or utc_now()
        match = await self.matches.get_next_scheduled(guild_id)
        if match is None:
            raise LookupError("Nie znaleziono nierozliczonego meczu.")
        if match.kickoff_at > current_time:
            raise DomainError("Najbliższy mecz jeszcze się nie rozpoczął.")
        finished = await self.matches.update(match.finish(score))
        predictions = await self.predictions.settle_match(match.id, score)
        return finished, predictions
