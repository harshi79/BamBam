"""
YoriNetflix — Leaderboard handler.
"""

from __future__ import annotations

from aiogram import Dispatcher
from aiogram.types import Message

from app.database.connection import get_pool
from app.database.repositories import user_repo
from app.keyboards.inline import back_to_menu_kb
from app.utils.text import sc, sc_html, esc
from app.utils.formatting import build_leaderboard, build_leaderboard_empty


def register(dp: Dispatcher):

    @dp.message(Command("top"))
    async def cmd_top(message: Message):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await user_repo.get_top_generators(conn, 10)

        if not rows:
            await message.answer(build_leaderboard_empty(), reply_markup=back_to_menu_kb())
            return

        entries = [
            {
                "name": r["full_name"] or r["username"] or "Unknown",
                "total": r["total_generated"],
            }
            for r in rows
        ]
        await message.answer(build_leaderboard(entries), reply_markup=back_to_menu_kb())