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
from urllib.parse import urlsplit

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

# Sign-in destinations.  Plain, public Netflix pages carrying no credentials:
# whoever opens them signs in as themselves.
#
# DEFAULT_TV_URL is the official TV activation page — the one the Netflix app
# shows on a television ("go to netflix.com/tv8 and enter the code displayed on
# your TV").  It must stay tokenless: the TV flow is *code entry*, not
# auto-login.  There is no authorized, documented Netflix API through which
# this bot could mint a per-account auto-login token for somebody else's
# account, so no token is ever generated, stored, or embedded here.
DEFAULT_TV_URL = "https://www.netflix.com/tv8"
DEFAULT_PC_URL = "https://www.netflix.com/account"
DEFAULT_MOBILE_URL = "https://www.netflix.com/login"

# Query parameters that carry credentials.  Netflix's auto-login token
# (``nftoken``) and friends sign whoever opens the link straight into an
# account, with no password prompt.  A button URL is shared, cached and logged
# by Telegram, so such a parameter must never survive into a button.
CREDENTIAL_QUERY_PARAMS = frozenset({
    "nftoken", "nf_token", "token", "authtoken", "auth_token",
    "access_token", "accesstoken", "idtoken", "id_token", "session",
    "sessionid", "session_id", "sid", "password", "pass", "pwd",
    "netflixid", "securenetflixid",
})

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
                    await event.answer("Please wait a moment before trying again.", show_alert=False)
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
            return await message.answer(
                _ui_notice("Admin only", "This command is reserved for administrators.")
            )
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

_UI_RULE = "┄┄┄┄┄┄┄┄┄┄┄"


def _ui_heading(title: str) -> str:
    return f"<b>◇ {sc_html(title)}</b>"


def _ui_section(title: str) -> str:
    return f"<b>{sc_html(title)}</b>"


def _ui_notice(title: str, body: str) -> str:
    return f"{_ui_heading(title)}\n{body}"

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


def strip_credential_params(url: str) -> str:
    """Remove credential-bearing query parameters from a URL.

    Netflix auto-login tokens (``nftoken``) and similar session parameters are
    dropped, along with any fragment that accompanied them.  Harmless
    parameters and the path are left untouched, so ordinary sign-in and
    activation links pass through unchanged.
    """
    if "?" not in url:
        return url

    base, _, rest = url.partition("?")
    query, _, fragment = rest.partition("#")

    kept = []
    dropped = False
    for pair in query.split("&"):
        if not pair:
            continue
        name = pair.split("=", 1)[0].strip().lower()
        if name in CREDENTIAL_QUERY_PARAMS:
            dropped = True
            continue
        kept.append(pair)

    cleaned = base + ("?" + "&".join(kept) if kept else "")
    if fragment and not dropped:
        cleaned += "#" + fragment
    return cleaned


def normalize_url(url: str, fallback: str) -> str:
    """Return a button-safe sign-in URL.

    Uses ``fallback`` when the inventory carried no usable URL, adds the scheme
    when it is missing, and strips credential-bearing query parameters so a
    button can never hand out a pre-authenticated session.  When stripping
    leaves nothing but a bare host, the official fallback page is used instead.
    """
    url = (url or "").strip()
    if not url or url.upper() == "N/A":
        return strip_credential_params(fallback)
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    cleaned = strip_credential_params(url)
    if cleaned != url and urlsplit(cleaned).path in ("", "/"):
        # The URL was only a credential carrier — send the person to the
        # official page for that route instead of a bare domain root.
        return strip_credential_params(fallback)
    return cleaned


def cookie_action_kb(pc_url: str, tv_url: str, mobile_url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="↗ Pᴄ", url=normalize_url(pc_url, DEFAULT_PC_URL)),
            InlineKeyboardButton(text="↗ Tᴠ", url=normalize_url(tv_url, DEFAULT_TV_URL)),
            InlineKeyboardButton(text="↗ Mᴏʙɪʟᴇ", url=normalize_url(mobile_url, DEFAULT_MOBILE_URL)),
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
        f"<b>◇ {esc(country)}</b>  ·  {sc_html('Netflix access')}",
        _UI_RULE,
    ]
    if info:
        parts.extend(["", f"<blockquote>{esc(info)}</blockquote>"])

    if cookie_str:
        parts.extend([
            "",
            f"{_ui_section('Cookie')}  <i>{sc_html('tap to copy')}</i>",
            f"<blockquote><code>{esc(cookie_str)}</code></blockquote>",
        ])

    parts.extend([
        "",
        _UI_RULE,
        f"<b>{remaining}</b> {sc_html('remaining')}  ·  {esc(country)}",
        f"<i>{sc_html('Use a route below to open sign-in.')}</i>",
    ])
    return "\n".join(parts)


# ─────────────────────────────────────────────────────────────
# KEYBOARDS
# ─────────────────────────────────────────────────────────────
def main_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✦ Gᴇɴᴇʀᴀᴛᴇ", callback_data="gen:0")],
        [
            InlineKeyboardButton(text="◉ Pʀᴏꜰɪʟᴇ", callback_data="profile"),
            InlineKeyboardButton(text="≡ Hɪꜱᴛᴏʀʏ", callback_data="history:1"),
        ],
    ])


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="‹ Menu", callback_data="menu")]
    ])


def join_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="↗ Join Channel", url=FORCE_CHANNEL_URL or "https://t.me/"
        )],
        [InlineKeyboardButton(text="✓ Joined · Verify", callback_data="check_join")],
    ])


# ─────────────────────────────────────────────────────────────
# /start — ONE message: video + caption + buttons
# ─────────────────────────────────────────────────────────────
def build_welcome_text() -> str:
    return (
        f"<b>✦ {sc_html('yorinetflix')}</b>\n"
        f"<blockquote>{sc_html('welcome to the premium account desk')}</blockquote>\n\n"
        f"{sc_html('premium accounts · free · instant · no strings')}\n\n"
        f"<i>Crafted by <a href=\"https://t.me/Yorichiiprime\">@Yorichiiprime</a></i>\n"
        f"<i>Choose a destination below to begin.</i>"
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
            "<b>◇ ᴀᴄᴄᴇꜱꜱ ʀᴇǫᴜɪʀᴇᴅ</b>\nJoin our channel to use the account desk, then verify below.",
            reply_markup=join_kb()
        )
    await send_welcome(message)


@dp.callback_query(F.data == "check_join")
async def cb_check_join(callback: CallbackQuery):
    if not await is_member(callback.from_user.id):
        return await safe_answer(callback, "× You have not joined the channel yet.", alert=True)
    await safe_edit(callback.message, build_welcome_text(), reply_markup=main_menu_kb())
    await safe_answer(callback, "✓ Membership verified.")


@dp.callback_query(F.data == "menu")
async def cb_menu(callback: CallbackQuery):
    await safe_edit(callback.message, build_welcome_text(), reply_markup=main_menu_kb())
    await safe_answer(callback)


# ─────────────────────────────────────────────────────────────
# GENERATE FLOW
# ─────────────────────────────────────────────────────────────
# Telegram caps InlineKeyboardButton.callback_data at 64 *bytes*.  A country
# button used to carry the raw country name ("pick:United States"), so any
# country whose name did not fit — long names, flag emojis, non-Latin scripts
# (every such character is 2–4 bytes) — made Telegram reject the whole
# keyboard with BUTTON_DATA_INVALID.  Buttons now carry a short fixed-size key
# that is resolved back to the exact country name when pressed.
COUNTRY_KEY_LEN = 16  # hex chars → "pick:" + 16 = 21 bytes, always within 64


def country_key(country: str) -> str:
    """Short, stable, Telegram-safe identifier for a country name."""
    return hashlib.sha256(country.encode("utf-8")).hexdigest()[:COUNTRY_KEY_LEN]


async def resolve_country(db, token: str) -> str | None:
    """Map a ``pick:`` payload back to the stocked country it refers to.

    Accepts the country key used by current keyboards, and — so that country
    lists sent by earlier builds keep working — the raw country name used by
    older keyboards.  Returns None when no such country is in stock.
    """
    async with db.execute(
        "SELECT DISTINCT country FROM cookies "
        "WHERE country IS NOT NULL AND country != 'Unknown'"
    ) as cur:
        countries = [row[0] for row in await cur.fetchall()]

    for country in countries:
        if country_key(country) == token:
            return country
    if token in countries:  # legacy keyboard: raw country name
        return token
    return None


async def render_countries(page: int) -> tuple[str, InlineKeyboardMarkup]:
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT country, COUNT(id) FROM cookies "
            "WHERE country IS NOT NULL AND country != 'Unknown' "
            "GROUP BY country ORDER BY LOWER(country)"
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        return (
            (
                f"{_ui_heading('Inventory unavailable')}\n\n"
                "<blockquote>There are no accounts available at the moment.\n"
                "Please check back later.</blockquote>"
            ),
            back_to_menu_kb(),
        )

    total_available = sum(c for _, c in rows)
    total_pages = max(1, ceil(len(rows) / PAGE_SIZE))
    page = max(1, min(page, total_pages))
    start = (page - 1) * PAGE_SIZE
    page_rows = rows[start:start + PAGE_SIZE]

    buttons = [[InlineKeyboardButton(
        text=f"◇ {c}  ·  {n}",
        callback_data=f"pick:{country_key(c)}"
    )] for c, n in page_rows]

    nav = []
    if page > 1:
        nav.append(InlineKeyboardButton(text="‹", callback_data=f"gen:{page-1}"))
    nav.append(InlineKeyboardButton(text=f"· {page} / {total_pages} ·", callback_data="noop"))
    if page < total_pages:
        nav.append(InlineKeyboardButton(text="›", callback_data=f"gen:{page+1}"))
    if nav:
        buttons.append(nav)
    buttons.append([InlineKeyboardButton(text="‹ Menu", callback_data="menu")])

    text = (
        f"<b>◇ {sc_html('Select a country')}</b>\n\n"
        f"<blockquote>Choose a country to browse available stock.</blockquote>\n\n"
        f"<code>{total_available}</code> {sc_html('accounts in stock')}  ·  "
        f"<code>{len(rows)}</code> {sc_html('countries')}"
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
    token = callback.data.split(":", 1)[1]
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
                f"↻ Available in {wait}s. Please wait before generating again.",
                alert=True
            )

        country = await resolve_country(db, token)
        if country is None:
            return await safe_answer(callback, "No stock remains for this country.", alert=True)

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
            return await safe_answer(callback, "No stock remains for this country.", alert=True)

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
        return await safe_answer(callback, "Delivery failed. Please contact an administrator.", alert=True)

    await safe_answer(callback, "✓ Delivered. Your account is in the message below.")


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
    cd_text = f"{remaining}s" if remaining else sc("ready")
    joined_str = datetime.fromtimestamp(joined, tz=timezone.utc).strftime("%Y-%m-%d")

    return (
        f"{_ui_heading('Your profile')}\n\n"
        f"<blockquote><b>{esc(user.full_name)}</b>\n"
        f"<code>{uid}</code>  ·  {sc_html('member since')} <i>{joined_str}</i></blockquote>\n\n"
        f"{_UI_RULE}\n"
        f"{_ui_section('Account overview')}\n"
        f"·  {sc_html('Generated')}  <b>{total}</b>\n"
        f"·  {sc_html('Countries')}  <b>{countries}</b>\n"
        f"·  {sc_html('Cooldown')}  <b>{cd_text}</b>"
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
        text = (
            f"{_ui_heading('Generation history')}\n\n"
            "<blockquote>No generations yet.\nYour first account will appear here.</blockquote>"
        )
        kb = back_to_menu_kb()
    else:
        total_pages = max(1, ceil(total / per_page))
        first_index = (page - 1) * per_page + 1
        lines = [
            _ui_heading("Generation history"),
            f"<i>{sc_html('Most recent first')}</i>",
            "",
        ]
        for rank, (country, timestamp) in enumerate(rows, start=first_index):
            when = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            lines.append(
                f"<code>{rank:02d}</code>  <b>{esc(country)}</b>\n"
                f"     <i>{when} UTC</i>"
            )
        lines.extend([
            "",
            _UI_RULE,
            (
                f"<code>{page:02d} / {total_pages:02d}</code>  ·  "
                f"{sc_html('Entries')}  <b>{total}</b>"
            ),
        ])
        text = "\n".join(lines)

        nav = []
        if page > 1:
            nav.append(InlineKeyboardButton(text="‹", callback_data=f"history:{page-1}"))
        if page < total_pages:
            nav.append(InlineKeyboardButton(text="›", callback_data=f"history:{page+1}"))
        buttons = [nav] if nav else []
        buttons.append([InlineKeyboardButton(text="‹ Menu", callback_data="menu")])
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
            f"{_ui_heading('Top generators')}\n\n"
            "<blockquote>No generations have been recorded yet.</blockquote>",
            reply_markup=back_to_menu_kb()
        )

    lines = [
        _ui_heading("Top generators"),
        f"<i>{sc_html('All-time ranking')}</i>",
        "",
    ]
    for rank, (_uid, full_name, username, total) in enumerate(rows, start=1):
        name = esc(full_name or username or "Unknown")
        lines.append(f"<code>{rank:02d}</code>  <b>{name}</b>  ·  <b>{total}</b>")
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
            return await message.answer(_ui_notice("Unsupported attachment", "Reply to text or a <code>.txt</code> file."))
    elif message.text and len(message.text.split(maxsplit=1)) > 1:
        text_to_parse = message.text.split(maxsplit=1)[1]
    else:
        return await message.answer(
            "<b>◇ ᴜꜱᴀɢᴇ</b>\nReply to a <code>.txt</code> file with <code>/add</code>, "
            "or send <code>/add &lt;cookie text&gt;</code>."
        )

    parsed = parse_bulk_cookies(text_to_parse)
    if not parsed:
        return await message.answer(_ui_notice(
            "No inventory found", "Add a supported export or a <code>.txt</code> file."
        ))

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

    await message.answer(
        f"{_ui_heading('Inventory updated')}\n\n"
        f"{sc_html('Added')}  <b>{added}</b> {sc_html('accounts')}\n"
        f"{sc_html('Duplicates skipped')}  <b>{dupes}</b>"
    )


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

    top_text = "\n".join(
        f"·  {esc(country)}  <b>{count}</b>" for country, count in top
    ) or "·  —"

    await message.answer(
        f"{_ui_heading('Bot overview')}\n\n"
        f"{_ui_section('Inventory')}\n"
        f"·  {sc_html('Accounts')}  <b>{total_cookies}</b>\n"
        f"·  {sc_html('Countries')}  <b>{total_countries}</b>\n\n"
        f"{_UI_RULE}\n"
        f"{_ui_section('Community')}\n"
        f"·  {sc_html('Users')}  <b>{total_users}</b>\n"
        f"·  {sc_html('Active · 24h')}  <b>{active_24h}</b>\n\n"
        f"{_UI_RULE}\n"
        f"{_ui_section('Generations')}\n"
        f"·  {sc_html('All time')}  <b>{total_gens}</b>\n"
        f"·  {sc_html('Last 24h')}  <b>{gens_24h}</b>\n"
        f"·  {sc_html('Last 7d')}  <b>{gens_7d}</b>\n\n"
        f"{_ui_section('Top stock')}\n{top_text}"
    )


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
        return await message.answer(
            f"{_ui_heading('Inventory empty')}\n"
            "There is currently nothing in stock."
        )
    lines = [
        _ui_heading("Stock overview"),
        (
            f"<i>{len(rows)} {sc_html('countries')}  ·  "
            f"{sum(count for _, count in rows)} {sc_html('accounts')}</i>"
        ),
        _UI_RULE,
    ]
    for country, count in rows:
        lines.append(f"{esc(country)}  ·  <b>{count}</b>")
    lines.extend([
        _UI_RULE,
        f"{_ui_section('Total')}  <b>{sum(count for _, count in rows)}</b>",
    ])
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
        return await message.answer(_ui_notice("Nothing to export", "No inventory matches this request."))

    path = os.path.join(BACKUP_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(r[0] for r in rows))

    await message.answer_document(
        FSInputFile(path),
        caption=(
            f"{_ui_heading('Export ready')}\n"
            f"{sc_html('Accounts')}  <b>{len(rows)}</b>"
        )
    )


@dp.message(Command("backup"))
@admin_only
async def admin_backup(message: Message):
    if not os.path.exists(DB_NAME):
        return await message.answer(_ui_notice("Snapshot unavailable", "No database file is available yet."))
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
        caption=(
            f"{_ui_heading('Database snapshot ready')}\n"
            f"<code>{stamp}</code>"
        )
    )


@dp.message(Command("broadcast"))
@admin_only
async def admin_broadcast(message: Message):
    if not message.reply_to_message:
        return await message.answer(_ui_notice(
            "Broadcast needs a message",
            "Reply to a message with <code>/broadcast</code> to send it."
        ))

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cur:
            users = [r[0] for r in await cur.fetchall()]

    status = await message.answer(
        f"{_ui_heading('Broadcasting')}\n"
        f"{sc_html('Delivering to')}  <b>{len(users)}</b> {sc_html('users')}…"
    )

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
                await status.edit_text(f"{_ui_heading('Broadcast in progress')}\n\n"
                    f"{sc_html('Sent')}  <b>{sent}</b>  ·  "
                    f"{sc_html('Failed')}  <b>{failed}</b>  ·  "
                    f"{sc_html('Blocked')}  <b>{blocked}</b>")
            except TelegramBadRequest:
                pass

    await status.edit_text(
        f"{_ui_heading('Broadcast complete')}\n\n"
        f"{sc_html('Delivered')}  <b>{sent}</b>\n"
        f"{sc_html('Failed')}  <b>{failed}</b>\n"
        f"{sc_html('Blocked')}  <b>{blocked}</b>"
    )


@dp.message(Command("clear_country"))
@admin_only
async def admin_clear_country(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        return await message.answer(_ui_notice("Usage", "Use <code>/clear_country &lt;country&gt;</code>."))
    country = parts[1].strip()
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("DELETE FROM cookies WHERE country = ?", (country,))
        await db.commit()
        deleted = cur.rowcount
    await message.answer(
        f"{_ui_heading('Inventory cleared')}\n"
        f"{sc_html('Removed')}  <b>{deleted}</b> {sc_html('items')}  ·  "
        f"{esc(country)}"
    )


@dp.message(Command("wipe"))
@admin_only
async def admin_wipe(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or args[1].strip() != "CONFIRM":
        return await message.answer(
            f"{_ui_heading('Confirm inventory reset')}\n"
            "This deletes <b>all inventory</b>.\n"
            "Send <code>/wipe CONFIRM</code> to proceed."
        )
    async with aiosqlite.connect(DB_NAME) as db:
        cur = await db.execute("DELETE FROM cookies")
        await db.commit()
        deleted = cur.rowcount
    await message.answer(
        f"{_ui_heading('Inventory wiped')}\n"
        f"{sc_html('Removed')}  <b>{deleted}</b> {sc_html('accounts')}"
    )


@dp.message(Command("admin"))
@admin_only
async def admin_help(message: Message):
    await message.answer(
        f"{_ui_heading('Admin console')}\n"
        f"<i>{sc_html('Operations · authorized access')}</i>\n\n"
        f"{_ui_section('Inventory')}\n"
        "<code>/add</code>  Add inventory (.txt or text)\n"
        "<code>/stock</code>  View the stock breakdown\n"
        "<code>/export [country]</code>  Export inventory\n"
        "<code>/backup</code>  Download a database snapshot\n"
        "<code>/clear_country &lt;name&gt;</code>  Remove one country\n"
        "<code>/wipe CONFIRM</code>  Delete all inventory\n\n"
        f"{_ui_section('Analytics and users')}\n"
        "<code>/stats</code>  View bot statistics\n"
        "<code>/broadcast</code>  Message all users\n\n"
        f"<i><code>/admin</code> opens this console.</i>"
    )


# ─────────────────────────────────────────────────────────────
# FALLBACK
# ─────────────────────────────────────────────────────────────
@dp.message(F.text & ~F.text.startswith("/"))
async def fallback(message: Message):
    await message.answer(
        f"{_ui_heading('Account desk')}\n"
        "Send /start to begin, /profile to view your stats, "
        "or /history to review previous generations.",
        reply_markup=main_menu_kb()
    )


# ─────────────────────────────────────────────────────────────
# STARTUP
# ─────────────────────────────────────────────────────────────
async def set_commands():
    await bot.set_my_commands([
        BotCommand(command="start", description="Open the YoriNetflix account desk"),
        BotCommand(command="profile", description="View your account overview"),
        BotCommand(command="history", description="Review your recent generations"),
        BotCommand(command="top", description="View the all-time ranking"),
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