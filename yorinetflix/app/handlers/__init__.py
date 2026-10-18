"""
YoriNetflix — Handler registration.

Call register_all() during startup to wire all handlers to the dispatcher.
"""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.types import CallbackQuery

from app.config import Settings
from app.handlers import start, generation, profile, history, leaderboard, rewards, admin
from app.utils.messaging import safe_answer

log = logging.getLogger("yorinetflix.handlers")


def register_all(dp: Dispatcher, bot: Bot, settings: Settings) -> None:
    """Register all handler modules with the dispatcher.

    Order matters: the catch-all handlers registered by
    :func:`_register_fallbacks` must come last so every more specific
    handler gets a chance to match first.
    """
    start.register(dp, bot, settings)
    generation.register(dp, settings)
    profile.register(dp, settings)
    history.register(dp)
    leaderboard.register(dp)
    rewards.register(dp, bot, settings)
    admin.register(dp, bot, settings)
    _register_fallbacks(dp)


def _register_fallbacks(dp: Dispatcher) -> None:
    """Register catch-all handlers that guarantee every press is answered.

    Inline keyboards live in the chat forever, so the bot keeps receiving
    callback data it no longer handles (stale menus, keyboards sent by an
    older build).  Telegram never acknowledges an unmatched callback query
    on its own: the button stays in its "loading" state for a full minute,
    which users experience as a broken button.  Answering here makes sure
    every single press gets feedback, and the log line keeps the unknown
    payload visible for debugging.
    """

    @dp.callback_query()
    async def cb_unhandled(callback: CallbackQuery):
        user_id = callback.from_user.id if callback.from_user else None
        log.info("Unhandled callback data %r from user %s", callback.data, user_id)
        await safe_answer(callback, "🔄 menu refreshed — send /start")
