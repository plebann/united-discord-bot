from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from zoneinfo import ZoneInfo

import discord
from discord import app_commands
from discord.ext import commands, tasks

from .announcements import AnnouncementService
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


class DiscordAnnouncementPublisher:
    def __init__(self) -> None:
        self.bot: commands.Bot | None = None

    async def publish(self, content: str) -> None:
        configured_channel = os.getenv("CHANNEL_ID", "").strip()
        if not configured_channel.isdigit() or int(configured_channel) <= 0:
            raise RuntimeError("Nie można opublikować ogłoszenia: nieprawidłowy CHANNEL_ID.")
        if self.bot is None:
            raise RuntimeError("Nie można opublikować ogłoszenia przed uruchomieniem bota.")
        channel = self.bot.get_channel(int(configured_channel))
        if channel is None:
            channel = await self.bot.fetch_channel(int(configured_channel))
        if not hasattr(channel, "send"):
            raise RuntimeError("Skonfigurowany kanał nie obsługuje wysyłania wiadomości.")
        await channel.send(content)


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
    def __init__(self, service: TyperService, announcements: AnnouncementService) -> None:
        self.service = service
        self.announcements = announcements

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
            await interaction.response.defer()
            await self.announcements.publish_match_configured(match)
            await _acknowledge_announcement(interaction)
            logger.info(
                "Dodano mecz #%s na guildzie %s: %s - %s",
                match.id,
                match.guild_id,
                match.home_team,
                match.away_team,
            )
        except (DomainError, LookupError, RuntimeError, discord.DiscordException) as exc:
            await _send_command_error(interaction, exc)

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
            previous, match = await self.service.edit_kickoff(
                interaction.guild_id or 0,
                parse_kickoff(kickoff),
            )
            await interaction.response.defer()
            await self.announcements.publish_match_edited(previous, match)
            await _acknowledge_announcement(interaction)
            logger.info("Zmieniono kickoff meczu #%s na guildzie %s", match.id, match.guild_id)
        except (DomainError, LookupError, RuntimeError, discord.DiscordException) as exc:
            await _send_command_error(interaction, exc)

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
            await interaction.response.defer()
            await self.announcements.publish_result(match, predictions)
            await _acknowledge_announcement(interaction)
            logger.info(
                "Zapisano wynik meczu #%s na guildzie %s: %s:%s",
                match.id,
                match.guild_id,
                match.final_score.home,
                match.final_score.away,
            )
        except (DomainError, LookupError, RuntimeError, discord.DiscordException) as exc:
            await _send_command_error(interaction, exc)

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
            if (
                previous_prediction is not None
                and previous_prediction.score == prediction.score
            ):
                await interaction.response.send_message(
                    "Typ nie został zmieniony.",
                    ephemeral=True,
                )
                return
            if previous_prediction is None:
                announcement = (
                    f"<@{interaction.user.id}> wytypował "
                    f"{prediction.score.home}:{prediction.score.away} na mecz "
                    f"{match.home_team} - {match.away_team}"
                )
            else:
                announcement = (
                    f"<@{interaction.user.id}> zmienił typ na mecz "
                    f"{match.home_team} - {match.away_team} na "
                    f"{prediction.score.home}:{prediction.score.away}\n"
                    f"Poprzednio: {previous_prediction.score.home}:"
                    f"{previous_prediction.score.away}"
                )
            await interaction.response.send_message(
                announcement
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


async def create_bot(
    service: TyperService,
    announcements: AnnouncementService,
    publisher: DiscordAnnouncementPublisher,
) -> commands.Bot:
    intents = discord.Intents.none()
    bot = commands.Bot(command_prefix="!", intents=intents)
    await bot.add_cog(TyperCog(service, announcements))
    await bot.add_cog(UserTyperCog(service))

    async def sync_commands() -> None:
        await bot.tree.sync()

    bot.setup_hook = sync_commands

    @tasks.loop(minutes=5)
    async def poll_announcements() -> None:
        try:
            await announcements.poll()
        except (discord.DiscordException, RuntimeError):
            logger.exception("Błąd schedulera ogłoszeń")

    @poll_announcements.before_loop
    async def wait_for_bot() -> None:
        await bot.wait_until_ready()

    @bot.event
    async def on_ready() -> None:
        if bot.user is not None:
            logger.info("Bot zalogowany jako %s (id=%s)", bot.user, bot.user.id)
        if not poll_announcements.is_running():
            poll_announcements.start()

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

    publisher.bot = bot
    return bot


async def _send_command_error(
    interaction: discord.Interaction,
    error: Exception,
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(str(error), ephemeral=True)
    else:
        await interaction.response.send_message(str(error), ephemeral=True)


async def _acknowledge_announcement(interaction: discord.Interaction) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(
            "Ogłoszenie zostało opublikowane.",
            ephemeral=True,
        )
    else:
        await interaction.response.send_message(
            "Ogłoszenie zostało opublikowane.",
            ephemeral=True,
        )


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
