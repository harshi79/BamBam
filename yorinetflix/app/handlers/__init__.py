"""
YoriNetflix — Handler registration.

Call register_all() during startup to wire all handlers to the dispatcher.
"""

from __future__ import annotations

from aiogram import Bot, Dispatcher

from app.config import Settings
from app.handlers import start, generation, profile, history, leaderboard, rewards, admin


def register_all(dp: Dispatcher, bot: Bot, settings: Settings) -> None:
    """Register all handler modules with the dispatcher."""
    start.register(dp, bot, settings)
    generation.register(dp, settings)
    profile.register(dp, settings)
    history.register(dp)
    leaderboard.register(dp)
    rewards.register(dp, bot, settings)
    admin.register(dp, bot, settings)