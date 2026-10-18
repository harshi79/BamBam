"""
YoriNetflix — Migration runner tests.

Tests the migration discovery and file structure without requiring
a live database connection. The actual SQL correctness is verified
by running migrations against a test database (integration test).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.database.migrations.runner import (
    discover_migrations,
    MIGRATIONS_DIR,
    MIGRATION_FILE_PATTERN,
)


class TestMigrationDiscovery:
    """Test that migration files are found and parsed correctly."""

    def test_discover_returns_list(self):
        """discover_migrations should return a list."""
        result = discover_migrations()
        assert isinstance(result, list)

    def test_discover_finds_initial_migration(self):
        """001_initial.sql should always be found."""
        migrations = discover_migrations()
        versions = [v for v, _, _ in migrations]
        assert 1 in versions

    def test_discover_finds_rewards_migration(self):
        """002_rewards.sql should always be found."""
        migrations = discover_migrations()
        versions = [v for v, _, _ in migrations]
        assert 2 in versions

    def test_discover_finds_config_migration(self):
        """003_config.sql should always be found."""
        migrations = discover_migrations()
        versions = [v for v, _, _ in migrations]
        assert 3 in versions

    def test_discover_finds_consumed_cookies_migration(self):
        """004_consumed_cookies.sql should always be found."""
        migrations = discover_migrations()
        versions = [v for v, _, _ in migrations]
        assert 4 in versions

    def test_migrations_sorted_by_version(self):
        """Migrations must be in ascending version order."""
        migrations = discover_migrations()
        versions = [v for v, _, _ in migrations]
        assert versions == sorted(versions)

    def test_migration_names_extracted(self):
        """Names should match the part between version number and .sql."""
        migrations = discover_migrations()
        names = {v: name for v, name, _ in migrations}
        assert names[1] == "initial"
        assert names[2] == "rewards"
        assert names[3] == "config"
        assert names[4] == "consumed_cookies"

    def test_all_migration_files_exist(self):
        """Every discovered migration should point to an existing file."""
        for version, name, path in discover_migrations():
            assert path.exists(), f"Migration file missing: {path}"
            assert path.is_file(), f"Migration path is not a file: {path}"

    def test_all_migrations_are_valid_sql(self):
        """Every migration file should be readable and non-empty."""
        for version, name, path in discover_migrations():
            content = path.read_text(encoding="utf-8")
            assert len(content.strip()) > 0, f"Migration {path.name} is empty"


class TestMigrationFilePattern:
    """Test the regex that parses migration filenames."""

    def test_matches_standard_name(self):
        m = MIGRATION_FILE_PATTERN.match("001_initial.sql")
        assert m is not None
        assert m.group(1) == "001"
        assert m.group(2) == "initial"

    def test_matches_multi_word_name(self):
        m = MIGRATION_FILE_PATTERN.match("002_rewards_and_referrals.sql")
        assert m is not None
        assert m.group(1) == "002"
        assert m.group(2) == "rewards_and_referrals"

    def test_no_match_without_version(self):
        assert MIGRATION_FILE_PATTERN.match("initial.sql") is None

    def test_no_match_without_sql_extension(self):
        assert MIGRATION_FILE_PATTERN.match("001_initial.py") is None

    def test_no_match_random_file(self):
        assert MIGRATION_FILE_PATTERN.match("README.md") is None

    def test_no_match_init_file(self):
        assert MIGRATION_FILE_PATTERN.match("__init__.py") is None


class TestMigrationSqlStructure:
    """Test that migration SQL files contain expected constructs."""

    def test_initial_creates_core_tables(self):
        """001_initial.sql should create the three core tables."""
        path = MIGRATIONS_DIR / "001_initial.sql"
        content = path.read_text(encoding="utf-8").lower()
        assert "create table" in content
        assert "users" in content
        assert "cookies" in content
        assert "generation_history" in content

    def test_initial_creates_schema_migrations_table(self):
        """001 should create schema_migrations for tracking."""
        path = MIGRATIONS_DIR / "001_initial.sql"
        content = path.read_text(encoding="utf-8").lower()
        assert "schema_migrations" in content

    def test_initial_uses_if_not_exists(self):
        """Tables should use IF NOT EXISTS for idempotency."""
        path = MIGRATIONS_DIR / "001_initial.sql"
        content = path.read_text(encoding="utf-8").lower()
        assert "if not exists" in content

    def test_rewards_creates_reward_tables(self):
        """002_rewards.sql should create daily_claims, referrals, point_transactions."""
        path = MIGRATIONS_DIR / "002_rewards.sql"
        content = path.read_text(encoding="utf-8").lower()
        assert "daily_claims" in content
        assert "referrals" in content
        assert "point_transactions" in content

    def test_rewards_has_unique_constraints(self):
        """Reward tables should have UNIQUE constraints for dedup."""
        path = MIGRATIONS_DIR / "002_rewards.sql"
        content = path.read_text(encoding="utf-8").lower()
        assert "uq_daily_claim" in content
        assert "uq_referred" in content
        assert "chk_no_self_referral" in content

    def test_config_creates_config_table(self):
        """003_config.sql should create bot_config table."""
        path = MIGRATIONS_DIR / "003_config.sql"
        content = path.read_text(encoding="utf-8").lower()
        assert "bot_config" in content
        assert "on conflict" in content

    def test_config_seeds_defaults(self):
        """003 should seed default config values."""
        path = MIGRATIONS_DIR / "003_config.sql"
        content = path.read_text(encoding="utf-8").lower()
        assert "daily_reward_points" in content
        assert "referral_reward_points" in content
        assert "daily_generation_limit" in content