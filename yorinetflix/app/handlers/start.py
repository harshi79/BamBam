"""
YoriNetflix — /start, welcome, FSUB, and menu handlers.
"""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from app.config import Settings
from app.database.connection import get_pool
from app.database.repositories import user_repo
from app.keyboards.inline import join_kb, main_menu_kb
from app.services import subscriptions
from app.services.referrals import process_referral
from app.utils.formatting import build_fsub_prompt, build_welcome_text
from app.utils.messaging import safe_answer, safe_edit

log = logging.getLogger("yorinetflix.handlers.start")


def register(dp: Dispatcher, bot: Bot, settings: Settings):
    """Register /start, check_join, and menu handlers."""

    @dp.message(Command("start"))
    async def cmd_start(message: Message):
        if not message.from_user:
            return

        # Parse referral from start parameter
        referrer_id = None
        args = message.text.split(maxsplit=1)
        if len(args) > 1 and args[1].startswith("ref_"):
            try:
                referrer_id = int(args[1][4:])
            except ValueError:
                pass

        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await user_repo.upsert(
                    conn, message.from_user.id,
                    message.from_user.username or "",
                    message.from_user.full_name or "",
                )
                # Process referral if present
                if referrer_id and referrer_id != message.from_user.id:
                    await process_referral(
                        conn, message.from_user.id,
                        referrer_id, settings.REFERRAL_REWARD_POINTS,
                    )

        # FSUB check
        if settings.FORCE_CHANNEL:
            is_member, err = await subscriptions.check_membership(
                bot, settings.FORCE_CHANNEL, message.from_user.id,
                fail_open=settings.FSUB_FAIL_OPEN,
            )
            if not is_member:
                await message.answer(
                    build_fsub_prompt(),
                    reply_markup=join_kb(settings.FORCE_CHANNEL_URL),
                )
                return

        # Send welcome
        text = build_welcome_text()
        kb = main_menu_kb()
        if settings.START_VIDEO_URL:
            try:
                await message.answer_video(
                    video=settings.START_VIDEO_URL,
                    caption=text,
                    reply_markup=kb,
                    supports_streaming=True,
                )
                return
            except Exception as e:
                log.warning("Video send failed (%s) — falling back to text.", e)
        await message.answer(text, reply_markup=kb, disable_web_page_preview=True)

    @dp.callback_query(F.data == "check_join")
    async def cb_check_join(callback: CallbackQuery):
        if not callback.from_user or not settings.FORCE_CHANNEL:
            return await safe_answer(callback)

        is_member, err = await subscriptions.check_membership(
            bot, settings.FORCE_CHANNEL, callback.from_user.id,
            fail_open=settings.FSUB_FAIL_OPEN,
        )
        if not is_member:
            if err in ("channel_not_found", "bot_not_admin"):
                return await safe_answer(
                    callback, "! Verification is unavailable right now. Please try again later.", True
                )
            return await safe_answer(callback, "× You have not joined the channel yet.", True)

        # Feedback first so the button stops spinning, then swap the screen.
        await safe_answer(callback, "✓ Membership verified.")
        await safe_edit(callback, build_welcome_text(), main_menu_kb(), bot=bot)

    @dp.callback_query(F.data == "menu")
    async def cb_menu(callback: CallbackQuery):
        await safe_answer(callback)
        await safe_edit(callback, build_welcome_text(), main_menu_kb(), bot=bot)

    @dp.callback_query(F.data == "noop")
    async def cb_noop(callback: CallbackQuery):
        await safe_answer(callback)
