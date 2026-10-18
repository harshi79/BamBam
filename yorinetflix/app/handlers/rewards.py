"""
YoriNetflix — Daily reward and referral handlers.
"""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.config import Settings
from app.database.connection import get_pool
from app.database.repositories import user_repo, rewards_repo
from app.services.points import credit
from app.services.referrals import get_referral_link, get_referral_stats
from app.keyboards.inline import back_to_menu_kb
from app.utils.text import sc, sc_html, esc
from app.utils.messaging import ack, respond
from app.utils.formatting import (
    build_daily_reward_text, build_daily_already_claimed, build_referral_text,
)


def register(dp: Dispatcher, bot: Bot, settings: Settings):

    @dp.message(Command("daily"))
    @dp.callback_query(F.data == "daily")
    async def cmd_daily(event: Message | CallbackQuery):
        user = event.from_user
        if not user:
            return await ack(event)

        # Clear the button spinner before the database round-trip.
        await ack(event)

        balance = 0
        pool = get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                await user_repo.upsert(conn, user.id, user.username or "", user.full_name or "")

                claimed = await rewards_repo.try_claim_daily(
                    conn, user.id, settings.DAILY_REWARD_POINTS
                )

                if claimed:
                    if settings.DAILY_REWARD_POINTS > 0:
                        await user_repo.add_points(conn, user.id, settings.DAILY_REWARD_POINTS)
                        await rewards_repo.add_transaction(
                            conn, user.id, settings.DAILY_REWARD_POINTS,
                            "daily_reward", f"daily:{datetime.now(timezone.utc).date()}",
                        )
                    balance = await user_repo.get_points(conn, user.id)

        text = build_daily_reward_text(
            settings.DAILY_REWARD_POINTS, balance, 24
        ) if claimed else build_daily_already_claimed(24)

        await respond(event, text, back_to_menu_kb(), bot=bot)

    @dp.message(Command("referral"))
    @dp.callback_query(F.data == "referral")
    async def cmd_referral(event: Message | CallbackQuery):
        user = event.from_user
        if not user:
            return await ack(event)

        # Clear the button spinner before the database round-trip.
        await ack(event)

        # `bot.me` is aiogram's *cached* getMe; calling `bot.get_me()` here made
        # a live Telegram round-trip on every single button press.
        bot_info = await bot.me()
        # get_referral_link is a coroutine — it must be awaited, otherwise the
        # coroutine repr lands inside <code>…</code> and Telegram rejects the
        # whole message with "can't parse entities: Unsupported start tag".
        link = await get_referral_link(bot_info.username, user.id)

        pool = get_pool()
        async with pool.acquire() as conn:
            stats = await get_referral_stats(conn, user.id)
            balance = await user_repo.get_points(conn, user.id)

        text = build_referral_text(
            link=link,
            referral_count=stats["referral_count"],
            balance=balance,
            reward_points=settings.REFERRAL_REWARD_POINTS,
        )

        await respond(event, text, back_to_menu_kb(), bot=bot)
