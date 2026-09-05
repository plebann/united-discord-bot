from __future__ import annotations

import asyncio
import os
from pathlib import Path
import logging

from dotenv import load_dotenv

from .application import TyperService
from .db import MatchRepository, PredictionRepository, create_schema, create_session_factory
from .discord_bot import create_bot
from .logging_setup import configure_logging

logger = logging.getLogger(__name__)


async def run() -> None:
    configure_logging()
    load_dotenv()
    token = os.environ["DISCORD_TOKEN"]
    database_url = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/united-bot.db")
    Path("data").mkdir(exist_ok=True)
    logger.info("Uruchamianie bota; baza danych: %s", database_url)
    session_factory = create_session_factory(database_url)
    await create_schema(session_factory)
    service = TyperService(
        MatchRepository(session_factory),
        PredictionRepository(session_factory),
    )
    bot = await create_bot(service)
    await bot.start(token)


if __name__ == "__main__":
    asyncio.run(run())
