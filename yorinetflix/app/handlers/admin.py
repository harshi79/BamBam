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
from app.keyboards.inline import back_to_menu_kb

log = logging.getLogger("yorinetflix.handlers.admin")


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_id_set


def register(dp: Dispatcher, bot: Bot, settings: Settings):

    @dp.message(Command("add"))
    async def admin_add(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))

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
                return await message.answer(sc("⚠️ reply to a text message or a .txt file."))
        elif message.text and len(message.text.split(maxsplit=1)) > 1:
            text_to_parse = message.text.split(maxsplit=1)[1]
        else:
            return await message.answer(sc_html(
                "⚠️ usage: reply to a .txt with /add, or send /add &lt;text&gt;"
            ))

        parsed = parse_bulk_cookies(text_to_parse)
        if not parsed:
            return await message.answer(sc("⚠️ nothing to parse."))

        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                added, dupes = await add_inventory(conn, parsed)

        await message.answer(sc_html(
            f"✅ added <b>{added}</b> account(s).\n"
            f"♻️ skipped <b>{dupes}</b> duplicate(s)."
        ))

    @dp.message(Command("stats"))
    async def admin_stats(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))

        pool = get_pool()
        async with pool.acquire() as conn:
            user_stats = await user_repo.get_stats(conn)
            gen_stats = await history_repo.get_global_stats(conn)
            stock = await inventory_repo.get_stock_breakdown(conn)
            total_stock = await inventory_repo.get_total_stock(conn)
            total_countries = len(stock)
            top = stock[:5]

        top_text = "\n".join(
            sc_html(f"  • {esc(r['country'])} — {r['cnt']}") for r in top
        ) or "  —"

        await message.answer(sc_html(
            f"📊 <b>bot statistics</b>\n\n"
            f"🍿 <b>stock</b>\n"
            f"  • accounts: <b>{total_stock}</b>\n"
            f"  • countries: <b>{total_countries}</b>\n\n"
            f"👥 <b>users</b>\n"
            f"  • total: <b>{user_stats['total_users']}</b>\n"
            f"  • active (24h): <b>{user_stats['active_24h']}</b>\n\n"
            f"🎁 <b>generations</b>\n"
            f"  • all time: <b>{gen_stats['total_gens']}</b>\n"
            f"  • last 24h: <b>{gen_stats['gens_24h']}</b>\n"
            f"  • last 7d: <b>{gen_stats['gens_7d']}</b>\n\n"
            f"<b>top stock:</b>\n{top_text}"
        ))

    @dp.message(Command("stock"))
    async def admin_stock(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))

        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await inventory_repo.get_stock_breakdown(conn)
            total = await inventory_repo.get_total_stock(conn)

        if not rows:
            return await message.answer(sc("📦 stock is empty."))

        lines = [sc_html("📦 <b>stock breakdown</b>\n")]
        for r in rows:
            lines.append(sc_html(f"• {esc(r['country'])} — <b>{r['cnt']}</b>"))
        lines.append(sc_html(f"\n<b>total:</b> {total}"))
        await message.answer("\n".join(lines))

    @dp.message(Command("export"))
    async def admin_export(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))

        parts = (message.text or "").split(maxsplit=1)
        country = parts[1].strip() if len(parts) > 1 else None

        pool = get_pool()
        async with pool.acquire() as conn:
            texts = await inventory_repo.get_raw_texts_by_country(conn, country)

        if not texts:
            return await message.answer(sc("⚠️ nothing to export."))

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
            return await message.answer(sc("⛔️ unauthorized."))

        if not message.reply_to_message:
            return await message.answer(sc("⚠️ reply to a message with /broadcast"))

        pool = get_pool()
        async with pool.acquire() as conn:
            user_ids = await user_repo.get_all_user_ids(conn)

        status = await message.answer(sc_html(
            f"📤 broadcasting to <b>{len(user_ids)}</b> user(s)…"
        ))

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
                    await status.edit_text(sc_html(
                        f"📤 broadcasting…\n✅ {sent} · ❌ {failed} · 🚫 {blocked}"
                    ))
                except TelegramBadRequest:
                    pass

        await status.edit_text(sc_html(
            f"✅ <b>broadcast complete</b>\n\n"
            f"📬 sent: <b>{sent}</b>\n"
            f"❌ failed: <b>{failed}</b>\n"
            f"🚫 blocked: <b>{blocked}</b>"
        ))

    @dp.message(Command("clear_country"))
    async def admin_clear_country(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.answer(sc_html("usage: /clear_country &lt;country&gt;"))
        country = parts[1].strip()
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                deleted = await inventory_repo.delete_by_country(conn, country)
        await message.answer(sc_html(
            f"🗑 deleted <b>{deleted}</b> item(s) from <b>{esc(country)}</b>."
        ))

    @dp.message(Command("wipe"))
    async def admin_wipe(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))
        args = (message.text or "").split(maxsplit=1)
        if len(args) < 2 or args[1].strip() != "CONFIRM":
            return await message.answer(sc_html(
                "⚠️ this deletes <b>all inventory</b>. send <code>/wipe CONFIRM</code> to proceed."
            ))
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                deleted = await inventory_repo.delete_all(conn)
        await message.answer(sc_html(f"🗑 wiped <b>{deleted}</b> item(s)."))

    @dp.message(Command("givepoints"))
    async def admin_givepoints(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))
        parts = (message.text or "").split()
        if len(parts) < 3:
            return await message.answer(sc_html(
                "usage: /givepoints &lt;user_id&gt; &lt;amount&gt;"
            ))
        try:
            target_id = int(parts[1])
            amount = int(parts[2])
        except ValueError:
            return await message.answer(sc("⚠️ user_id and amount must be integers."))
        if amount == 0:
            return await message.answer(sc("⚠️ amount cannot be zero."))

        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await user_repo.upsert(conn, target_id, "", "")
                new_balance = await admin_adjust(
                    conn, target_id, amount, message.from_user.id
                )
        await message.answer(sc_html(
            f"✅ adjusted <code>{target_id}</code> by <b>{amount:+d}</b> points.\n"
            f"💰 new balance: <b>{new_balance}</b>"
        ))

    @dp.message(Command("ban"))
    async def admin_ban(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))
        parts = (message.text or "").split()
        if len(parts) < 2:
            return await message.answer(sc_html("usage: /ban &lt;user_id&gt;"))
        try:
            target_id = int(parts[1])
        except ValueError:
            return await message.answer(sc("⚠️ user_id must be an integer."))
        pool = get_pool()
        async with pool.acquire() as conn:
            await user_repo.ban_user(conn, target_id)
        await message.answer(sc_html(f"🚫 user <code>{target_id}</code> banned."))

    @dp.message(Command("unban"))
    async def admin_unban(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))
        parts = (message.text or "").split()
        if len(parts) < 2:
            return await message.answer(sc_html("usage: /unban &lt;user_id&gt;"))
        try:
            target_id = int(parts[1])
        except ValueError:
            return await message.answer(sc("⚠️ user_id must be an integer."))
        pool = get_pool()
        async with pool.acquire() as conn:
            await user_repo.unban_user(conn, target_id)
        await message.answer(sc_html(f"✅ user <code>{target_id}</code> unbanned."))

    @dp.message(Command("admin"))
    async def admin_help(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(sc("⛔️ unauthorized."))
        await message.answer(sc_html(
            "🛠 <b>admin commands</b>\n\n"
            "/add — reply to .txt or text to add inventory\n"
            "/stats — bot statistics\n"
            "/stock — stock breakdown per country\n"
            "/export [country] — export inventory to .txt\n"
            "/broadcast — reply to a message to send to all users\n"
            "/clear_country &lt;name&gt; — wipe inventory for one country\n"
            "/wipe CONFIRM — delete all inventory\n"
            "/givepoints &lt;user_id&gt; &lt;amount&gt; — adjust points\n"
            "/ban &lt;user_id&gt; — ban a user\n"
            "/unban &lt;user_id&gt; — unban a user\n"
            "/admin — this menu"
        ))