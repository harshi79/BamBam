"""
YoriNetflix — Application entry point.

Responsibilities:
1. Load and validate configuration.
2. Initialize the database connection pool.
3. Run pending migrations.
4. (Future) Start the Telegram bot with registered handlers.
5. Graceful shutdown on SIGINT/SIGTERM.

Usage:
    python -m app.main
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from app.config import Settings
from app.database.connection import get_pool, init_pool, close_pool, check_connection
from app.database.migrations.runner import run_migrations


def setup_logging(level: str, log_dir: str) -> None:
    """Configure application logging with console and file handlers."""
    from logging.handlers import RotatingFileHandler
    import os

    os.makedirs(log_dir, exist_ok=True)

    log_level = getattr(logging, level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    file_handler = RotatingFileHandler(
        os.path.join(log_dir, "bot.log"),
        maxBytes=5 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handlers.append(file_handler)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=handlers,
    )


async def startup(settings: Settings) -> None:
    """Initialize database and run migrations.

    Args:
        settings: Validated application settings.
    """
    log = logging.getLogger("yorinetflix.startup")

    # Initialize connection pool.
    log.info("Initializing database pool…")
    await init_pool(
        settings.DATABASE_URL,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )

    # Run pending migrations.
    log.info("Checking for pending migrations…")
    pool = get_pool()
    applied = await run_migrations(pool)
    if applied > 0:
        log.info("Applied %d new migration(s).", applied)

    # Health check.
    healthy = await check_connection()
    if not healthy:
        log.error("Database health check failed after startup!")
        sys.exit(1)

    log.info("Startup complete.")


async def shutdown() -> None:
    """Clean up resources on exit."""
    log = logging.getLogger("yorinetflix.shutdown")
    log.info("Shutting down…")
    await close_pool()
    log.info("Shutdown complete.")


async def run_bot(settings: Settings) -> None:
    """Run the Telegram bot (placeholder for Phase 4+).

    This function will be expanded in Phase 4 when handlers are implemented.
    For now, it validates the configuration and demonstrates the startup/shutdown
    lifecycle without actually connecting to Telegram.
    """
    log = logging.getLogger("yorinetflix")

    log.info("YoriNetflix starting…")
    log.info("Admin IDs: %s", settings.admin_id_set)
    log.info("FSUB channel: %s", settings.FORCE_CHANNEL or "(disabled)")
    log.info("Cooldown: %ds", settings.COOLDOWN_SECONDS)
    log.info("Daily limit: %d", settings.DAILY_GENERATION_LIMIT)
    log.info("Daily reward: %d pts", settings.DAILY_REWARD_POINTS)
    log.info("Referral reward: %d pts", settings.REFERRAL_REWARD_POINTS)
    log.info("FSUB fail-open: %s", settings.FSUB_FAIL_OPEN)

    await startup(settings)

    # ── Placeholder: Bot polling will go here in Phase 4 ──────
    log.info("Bot infrastructure ready. Handler registration pending (Phase 4).")
    log.info("Database pool is active. Migrations are current.")
    log.info("Press Ctrl+C to stop.")

    # Keep the process alive so the pool stays open (useful for testing).
    # In Phase 4, this will be replaced with dp.start_polling().
    stop_event = asyncio.Event()

    def _signal_handler():
        log.info("Received shutdown signal.")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler.
            pass

    try:
        await stop_event.wait()
    except asyncio.CancelledError:
        pass
    finally:
        await shutdown()


def main() -> None:
    """Load config, set up logging, and run the async bot loop."""
    # Load and validate settings. This will exit with a clear error
    # if required environment variables are missing.
    try:
        settings = Settings()
    except Exception as e:
        print(f"Configuration error:\n{e}", file=sys.stderr)
        sys.exit(1)

    setup_logging(settings.LOG_LEVEL, settings.LOG_DIR)
    log = logging.getLogger("yorinetflix")
    log.info("Configuration validated successfully.")

    try:
        asyncio.run(run_bot(settings))
    except KeyboardInterrupt:
        log.info("Interrupted by user.")


if __name__ == "__main__":
    main()