"""
YoriNetflix — Database connection module tests.

Tests the connection pool lifecycle (init, get, close) using mocks
to avoid requiring a live PostgreSQL instance.
"""

from __future__ import annotations

import pytest
import pytest_asyncio

from app.database import connection as db_conn


class TestPoolLifecycle:
    """Test get_pool / init_pool / close_pool state transitions."""

    @pytest.fixture(autouse=True)
    def _reset_pool(self):
        """Ensure the module-level pool is None before and after each test."""
        db_conn._pool = None
        yield
        db_conn._pool = None

    def test_get_pool_before_init_raises(self):
        """get_pool() should raise RuntimeError before init_pool()."""
        with pytest.raises(RuntimeError, match="not initialized"):
            db_conn.get_pool()

    @pytest.mark.asyncio
    async def test_close_pool_when_none_is_safe(self):
        """close_pool() should not raise when pool is already None."""
        await db_conn.close_pool()  # Should log and return cleanly.

    @pytest.mark.asyncio
    async def test_init_pool_returns_pool(self, monkeypatch):
        """init_pool should return an asyncpg.Pool."""
        import asyncpg

        class FakeConn:
            """Mock database connection."""
            async def fetchval(self, query):
                return "PostgreSQL 16.0"

        class FakeAcquireCtx:
            """Mock async context manager returned by pool.acquire()."""
            def __init__(self):
                self._conn = FakeConn()

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, *args):
                pass

        class FakePool:
            """Minimal mock of asyncpg.Pool."""
            def acquire(self):
                # NOT async — returns an async context manager directly,
                # matching real asyncpg.Pool.acquire() behavior.
                return FakeAcquireCtx()

            async def close(self):
                pass

        async def fake_create_pool(**kwargs):
            return FakePool()

        monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)

        pool = await db_conn.init_pool("postgresql://u:p@h:5432/d")
        assert pool is not None
        assert db_conn.get_pool() is pool

    @pytest.mark.asyncio
    async def test_double_init_returns_existing(self, monkeypatch):
        """Calling init_pool twice should return the existing pool."""
        import asyncpg

        call_count = 0

        class FakeConn:
            async def fetchval(self, query):
                return "PostgreSQL 16.0"

        class FakeAcquireCtx:
            def __init__(self):
                self._conn = FakeConn()

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, *args):
                pass

        class FakePool:
            def acquire(self):
                return FakeAcquireCtx()

            async def close(self):
                pass

        async def fake_create_pool(**kwargs):
            nonlocal call_count
            call_count += 1
            return FakePool()

        monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)

        pool1 = await db_conn.init_pool("postgresql://u:p@h:5432/d")
        pool2 = await db_conn.init_pool("postgresql://u:p@h:5432/d")
        assert pool1 is pool2
        assert call_count == 1  # Only one pool created.

    @pytest.mark.asyncio
    async def test_close_then_get_raises(self, monkeypatch):
        """After close_pool(), get_pool() should raise again."""
        import asyncpg

        class FakeConn:
            async def fetchval(self, query):
                return "PostgreSQL 16.0"

        class FakeAcquireCtx:
            def __init__(self):
                self._conn = FakeConn()

            async def __aenter__(self):
                return self._conn

            async def __aexit__(self, *args):
                pass

        class FakePool:
            def acquire(self):
                return FakeAcquireCtx()

            async def close(self):
                pass

        async def fake_create_pool(**kwargs):
            return FakePool()

        monkeypatch.setattr(asyncpg, "create_pool", fake_create_pool)

        await db_conn.init_pool("postgresql://u:p@h:5432/d")
        await db_conn.close_pool()
        with pytest.raises(RuntimeError, match="not initialized"):
            db_conn.get_pool()


class TestCheckConnection:
    """Test the health check utility."""

    @pytest.fixture(autouse=True)
    def _reset_pool(self):
        db_conn._pool = None
        yield
        db_conn._pool = None

    @pytest.mark.asyncio
    async def test_check_returns_false_when_no_pool(self):
        """check_connection should return False if pool isn't initialized."""
        result = await db_conn.check_connection()
        assert result is False