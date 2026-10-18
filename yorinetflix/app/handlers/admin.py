"""
YoriNetflix — Admin command handlers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message

from app.config import Settings
from app.database.connection import get_pool
from app.database.repositories import (
    history_repo,
    inventory_repo,
    user_repo,
)
from app.services.inventory import add_inventory, parse_bulk_cookies
from app.services.points import admin_adjust
from app.utils.formatting import (
    build_add_result,
    build_admin_help,
    build_admin_only,
    build_admin_stats,
    build_broadcast_complete,
    build_broadcast_progress,
    build_givepoints_result,
    build_stock_breakdown,
)
from app.utils.messaging import safe_edit
from app.utils.text import esc, sc_html

log = logging.getLogger("yorinetflix.handlers.admin")


def _is_admin(user_id: int, settings: Settings) -> bool:
    return user_id in settings.admin_id_set


def _notice(title: str, body: str) -> str:
    return f"<b>◇ {sc_html(title)}</b>\n{body}"


def register(dp: Dispatcher, bot: Bot, settings: Settings):

    @dp.message(Command("admin"))
    async def admin_help(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(build_admin_only())
        await message.answer(build_admin_help())

    @dp.message(Command("add"))
    async def admin_add(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(build_admin_only())

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
                return await message.answer(_notice(
                    "Unsupported attachment",
                    "Reply to a text message or a <code>.txt</code> file.",
                ))
        elif message.text and len(message.text.split(maxsplit=1)) > 1:
            text_to_parse = message.text.split(maxsplit=1)[1]
        else:
            return await message.answer(
                _notice(
                    "Usage",
                    "Reply to a <code>.txt</code> file with <code>/add</code>, "
                    "or send <code>/add &lt;text&gt;</code>."
                )
            )

        parsed = parse_bulk_cookies(text_to_parse)
        if not parsed:
            return await message.answer(_notice(
                    "No inventory found",
                    "Add a supported inventory export or a <code>.txt</code> file.",
                ))

        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                added, dupes = await add_inventory(conn, parsed)

        await message.answer(build_add_result(added, dupes))

    @dp.message(Command("stats"))
    async def admin_stats(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(build_admin_only())

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
            return await message.answer(build_admin_only())

        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await inventory_repo.get_stock_breakdown(conn)
            total = await inventory_repo.get_total_stock(conn)

        if not rows:
            return await message.answer(_notice("Inventory empty", "There is currently nothing in stock."))

        await message.answer(build_stock_breakdown(
            [{"country": r["country"], "count": r["cnt"]} for r in rows],
            total,
        ))

    @dp.message(Command("export"))
    async def admin_export(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(build_admin_only())

        parts = (message.text or "").split(maxsplit=1)
        country = parts[1].strip() if len(parts) > 1 else None

        pool = get_pool()
        async with pool.acquire() as conn:
            texts = await inventory_repo.get_raw_texts_by_country(conn, country)

        if not texts:
            return await message.answer(_notice("Nothing to export", "No inventory matches this request."))

        filename = f"export_{country.replace(' ', '_')}.txt" if country else "export_all.txt"
        os.makedirs(settings.BACKUP_DIR, exist_ok=True)
        path = os.path.join(settings.BACKUP_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(texts))

        await message.answer_document(
            FSInputFile(path),
            caption=(
                f"<b>◇ {sc_html('Export ready')}</b>\n"
                f"{sc_html('Accounts')}  <b>{len(texts)}</b>"
            ),
        )

    @dp.message(Command("broadcast"))
    async def admin_broadcast(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(build_admin_only())

        if not message.reply_to_message:
            return await message.answer(_notice(
                "Broadcast needs a message",
                "Reply to a message with <code>/broadcast</code> to send it.",
            ))

        pool = get_pool()
        async with pool.acquire() as conn:
            user_ids = await user_repo.get_all_user_ids(conn)

        status = await message.answer(
            f"<b>◇ {sc_html('Broadcasting')}</b>\n"
            f"{sc_html('Delivering to')}  <b>{len(user_ids)}</b> {sc_html('users')}…"
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
                await safe_edit(status, build_broadcast_progress(sent, failed, blocked))

        # Never let a progress-message edit failure mask a completed broadcast.
        await safe_edit(status, build_broadcast_complete(sent, failed, blocked))

    @dp.message(Command("clear_country"))
    async def admin_clear_country(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(build_admin_only())
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2:
            return await message.answer(_notice(
                "Usage", "Use <code>/clear_country &lt;country&gt;</code>."
            ))
        country = parts[1].strip()
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                deleted = await inventory_repo.delete_by_country(conn, country)
        await message.answer(
            f"<b>◇ {sc_html('Inventory cleared')}</b>\n"
            f"{sc_html('Removed')}  <b>{deleted}</b> {sc_html('items')}  ·  "
            f"{esc(country)}"
        )

    @dp.message(Command("wipe"))
    async def admin_wipe(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(build_admin_only())
        args = (message.text or "").split(maxsplit=1)
        if len(args) < 2 or args[1].strip() != "CONFIRM":
            return await message.answer(
                "<b>◇ ᴄᴏɴꜰɪʀᴍ ɪɴᴠᴇɴᴛᴏʀʏ ʀᴇꜱᴇᴛ</b>\n"
                "This deletes <b>all inventory</b>.\n"
                "Send <code>/wipe CONFIRM</code> to proceed."
            )
        pool = get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                deleted = await inventory_repo.delete_all(conn)
        await message.answer(
            f"<b>◇ {sc_html('Inventory wiped')}</b>\n"
            f"{sc_html('Removed')}  <b>{deleted}</b> {sc_html('items')}"
        )

    @dp.message(Command("givepoints"))
    async def admin_givepoints(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(build_admin_only())
        parts = (message.text or "").split()
        if len(parts) < 3:
            return await message.answer(_notice(
                    "Usage",
                    "Use <code>/givepoints &lt;user_id&gt; &lt;amount&gt;</code>."
                ))
        try:
            target_id = int(parts[1])
            amount = int(parts[2])
        except ValueError:
            return await message.answer(_notice("Invalid values", "The user ID and amount must be integers."))
        if amount == 0:
            return await message.answer(_notice("Invalid amount", "The amount cannot be zero."))

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
            return await message.answer(build_admin_only())
        parts = (message.text or "").split()
        if len(parts) < 2:
            return await message.answer(_notice("Usage", "Use <code>/ban &lt;user_id&gt;</code>."))
        try:
            target_id = int(parts[1])
        except ValueError:
            return await message.answer(_notice("Invalid user ID", "The user ID must be an integer."))
        pool = get_pool()
        async with pool.acquire() as conn:
            await user_repo.ban_user(conn, target_id)
        await message.answer(
            f"<b>◇ {sc_html('User restricted')}</b>\n<code>{target_id}</code>"
        )

    @dp.message(Command("unban"))
    async def admin_unban(message: Message):
        if not message.from_user or not _is_admin(message.from_user.id, settings):
            return await message.answer(build_admin_only())
        parts = (message.text or "").split()
        if len(parts) < 2:
            return await message.answer(_notice("Usage", "Use <code>/unban &lt;user_id&gt;</code>."))
        try:
            target_id = int(parts[1])
        except ValueError:
            return await message.answer(_notice("Invalid user ID", "The user ID must be an integer."))
        pool = get_pool()
        async with pool.acquire() as conn:
            await user_repo.unban_user(conn, target_id)
        await message.answer(
            f"<b>◇ {sc_html('User access restored')}</b>\n<code>{target_id}</code>"
        )
