"""
YoriNetflix — Points service.

Manages point balances and transaction ledger.
"""

from __future__ import annotations

import asyncpg

from app.database.repositories import user_repo, rewards_repo


async def get_balance(conn: asyncpg.Connection, user_id: int) -> int:
    return await user_repo.get_points(conn, user_id)


async def credit(
    conn: asyncpg.Connection,
    user_id: int,
    amount: int,
    reason: str,
    reference: str | None = None,
) -> int:
    """Credit points to a user. Returns new balance."""
    await user_repo.add_points(conn, user_id, amount)
    await rewards_repo.add_transaction(conn, user_id, amount, reason, reference)
    return await user_repo.get_points(conn, user_id)


async def admin_adjust(
    conn: asyncpg.Connection,
    user_id: int,
    amount: int,
    admin_id: int,
    note: str = "",
) -> int:
    """Admin point adjustment. Logs who made the change."""
    ref = f"admin:{admin_id}"
    if note:
        ref += f":{note}"
    return await credit(conn, user_id, amount, "admin_adjust", ref)