"""
YoriNetflix — Integration tests for the delivery → history flow.

Regression coverage for the production crash:

    asyncpg.exceptions.ForeignKeyViolationError: insert or update on table
    "generation_history" violates foreign key constraint
    "generation_history_cookie_id_fkey"
    DETAIL:  Key (cookie_id)=(N) is not present in table "cookies".

Root cause: the picked cookie row was DELETEd inside the same transaction
that recorded it in generation_history.cookie_id.  Delivered accounts are now
marked ``consumed_at`` instead of deleted, so the FK is satisfied and the
audit link survives.

These tests run against a real PostgreSQL (bundled via ``pgserver``).
"""

from __future__ import annotations

import pytest

pgserver = pytest.importorskip("pgserver")
asyncpg = pytest.importorskip("asyncpg")

from app.database.migrations.runner import run_migrations  # noqa: E402
from app.database.repositories import (  # noqa: E402
    history_repo,
    inventory_repo,
    user_repo,
)
from app.services import inventory  # noqa: E402

pytestmark = pytest.mark.integration

TEST_USER_ID = 111
COOKIE_RAW = "📁 Source: t\n🌍 Country: India\n🍪 Cookie: NetflixId=abc"


@pytest.fixture
async def db(tmp_path):
    """Fresh schema on a throwaway PostgreSQL server for every test."""
    server = pgserver.get_server(tmp_path / "pgdata")
    pool = await asyncpg.create_pool(server.get_uri(), min_size=1, max_size=2)
    await run_migrations(pool)
    yield pool
    await pool.close()
    server.cleanup()


async def _stock_up(conn, n: int = 1, country: str = "India") -> None:
    await user_repo.upsert(conn, TEST_USER_ID, "tester", "Test User")
    for i in range(n):
        await inventory_repo.add(
            conn,
            country=country,
            raw_text=f"{COOKIE_RAW}-{country}-{i}",
            pc_url="https://example.com",
            netflix_id=f"abc{i}",
            secure_netflix_id=f"def{i}",
        )


async def _deliver(conn, country: str = "India"):
    """The exact production sequence from generation.py::cb_pick_country."""
    cookie = await inventory.pick_account(conn, country)
    assert cookie is not None
    await history_repo.add(conn, TEST_USER_ID, country, cookie["id"])
    await user_repo.set_last_gen_time(conn, TEST_USER_ID)
    await user_repo.increment_total_generated(conn, TEST_USER_ID)
    return cookie


class TestDeliveryWritesHistory:
    async def test_generation_flow_does_not_violate_cookie_fk(self, db):
        """The exact crash sequence must succeed and keep the audit link."""
        async with db.acquire() as conn:
            async with conn.transaction():
                await _stock_up(conn)
                cookie = await _deliver(conn)

        async with db.acquire() as conn:
            hist = await conn.fetchrow(
                "SELECT user_id, country, cookie_id FROM generation_history"
            )
            assert hist is not None, "history row must be recorded"
            assert hist["cookie_id"] == cookie["id"], (
                "history must reference the exact delivered account"
            )
            row = await conn.fetchrow(
                "SELECT consumed_at FROM cookies WHERE id = $1", cookie["id"]
            )
            assert row is not None, "delivered account is kept for the FK/audit link"
            assert row["consumed_at"] is not None, "delivered account is marked consumed"

    async def test_delivered_account_is_not_stocked_again(self, db):
        async with db.acquire() as conn:
            async with conn.transaction():
                await _stock_up(conn, n=2)
                first = await _deliver(conn)

        async with db.acquire() as conn:
            # Only the undelivered account counts as stock.
            assert await inventory_repo.get_country_total(conn, "India") == 1
            assert await inventory_repo.get_total_stock(conn) == 1
            assert await inventory.get_country_stock(conn) == [
                {"country": "India", "count": 1}
            ]
            assert len(await inventory_repo.get_stock_breakdown(conn)) == 1
            assert len(await inventory_repo.get_raw_texts_by_country(conn)) == 1

            # A pick can never return the consumed account again.
            async with conn.transaction():
                second = await inventory.pick_account(conn, "India")
                assert second is not None
                assert second["id"] != first["id"]
                assert await inventory.pick_account(conn, "India") is None

    async def test_history_add_survives_missing_cookie(self, db):
        """A stale cookie_id must not poison the transaction or the delivery."""
        async with db.acquire() as conn:
            async with conn.transaction():
                await _stock_up(conn)
                await history_repo.add(conn, TEST_USER_ID, "India", 999999)
                # The transaction must remain usable after the fallback…
                n = await inventory_repo.get_country_total(conn, "India")
                assert n == 1

        async with db.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT cookie_id FROM generation_history"
            )
            assert row is not None, "event is still recorded"
            assert row["cookie_id"] is None, "…with a NULL link"


class TestAdminWipes:
    async def test_wipe_keeps_history_but_clears_links(self, db):
        """ON DELETE SET NULL semantics: history survives admin wipes."""
        async with db.acquire() as conn:
            async with conn.transaction():
                await _stock_up(conn)
                await _deliver(conn)

        async with db.acquire() as conn:
            deleted = await inventory_repo.delete_all(conn)
            assert deleted == 1
            hist = await conn.fetchrow("SELECT cookie_id FROM generation_history")
            assert hist is not None
            assert hist["cookie_id"] is None

    async def test_clear_country_keeps_history_but_clears_links(self, db):
        async with db.acquire() as conn:
            async with conn.transaction():
                await _stock_up(conn, country="India")
                await _stock_up(conn, country="Japan")
                await _deliver(conn, country="India")

        async with db.acquire() as conn:
            deleted = await inventory_repo.delete_by_country(conn, "India")
            assert deleted == 1
            hist = await conn.fetchrow("SELECT country, cookie_id FROM generation_history")
            assert hist is not None
            assert hist["country"] == "India"
            assert hist["cookie_id"] is None
