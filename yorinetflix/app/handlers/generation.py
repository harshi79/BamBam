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
from app.utils.formatting import (
    build_account_message, build_country_list_text, build_country_empty,
)

log = logging.getLogger("yorinetflix.handlers.gen")


def register(dp: Dispatcher, settings: Settings):

    @dp.callback_query(F.data.startswith("gen:"))
    async def cb_gen(callback: CallbackQuery):
        page = int(callback.data.split(":", 1)[1])
        pool = get_pool()
        async with pool.acquire() as conn:
            countries = await inventory.get_country_stock(conn)

        if not countries:
            try:
                await callback.message.edit_text(
                    build_country_empty(),
                    reply_markup=back_to_menu_kb(),
                    disable_web_page_preview=True,
                )
            except Exception:
                pass
            return await callback.answer()

        total = sum(c["count"] for c in countries)
        kb = country_list_kb(countries, page, settings.PAGE_SIZE)
        text = build_country_list_text(total, len(countries))
        try:
            await callback.message.edit_text(
                text, reply_markup=kb, disable_web_page_preview=True
            )
        except Exception:
            pass
        await callback.answer()

    @dp.callback_query(F.data.startswith("pick:"))
    async def cb_pick_country(callback: CallbackQuery):
        user = callback.from_user
        if not user:
            return await callback.answer()

        country = callback.data.split(":", 1)[1]
        pool = get_pool()

        async with pool.acquire() as conn:
            async with conn.transaction():
                # Upsert user
                await user_repo.upsert(conn, user.id, user.username or "", user.full_name or "")

                # Check ban
                if await user_repo.is_banned(conn, user.id):
                    return await callback.answer("🚫 you are banned.", show_alert=True)

                # Check cooldown
                cd_ok, cd_remaining = await limits.check_cooldown(
                    conn, user.id, settings.COOLDOWN_SECONDS
                )
                if not cd_ok:
                    return await callback.answer(
                        f"⏳ wait {cd_remaining}s before generating again.",
                        show_alert=True,
                    )

                # Check daily limit
                dl_ok, dl_remaining = await limits.check_daily_limit(
                    conn, user.id, settings.DAILY_GENERATION_LIMIT
                )
                if not dl_ok:
                    return await callback.answer(
                        "📊 daily limit reached — try again tomorrow.",
                        show_alert=True,
                    )

                # Pick an account atomically
                cookie = await inventory.pick_account(conn, country)
                if cookie is None:
                    return await callback.answer(
                        "❌ out of stock for this country!", show_alert=True
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

        try:
            await callback.message.answer(
                account_text,
                reply_markup=cookie_action_kb(
                    cookie["pc_url"] or "", cookie["tv_url"] or "", cookie["phone_url"] or ""
                ),
                disable_web_page_preview=True,
            )
        except Exception as e:
            log.exception("Failed to deliver account: %s", e)
            return await callback.answer("⚠️ delivery error — contact admin.", show_alert=True)

        await callback.answer("✅ delivered — check below!")


async def inventory_repo_count(conn, country: str) -> int:
    """Quick count query — avoids importing the full repo here."""
    from app.database.repositories import inventory_repo
    return await inventory_repo.get_country_total(conn, country)