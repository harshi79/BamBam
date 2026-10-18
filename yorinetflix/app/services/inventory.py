"""
YoriNetflix — Inventory service.

Cookie parsing, stock management, and allocation logic.
"""

from __future__ import annotations

import hashlib
import re
from typing import Optional

import asyncpg

from app.database.repositories import inventory_repo


# ── Cookie Parser (ported from original) ───────────────────────


def parse_cookie_text(text: str) -> dict:
    """Parse a single cookie/account text block into structured data."""
    data: dict = {"raw_text": text.strip()}

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

    data["cookie_hash"] = hashlib.sha256(
        data["raw_text"].encode("utf-8")
    ).hexdigest()
    return data


def parse_bulk_cookies(text: str) -> list[dict]:
    """Parse bulk cookie text, splitting on source markers."""
    chunks = re.split(r"(?=📁 Source:)", text)
    parsed = [parse_cookie_text(c) for c in chunks if "🌍 Country:" in c]
    if parsed:
        return parsed
    return [parse_cookie_text(text)] if text.strip() else []


# ── Country keys (Telegram callback payloads) ──────────────────

# Telegram caps InlineKeyboardButton.callback_data at 64 *bytes*.  Country
# buttons used to carry the raw country name ("pick:United States"), so any
# country whose name did not fit — long names, flag emojis, non-Latin scripts
# (every such character is 2–4 bytes) — made Telegram reject the whole
# keyboard with BUTTON_DATA_INVALID.  Buttons now carry a short fixed-size key
# that is resolved back to the exact country name when pressed.
COUNTRY_KEY_LEN = 16  # hex chars → "pick:" + 16 = 21 bytes, always within 64


def country_key(country: str) -> str:
    """Short, stable, Telegram-safe identifier for a country name."""
    return hashlib.sha256(country.encode("utf-8")).hexdigest()[:COUNTRY_KEY_LEN]


async def resolve_country(conn: asyncpg.Connection, token: str) -> Optional[str]:
    """Map a ``pick:`` payload back to the stocked country it refers to.

    Accepts the country key used by current keyboards, and — so that country
    lists sent by earlier builds keep working — the raw country name used by
    older keyboards.  Returns None when no such country is in stock.
    """
    countries = [r["country"] for r in await inventory_repo.get_country_stock(conn)]
    for country in countries:
        if country_key(country) == token:
            return country
    if token in countries:  # legacy keyboard: raw country name
        return token
    return None


# ── Database Operations ────────────────────────────────────────


async def add_inventory(
    conn: asyncpg.Connection, parsed: list[dict]
) -> tuple[int, int]:
    """Add parsed cookies to inventory. Returns (added, duplicates)."""
    added = 0
    dupes = 0
    for p in parsed:
        try:
            await inventory_repo.add(
                conn,
                country=p["country"],
                raw_text=p["raw_text"],
                pc_url=p.get("pc_url", ""),
                phone_url=p.get("phone_url", ""),
                tv_url=p.get("tv_url", ""),
                netflix_id=p.get("netflix_id", ""),
                secure_netflix_id=p.get("secure_netflix_id", ""),
            )
            added += 1
        except asyncpg.UniqueViolationError:
            dupes += 1
    return added, dupes


async def get_country_stock(conn: asyncpg.Connection) -> list[dict]:
    """Return stock per country as list of dicts."""
    rows = await inventory_repo.get_country_stock(conn)
    return [{"country": r["country"], "count": r["cnt"]} for r in rows]


async def pick_account(
    conn: asyncpg.Connection, country: str
) -> Optional[asyncpg.Record]:
    """Atomically pick a random undelivered account for a country.

    Returns the cookie record (already marked consumed) or None.
    The caller must commit the transaction to finalize the allocation.
    """
    return await inventory_repo.pick_random(conn, country)