"""
YoriNetflix — Profile handler.
"""

from __future__ import annotations

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.config import Settings
from app.database.connection import get_pool
from app.database.repositories import user_repo
from app.services.users import get_profile_data
from app.services.limits import check_daily_limit
from app.keyboards.inline import main_menu_kb
from app.utils.messaging import ack, safe_edit
from app.utils.formatting import build_profile_text


def register(dp: Dispatcher, settings: Settings):

    async def _build_profile(user) -> str:
        pool = get_pool()
        async with pool.acquire() as conn:
            data = await get_profile_data(conn, user.id)
            if not data:
                return "no profile data found. send /start first."
            dl_ok, dl_remaining = await check_daily_limit(
                conn, user.id, settings.DAILY_GENERATION_LIMIT
            )
        return build_profile_text(
            full_name=user.full_name or data["full_name"],
            user_id=user.id,
            joined_at=data["joined_at"],
            total_generated=data["total_generated"],
            unique_countries=data["unique_countries"],
            last_gen_time=data["last_gen_time"],
            cooldown_seconds=settings.COOLDOWN_SECONDS,
            points=data["points"],
            daily_remaining=dl_remaining,
            daily_limit=settings.DAILY_GENERATION_LIMIT,
        )

    @dp.message(Command("profile"))
    async def cmd_profile(message: Message):
        if not message.from_user:
            return
        text = await _build_profile(message.from_user)
        await message.answer(text, reply_markup=main_menu_kb())

    @dp.callback_query(F.data == "profile")
    async def cb_profile(callback: CallbackQuery):
        if not callback.from_user:
            return await ack(callback)

        # Clear the button spinner before the database round-trip.
        await ack(callback)
        text = await _build_profile(callback.from_user)
        await safe_edit(callback, text, main_menu_kb())
