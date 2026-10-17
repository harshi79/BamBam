"""
YoriNetflix — Referrals service.
"""

from __future__ import annotations

import asyncpg

from app.database.repositories import user_repo, rewards_repo


async def process_referral(
    conn: asyncpg.Connection,
    new_user_id: int,
    referrer_id: int,
    reward_points: int,
) -> str:
    """Process a new user's referral. Returns status string.

    Called during /start when a ref_ parameter is present.
    Must be called within an existing transaction.
    """
    if new_user_id == referrer_id:
        return "self_referral"

    # Verify referrer exists
    referrer = await user_repo.get_by_id(conn, referrer_id)
    if not referrer:
        return "invalid_referrer"

    # Set referrer on the new user (fails if already set)
    set_ok = await user_repo.set_referrer(conn, new_user_id, referrer_id)
    if not set_ok:
        return "already_referred"

    # Record the referral
    created = await rewards_repo.create_referral(conn, referrer_id, new_user_id)
    if not created:
        return "already_referred"

    # Credit the referrer
    if reward_points > 0:
        await user_repo.add_points(conn, referrer_id, reward_points)
        await user_repo.increment_referral_count(conn, referrer_id)
        await rewards_repo.add_transaction(
            conn, referrer_id, reward_points,
            "referral_reward", str(new_user_id),
        )
        await rewards_repo.mark_referral_credited(conn, new_user_id)

    return "success"


async def get_referral_link(bot_username: str, user_id: int) -> str:
    """Build a referral link for a user."""
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


async def get_referral_stats(
    conn: asyncpg.Connection, user_id: int
) -> dict:
    count = await rewards_repo.get_referral_count(conn, user_id)
    return {"referral_count": count}