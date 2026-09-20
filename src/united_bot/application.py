from __future__ import annotations

from datetime import datetime

from .db import MatchRepository, PredictionRepository
from .domain import DomainError, Match, Prediction, Score, ensure_kickoff_in_future, utc_now


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
        if "manchester united" not in {home_team.strip().lower(), away_team.strip().lower()}:
            raise DomainError("Mecz musi obejmować Manchester United.")
        ensure_kickoff_in_future(kickoff_at, current_time)
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

    async def save_prediction(
        self,
        guild_id: int,
        user_id: int,
        score: Score,
        now: datetime | None = None,
    ) -> tuple[Match, Prediction, Prediction | None]:
        current_time = now or utc_now()
        match = await self.matches.get_current(guild_id, current_time)
        if match is None:
            in_progress = await self.matches.get_in_progress(guild_id, current_time)
            if in_progress is not None:
                raise DomainError(
                    f"Czas typowania dla meczu {in_progress.home_team} - "
                    f"{in_progress.away_team} minął."
                )
            raise DomainError("Nie ma teraz aktywnego meczu do typowania.")
        previous_prediction = await self.predictions.get(match.id, user_id)
        prediction = await self.predictions.upsert(
            Prediction(match_id=match.id, user_id=user_id, score=score, updated_at=current_time)
        )
        return match, prediction, previous_prediction

    async def get_prediction(
        self,
        guild_id: int,
        user_id: int,
        now: datetime | None = None,
    ) -> tuple[Match | None, Prediction | None]:
        current_time = now or utc_now()
        in_progress = await self.matches.get_in_progress(guild_id, current_time)
        if in_progress is not None:
            return in_progress, await self.predictions.get(in_progress.id, user_id)
        match = await self.matches.get_current(guild_id, current_time)
        if match is not None:
            prediction = await self.predictions.get(match.id, user_id)
            if prediction is not None or await self.predictions.has_any_for_user(guild_id, user_id):
                return match, prediction
            return None, None
        previous = await self.predictions.get_latest_for_user(guild_id, user_id)
        return previous if previous is not None else (None, None)

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
