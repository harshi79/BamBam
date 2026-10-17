"""
YoriNetflix — Runtime configuration repository.

Reads and writes the bot_config key-value table.
"""

from __future__ import annotations

from typing import Optional

import asyncpg


async def get(conn: asyncpg.Connection, key: str) -> Optional[str]:
    """Return a config value by key, or None."""
    row = await conn.fetchrow(
        "SELECT value FROM bot_config WHERE key = $1", key
    )
    return row["value"] if row else None


async def get_int(conn: asyncpg.Connection, key: str, default: int = 0) -> int:
    """Return a config value as int, with fallback."""
    val = await get(conn, key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


async def set_value(
    conn: asyncpg.Connection, key: str, value: str
) -> None:
    """Insert or update a config value."""
    await conn.execute(
        """
        INSERT INTO bot_config (key, value, updated_at)
        VALUES ($1, $2, NOW())
        ON CONFLICT (key) DO UPDATE SET
            value = EXCLUDED.value,
            updated_at = NOW()
        """,
        key,
        value,
    )


async def get_all(conn: asyncpg.Connection) -> dict[str, str]:
    """Return all config key-value pairs."""
    rows = await conn.fetch("SELECT key, value FROM bot_config ORDER BY key")
    return {r["key"]: r["value"] for r in rows}