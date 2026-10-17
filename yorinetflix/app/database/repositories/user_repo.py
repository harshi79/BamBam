"""
YoriNetflix — User repository.

All user-related database operations. Accepts an asyncpg.Connection
so callers control transaction boundaries.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import asyncpg


async def upsert(
    conn: asyncpg.Connection,
    user_id: int,
    username: str,
    full_name: str,
) -> None:
    """Insert or update a user record."""
    await conn.execute(
        """
        INSERT INTO users (user_id, username, full_name, joined_at)
        VALUES ($1, $2, $3, NOW())
        ON CONFLICT (user_id) DO UPDATE SET
            username = EXCLUDED.username,
            full_name = EXCLUDED.full_name
        """,
        user_id,
        username,
        full_name,
    )


async def get_by_id(conn: asyncpg.Connection, user_id: int) -> Optional[asyncpg.Record]:
    """Return user row or None."""
    return await conn.fetchrow(
        "SELECT * FROM users WHERE user_id = $1", user_id
    )


async def get_profile(conn: asyncpg.Connection, user_id: int) -> Optional[asyncpg.Record]:
    """Return user row with derived fields for profile display."""
    return await conn.fetchrow(
        "SELECT * FROM users WHERE user_id = $1", user_id
    )


async def get_unique_country_count(conn: asyncpg.Connection, user_id: int) -> int:
    """Count distinct countries a user has generated from."""
    row = await conn.fetchrow(
        "SELECT COUNT(DISTINCT country) AS cnt FROM generation_history WHERE user_id = $1",
        user_id,
    )
    return row["cnt"] if row else 0


async def set_last_gen_time(conn: asyncpg.Connection, user_id: int) -> None:
    """Update the user's last generation timestamp to now."""
    await conn.execute(
        "UPDATE users SET last_gen_time = NOW() WHERE user_id = $1",
        user_id,
    )


async def increment_total_generated(conn: asyncpg.Connection, user_id: int) -> None:
    """Atomically increment the user's total_generated counter."""
    await conn.execute(
        "UPDATE users SET total_generated = total_generated + 1 WHERE user_id = $1",
        user_id,
    )


async def add_points(conn: asyncpg.Connection, user_id: int, amount: int) -> None:
    """Add points to a user's balance. Use negative amount to subtract."""
    await conn.execute(
        "UPDATE users SET points = points + $1 WHERE user_id = $2",
        amount,
        user_id,
    )


async def get_points(conn: asyncpg.Connection, user_id: int) -> int:
    """Return current point balance."""
    row = await conn.fetchrow(
        "SELECT points FROM users WHERE user_id = $1", user_id
    )
    return row["points"] if row else 0


async def set_referrer(
    conn: asyncpg.Connection,
    user_id: int,
    referrer_id: int,
) -> bool:
    """Set referrer for a user. Returns False if already set or self-referral."""
    if user_id == referrer_id:
        return False
    result = await conn.execute(
        """
        UPDATE users SET referrer_id = $1
        WHERE user_id = $2 AND referrer_id IS NULL
        """,
        referrer_id,
        user_id,
    )
    return result.endswith("1")


async def increment_referral_count(conn: asyncpg.Connection, user_id: int) -> None:
    """Increment the referral count for a user."""
    await conn.execute(
        "UPDATE users SET referral_count = referral_count + 1 WHERE user_id = $1",
        user_id,
    )


async def ban_user(conn: asyncpg.Connection, user_id: int) -> None:
    """Mark a user as banned."""
    await conn.execute(
        "UPDATE users SET is_banned = TRUE WHERE user_id = $1", user_id
    )


async def unban_user(conn: asyncpg.Connection, user_id: int) -> None:
    """Remove ban from a user."""
    await conn.execute(
        "UPDATE users SET is_banned = FALSE WHERE user_id = $1", user_id
    )


async def is_banned(conn: asyncpg.Connection, user_id: int) -> bool:
    """Check if a user is banned."""
    row = await conn.fetchrow(
        "SELECT is_banned FROM users WHERE user_id = $1", user_id
    )
    return row["is_banned"] if row else False


async def get_all_user_ids(conn: asyncpg.Connection) -> list[int]:
    """Return all user IDs (for broadcast)."""
    rows = await conn.fetch("SELECT user_id FROM users ORDER BY user_id")
    return [r["user_id"] for r in rows]


async def get_top_generators(
    conn: asyncpg.Connection, limit: int = 10
) -> list[asyncpg.Record]:
    """Return top generators by total_generated."""
    return await conn.fetch(
        """
        SELECT user_id, full_name, username, total_generated
        FROM users
        WHERE total_generated > 0
        ORDER BY total_generated DESC
        LIMIT $1
        """,
        limit,
    )


async def get_stats(conn: asyncpg.Connection) -> dict:
    """Return aggregate user statistics."""
    row = await conn.fetchrow(
        """
        SELECT
            COUNT(*) AS total_users,
            COUNT(*) FILTER (WHERE last_gen_time > NOW() - INTERVAL '24 hours') AS active_24h
        FROM users
        """
    )
    return dict(row) if row else {"total_users": 0, "active_24h": 0}