from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .db import AnnouncementRepository, MatchRepository
from .domain import Match, Prediction, utc_now


MATCH_CONFIGURED = "MATCH_CONFIGURED"
PREDICTION_OPENED = "PREDICTION_OPENED"
MATCH_STARTED = "MATCH_STARTED"


class AnnouncementPublisher(Protocol):
    async def publish(self, content: str) -> None: ...


class AnnouncementService:
    def __init__(
        self,
        matches: MatchRepository,
        announcements: AnnouncementRepository,
        publisher: AnnouncementPublisher,
    ) -> None:
        self.matches = matches
        self.announcements = announcements
        self.publisher = publisher

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
        content = (
            f"Mecz rozpoczęty: {match.home_team} - {match.away_team}\n"
            f"Rozgrywki: {match.competition}\n"
            f"Kick-off: <t:{int(match.kickoff_at.timestamp())}:f>\n"
            "Typowanie zamknięte."
        )
        await self._publish_once(match, MATCH_STARTED, content, current_time)

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
        await self.publisher.publish(
            content
        )
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
