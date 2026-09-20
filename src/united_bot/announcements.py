from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol

from .db import AnnouncementRepository, MatchRepository, PredictionRepository
from .domain import (
    Match,
    Prediction,
    ResultType,
    result_type,
    sort_predictions_for_listing,
    utc_now,
)

MATCH_CONFIGURED = "MATCH_CONFIGURED"
PREDICTION_OPENED = "PREDICTION_OPENED"
MATCH_STARTED = "MATCH_STARTED"


class AnnouncementPublisher(Protocol):
    async def publish(self, content: str) -> None: ...


class DisplayNameResolver(Protocol):
    async def resolve(self, guild_id: int, user_ids: list[int]) -> dict[int, str]: ...


LISTING_GROUP_HEADINGS = {
    ResultType.HOME_WIN: "\U0001f535 Wygrana gospodarzy",
    ResultType.DRAW: "\u26aa Remis",
    ResultType.AWAY_WIN: "\U0001f534 Wygrana gości",
}


def prediction_listing_text(
    match: Match,
    predictions: list[Prediction],
    display_user: Callable[[int], str],
) -> str:
    if not predictions:
        return f"Nikt jeszcze nie typował na mecz {match.home_team} - {match.away_team}."
    lines = [f"Typy na mecz {match.home_team} - {match.away_team}"]
    groups: dict[ResultType, list[Prediction]] = {
        ResultType.HOME_WIN: [],
        ResultType.DRAW: [],
        ResultType.AWAY_WIN: [],
    }
    for prediction in predictions:
        groups[result_type(prediction.score)].append(prediction)
    for result_type_group in (
        ResultType.HOME_WIN,
        ResultType.DRAW,
        ResultType.AWAY_WIN,
    ):
        group = groups[result_type_group]
        if not group:
            continue
        lines.append("")
        lines.append(LISTING_GROUP_HEADINGS[result_type_group])
        lines.extend(
            f"{index}. {display_user(prediction.user_id)} — "
            f"{prediction.score.home}:{prediction.score.away}"
            for index, prediction in enumerate(group, start=1)
        )
    return "\n".join(lines)


class AnnouncementService:
    def __init__(
        self,
        matches: MatchRepository,
        predictions: PredictionRepository,
        announcements: AnnouncementRepository,
        publisher: AnnouncementPublisher,
        display_names: DisplayNameResolver | None = None,
    ) -> None:
        self.matches = matches
        self.predictions = predictions
        self.announcements = announcements
        self.publisher = publisher
        self.display_names = display_names

    async def publish_match_configured(
        self,
        match: Match,
        now: datetime | None = None,
    ) -> None:
        current_time = now or utc_now()
        opening = match.can_predict(current_time)
        if opening:
            content = (
                f"# ⚽ NADCHODZĄCY MECZ\n"
                f"## {match.home_team} vs {match.away_team}\n\n"
                f"🏆 **Rozgrywki:** {match.competition}\n"
                f"🕐 **Kick-off:** <t:{int(match.kickoff_at.timestamp())}:f>\n"
                f"🟢 **Typowanie aktywne!**\n\n"
                "Wpisz `/typ 3:1`, aby zapisać swój typ.\n"
                "-# Typowanie zamknie się wraz z pierwszym gwizdkiem."
            )
        else:
            content = (
                f"# ⚽ NADCHODZĄCY MECZ\n"
                f"## {match.home_team} vs {match.away_team}\n\n"
                f"🏆 **Rozgrywki:** {match.competition}\n"
                f"🕐 **Kick-off:** <t:{int(match.kickoff_at.timestamp())}:f>\n"
                f"🟢 **Typowanie rozpocznie się 3 dni przed pierwszym gwizdkiem!**\n\n"
                "Wpisz `/typ 3:1`, aby zapisać swój typ.\n"
                "-# Typowanie zamknie się wraz z pierwszym gwizdkiem."
            )
        await self._publish_once(match, MATCH_CONFIGURED, content, current_time)
        if opening:
            await self._mark_once(match, PREDICTION_OPENED, current_time)

    async def publish_prediction_opened(
        self,
        match: Match,
        now: datetime | None = None,
    ) -> None:
        current_time = now or utc_now()
        content = (
            f"Typowanie rozpoczęte: {match.home_team} - {match.away_team}\n"
            f"Kick-off: <t:{int(match.kickoff_at.timestamp())}:f>\n"
            "Typowanie jest aktywne do rozpoczęcia meczu."
        )
        await self._publish_once(match, PREDICTION_OPENED, content, current_time)

    async def poll(self, now: datetime | None = None) -> None:
        current_time = now or utc_now()
        for match in await self.matches.list_started_due(current_time):
            await self.publish_match_started(match, current_time)
        for match in await self.matches.list_prediction_open_due(current_time):
            await self.publish_prediction_opened(match, current_time)

    async def publish_match_started(
        self,
        match: Match,
        now: datetime | None = None,
    ) -> None:
        current_time = now or utc_now()
        if await self.announcements.was_sent(match.id, MATCH_STARTED):
            return
        predictions = sort_predictions_for_listing(await self.predictions.list_for_match(match.id))
        names = await self._resolve_names(
            match.guild_id, [prediction.user_id for prediction in predictions]
        )
        listing = prediction_listing_text(
            match,
            predictions,
            lambda user_id: names.get(user_id) or f"<@{user_id}>",
        )
        content = (
            f"Mecz rozpoczęty: {match.home_team} - {match.away_team}\n"
            f"Rozgrywki: {match.competition}\n"
            f"Kick-off: <t:{int(match.kickoff_at.timestamp())}:f>\n"
            "Typowanie zamknięte.\n\n"
            f"{listing}"
        )
        await self.publisher.publish(content)
        await self.announcements.mark_sent(match.id, MATCH_STARTED, current_time)

    async def _resolve_names(self, guild_id: int, user_ids: list[int]) -> dict[int, str]:
        if self.display_names is None or not user_ids:
            return {}
        return await self.display_names.resolve(guild_id, user_ids)

    async def publish_match_edited(
        self,
        previous: Match,
        updated: Match,
        now: datetime | None = None,
    ) -> None:
        current_time = now or utc_now()
        if updated.can_predict(current_time):
            content = (
                f"Zmieniono termin meczu i rozpoczęto typowanie: "
                f"{updated.home_team} - {updated.away_team}\n"
                f"Rozgrywki: {updated.competition}\n"
                f"Poprzedni kick-off: <t:{int(previous.kickoff_at.timestamp())}:f>\n"
                f"Nowy kick-off: <t:{int(updated.kickoff_at.timestamp())}:f>\n"
                "Typowanie już aktywne!"
            )
        elif updated.kickoff_at <= current_time:
            content = (
                f"Zmieniono termin meczu: {updated.home_team} - {updated.away_team}\n"
                f"Rozgrywki: {updated.competition}\n"
                f"Poprzedni kick-off: <t:{int(previous.kickoff_at.timestamp())}:f>\n"
                f"Nowy kick-off: <t:{int(updated.kickoff_at.timestamp())}:f>\n"
                "Czas typowania minął."
            )
        else:
            content = (
                f"Zmieniono termin meczu: {updated.home_team} - {updated.away_team}\n"
                f"Rozgrywki: {updated.competition}\n"
                f"Poprzedni kick-off: <t:{int(previous.kickoff_at.timestamp())}:f>\n"
                f"Nowy kick-off: <t:{int(updated.kickoff_at.timestamp())}:f>\n"
                f"Typowanie rozpocznie się "
                f"<t:{int(updated.prediction_opens_at.timestamp())}:f>."
            )
        await self.publisher.publish(content)
        if updated.can_predict(current_time):
            await self._mark_once(updated, PREDICTION_OPENED, current_time)

    async def publish_prediction(
        self,
        match: Match,
        user_id: int,
        prediction: Prediction,
        previous_prediction: Prediction | None,
    ) -> None:
        if previous_prediction is None:
            content = (
                f"<@{user_id}> wytypował "
                f"{prediction.score.home}:{prediction.score.away} na mecz "
                f"{match.home_team} - {match.away_team}"
            )
        else:
            content = (
                f"<@{user_id}> zmienił typ na mecz "
                f"{match.home_team} - {match.away_team} na "
                f"{prediction.score.home}:{prediction.score.away}\n"
                f"Poprzednio: {previous_prediction.score.home}:"
                f"{previous_prediction.score.away}"
            )
        await self.publisher.publish(content)

    async def publish_result(
        self,
        match: Match,
        predictions: list[Prediction],
    ) -> None:
        top_predictions = sorted(
            predictions,
            key=lambda prediction: (
                -(prediction.points if prediction.points is not None else 0),
                prediction.submitted_at,
            ),
        )[:10]
        lines = [
            f"Typowanie meczu {match.home_team} - {match.away_team} zostało zakończone.",
            f"Wynik: {match.final_score.home}:{match.final_score.away}",
            f"Pokazano top {len(top_predictions)} z {len(predictions)} typów",
        ]
        lines.extend(
            f"{index}. <@{prediction.user_id}> — "
            f"{prediction.score.home}:{prediction.score.away} — "
            f"{prediction.points} pkt"
            for index, prediction in enumerate(top_predictions, start=1)
        )
        await self.publisher.publish("\n".join(lines))

    async def _publish_once(
        self,
        match: Match,
        announcement_type: str,
        content: str,
        sent_at: datetime,
    ) -> None:
        if await self.announcements.was_sent(match.id, announcement_type):
            return
        await self.publisher.publish(content)
        await self.announcements.mark_sent(match.id, announcement_type, sent_at)

    async def _mark_once(
        self,
        match: Match,
        announcement_type: str,
        sent_at: datetime,
    ) -> None:
        if not await self.announcements.was_sent(match.id, announcement_type):
            await self.announcements.mark_sent(match.id, announcement_type, sent_at)
