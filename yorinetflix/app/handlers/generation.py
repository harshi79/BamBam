"""
YoriNetflix — Generation flow handlers.

Country selection, account picking, cooldown, and delivery.
"""

from __future__ import annotations

import logging

from aiogram import Dispatcher, F
from aiogram.types import Message, CallbackQuery

from app.config import Settings
from app.database.connection import get_pool
from app.database.repositories import user_repo, history_repo
from app.services import inventory, limits
from app.keyboards.inline import country_list_kb, cookie_action_kb, back_to_menu_kb
from app.utils.text import sc, sc_html, esc
from app.utils.messaging import ack, parse_page, safe_answer, safe_edit, send_new
from app.utils.formatting import (
    build_account_message, build_country_list_text, build_country_empty,
)

log = logging.getLogger("yorinetflix.handlers.gen")


def register(dp: Dispatcher, settings: Settings):

    @dp.callback_query(F.data.startswith("gen:"))
    async def cb_gen(callback: CallbackQuery):
        # Clear the button spinner before the database round-trip, and tolerate
        # a malformed/stale page number instead of raising ValueError.
        await ack(callback)
        page = parse_page(callback.data)
        pool = get_pool()
        async with pool.acquire() as conn:
            countries = await inventory.get_country_stock(conn)

        if not countries:
            await safe_edit(callback, build_country_empty(), back_to_menu_kb())
            return

        total = sum(c["count"] for c in countries)
        kb = country_list_kb(countries, page, settings.PAGE_SIZE)
        text = build_country_list_text(total, len(countries))
        await safe_edit(callback, text, kb)

    @dp.callback_query(F.data.startswith("pick:"))
    async def cb_pick_country(callback: CallbackQuery):
        user = callback.from_user
        if not user:
            return await safe_answer(callback)

        country = callback.data.split(":", 1)[1].strip()
        if not country:
            return await safe_answer(
                callback, "🔄 this menu is out of date — press Generate again.", True
            )
        pool = get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                # Upsert user
                await user_repo.upsert(conn, user.id, user.username or "", user.full_name or "")

                # Check ban
                if await user_repo.is_banned(conn, user.id):
                    return await safe_answer(callback, "🚫 you are banned.", True)

                # Check cooldown
                cd_ok, cd_remaining = await limits.check_cooldown(
                    conn, user.id, settings.COOLDOWN_SECONDS
                )
                if not cd_ok:
                    return await safe_answer(
                        callback, f"⏳ wait {cd_remaining}s before generating again.", True
                    )

                # Check daily limit
                dl_ok, dl_remaining = await limits.check_daily_limit(
                    conn, user.id, settings.DAILY_GENERATION_LIMIT
                )
                if not dl_ok:
                    return await safe_answer(
                        callback, "📊 daily limit reached — try again tomorrow.", True
                    )

                # Pick an account atomically
                cookie = await inventory.pick_account(conn, country)
                if cookie is None:
                    return await safe_answer(
                        callback, "❌ out of stock for this country!", True
                    )

                # Record history and update user
                await history_repo.add(conn, user.id, country, cookie["id"])
                await user_repo.set_last_gen_time(conn, user.id)
                await user_repo.increment_total_generated(conn, user.id)

                # Award points if configured
                if settings.POINTS_PER_GENERATION > 0:
                    await user_repo.add_points(conn, user.id, settings.POINTS_PER_GENERATION)

                # Get remaining stock
                remaining = await inventory_repo_count(conn, country)

        # Build and send the account message
        account_text = build_account_message(
            country=country,
            raw_text=cookie["raw_text"],
            netflix_id=cookie["netflix_id"] or "",
            secure_id=cookie["secure_netflix_id"] or "",
            remaining=remaining,
        )

        # A delivered account is always a fresh message — never an edit of the
        # country list, and never dependent on that message still existing.
        delivered = await send_new(
            callback,
            account_text,
            reply_markup=cookie_action_kb(
                cookie["pc_url"] or "", cookie["tv_url"] or "", cookie["phone_url"] or ""
            ),
        )
        if not delivered:
            log.error("Failed to deliver account for country %r to user %s", country, user.id)
            return await safe_answer(callback, "⚠️ delivery error — contact admin.", True)

        await safe_answer(callback, "✅ delivered — check below!")


async def inventory_repo_count(conn, country: str) -> int:
    """Quick count query — avoids importing the full repo here."""
    from app.database.repositories import inventory_repo
    return await inventory_repo.get_country_total(conn, country)
