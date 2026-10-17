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


def register(dp: Dispatcher):

    @dp.message(Command("top"))
    async def cmd_top(message: Message):
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await user_repo.get_top_generators(conn, 10)

        if not rows:
            await message.answer(sc("🏆 no generations yet."), reply_markup=back_to_menu_kb())
            return

        lines = [sc_html("🏆 <b>top generators</b>\n")]
        medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
        for i, r in enumerate(rows):
            name = esc(r["full_name"] or r["username"] or "Unknown")
            lines.append(sc_html(f"{medals[i]} <b>{name}</b> — {r['total_generated']}"))
        await message.answer("\n".join(lines), reply_markup=back_to_menu_kb())