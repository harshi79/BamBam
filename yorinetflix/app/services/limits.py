"""
YoriNetflix — Limits service.

Cooldowns, daily generation limits, and anti-abuse.
"""

from __future__ import annotations

from datetime import datetime, timezone

import asyncpg

from app.database.repositories import history_repo, user_repo


async def check_cooldown(
    conn: asyncpg.Connection,
    user_id: int,
    cooldown_seconds: int,
) -> tuple[bool, int]:
    """Check if user is within cooldown. Returns (allowed, seconds_remaining)."""
    user = await user_repo.get_by_id(conn, user_id)
    if not user or user["last_gen_time"] is None:
        return True, 0
    last_gen = user["last_gen_time"]
    now = datetime.now(timezone.utc)
    elapsed = (now - last_gen).total_seconds()
    if elapsed >= cooldown_seconds:
        return True, 0
    remaining = int(cooldown_seconds - elapsed)
    return False, remaining


async def check_daily_limit(
    conn: asyncpg.Connection,
    user_id: int,
    daily_limit: int,
) -> tuple[bool, int]:
    """Check if user is under the daily generation limit.

    Returns (allowed, remaining_today).
    daily_limit=0 means unlimited.
    """
    if daily_limit <= 0:
        return True, -1  # unlimited
    used = await history_repo.get_today_count(conn, user_id)
    remaining = daily_limit - used
    if remaining <= 0:
        return False, 0
    return True, remaining