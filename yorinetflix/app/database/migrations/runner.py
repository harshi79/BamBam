"""
YoriNetflix — Database migration runner.

Reads numbered .sql files from the migrations/ directory and applies
any that haven't been run yet. Migrations are tracked in the
schema_migrations table (created in 001_initial.sql).

Usage (standalone):
    python -m app.database.migrations.runner

Usage (from application startup):
    from app.database.migrations.runner import run_migrations
    await run_migrations(pool)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import List, Tuple

import asyncpg

log = logging.getLogger("yorinetflix.migrations")

MIGRATIONS_DIR = Path(__file__).parent
MIGRATION_FILE_PATTERN = re.compile(r"^(\d{3})_(.+)\.sql$")


def discover_migrations() -> List[Tuple[int, str, Path]]:
    """Find all numbered .sql files in the migrations directory.

    Returns:
        Sorted list of (version, name, path) tuples.
    """
    migrations: List[Tuple[int, str, Path]] = []
    for f in sorted(MIGRATIONS_DIR.iterdir()):
        if not f.is_file():
            continue
        m = MIGRATION_FILE_PATTERN.match(f.name)
        if m:
            version = int(m.group(1))
            name = m.group(2)
            migrations.append((version, name, f))
    return sorted(migrations, key=lambda x: x[0])


async def _ensure_migrations_table(conn: asyncpg.Connection) -> None:
    """Create schema_migrations table if it doesn't exist.

    This table is also defined in 001_initial.sql (with IF NOT EXISTS),
    but we need it to exist BEFORE running 001 so we can record which
    migrations have been applied. This bootstrap runs first; the
    IF NOT EXISTS in 001 is harmless if this already created it.
    """
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            name        TEXT NOT NULL,
            applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


async def _get_applied_versions(conn: asyncpg.Connection) -> set:
    """Return the set of migration versions already applied."""
    rows = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
    return {r["version"] for r in rows}


async def _apply_migration(
    conn: asyncpg.Connection,
    version: int,
    name: str,
    path: Path,
) -> None:
    """Apply a single migration file within a transaction."""
    sql = path.read_text(encoding="utf-8")
    log.info("Applying migration %03d_%s…", version, name)
    await conn.execute(sql)
    await conn.execute(
        "INSERT INTO schema_migrations (version, name) VALUES ($1, $2)",
        version,
        name,
    )
    log.info("Migration %03d_%s applied successfully.", version, name)


async def run_migrations(pool: asyncpg.Pool) -> int:
    """Discover and apply all pending migrations.

    Args:
        pool: The asyncpg connection pool.

    Returns:
        Number of migrations applied in this run.

    Raises:
        asyncpg.PostgresError: If a migration fails.
    """
    migrations = discover_migrations()
    if not migrations:
        log.info("No migration files found in %s", MIGRATIONS_DIR)
        return 0

    applied_count = 0
    async with pool.acquire() as conn:
        # Use a transaction for the migration check + apply sequence.
        # Each individual migration is also run within this transaction.
        tr = conn.transaction()
        await tr.start()

        try:
            await _ensure_migrations_table(conn)
            applied = await _get_applied_versions(conn)

            for version, name, path in migrations:
                if version in applied:
                    log.debug("Migration %03d_%s already applied — skipping.", version, name)
                    continue
                await _apply_migration(conn, version, name, path)
                applied_count += 1

            await tr.commit()
        except Exception:
            await tr.rollback()
            raise

    if applied_count > 0:
        log.info("Applied %d migration(s).", applied_count)
    else:
        log.info("All %d migration(s) already applied — database is up to date.", len(migrations))

    return applied_count


# ── Standalone runner ──────────────────────────────────────────

async def _main() -> None:
    """Run migrations from the command line."""
    import os
    import sys

    # Add parent directories to path so we can import app.config.
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from app.config import Settings  # noqa: E402
    from app.database.connection import init_pool, close_pool  # noqa: E402

    # Load settings — will fail if required env vars are missing.
    settings = Settings()
    pool = await init_pool(
        settings.DATABASE_URL,
        min_size=settings.db_pool_min,
        max_size=settings.db_pool_max,
    )
    try:
        count = await run_migrations(pool)
        print(f"Done. {count} migration(s) applied.")
    finally:
        await close_pool()


if __name__ == "__main__":
    import asyncio
    asyncio.run(_main())