from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from .bot_handlers import build_router
from .config import Settings
from .db import build_engine, build_sessionmaker, init_db
from .engine import ScanEngine
from .scheduler import BotScheduler
from .sources.base import load_sources


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings.load()
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is empty in .env")

    engine_db = build_engine(settings.database_url)
    await init_db(engine_db)
    sessionmaker = build_sessionmaker(engine_db)

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    sources = load_sources(str(settings.sources_file))
    scan_engine = ScanEngine(
        bot=bot,
        sessionmaker=sessionmaker,
        sources=sources,
        admin_ids=settings.admin_ids,
        enable_playwright=settings.enable_playwright,
        max_alerts=settings.max_deals_per_alert,
    )
    dp.include_router(build_router(settings, sessionmaker, scan_engine))

    scheduler = BotScheduler(settings.check_interval_minutes, scan_engine.run_once)
    scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        scheduler.shutdown()
        await bot.session.close()
        await engine_db.dispose()


if __name__ == "__main__":
    asyncio.run(main())
