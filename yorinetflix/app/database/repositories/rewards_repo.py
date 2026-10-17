"""
YoriNetflix — Rewards, referrals, and point transactions repository.
"""

from __future__ import annotations

from typing import Optional

import asyncpg


# ── Daily Claims ───────────────────────────────────────────────


async def try_claim_daily(
    conn: asyncpg.Connection,
    user_id: int,
    points: int,
) -> bool:
    """Attempt to claim daily reward. Returns True if claimed, False if already done.

    Uses UNIQUE(user_id, claim_date) to prevent duplicate claims at the DB level.
    Caller is responsible for updating the user's point balance.
    """
    try:
        await conn.execute(
            """
            INSERT INTO daily_claims (user_id, points)
            VALUES ($1, $2)
            """,
            user_id,
            points,
        )
        return True
    except asyncpg.UniqueViolationError:
        return False


async def get_last_claim_date(
    conn: asyncpg.Connection, user_id: int
) -> Optional[str]:
    """Return the date of the user's last daily claim, or None."""
    row = await conn.fetchrow(
        """
        SELECT claim_date FROM daily_claims
        WHERE user_id = $1
        ORDER BY claim_date DESC
        LIMIT 1
        """,
        user_id,
    )
    return str(row["claim_date"]) if row else None


# ── Referrals ──────────────────────────────────────────────────


async def create_referral(
    conn: asyncpg.Connection,
    referrer_id: int,
    referred_id: int,
) -> bool:
    """Record a referral. Returns False if already referred or self-referral.

    Uses UNIQUE(referred_id) and CHECK constraints for safety.
    """
    try:
        await conn.execute(
            """
            INSERT INTO referrals (referrer_id, referred_id)
            VALUES ($1, $2)
            """,
            referrer_id,
            referred_id,
        )
        return True
    except (
        asyncpg.UniqueViolationError,
        asyncpg.CheckViolationError,
    ):
        return False


async def mark_referral_credited(
    conn: asyncpg.Connection,
    referred_id: int,
) -> None:
    """Mark a referral as reward-credited."""
    await conn.execute(
        "UPDATE referrals SET reward_credited = TRUE WHERE referred_id = $1",
        referred_id,
    )


async def get_referral_by_referred(
    conn: asyncpg.Connection, referred_id: int
) -> Optional[asyncpg.Record]:
    """Find referral record by referred user ID."""
    return await conn.fetchrow(
        "SELECT * FROM referrals WHERE referred_id = $1", referred_id
    )


async def get_referral_count(
    conn: asyncpg.Connection, referrer_id: int
) -> int:
    """Count successful referrals for a user."""
    row = await conn.fetchrow(
        "SELECT COUNT(*) AS cnt FROM referrals WHERE referrer_id = $1",
        referrer_id,
    )
    return row["cnt"] if row else 0


# ── Point Transactions (Ledger) ───────────────────────────────


async def add_transaction(
    conn: asyncpg.Connection,
    user_id: int,
    amount: int,
    reason: str,
    reference: str | None = None,
) -> None:
    """Record a point transaction in the ledger."""
    await conn.execute(
        """
        INSERT INTO point_transactions (user_id, amount, reason, reference)
        VALUES ($1, $2, $3, $4)
        """,
        user_id,
        amount,
        reason,
        reference,
    )


async def get_user_transactions(
    conn: asyncpg.Connection,
    user_id: int,
    limit: int = 20,
) -> list[asyncpg.Record]:
    """Return recent point transactions for a user."""
    return await conn.fetch(
        """
        SELECT amount, reason, reference, created_at
        FROM point_transactions
        WHERE user_id = $1
        ORDER BY id DESC
        LIMIT $2
        """,
        user_id,
        limit,
    )