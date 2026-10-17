"""
YoriNetflix — User service.

Coordinates user operations across repositories.
"""

from __future__ import annotations

from typing import Optional

import asyncpg

from app.database.repositories import user_repo


async def upsert_user(
    conn: asyncpg.Connection,
    user_id: int,
    username: str = "",
    full_name: str = "",
) -> None:
    """Ensure a user exists in the database."""
    await user_repo.upsert(conn, user_id, username, full_name)


async def get_profile_data(
    conn: asyncpg.Connection, user_id: int
) -> Optional[dict]:
    """Build a profile data dict for display."""
    user = await user_repo.get_by_id(conn, user_id)
    if not user:
        return None
    unique_countries = await user_repo.get_unique_country_count(conn, user_id)
    return {
        "user_id": user["user_id"],
        "username": user["username"],
        "full_name": user["full_name"],
        "joined_at": user["joined_at"],
        "total_generated": user["total_generated"],
        "unique_countries": unique_countries,
        "last_gen_time": user["last_gen_time"],
        "points": user["points"],
        "referral_count": user["referral_count"],
    }


async def ban(conn: asyncpg.Connection, user_id: int) -> None:
    await user_repo.ban_user(conn, user_id)


async def unban(conn: asyncpg.Connection, user_id: int) -> None:
    await user_repo.unban_user(conn, user_id)


async def is_banned(conn: asyncpg.Connection, user_id: int) -> bool:
    return await user_repo.is_banned(conn, user_id)