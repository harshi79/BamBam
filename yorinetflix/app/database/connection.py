"""
YoriNetflix — Database connection pool management.

Provides an async connection pool (asyncpg) that lives for the
lifetime of the application. All database access should go through
this module or through the repository layer built on top of it.

Usage:
    from app.database.connection import get_pool

    async def some_query():
        async with get_pool().acquire() as conn:
            row = await conn.fetchrow("SELECT 1")
"""

from __future__ import annotations

import logging
from typing import Optional

import asyncpg

log = logging.getLogger("yorinetflix.db")

# Module-level pool reference, initialized by init_pool(), closed by close_pool().
_pool: Optional[asyncpg.Pool] = None


async def init_pool(dsn: str, *, min_size: int = 1, max_size: int = 5) -> asyncpg.Pool:
    """Create and return the application's connection pool.

    Call this once during startup. The pool handles reconnection
    automatically when Neon terminates idle connections.

    Args:
        dsn: PostgreSQL connection string (e.g. from settings.DATABASE_URL).
        min_size: Minimum number of connections kept in the pool.
        max_size: Maximum number of connections.

    Returns:
        The created asyncpg.Pool instance.

    Raises:
        asyncpg.InvalidCatalogNameError: Database does not exist.
        asyncpg.InvalidAuthorizationSpecError: Bad credentials.
        OSError: Network/DNS failure.
    """
    global _pool
    if _pool is not None:
        log.warning("init_pool called but pool already exists — returning existing pool.")
        return _pool

    log.info("Connecting to database (pool %d-%d)…", min_size, max_size)
    _pool = await asyncpg.create_pool(
        dsn=dsn,
        min_size=min_size,
        max_size=max_size,
        # Neon terminates idle connections after ~5 minutes.
        # Explicitly set to 4 minutes so the pool recycles before Neon drops.
        max_inactive_connection_lifetime=240,
        command_timeout=30,
    )
    # Verify connectivity.
    async with _pool.acquire() as conn:
        version = await conn.fetchval("SELECT version()")
        log.info("Database connected: %s", version[:80])

    return _pool


def get_pool() -> asyncpg.Pool:
    """Return the active connection pool.

    Raises:
        RuntimeError: If init_pool() has not been called yet.
    """
    if _pool is None:
        raise RuntimeError(
            "Database pool is not initialized. "
            "Call init_pool() during application startup."
        )
    return _pool


async def close_pool() -> None:
    """Close all connections in the pool. Call during shutdown."""
    global _pool
    if _pool is not None:
        log.info("Closing database pool…")
        await _pool.close()
        _pool = None
        log.info("Database pool closed.")
    else:
        log.debug("close_pool called but pool was already None.")


async def check_connection() -> bool:
    """Quick health check. Returns True if a query succeeds."""
    try:
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        return True
    except Exception as e:
        log.error("Database health check failed: %s", e)
        return False