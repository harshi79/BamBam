"""
YoriNetflix — Generation history repository.
"""

from __future__ import annotations

import asyncpg


async def add(
    conn: asyncpg.Connection,
    user_id: int,
    country: str,
    cookie_id: int | None = None,
) -> None:
    """Record a generation event."""
    await conn.execute(
        """
        INSERT INTO generation_history (user_id, country, cookie_id)
        VALUES ($1, $2, $3)
        """,
        user_id,
        country,
        cookie_id,
    )


async def get_user_history(
    conn: asyncpg.Connection,
    user_id: int,
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[asyncpg.Record], int]:
    """Return (rows, total_count) for paginated user history."""
    total_row = await conn.fetchrow(
        "SELECT COUNT(*) AS cnt FROM generation_history WHERE user_id = $1",
        user_id,
    )
    total = total_row["cnt"]
    rows = await conn.fetch(
        """
        SELECT country, generated_at
        FROM generation_history
        WHERE user_id = $1
        ORDER BY id DESC
        LIMIT $2 OFFSET $3
        """,
        user_id,
        limit,
        offset,
    )
    return rows, total


async def get_today_count(conn: asyncpg.Connection, user_id: int) -> int:
    """Count how many generations a user has done today (UTC)."""
    row = await conn.fetchrow(
        """
        SELECT COUNT(*) AS cnt
        FROM generation_history
        WHERE user_id = $1
          AND generated_at >= (NOW() AT TIME ZONE 'UTC')::DATE
        """,
        user_id,
    )
    return row["cnt"] if row else 0


async def get_global_stats(conn: asyncpg.Connection) -> dict:
    """Return generation statistics."""
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS total_gens,
            COUNT(*) FILTER (
                WHERE generated_at > NOW() - INTERVAL '24 hours'
            ) AS gens_24h,
            COUNT(*) FILTER (
                WHERE generated_at > NOW() - INTERVAL '7 days'
            ) AS gens_7d
        FROM generation_history
        """
    )
    return dict(row) if row else {"total_gens": 0, "gens_24h": 0, "gens_7d": 0}