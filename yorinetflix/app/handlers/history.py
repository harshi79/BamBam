"""
YoriNetflix — History handler.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import ceil

from aiogram import Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery

from app.database.connection import get_pool
from app.database.repositories import history_repo
from app.keyboards.inline import history_nav_kb, back_to_menu_kb
from app.utils.text import sc, sc_html, esc
from app.utils.formatting import build_history_empty, build_history_page


def register(dp: Dispatcher):

    @dp.message(Command("history"))
    async def cmd_history(message: Message):
        if not message.from_user:
            return
        pool = get_pool()
        async with pool.acquire() as conn:
            rows, total = await history_repo.get_user_history(conn, message.from_user.id, 10, 0)
        text, kb = _format_history(rows, total, 1)
        await message.answer(text, reply_markup=kb)

    @dp.callback_query(F.data.startswith("history:"))
    async def cb_history(callback: CallbackQuery):
        page = int(callback.data.split(":", 1)[1])
        offset = (page - 1) * 10
        pool = get_pool()
        async with pool.acquire() as conn:
            rows, total = await history_repo.get_user_history(
                conn, callback.from_user.id, 10, offset
            )
        text, kb = _format_history(rows, total, page)
        try:
            await callback.message.edit_text(
                text, reply_markup=kb, disable_web_page_preview=True
            )
        except Exception:
            pass
        await callback.answer()


def _format_history(rows, total: int, page: int):
    per_page = 10
    if not rows:
        return build_history_empty(), back_to_menu_kb()

    total_pages = max(1, ceil(total / per_page))
    entries = []
    for r in rows:
        when = r["generated_at"].strftime("%Y-%m-%d %H:%M") + " UTC"
        entries.append({"country": r["country"], "when": when})

    text = build_history_page(entries, page, total_pages, total)
    kb = history_nav_kb(page, total_pages)
    return text, kb