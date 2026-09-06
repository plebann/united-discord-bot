from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands

from .application import TyperService
from .domain import DomainError, Score

logger = logging.getLogger(__name__)
LOCAL_TIMEZONE = ZoneInfo("Europe/Warsaw")
CHANNEL_CONFIGURATION_ERROR = (
    "Bot nie ma skonfigurowanego poprawnego kanału dla komend. "
    "Skontaktuj się z administratorem serwera."
)


class ChannelCheckFailure(app_commands.CheckFailure):
    """Raised when a command is used outside the configured channel."""


def configured_channel_check(interaction: discord.Interaction) -> bool:
    configured_channel = os.getenv("CHANNEL_ID", "").strip()
    if not configured_channel.isdigit() or int(configured_channel) <= 0:
        raise ChannelCheckFailure(CHANNEL_CONFIGURATION_ERROR)
    if interaction.guild is None:
        raise ChannelCheckFailure(
            "Ta komenda działa tylko na skonfigurowanym kanale serwera."
        )
    if interaction.channel_id != int(configured_channel):
        raise ChannelCheckFailure(
            f"Tej komendy można używać tylko na kanale <#{configured_channel}>."
        )
    return True


def parse_kickoff(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise DomainError("Kickoff musi mieć format RRRR-MM-DD GG:MM, np. 2026-09-12 18:30.") from exc
    return parsed.replace(tzinfo=LOCAL_TIMEZONE).astimezone(timezone.utc)


class TyperCog(commands.Cog):
    def __init__(self, service: TyperService) -> None:
        self.service = service

    @app_commands.command(name="admin-mecz-dodaj")
    @app_commands.check(configured_channel_check)
    @app_commands.describe(
        gospodarze="Pełna nazwa gospodarzy",
        goscie="Pełna nazwa gości",
        rozgrywki="Nazwa rozgrywek",
        kickoff="Kickoff w formacie RRRR-MM-DD GG:MM, np. 2026-09-12 18:30",
    )
    async def add_match(
        self,
        interaction: discord.Interaction,
        gospodarze: str,
        goscie: str,
        rozgrywki: str,
        kickoff: str,
    ) -> None:
        if not await self._require_admin(interaction):
            return
        try:
            match = await self.service.add_match(
                interaction.guild_id or 0,
                gospodarze,
                goscie,
                rozgrywki,
                parse_kickoff(kickoff),
            )
            await interaction.response.send_message(
                f"Dodano mecz #{match.id}: {match.home_team} - {match.away_team}. "
                f"Typowanie otworzy się <t:{int(match.prediction_opens_at.timestamp())}:f>."
            )
            logger.info(
                "Dodano mecz #%s na guildzie %s: %s - %s",
                match.id,
                match.guild_id,
                match.home_team,
                match.away_team,
            )
        except (DomainError, LookupError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)

    @app_commands.command(name="admin-mecz-edytuj")
    @app_commands.check(configured_channel_check)
    @app_commands.describe(
        kickoff="Nowy kickoff w formacie RRRR-MM-DD GG:MM",
    )
    async def edit_match(
        self,
        interaction: discord.Interaction,
        kickoff: str,
    ) -> None:
        if not await self._require_admin(interaction):
            return
        try:
            match = await self.service.edit_kickoff(
                interaction.guild_id or 0,
                parse_kickoff(kickoff),
            )
            await interaction.response.send_message(
                f"Zmieniono kickoff meczu #{match.id} na <t:{int(match.kickoff_at.timestamp())}:f>."
            )
            logger.info("Zmieniono kickoff meczu #%s na guildzie %s", match.id, match.guild_id)
        except (DomainError, LookupError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)

    @app_commands.command(name="admin-mecz-wynik")
    @app_commands.check(configured_channel_check)
    @app_commands.describe(wynik="Wynik regulaminowy, np. 3:0")
    async def finish_match(
        self,
        interaction: discord.Interaction,
        wynik: str,
    ) -> None:
        if not await self._require_admin(interaction):
            return
        try:
            match, predictions = await self.service.finish_match(
                interaction.guild_id or 0,
                Score.parse(wynik),
            )
            lines = [
                f"Wynik meczu {match.home_team} - {match.away_team}: "
                f"{match.final_score.home}:{match.final_score.away}",
                f"Rozliczono typów: {len(predictions)}",
            ]
            top_predictions = sorted(
                predictions,
                key=lambda prediction: (
                    -(prediction.points if prediction.points is not None else 0),
                    prediction.submitted_at,
                ),
            )[:10]
            lines[1] = f"Pokazano top {len(top_predictions)} z {len(predictions)} typów"
            lines.extend(
                f"<@{prediction.user_id}>: "
                f"{prediction.score.home}:{prediction.score.away} -> {prediction.points} pkt"
                for prediction in top_predictions
            )
            messages = _split_messages("\n".join(lines))
            await interaction.response.send_message(messages[0])
            for message in messages[1:]:
                await interaction.followup.send(message)
            logger.info(
                "Zapisano wynik meczu #%s na guildzie %s: %s:%s",
                match.id,
                match.guild_id,
                match.final_score.home,
                match.final_score.away,
            )
        except (DomainError, LookupError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)

    async def _require_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None:
            await interaction.response.send_message(
                "Ta komenda działa tylko na serwerze Discord.",
                ephemeral=True,
            )
            return False
        permissions = interaction.permissions
        if not (permissions.manage_guild or permissions.administrator):
            await interaction.response.send_message(
                "Ta komenda wymaga uprawnienia Manage Guild lub Administrator.",
                ephemeral=True,
            )
            return False
        return True


class UserTyperCog(commands.Cog):
    def __init__(self, service: TyperService) -> None:
        self.service = service

    @app_commands.command(name="typ")
    @app_commands.check(configured_channel_check)
    @app_commands.describe(wynik="Wynik bieżącego meczu, np. 3:0")
    async def predict(
        self,
        interaction: discord.Interaction,
        wynik: str,
    ) -> None:
        try:
            match, prediction, previous_prediction = await self.service.save_prediction(
                interaction.guild_id or 0,
                interaction.user.id,
                Score.parse(wynik),
            )
            previous = ""
            if previous_prediction is not None:
                previous = (
                    f" (poprzedni typ {previous_prediction.score.home}:"
                    f"{previous_prediction.score.away})"
                )
            await interaction.response.send_message(
                f"Zapisano typ {match.home_team} - {match.away_team} "
                f"{prediction.score.home}:{prediction.score.away}{previous}"
            )
            logger.info(
                "Zapisano typ użytkownika %s dla meczu #%s na guildzie %s",
                interaction.user.id,
                prediction.match_id,
                interaction.guild_id,
            )
        except (DomainError, LookupError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)

    @app_commands.command(name="moj-typ")
    @app_commands.check(configured_channel_check)
    async def my_prediction(self, interaction: discord.Interaction) -> None:
        try:
            match, prediction = await self.service.get_prediction(
                interaction.guild_id or 0,
                interaction.user.id,
            )
            if match is None:
                message = "Jeszcze nie typowałeś."
            elif prediction is None and match.kickoff_at <= datetime.now(timezone.utc):
                message = (
                    f"Nie masz typu na aktualnie trwający mecz "
                    f"{match.home_team} - {match.away_team}."
                )
            elif prediction is None:
                message = f"Nie masz jeszcze typu dla meczu #{match.id}."
            else:
                points = (
                    f"{prediction.points} pkt"
                    if prediction.points is not None
                    else "nierozliczony"
                )
                if match.final_score is not None:
                    message = (
                        f"{match.home_team} - {match.away_team}: "
                        f"typ {prediction.score.home}:{prediction.score.away}, "
                        f"wynik {match.final_score.home}:{match.final_score.away} "
                        f"({points})."
                    )
                else:
                    message = (
                        f"{match.home_team} - {match.away_team}: "
                        f"{prediction.score.home}:{prediction.score.away} ({points})."
                    )
            await interaction.response.send_message(message, ephemeral=True)
        except (DomainError, LookupError) as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)


async def create_bot(service: TyperService) -> commands.Bot:
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    await bot.add_cog(TyperCog(service))
    await bot.add_cog(UserTyperCog(service))

    async def sync_commands() -> None:
        await bot.tree.sync()

    bot.setup_hook = sync_commands

    @bot.event
    async def on_ready() -> None:
        if bot.user is not None:
            logger.info("Bot zalogowany jako %s (id=%s)", bot.user, bot.user.id)

    @bot.tree.error
    async def on_app_command_error(
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, ChannelCheckFailure):
            if interaction.response.is_done():
                await interaction.followup.send(str(error), ephemeral=True)
            else:
                await interaction.response.send_message(str(error), ephemeral=True)
            return
        logger.error("Błąd komendy aplikacji: %s", error)

    return bot


def _split_messages(content: str, limit: int = 1900) -> list[str]:
    lines = content.splitlines()
    messages: list[str] = []
    current = ""
    for line in lines:
        if current and len(current) + len(line) + 1 > limit:
            messages.append(current)
            current = ""
        current = f"{current}\n{line}".strip()
    if current:
        messages.append(current)
    return messages or [""]
