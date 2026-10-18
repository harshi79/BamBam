"""
YoriNetflix — Generation history repository.
"""

from __future__ import annotations

import logging

import asyncpg

log = logging.getLogger("yorinetflix.history")


async def _insert(
    conn: asyncpg.Connection,
    user_id: int,
    country: str,
    cookie_id: int | None,
) -> None:
    await conn.execute(
        """
        INSERT INTO generation_history (user_id, country, cookie_id)
        VALUES ($1, $2, $3)
        """,
        user_id,
        country,
        cookie_id,
    )


async def add(
    conn: asyncpg.Connection,
    user_id: int,
    country: str,
    cookie_id: int | None = None,
) -> None:
    """Record a generation event.

    ``cookie_id`` links the event to the inventory row that was delivered.
    If that row no longer exists (racing admin wipe, stale data), the event is
    still recorded with a NULL link instead of failing the delivery — the
    history write must never break generation.  A SAVEPOINT keeps the caller's
    transaction usable after such a violation.
    """
    if cookie_id is None:
        await _insert(conn, user_id, country, None)
        return
    try:
        # Nested `transaction()` opens a SAVEPOINT when the caller already has
        # a transaction open, so a failed insert does not poison it.
        async with conn.transaction():
            await _insert(conn, user_id, country, cookie_id)
    except asyncpg.ForeignKeyViolationError:
        log.warning(
            "cookie_id=%s vanished before history insert; recording NULL link",
            cookie_id,
        )
        await _insert(conn, user_id, country, None)


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
