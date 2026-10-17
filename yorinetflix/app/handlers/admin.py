"""
YoriNetflix — Admin command handlers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, FSInputFile
from aiogram.exceptions import TelegramBadRequest, TelegramRetryAfter, TelegramForbiddenError

from app.config import Settings
from app.database.connection import get_pool
from app.database.repositories import (
    user_repo, inventory_repo, history_repo, config_repo,
)
from app.services.inventory import parse_bulk_cookies, add_inventory
from app.services.points import admin_adjust
from app.utils.text import sc, sc_html, esc
from app.utils.formatting import (
    build_admin_help, build_admin_stats, build_stock_breakdown,
    build_add_result, build_givepoints_result,
    build_broadcast_progress, build_broadcast_complete,
)
from app.keyboards.inline import back_to_menu_kb

log = logging.getLogger("yorinetflix.handlers.admin")


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_id_set


def register(dp: Dispatcher, bot: Bot, settings: Settings):

    @dp.message(Command("admin"))
    async def admin_help(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")
        await message.answer(build_admin_help())

    @dp.message(Command("add"))
    async def admin_add(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")

        text_to_parse = ""
        if message.reply_to_message:
            replied = message.reply_to_message
            if replied.document:
                with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, mode="wb") as tmp:
                    await bot.download(replied.document, tmp.name)
                    tmp_path = tmp.name
                try:
                    with open(tmp_path, "r", encoding="utf-8", errors="ignore") as f:
                        text_to_parse = f.read()
                finally:
                    os.unlink(tmp_path)
            elif replied.text:
                text_to_parse = replied.text
            else:
                return await message.answer("⚠️ reply to a text message or a .txt file.")
        elif message.text and len(message.text.split(maxsplit=1)) > 1:
            text_to_parse = message.text.split(maxsplit=1)[1]
        else:
            return await message.answer(
                "⚠️ usage: reply to a .txt with <code>/add</code>, "
                "or send <code>/add &lt;text&gt;</code>"
            )

        parsed = parse_bulk_cookies(text_to_parse)
        if not parsed:
            return await message.answer("⚠️ nothing to parse.")

        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                added, dupes = await add_inventory(conn, parsed)

        await message.answer(build_add_result(added, dupes))

    @dp.message(Command("stats"))
    async def admin_stats(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")

        pool = get_pool()
        async with pool.acquire() as conn:
            user_stats = await user_repo.get_stats(conn)
            gen_stats = await history_repo.get_global_stats(conn)
            stock = await inventory_repo.get_stock_breakdown(conn)
            total_stock = await inventory_repo.get_total_stock(conn)
            total_countries = len(stock)
            top = stock[:5]

        await message.answer(build_admin_stats(
            total_stock=total_stock,
            total_countries=total_countries,
            total_users=user_stats["total_users"],
            active_24h=user_stats["active_24h"],
            total_gens=gen_stats["total_gens"],
            gens_24h=gen_stats["gens_24h"],
            gens_7d=gen_stats["gens_7d"],
            top_stock=[{"country": r["country"], "count": r["cnt"]} for r in top],
        ))

    @dp.message(Command("stock"))
    async def admin_stock(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")

        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await inventory_repo.get_stock_breakdown(conn)
            total = await inventory_repo.get_total_stock(conn)

        if not rows:
            return await message.answer("📦 stock is empty.")

        await message.answer(build_stock_breakdown(
            [{"country": r["country"], "count": r["cnt"]} for r in rows],
            total,
        ))

    @dp.message(Command("export"))
    async def admin_export(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")

        parts = (message.text or "").split(maxsplit=1)
        country = parts[1].strip() if len(parts) > 1 else None

        pool = get_pool()
        async with pool.acquire() as conn:
            texts = await inventory_repo.get_raw_texts_by_country(conn, country)

        if not texts:
            return await message.answer("⚠️ nothing to export.")

        filename = f"export_{country.replace(' ', '_')}.txt" if country else "export_all.txt"
        os.makedirs(settings.BACKUP_DIR, exist_ok=True)
        path = os.path.join(settings.BACKUP_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(texts))

        await message.answer_document(
            FSInputFile(path),
            caption=sc_html(f"📤 exported <b>{len(texts)}</b> account(s)."),
        )

    @dp.message(Command("broadcast"))
    async def admin_broadcast(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")

        if not message.reply_to_message:
            return await message.answer("⚠️ reply to a message with <code>/broadcast</code>")

        pool = get_pool()
        async with pool.acquire() as conn:
            user_ids = await user_repo.get_all_user_ids(conn)

        status = await message.answer(
            f"📤 <b>Broadcasting</b>  to <b>{len(user_ids)}</b> user(s)…"
        )

        sent = failed = blocked = 0
        for uid in user_ids:
            try:
                await message.reply_to_message.copy_to(uid)
                sent += 1
            except TelegramRetryAfter as e:
                await asyncio.sleep(e.retry_after + 1)
                try:
                    await message.reply_to_message.copy_to(uid)
                    sent += 1
                except Exception:
                    failed += 1
            except TelegramForbiddenError:
                blocked += 1
            except Exception:
                failed += 1
            await asyncio.sleep(0.05)

            if (sent + failed + blocked) % 25 == 0:
                try:
                    await status.edit_text(build_broadcast_progress(sent, failed, blocked))
                except TelegramBadRequest:
                    pass

        await status.edit_text(build_broadcast_complete(sent, failed, blocked))

    @dp.message(Command("clear_country"))
    async def admin_clear_country(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.answer("usage: <code>/clear_country &lt;country&gt;</code>")
        country = parts[1].strip()
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                deleted = await inventory_repo.delete_by_country(conn, country)
        await message.answer(
            f"🗑 deleted <b>{deleted}</b> item(s) from <b>{esc(country)}</b>."
        )

    @dp.message(Command("wipe"))
    async def admin_wipe(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")
        args = (message.text or "").split(maxsplit=1)
        if len(args) < 2 or args[1].strip() != "CONFIRM":
            return await message.answer(
                "⚠️ this deletes <b>all inventory</b>.\n"
                "send <code>/wipe CONFIRM</code> to proceed."
            )
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                deleted = await inventory_repo.delete_all(conn)
        await message.answer(f"🗑 wiped <b>{deleted}</b> item(s).")

    @dp.message(Command("givepoints"))
    async def admin_givepoints(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")
        parts = (message.text or "").split()
        if len(parts) < 3:
            return await message.answer(
                "usage: <code>/givepoints &lt;user_id&gt; &lt;amount&gt;</code>"
            )
        try:
            target_id = int(parts[1])
            amount = int(parts[2])
        except ValueError:
            return await message.answer("⚠️ user_id and amount must be integers.")
        if amount == 0:
            return await message.answer("⚠️ amount cannot be zero.")

        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await user_repo.upsert(conn, target_id, "", "")
                new_balance = await admin_adjust(
                    conn, target_id, amount, message.from_user.id
                )
        await message.answer(build_givepoints_result(target_id, amount, new_balance))

    @dp.message(Command("ban"))
    async def admin_ban(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")
        parts = (message.text or "").split()
        if len(parts) < 2:
            return await message.answer("usage: <code>/ban &lt;user_id&gt;</code>")
        try:
            target_id = int(parts[1])
        except ValueError:
            return await message.answer("⚠️ user_id must be an integer.")
        pool = get_pool()
        async with pool.acquire() as conn:
            await user_repo.ban_user(conn, target_id)
        await message.answer(f"🚫 user <code>{target_id}</code> banned.")

    @dp.message(Command("unban"))
    async def admin_unban(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer("⛔️ unauthorized.")
        parts = (message.text or "").split()
        if len(parts) < 2:
            return await message.answer("usage: <code>/unban &lt;user_id&gt;</code>")
        try:
            target_id = int(parts[1])
        except ValueError:
            return await message.answer("⚠️ user_id must be an integer.")
        pool = get_pool()
        async with pool.acquire() as conn:
            await user_repo.unban_user(conn, target_id)
        await message.answer(f"✅ user <code>{target_id}</code> unbanned.")