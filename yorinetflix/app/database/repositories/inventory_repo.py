"""
YoriNetflix — Inventory repository.

Cookie/account CRUD, stock queries, and atomic allocation.
"""

from __future__ import annotations

import hashlib
from typing import Optional

import asyncpg


async def add(
    conn: asyncpg.Connection,
    country: str,
    raw_text: str,
    pc_url: str = "",
    phone_url: str = "",
    tv_url: str = "",
    netflix_id: str = "",
    secure_netflix_id: str = "",
) -> int:
    """Insert one inventory item. Returns the new ID.

    Raises:
        asyncpg.UniqueViolationError: If cookie_hash already exists.
    """
    cookie_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    row = await conn.fetchrow(
        """
        INSERT INTO cookies
            (country, raw_text, pc_url, phone_url, tv_url,
             netflix_id, secure_netflix_id, cookie_hash)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """,
        country, raw_text, pc_url, phone_url, tv_url,
        netflix_id, secure_netflix_id, cookie_hash,
    )
    return row["id"]


async def get_country_stock(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Return (country, count) for all known countries with undelivered stock."""
    return await conn.fetch(
        """
        SELECT country, COUNT(id) AS cnt
        FROM cookies
        WHERE country IS NOT NULL AND country != 'Unknown'
          AND consumed_at IS NULL
        GROUP BY country
        ORDER BY LOWER(country)
        """
    )


async def get_total_stock(conn: asyncpg.Connection) -> int:
    """Return total undelivered cookie count."""
    row = await conn.fetchrow(
        "SELECT COUNT(id) AS cnt FROM cookies WHERE consumed_at IS NULL"
    )
    return row["cnt"] if row else 0


async def get_country_total(conn: asyncpg.Connection, country: str) -> int:
    """Return undelivered cookie count for a specific country."""
    row = await conn.fetchrow(
        "SELECT COUNT(id) AS cnt FROM cookies WHERE country = $1 AND consumed_at IS NULL",
        country,
    )
    return row["cnt"] if row else 0


async def pick_random(
    conn: asyncpg.Connection, country: str
) -> Optional[asyncpg.Record]:
    """Atomically allocate one random undelivered cookie for the given country.

    Uses SELECT ... FOR UPDATE SKIP LOCKED to prevent concurrent double-allocation.
    Returns the cookie row (with all fields) or None if out of stock.

    The row is marked consumed (``consumed_at``) within the same transaction
    rather than deleted — it is kept so ``generation_history.cookie_id`` can
    reference the exact account that was delivered.  Caller must commit.
    """
    row = await conn.fetchrow(
        """
        SELECT id, country, raw_text, pc_url, phone_url, tv_url,
               netflix_id, secure_netflix_id
        FROM cookies
        WHERE country = $1 AND consumed_at IS NULL
        ORDER BY RANDOM()
        LIMIT 1
        FOR UPDATE SKIP LOCKED
        """,
        country,
    )
    if row is None:
        return None
    await conn.execute(
        "UPDATE cookies SET consumed_at = NOW() WHERE id = $1", row["id"]
    )
    return row


async def get_stock_breakdown(conn: asyncpg.Connection) -> list[asyncpg.Record]:
    """Return (country, count) of undelivered stock, sorted by count descending."""
    return await conn.fetch(
        """
        SELECT country, COUNT(id) AS cnt
        FROM cookies
        WHERE consumed_at IS NULL
        GROUP BY country
        ORDER BY COUNT(id) DESC
        """
    )


async def get_raw_texts_by_country(
    conn: asyncpg.Connection, country: Optional[str] = None
) -> list[str]:
    """Return raw_text for export (undelivered stock only). If country is set, filter."""
    if country:
        rows = await conn.fetch(
            "SELECT raw_text FROM cookies WHERE country = $1 AND consumed_at IS NULL ORDER BY id",
            country,
        )
    else:
        rows = await conn.fetch(
            "SELECT raw_text FROM cookies WHERE consumed_at IS NULL ORDER BY id"
        )
    return [r["raw_text"] for r in rows]


async def delete_by_country(conn: asyncpg.Connection, country: str) -> int:
    """Hard-delete all cookies for a country (delivered or not). Returns count deleted.

    History rows referencing deleted cookies keep existing; their cookie_id
    links are cleared by the FK's ON DELETE SET NULL.
    """
    result = await conn.execute(
        "DELETE FROM cookies WHERE country = $1", country
    )
    return int(result.split()[-1])


async def delete_all(conn: asyncpg.Connection) -> int:
    """Hard-delete ALL cookies (delivered or not). Returns count deleted.

    History rows referencing deleted cookies keep existing; their cookie_id
    links are cleared by the FK's ON DELETE SET NULL.
    """
    result = await conn.execute("DELETE FROM cookies")
    return int(result.split()[-1])