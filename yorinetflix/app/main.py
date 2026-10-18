"""
YoriNetflix — Application entry point.

Loads config, connects to DB, runs migrations, registers handlers,
and starts Telegram polling with graceful shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from app.config import Settings
from app.database.connection import init_pool, close_pool, check_connection, get_pool
from app.database.migrations.runner import run_migrations
from app.handlers import register_all
from app.middleware.throttle import ThrottleMiddleware
from app.health import start_health_server


def setup_logging(level: str, log_dir: str) -> None:
    from logging.handlers import RotatingFileHandler
    import os

    os.makedirs(log_dir, exist_ok=True)
    log_level = getattr(logging, level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    handlers.append(RotatingFileHandler(
        os.path.join(log_dir, "bot.log"),
        maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8",
    ))
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=handlers,
    )


async def startup(settings: Settings) -> None:
    log = logging.getLogger("yorinetflix.startup")
    log.info("Initializing database pool…")
    await init_pool(
        settings.DATABASE_URL,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )
    log.info("Running migrations…")
    pool = get_pool()
    applied = await run_migrations(pool)
    if applied > 0:
        log.info("Applied %d new migration(s).", applied)
    healthy = await check_connection()
    if not healthy:
        log.error("Database health check failed!")
        sys.exit(1)
    log.info("Startup complete.")


async def shutdown(bot: Bot) -> None:
    log = logging.getLogger("yorinetflix.shutdown")
    log.info("Shutting down…")
    await close_pool()
    await bot.session.close()
    log.info("Shutdown complete.")


async def run_bot(settings: Settings) -> None:
    log = logging.getLogger("yorinetflix")

    log.info("YoriNetflix starting…")
    log.info("Admin IDs: %s", settings.admin_id_set)
    log.info("FSUB channel: %s", settings.FORCE_CHANNEL or "(disabled)")

    # Render and similar platforms require every web service to bind the PORT
    # they provide. Keep this lightweight listener alive alongside Telegram polling.
    health_server = await start_health_server()
    bot: Bot | None = None
    try:
        await startup(settings)

        bot = Bot(
            token=settings.BOT_TOKEN,
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        dp = Dispatcher()

        # Register middleware
        dp.message.middleware(ThrottleMiddleware(settings.THROTTLE_RATE))
        dp.callback_query.middleware(ThrottleMiddleware(settings.THROTTLE_RATE))

        # Register all handlers
        register_all(dp, bot, settings)

        # Set bot commands
        from aiogram.types import BotCommand
        await bot.set_my_commands([
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="daily", description="Claim daily reward"),
            BotCommand(command="profile", description="Your profile"),
            BotCommand(command="history", description="Generation history"),
            BotCommand(command="top", description="Top generators"),
            BotCommand(command="referral", description="Your referral link"),
        ])

        await bot.delete_webhook(drop_pending_updates=True)
        # Warms aiogram's cached identity so handlers never pay for a getMe call.
        me = await bot.me()
        log.info("Bot online: @%s (id=%s)", me.username, me.id)
        log.info("Starting polling…")

        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            close_bot_session=False,
        )
    finally:
        try:
            if bot is not None:
                await shutdown(bot)
            else:
                await close_pool()
        finally:
            health_server.close()
            await health_server.wait_closed()


def main() -> None:
    try:
        settings = Settings()
    except Exception as e:
        print(f"Configuration error:\n{e}", file=sys.stderr)
        sys.exit(1)

    setup_logging(settings.LOG_LEVEL, settings.LOG_DIR)
    log = logging.getLogger("yorinetflix")
    log.info("Configuration validated.")

    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        log.info("Interrupted by user.")


if __name__ == "__main__":
    main()