"""
YoriNetflix — /start, welcome, FSUB, and menu handlers.
"""

from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.config import Settings
from app.database.connection import get_pool
from app.database.repositories import user_repo
from app.services import subscriptions
from app.services.referrals import process_referral
from app.keyboards.inline import main_menu_kb, join_kb
from app.utils.text import sc, sc_html, esc
from app.utils.formatting import build_welcome_text

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
                    sc("🚪 to use this bot, please join our channel first."),
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
        if not settings.FORCE_CHANNEL:
            return await callback.answer()

        is_member, err = await subscriptions.check_membership(
            bot, settings.FORCE_CHANNEL, callback.from_user.id,
            fail_open=settings.FSUB_FAIL_OPEN,
        )
        if not is_member:
            if err in ("channel_not_found", "bot_not_admin"):
                await callback.answer(
                    "⚠️ verification unavailable. try again later.", show_alert=True
                )
            else:
                await callback.answer(sc("❌ you haven't joined yet."), show_alert=True)
            return

        text = build_welcome_text()
        kb = main_menu_kb()
        try:
            await callback.message.edit_text(
                text, reply_markup=kb, disable_web_page_preview=True
            )
        except Exception:
            pass
        await callback.answer(sc("✅ verified!"))

    @dp.callback_query(F.data == "menu")
    async def cb_menu(callback: CallbackQuery):
        text = build_welcome_text()
        kb = main_menu_kb()
        try:
            await callback.message.edit_text(
                text, reply_markup=kb, disable_web_page_preview=True
            )
        except Exception:
            pass
        await callback.answer()

    @dp.callback_query(F.data == "noop")
    async def cb_noop(callback: CallbackQuery):
        await callback.answer()