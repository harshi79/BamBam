"""
Netflix Account Distribution Bot — Full Production Build
Author: @Yorichiiprime
"""

import asyncio
import hashlib
import html
import logging
import os
import re
import time
from datetime import datetime, timezone
from functools import wraps
from logging.handlers import RotatingFileHandler
from math import ceil
from typing import Any, Awaitable, Callable

import aiosqlite
from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import (
    TelegramBadRequest, TelegramRetryAfter, TelegramForbiddenError
)
from aiogram.filters import Command
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton,
    BotCommand, FSInputFile, TelegramObject
)

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "7728424218"))

DB_NAME = os.getenv("DB_NAME", "netflix_bot.db")
BACKUP_DIR = os.getenv("BACKUP_DIR", "backups")
LOG_DIR = os.getenv("LOG_DIR", "logs")

COOLDOWN_SECONDS = int(os.getenv("COOLDOWN_SECONDS", "120"))
PAGE_SIZE = 12
THROTTLE_RATE = 0.5

FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "").strip()
FORCE_CHANNEL_URL = os.getenv(
    "FORCE_CHANNEL_URL",
    "https://t.me/+jijXk3MpjIo1NTFl"
).strip()

START_VIDEO_URL = os.getenv(
    "START_VIDEO_URL",
    "https://imglink.cc/cdn/GMTRCTX88F.mp4"
).strip()

DEFAULT_TV_URL = "https://www.netflix.com/tv2"
DEFAULT_PC_URL = "https://www.netflix.com/account"
DEFAULT_MOBILE_URL = "https://www.netflix.com/login"

# ─────────────────────────────────────────────────────────────
# SMALL CAPS UNICODE TRANSFORMER
# ─────────────────────────────────────────────────────────────
_SMALL_CAPS_MAP = {
    "a": "ᴀ", "b": "ʙ", "c": "ᴄ", "d": "ᴅ", "e": "ᴇ", "f": "ꜰ",
    "g": "ɢ", "h": "ʜ", "i": "ɪ", "j": "ᴊ", "k": "ᴋ", "l": "ʟ",
    "m": "ᴍ", "n": "ɴ", "o": "ᴏ", "p": "ᴘ", "q": "ǫ", "r": "ʀ",
    "s": "ꜱ", "t": "ᴛ", "u": "ᴜ", "v": "ᴠ", "w": "ᴡ", "x": "x",
    "y": "ʏ", "z": "ᴢ",
}

# Protected token patterns — anything matched here is left completely untouched.
# Order matters: more specific patterns first, most generic last.
_PROTECTED_TOKENS = re.compile(
    r"("
    r"https?://\S+"          # full URLs
    r"|t\.me/\S+"            # telegram links
    r"|<[^>]+>"              # HTML tags
    r"|&#\d+;"               # numeric HTML entities
    r"|&[a-zA-Z]+;"          # named HTML entities (&amp; &lt; &gt; etc.)
    r"|NetflixId=\S+"        # Netflix ID key-value
    r"|SecureNetflixId=\S+"  # SecureNetflixId key-value
    r"|cookie_hash=\S+"      # cookie hash key-value
    r"|\d{4,}"               # long numeric runs (IDs, timestamps)
    r")"
)


def sc(text: str) -> str:
    """Convert lowercase letters to Unicode small caps, leaving protected
    tokens (URLs, HTML tags, entities, IDs) untouched."""
    if not text:
        return ""

    parts = []
    last = 0
    for m in _PROTECTED_TOKENS.finditer(text):
        parts.append(text[last:m.start()])   # even index: transformable text
        parts.append(m.group(0))             # odd index: protected token
        last = m.end()
    parts.append(text[last:])                # trailing text

    out = []
    for idx, chunk in enumerate(parts):
        if idx % 2 == 1:
            out.append(chunk)  # protected — leave as-is
        else:
            out.append("".join(_SMALL_CAPS_MAP.get(c, c) for c in chunk))
    return "".join(out)


def sc_html(text: str) -> str:
    """Small-caps transform that skips HTML tags and protected tokens."""
    if not text:
        return ""
    pieces = re.split(r"(<[^>]+>)", text)
    out = []
    for piece in pieces:
        if piece.startswith("<") and piece.endswith(">"):
            out.append(piece)
        else:
            out.append(sc(piece))
    return "".join(out)


# ─────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(
            os.path.join(LOG_DIR, "bot.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)
log = logging.getLogger("netflix-bot")

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()


# ─────────────────────────────────────────────────────────────
# THROTTLE MIDDLEWARE
# ─────────────────────────────────────────────────────────────
class ThrottleMiddleware(BaseMiddleware):
    def __init__(self, rate: float):
        self.rate = rate
        self.last: dict[int, float] = {}

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is None:
            return await handler(event, data)
        now = time.monotonic()
        last = self.last.get(user.id, 0)
        if now - last < self.rate:
            if isinstance(event, Message):
                return None
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer(sc("⏳ slow down."), show_alert=False)
                except TelegramBadRequest:
                    pass
                return None
        self.last[user.id] = now
        return await handler(event, data)


dp.message.middleware(ThrottleMiddleware(THROTTLE_RATE))
dp.callback_query.middleware(ThrottleMiddleware(THROTTLE_RATE))


# ─────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────
def esc(text: str | None) -> str:
    return html.escape(text or "", quote=False)


def admin_only(func):
    @wraps(func)
    async def wrapper(message: Message, *args, **kwargs):
        if message.from_user is None or message.from_user.id != ADMIN_ID:
            return await message.answer(sc("⛔️ unauthorized."))
        return await func(message, *args, **kwargs)
    return wrapper


async def safe_edit(message: Message, text: str, reply_markup=None):
    """Edit a message safely. Falls back to sending a fresh message when the
    target can't be text-edited (media message, deleted, or restricted)."""
    try:
        await message.edit_text(
            text, reply_markup=reply_markup, disable_web_page_preview=True
        )
        return
    except TelegramBadRequest as e:
        err = str(e).lower()

    if "message is not modified" in err:
        return

    if any(kw in err for kw in (
        "no text in the message",
        "there is no text",
        "message to edit not found",
        "message can't be edited",
    )):
        try:
            await message.answer(
                text, reply_markup=reply_markup, disable_web_page_preview=True
            )
        except Exception as inner:
            log.warning("safe_edit fallback failed: %s", inner)
        return

    raise


async def safe_answer(callback: CallbackQuery, text: str = "", alert: bool = False):
    try:
        await callback.answer(text, show_alert=alert)
    except TelegramBadRequest:
        pass


async def upsert_user(user):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            INSERT INTO users (user_id, username, full_name, joined_at)
            VALUES (?, ?, ?, strftime('%s','now'))
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                full_name = excluded.full_name
        """, (user.id, user.username or "", user.full_name or ""))
        await db.commit()


async def is_member(user_id: int) -> bool:
    """Fail-open: if the check errors (bot not admin, network, etc.), let the
    user through so the bot doesn't become unusable."""
    if not FORCE_CHANNEL:
        return True
    try:
        m = await bot.get_chat_member(FORCE_CHANNEL, user_id)
        return m.status not in ("left", "kicked")
    except Exception as e:
        log.debug("Membership check failed for %s: %s", user_id, e)
        return True


# ─────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────
async def _column_exists(db, table: str, column: str) -> bool:
    async with db.execute(f"PRAGMA table_info({table})") as cur:
        rows = await cur.fetchall()
    return any(r[1] == column for r in rows)


async def _table_exists(db, table: str) -> bool:
    async with db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ) as cur:
        return await cur.fetchone() is not None


async def migrate_db(db):
    if await _table_exists(db, "cookies"):
        for col, ddl in (
            ("cookie_hash", "TEXT"),
            ("added_at", "INTEGER"),
            ("tv_url", "TEXT"),
        ):
            if not await _column_exists(db, "cookies", col):
                await db.execute(f"ALTER TABLE cookies ADD COLUMN {col} {ddl}")

        async with db.execute(
            "SELECT id, raw_text FROM cookies WHERE cookie_hash IS NULL OR cookie_hash = ''"
        ) as cur:
            rows = await cur.fetchall()
        for cid, raw in rows:
            h = hashlib.sha256((raw or "").encode("utf-8")).hexdigest()
            await db.execute("UPDATE cookies SET cookie_hash = ? WHERE id = ?", (h, cid))

        await db.execute(
            "UPDATE cookies SET added_at = strftime('%s','now') WHERE added_at IS NULL"
        )

    if await _table_exists(db, "users"):
        for col, ddl in (("username", "TEXT"), ("full_name", "TEXT"), ("joined_at", "INTEGER")):
            if not await _column_exists(db, "users", col):
                await db.execute(f"ALTER TABLE users ADD COLUMN {col} {ddl}")
        await db.execute(
            "UPDATE users SET joined_at = strftime('%s','now') WHERE joined_at IS NULL"
        )

    if not await _table_exists(db, "history"):
        await db.execute("""
            CREATE TABLE history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                country TEXT,
                generated_at INTEGER
            )
        """)

    await db.execute("""
        DELETE FROM cookies
        WHERE id NOT IN (SELECT MIN(id) FROM cookies GROUP BY cookie_hash)
          AND cookie_hash IS NOT NULL
          AND cookie_hash != ''
    """)

    await db.commit()


async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cookies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                country TEXT NOT NULL,
                raw_text TEXT NOT NULL,
                pc_url TEXT,
                phone_url TEXT,
                tv_url TEXT,
                netflix_id TEXT,
                secure_netflix_id TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                last_gen_time INTEGER DEFAULT 0,
                total_generated INTEGER DEFAULT 0
            )
        """)
        await db.commit()

        await migrate_db(db)

        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_cookies_hash_unique ON cookies(cookie_hash)"
        )
        await db.execute("CREATE INDEX IF NOT EXISTS idx_cookies_country ON cookies(country)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_user ON history(user_id)")
        await db.execute("CREATE INDEX IF NOT EXISTS idx_history_time ON history(generated_at)")
        await db.commit()

    log.info("Database ready: %s", DB_NAME)


# ─────────────────────────────────────────────────────────────
# COOKIE PARSER
# ─────────────────────────────────────────────────────────────
URL_LINE_RE = re.compile(r"^\s*[•\-]?\s*(PC|Phone|TV)\s*Login URL\s*:", re.IGNORECASE)
COOKIE_LINE_RE = re.compile(r"^\s*🍪\s*Cookie\s*:", re.IGNORECASE)
SECURE_LINE_RE = re.compile(r"^\s*🔐\s*SecureNetflixId\s*:", re.IGNORECASE)
SEP_LINE_RE = re.compile(r"^\s*[─━\-=]{3,}\s*$")


def parse_cookie_text(text: str) -> dict:
    data = {"raw_text": text.strip()}

    m = re.search(r"🌍 Country:\s*(.+)", text)
    if m:
        raw = m.group(1).strip()
        clean = re.sub(r"\s*\([A-Z]{2}\)\s*$", "", raw).strip()
        data["country"] = clean or "Unknown"
    else:
        data["country"] = "Unknown"

    m = re.search(r"•\s*PC Login URL:\s*(\S+)", text)
    data["pc_url"] = m.group(1) if m else ""

    m = re.search(r"•\s*Phone Login URL:\s*(\S+)", text)
    data["phone_url"] = m.group(1) if m else ""

    m = re.search(r"•\s*TV Login URL:\s*(\S+)", text)
    data["tv_url"] = m.group(1) if m else ""

    m = re.search(r"🍪\s*Cookie:\s*NetflixId=(\S+)", text)
    data["netflix_id"] = m.group(1) if m else ""

    m = re.search(r"🔐\s*SecureNetflixId:\s*(\S+)", text)
    data["secure_netflix_id"] = m.group(1) if m else ""

    data["cookie_hash"] = hashlib.sha256(data["raw_text"].encode("utf-8")).hexdigest()
    return data


def parse_bulk_cookies(text: str) -> list[dict]:
    chunks = re.split(r"(?=📁 Source:)", text)
    parsed = [parse_cookie_text(c) for c in chunks if "🌍 Country:" in c]
    if parsed:
        return parsed
    return [parse_cookie_text(text)] if text.strip() else []


# ─────────────────────────────────────────────────────────────
# DISPLAY BUILDERS
# ─────────────────────────────────────────────────────────────
def clean_info_block(raw_text: str) -> str:
    kept = []
    for line in raw_text.split("\n"):
        s = line.strip()
        if URL_LINE_RE.match(s):
            continue
        if COOKIE_LINE_RE.match(s):
            continue
        if SECURE_LINE_RE.match(s):
            continue
        if SEP_LINE_RE.match(s):
            continue
        kept.append(line)

    out = "\n".join(kept).strip()
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out


def build_cookie_string(netflix_id: str, secure_id: str) -> str:
    parts = []
    if netflix_id and netflix_id.upper() != "N/A":
        parts.append(f"NetflixId={netflix_id}")
    if secure_id and secure_id.upper() != "N/A":
        parts.append(f"SecureNetflixId={secure_id}")
    return "\n".join(parts)


def normalize_url(url: str, fallback: str) -> str:
    url = (url or "").strip()
    if not url or url.upper() == "N/A":
        return fallback
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def cookie_action_kb(pc_url: str, tv_url: str, mobile_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💻 PC", url=normalize_url(pc_url, DEFAULT_PC_URL)),
            InlineKeyboardButton(text="📺 TV", url=normalize_url(tv_url, DEFAULT_TV_URL)),
            InlineKeyboardButton(text="📱 Mobile", url=normalize_url(mobile_url, DEFAULT_MOBILE_URL)),
        ],
    ])


def build_account_message(
    country: str,
    raw_text: str,
    netflix_id: str,
    secure_id: str,
    remaining: int,
) -> str:
    info = clean_info_block(raw_text)
    cookie_str = build_cookie_string(netflix_id, secure_id)

    parts = [
        sc_html(f"🎬 <b>{esc(country)} — Netflix Account</b>"),
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
    ]
    if info:
        parts.append(f"<blockquote>{esc(info)}</blockquote>")
        parts.append("")

    if cookie_str:
        parts.append(sc_html("🍪 <b>Cookie</b> <i>(tap below to copy)</i>"))
        parts.append(f"<blockquote><code>{esc(cookie_str)}</code></blockquote>")
        parts.append("")

    parts.extend([
        "━━━━━━━━━━━━━━━━━━━━━━",
        sc_html(f"📦 remaining for {esc(country)}: <b>{remaining}</b>"),
        sc_html("💡 tap a button below to open the login page."),
        sc_html("📌 <i>save this message — you can reuse it anytime.</i>"),
    ])
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────
# KEYBOARDS
# ─────────────────────────────────────────────────────────────
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sc("Generate 🍿"), callback_data="gen:0")],
        [
            InlineKeyboardButton(text=sc("Profile 📊"), callback_data="profile"),
            InlineKeyboardButton(text=sc("History 🕘"), callback_data="history:1"),
        ],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sc("⬅️ Menu"), callback_data="menu")]
    ])


def join_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=sc("📢 Join Channel"),
                              url=FORCE_CHANNEL_URL or "https://t.me/")],
        [InlineKeyboardButton(text=sc("✅ I Joined"), callback_data="check_join")],
    ])


# ─────────────────────────────────────────────────────────────
# /start — ONE message: video + caption + buttons
# ─────────────────────────────────────────────────────────────
def build_welcome_text() -> str:
    return sc_html(
        "🎬 <b>Netflix Account Distributor</b>\n\n"
        "Get premium accounts — free, instant, no strings.\n"
        "Made by <a href=\"https://t.me/Yorichiiprime\">@Yorichiiprime</a>\n\n"
        "<i>Tap a button below to begin.</i>"
    )


async def send_welcome(target: Message | CallbackQuery):
    """Send the video with caption + buttons as a single message.
    This is the ONLY place the video appears."""
    text = build_welcome_text()
    kb = main_menu_kb()

    try:
        await target.answer_video(
            video=START_VIDEO_URL,
            caption=text,
            reply_markup=kb,
            supports_streaming=True,
        )
        return
    except Exception as e:
        log.warning("Video send failed (%s) — falling back to text.", e)

    await target.answer(text, reply_markup=kb, disable_web_page_preview=True)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await upsert_user(message.from_user)
    if not await is_member(message.from_user.id):
        return await message.answer(
            sc("🚪 to use this bot, please join our channel first."),
            reply_markup=join_kb()
        )
    await send_welcome(message)


@dp.callback_query(F.data == "check_join")
async def cb_check_join(callback: CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await safe_answer(callback, sc("❌ you haven't joined yet."), alert=True)
    await safe_edit(callback.message, build_welcome_text(), reply_markup=main_menu_kb())
    await safe_answer(callback, sc("✅ verified!"))


@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery):
    await safe_edit(callback.message, build_welcome_text(), reply_markup=main_menu_kb())
    await safe_answer(callback)


# ─────────────────────────────────────────────────────────────
# GENERATE FLOW
# ─────────────────────────────────────────────────────────────
async def render_countries(page: int) -> tuple[str, InlineKeyboardMarkup]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT country, COUNT(id) FROM cookies "
            "WHERE country IS NOT NULL AND country != 'Unknown' "
            "GROUP BY country ORDER BY LOWER(country)"
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        return (sc("❌ no cookies in stock right now. check back later!"),
                back_to_menu_kb())

    total_available = sum(c for _, c in rows)
    total_pages = max(1, ceil(len(rows) / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * PAGE_SIZE
    page_rows = rows[start:start + PAGE_SIZE]

    buttons = [[InlineKeyboardButton(
        text=f"🌍 {c} · {n}",
        callback_data=f"pick:{c}"
    )] for c, n in page_rows]

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"gen:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"{page}/{total_pages}", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"gen:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text=sc("⬅️ Menu"), callback_data="menu")])

    text = sc_html(
        f"🌍 <b>select a country</b>\n\n"
        f"📦 total in stock: <b>{total_available}</b>\n"
        f"🗂 countries: <b>{len(rows)}</b>"
    )
    return text, InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.callback_query(F.data.startswith("gen:"))
async def cb_gen(callback: CallbackQuery):
    page = int(callback.data.split(":", 1)[1])
    text, kb = await render_countries(page)
    await safe_edit(callback.message, text, reply_markup=kb)
    await safe_answer(callback)


@dp.callback_query(F.data == "noop")
async def cb_noop(callback: CallbackQuery):
    await safe_answer(callback)


# ─────────────────────────────────────────────────────────────
# GENERATE — pick a country (persistent delivery)
# ─────────────────────────────────────────────────────────────
@dp.callback_query(F.data.startswith("pick:"))
async def cb_pick_country(callback: CallbackQuery):
    user = callback.from_user
    await upsert_user(user)
    uid = user.id
    country = callback.data.split(":", 1)[1]
    now = int(time.time())

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT last_gen_time FROM users WHERE user_id = ?", (uid,)
        ) as cur:
            row = await cur.fetchone()
        last_gen = row[0] if row else 0

        if now - last_gen < COOLDOWN_SECONDS:
            wait = COOLDOWN_SECONDS - (now - last_gen)
            return await safe_answer(
                callback,
                sc(f"⏳ wait {wait}s before generating again."),
                alert=True
            )

        await db.execute("BEGIN IMMEDIATE")
        async with db.execute(
            "SELECT id, raw_text, pc_url, phone_url, tv_url, "
            "       netflix_id, secure_netflix_id "
            "FROM cookies WHERE country = ? ORDER BY RANDOM() LIMIT 1",
            (country,)
        ) as cur:
            cookie = await cur.fetchone()

        if not cookie:
            await db.execute("ROLLBACK")
            return await safe_answer(callback, sc("❌ out of stock for this country!"), alert=True)

        (cookie_id, raw_text, pc_url, phone_url, tv_url,
         netflix_id, secure_netflix_id) = cookie

        await db.execute("DELETE FROM cookies WHERE id = ?", (cookie_id,))
        await db.execute(
            "UPDATE users SET last_gen_time = ?, total_generated = total_generated + 1 "
            "WHERE user_id = ?", (now, uid)
        )
        await db.execute(
            "INSERT INTO history (user_id, country, generated_at) VALUES (?, ?, ?)",
            (uid, country, now)
        )
        await db.commit()

        async with db.execute(
            "SELECT COUNT(id) FROM cookies WHERE country = ?", (country,)
        ) as cur:
            left = (await cur.fetchone())[0]

    account_text = build_account_message(
        country=country,
        raw_text=raw_text,
        netflix_id=netflix_id or "",
        secure_id=secure_netflix_id or "",
        remaining=left,
    )

    try:
        await callback.message.answer(
            account_text,
            reply_markup=cookie_action_kb(pc_url or "", tv_url or "", phone_url or ""),
            disable_web_page_preview=True,
        )
    except Exception as e:
        log.exception("Failed to deliver cookie: %s", e)
        return await safe_answer(callback, sc("⚠️ delivery error. contact admin."), alert=True)

    await safe_answer(callback, sc("✅ account delivered — check below!"))


# ─────────────────────────────────────────────────────────────
# PROFILE
# ─────────────────────────────────────────────────────────────
async def build_profile(user) -> str:
    uid = user.id
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT total_generated, last_gen_time, joined_at FROM users WHERE user_id = ?",
            (uid,)
        ) as cur:
            row = await cur.fetchone()
        async with db.execute(
            "SELECT COUNT(DISTINCT country) FROM history WHERE user_id = ?", (uid,)
        ) as cur:
            countries = (await cur.fetchone())[0]

    total = row[0] if row else 0
    last_gen = row[1] if row else 0
    joined = row[2] if row else int(time.time())

    remaining = max(0, COOLDOWN_SECONDS - (int(time.time()) - last_gen))
    cd_text = sc(f"{remaining}s") if remaining else sc("ready ✅")
    joined_str = datetime.fromtimestamp(joined, tz=timezone.utc).strftime("%Y-%m-%d")

    return sc_html(
        f"📊 <b>your profile</b>\n\n"
        f"👤 <b>name:</b> {esc(user.full_name)}\n"
        f"🆔 <b>id:</b> <code>{uid}</code>\n"
        f"📅 <b>joined:</b> {joined_str}\n\n"
        f"🍿 <b>total generated:</b> {total}\n"
        f"🌍 <b>unique countries:</b> {countries}\n"
        f"⏳ <b>cooldown:</b> {cd_text}"
    )


@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    await upsert_user(message.from_user)
    await message.answer(await build_profile(message.from_user), reply_markup=main_menu_kb())


@dp.callback_query(F.data == "profile")
async def cb_profile(callback: CallbackQuery):
    await upsert_user(callback.from_user)
    await safe_edit(callback.message, await build_profile(callback.from_user),
                    reply_markup=main_menu_kb())
    await safe_answer(callback)


# ─────────────────────────────────────────────────────────────
# HISTORY
# ─────────────────────────────────────────────────────────────
@dp.message(Command("history"))
async def cmd_history(message: Message):
    await show_history(send=message.answer, user_id=message.from_user.id, page=1)


@dp.callback_query(F.data.startswith("history:"))
async def cb_history(callback: CallbackQuery):
    page = int(callback.data.split(":", 1)[1])
    await show_history(
        send=None,
        user_id=callback.from_user.id,
        page=page,
        edit=True,
        message=callback.message,
    )
    await safe_answer(callback)


async def show_history(send, user_id: int, page: int, edit: bool = False, message=None):
    if edit and message is None:
        raise ValueError("show_history: edit=True requires a message argument")
    if not edit and send is None:
        raise ValueError("show_history: edit=False requires a send callable")

    per_page = 10
    offset = (page - 1) * per_page

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM history WHERE user_id = ?", (user_id,)) as cur:
            total = (await cur.fetchone())[0]
        async with db.execute(
            "SELECT country, generated_at FROM history WHERE user_id = ? "
            "ORDER BY id DESC LIMIT ? OFFSET ?", (user_id, per_page, offset)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        text = sc_html("🕘 <b>your history is empty.</b>\n\ngenerate an account to see it here.")
        kb = back_to_menu_kb()
    else:
        total_pages = max(1, ceil(total / per_page))
        lines = [sc_html("🕘 <b>your recent generations</b>\n")]
        for c, ts in rows:
            when = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            lines.append(sc_html(f"• <b>{esc(c)}</b> — <i>{when} UTC</i>"))
        lines.append(sc_html(
            f"\n📄 page <b>{page}</b>/<b>{total_pages}</b> · total: <b>{total}</b>"
        ))
        text = "\n".join(lines)

        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"history:{page-1}"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="➡️", callback_data=f"history:{page+1}"))
        buttons = [nav] if nav else []
        buttons.append([InlineKeyboardButton(text=sc("⬅️ Menu"), callback_data="menu")])
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    if edit:
        await safe_edit(message, text, reply_markup=kb)
    else:
        await send(text, reply_markup=kb)


# ─────────────────────────────────────────────────────────────
# LEADERBOARD
# ─────────────────────────────────────────────────────────────
@dp.message(Command("top"))
async def cmd_top(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("""
            SELECT u.user_id, u.full_name, u.username, u.total_generated
            FROM users u
            WHERE u.total_generated > 0
            ORDER BY u.total_generated DESC
            LIMIT 10
        """) as cur:
            rows = await cur.fetchall()

    if not rows:
        return await message.answer(
            sc("🏆 no generations yet."),
            reply_markup=back_to_menu_kb()
        )

    lines = [sc_html("🏆 <b>top generators</b>\n")]
    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    for i, (_uid, full_name, username, total) in enumerate(rows):
        name = esc(full_name or username or "Unknown")
        lines.append(sc_html(f"{medals[i]} <b>{name}</b> — {total}"))
    await message.answer("\n".join(lines), reply_markup=back_to_menu_kb())


# ─────────────────────────────────────────────────────────────
# ADMIN — /add
# ─────────────────────────────────────────────────────────────
@dp.message(Command("add"))
@admin_only
async def admin_add(message: Message):
    text_to_parse = ""

    if message.reply_to_message:
        replied = message.reply_to_message
        if replied.document:
            file = await bot.get_file(replied.document.file_id)
            tmp = f"temp_{file.file_id}.txt"
            await bot.download_file(file.file_path, tmp)
            try:
                with open(tmp, "r", encoding="utf-8", errors="ignore") as f:
                    text_to_parse = f.read()
            finally:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        elif replied.text:
            text_to_parse = replied.text
        else:
            return await message.answer(sc("⚠️ reply to a text message or a .txt file."))
    elif message.text and len(message.text.split(maxsplit=1)) > 1:
        text_to_parse = message.text.split(maxsplit=1)[1]
    else:
        return await message.answer(
            sc_html("⚠️ usage: reply to a .txt with /add, or send /add &lt;cookie text&gt;")
        )

    parsed = parse_bulk_cookies(text_to_parse)
    if not parsed:
        return await message.answer(sc("⚠️ nothing to parse."))

    added = 0
    dupes = 0
    async with aiosqlite.connect(DB_NAME) as db:
        for p in parsed:
            try:
                await db.execute("""
                    INSERT INTO cookies
                    (country, raw_text, pc_url, phone_url, tv_url, netflix_id,
                     secure_netflix_id, cookie_hash, added_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                """, (
                    p["country"], p["raw_text"], p["pc_url"], p["phone_url"],
                    p["tv_url"], p["netflix_id"], p["secure_netflix_id"],
                    p["cookie_hash"]
                ))
                added += 1
            except aiosqlite.IntegrityError:
                dupes += 1
        await db.commit()

    await message.answer(sc_html(
        f"✅ added <b>{added}</b> account(s).\n"
        f"♻️ skipped <b>{dupes}</b> duplicate(s)."
    ))


# ─────────────────────────────────────────────────────────────
# ADMIN — /stats
# ─────────────────────────────────────────────────────────────
@dp.message(Command("stats"))
@admin_only
async def admin_stats(message: Message):
    cutoff_24h = int(time.time()) - 86400
    cutoff_7d = int(time.time()) - 7 * 86400

    async with aiosqlite.connect(DB_NAME) as db:
        async def scalar(sql, params=()):
            async with db.execute(sql, params) as cur:
                return (await cur.fetchone())[0]

        total_cookies = await scalar("SELECT COUNT(id) FROM cookies")
        total_countries = await scalar("SELECT COUNT(DISTINCT country) FROM cookies")
        total_users = await scalar("SELECT COUNT(*) FROM users")
        total_gens = await scalar("SELECT COUNT(*) FROM history")
        gens_24h = await scalar("SELECT COUNT(*) FROM history WHERE generated_at > ?", (cutoff_24h,))
        gens_7d = await scalar("SELECT COUNT(*) FROM history WHERE generated_at > ?", (cutoff_7d,))
        active_24h = await scalar("SELECT COUNT(*) FROM users WHERE last_gen_time > ?", (cutoff_24h,))

        async with db.execute(
            "SELECT country, COUNT(id) FROM cookies GROUP BY country "
            "ORDER BY COUNT(id) DESC LIMIT 5"
        ) as cur:
            top = await cur.fetchall()

    top_text = "\n".join(sc_html(f"  • {esc(c)} — {n}") for c, n in top) or "  —"

    await message.answer(sc_html(
        f"📊 <b>bot statistics</b>\n\n"
        f"🍿 <b>stock</b>\n"
        f"  • accounts: <b>{total_cookies}</b>\n"
        f"  • countries: <b>{total_countries}</b>\n\n"
        f"👥 <b>users</b>\n"
        f"  • total: <b>{total_users}</b>\n"
        f"  • active (24h): <b>{active_24h}</b>\n\n"
        f"🎁 <b>generations</b>\n"
        f"  • all time: <b>{total_gens}</b>\n"
        f"  • last 24h: <b>{gens_24h}</b>\n"
        f"  • last 7d: <b>{gens_7d}</b>\n\n"
        f"<b>top stock:</b>\n{top_text}"
    ))


# ─────────────────────────────────────────────────────────────
# ADMIN — misc
# ─────────────────────────────────────────────────────────────
@dp.message(Command("stock"))
@admin_only
async def admin_stock(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT country, COUNT(id) FROM cookies GROUP BY country ORDER BY COUNT(id) DESC"
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        return await message.answer(sc("📦 stock is empty."))
    lines = [sc_html("📦 <b>stock breakdown</b>\n")]
    for c, n in rows:
        lines.append(sc_html(f"• {esc(c)} — <b>{n}</b>"))
    lines.append(sc_html(f"\n<b>total:</b> {sum(n for _, n in rows)}"))
    await message.answer("\n".join(lines))


@dp.message(Command("export"))
@admin_only
async def admin_export(message: Message):
    parts = message.text.split(maxsplit=1)
    async with aiosqlite.connect(DB_NAME) as db:
        if len(parts) > 1:
            country = parts[1].strip()
            async with db.execute(
                "SELECT raw_text FROM cookies WHERE country = ?", (country,)
            ) as cur:
                rows = await cur.fetchall()
            filename = f"export_{country.replace(' ', '_')}.txt"
        else:
            async with db.execute("SELECT raw_text FROM cookies") as cur:
                rows = await cur.fetchall()
            filename = "export_all.txt"

    if not rows:
        return await message.answer(sc("⚠️ nothing to export."))

    path = os.path.join(BACKUP_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(r[0] for r in rows))

    await message.answer_document(
        FSInputFile(path),
        caption=sc_html(f"📤 exported <b>{len(rows)}</b> account(s).")
    )


@dp.message(Command("backup"))
@admin_only
async def admin_backup(message: Message):
    if not os.path.exists(DB_NAME):
        return await message.answer(sc("⚠️ no db file yet."))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = os.path.join(BACKUP_DIR, f"backup_{stamp}.db")

    src = await aiosqlite.connect(DB_NAME)
    dst = await aiosqlite.connect(path)
    try:
        await src.backup(dst)
    finally:
        await dst.close()
        await src.close()

    await message.answer_document(
        FSInputFile(path),
        caption=sc_html(f"💾 backup <b>{stamp}</b>")
    )


@dp.message(Command("broadcast"))
@admin_only
async def admin_broadcast(message: Message):
    if not message.reply_to_message:
        return await message.answer(sc("⚠️ reply to a message with /broadcast"))

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            users = [r[0] for r in await cur.fetchall()]

    status = await message.answer(sc_html(
        f"📤 broadcasting to <b>{len(users)}</b> user(s)…"
    ))

    sent = failed = blocked = 0
    for uid in users:
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
@admin_only
async def admin_clear_country(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer(sc_html("usage: /clear_country &lt;country&gt;"))
    country = parts[1].strip()
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("DELETE FROM cookies WHERE country = ?", (country,))
        await db.commit()
        deleted = cur.rowcount
    await message.answer(sc_html(
        f"🗑 deleted <b>{deleted}</b> cookie(s) from <b>{esc(country)}</b>."
    ))


@dp.message(Command("wipe"))
@admin_only
async def admin_wipe(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or args[1].strip() != "CONFIRM":
        return await message.answer(sc_html(
            "⚠️ this deletes <b>all cookies</b>. send <code>/wipe CONFIRM</code> to proceed."
        ))
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("DELETE FROM cookies")
        await db.commit()
        deleted = cur.rowcount
    await message.answer(sc_html(f"🗑 wiped <b>{deleted}</b> account(s)."))


@dp.message(Command("admin"))
@admin_only
async def admin_help(message: Message):
    await message.answer(sc_html(
        "🛠 <b>admin commands</b>\n\n"
        "/add — reply to .txt or text to add cookies\n"
        "/stats — bot statistics\n"
        "/stock — stock breakdown per country\n"
        "/export [country] — export cookies to .txt\n"
        "/backup — download db snapshot\n"
        "/broadcast — reply to a message to send to all users\n"
        "/clear_country &lt;name&gt; — wipe cookies for one country\n"
        "/wipe CONFIRM — delete all cookies\n"
        "/admin — this menu"
    ))


# ─────────────────────────────────────────────────────────────
# FALLBACK
# ─────────────────────────────────────────────────────────────
@dp.message(F.text & ~F.text.startswith("/"))
async def fallback(message: Message):
    await message.answer(
        sc("use /start to begin, /profile for stats, or /history to see past generations."),
        reply_markup=main_menu_kb()
    )


# ─────────────────────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────────────────────
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Start the bot"),
        BotCommand(command="profile", description="Your profile"),
        BotCommand(command="history", description="Your generation history"),
        BotCommand(command="top", description="Top generators"),
    ])


async def on_startup():
    me = await bot.me()  # cached identity — also warms the cache for handlers
    log.info("Bot online: @%s (id=%s)", me.username, me.id)


async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await set_commands()
    await on_startup()
    log.info("Starting polling…")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            close_bot_session=False,
        )
    finally:
        await bot.session.close()
        log.info("Shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.info("Interrupted by user.")