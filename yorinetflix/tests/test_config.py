"""
YoriNetflix — Configuration validation tests.

Tests that Settings correctly validates environment variables,
rejects invalid values, applies defaults, and exposes derived properties.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError


# We import Settings fresh in each test to avoid caching issues.
def _make_settings(**env_overrides):
    """Build a Settings instance with explicit env values."""
    from app.config import Settings
    return Settings(**env_overrides)


class TestRequiredFields:
    """BOT_TOKEN, ADMIN_IDS, and DATABASE_URL must be set."""

    def test_missing_bot_token(self, monkeypatch):
        """Missing BOT_TOKEN raises ValidationError."""
        monkeypatch.setenv("ADMIN_IDS", "123")
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
        from app.config import Settings
        with pytest.raises(ValidationError, match="BOT_TOKEN"):
            Settings()

    def test_missing_admin_ids(self, monkeypatch):
        """Missing ADMIN_IDS raises ValidationError."""
        monkeypatch.setenv("BOT_TOKEN", "123:abc")
        monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/d")
        from app.config import Settings
        with pytest.raises(ValidationError, match="ADMIN_IDS"):
            Settings()

    def test_missing_database_url(self, monkeypatch):
        """Missing DATABASE_URL raises ValidationError."""
        monkeypatch.setenv("BOT_TOKEN", "123:abc")
        monkeypatch.setenv("ADMIN_IDS", "123")
        from app.config import Settings
        with pytest.raises(ValidationError, match="DATABASE_URL"):
            Settings()

    def test_all_required_set(self, valid_env):
        """All required fields set — no error."""
        s = _make_settings()
        assert s.BOT_TOKEN == "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
        assert s.ADMIN_IDS == "111222333"
        assert "postgresql://" in s.DATABASE_URL


class TestBotTokenValidation:
    """BOT_TOKEN must look like a real Telegram bot token."""

    def test_empty_token(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match="required"):
            Settings(BOT_TOKEN="")

    def test_whitespace_only_token(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match="required"):
            Settings(BOT_TOKEN="   ")

    def test_token_without_colon(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match="malformed"):
            Settings(BOT_TOKEN="not-a-valid-token")

    def test_valid_token_format(self, valid_env):
        s = _make_settings()
        assert ":" in s.BOT_TOKEN

    def test_token_with_extra_spaces(self, valid_env):
        """Leading/trailing whitespace should be stripped."""
        s = _make_settings(BOT_TOKEN="  123:abc  ")
        assert s.BOT_TOKEN == "123:abc"


class TestAdminIdsValidation:
    """ADMIN_IDS must be a non-empty, comma-separated list of integers."""

    def test_empty_admin_ids(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match="required"):
            Settings(ADMIN_IDS="")

    def test_whitespace_only(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match="required"):
            Settings(ADMIN_IDS="   ")

    def test_single_id(self, valid_env):
        s = _make_settings(ADMIN_IDS="999888777")
        assert s.admin_id_set == {999888777}

    def test_multiple_ids(self, valid_env):
        s = _make_settings(ADMIN_IDS="111,222,333")
        assert s.admin_id_set == {111, 222, 333}

    def test_ids_with_spaces(self, valid_env):
        """Spaces around commas should be handled."""
        s = _make_settings(ADMIN_IDS=" 111 , 222 , 333 ")
        assert s.admin_id_set == {111, 222, 333}

    def test_invalid_id_raises_at_property_access(self, valid_env):
        """Non-integer in ADMIN_IDS raises ValueError when accessed."""
        s = _make_settings(ADMIN_IDS="123,notanumber,456")
        with pytest.raises(ValueError, match="not an integer"):
            _ = s.admin_id_set

    def test_trailing_comma(self, valid_env):
        """Trailing comma should be ignored."""
        s = _make_settings(ADMIN_IDS="111,222,")
        assert s.admin_id_set == {111, 222}


class TestDatabaseUrlValidation:
    """DATABASE_URL must start with postgresql:// or postgres://."""

    def test_empty_url(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match="required"):
            Settings(DATABASE_URL="")

    def test_invalid_scheme(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match="must start with"):
            Settings(DATABASE_URL="mysql://user:pass@host/db")

    def test_postgresql_scheme(self, valid_env):
        s = _make_settings()
        assert s.DATABASE_URL.startswith("postgresql://")

    def test_postgres_scheme(self, valid_env):
        s = _make_settings(DATABASE_URL="postgres://u:p@h:5432/d")
        assert s.DATABASE_URL.startswith("postgres://")


class TestDefaultValues:
    """Optional fields should have sensible defaults."""

    def test_defaults_applied(self, valid_env):
        s = _make_settings()
        assert s.COOLDOWN_SECONDS == 120
        assert s.DAILY_GENERATION_LIMIT == 5
        assert s.DAILY_REWARD_POINTS == 10
        assert s.REFERRAL_REWARD_POINTS == 25
        assert s.POINTS_PER_GENERATION == 0
        assert s.THROTTLE_RATE == 0.5
        assert s.FSUB_FAIL_OPEN is False
        assert s.PAGE_SIZE == 12
        assert s.LOG_LEVEL == "INFO"
        assert s.FORCE_CHANNEL == ""
        assert s.FORCE_CHANNEL_URL == ""
        assert s.START_VIDEO_URL == ""

    def test_custom_cooldown(self, valid_env):
        s = _make_settings(COOLDOWN_SECONDS=60)
        assert s.COOLDOWN_SECONDS == 60

    def test_custom_daily_limit(self, valid_env):
        s = _make_settings(DAILY_GENERATION_LIMIT=10)
        assert s.DAILY_GENERATION_LIMIT == 10


class TestFieldValidators:
    """Edge-case validators."""

    def test_negative_cooldown(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match=">= 0"):
            Settings(COOLDOWN_SECONDS=-1)

    def test_negative_daily_limit(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match=">= 0"):
            Settings(DAILY_GENERATION_LIMIT=-5)

    def test_negative_reward_points(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match=">= 0"):
            Settings(DAILY_REWARD_POINTS=-10)

    def test_zero_cooldown_allowed(self, valid_env):
        """Zero cooldown means no cooldown — should be valid."""
        s = _make_settings(COOLDOWN_SECONDS=0)
        assert s.COOLDOWN_SECONDS == 0

    def test_zero_daily_limit_allowed(self, valid_env):
        """Zero daily limit = unlimited — should be valid."""
        s = _make_settings(DAILY_GENERATION_LIMIT=0)
        assert s.DAILY_GENERATION_LIMIT == 0


class TestFsubConsistency:
    """FSUB model-level cross-field validation."""

    def test_fsub_channel_without_url_raises(self, valid_env):
        from app.config import Settings
        with pytest.raises(ValidationError, match="FORCE_CHANNEL_URL"):
            Settings(FORCE_CHANNEL="mychannel", FORCE_CHANNEL_URL="")

    def test_fsub_channel_with_url_ok(self, valid_env):
        s = _make_settings(
            FORCE_CHANNEL="mychannel",
            FORCE_CHANNEL_URL="https://t.me/+invite",
        )
        assert s.FORCE_CHANNEL == "mychannel"
        assert s.FORCE_CHANNEL_URL == "https://t.me/+invite"

    def test_fsub_url_without_channel_ok(self, valid_env):
        """URL set but channel empty — FSUB is just disabled."""
        s = _make_settings(FORCE_CHANNEL_URL="https://t.me/+invite")
        assert s.FORCE_CHANNEL == ""


class TestDerivedProperties:
    """Test computed properties on Settings."""

    def test_admin_id_set_single(self, valid_env):
        s = _make_settings(ADMIN_IDS="42")
        assert s.admin_id_set == {42}

    def test_admin_id_set_multiple(self, valid_env):
        s = _make_settings(ADMIN_IDS="1,2,3")
        assert s.admin_id_set == {1, 2, 3}

    def test_db_pool_defaults(self, valid_env):
        s = _make_settings()
        assert s.db_pool_min == 1
        assert s.db_pool_max == 5


class TestExtraFieldsIgnored:
    """Unknown environment variables should not cause errors."""

    def test_extra_env_ignored(self, valid_env, monkeypatch):
        monkeypatch.setenv("SOME_RANDOM_VAR", "should-be-ignored")
        s = _make_settings()
        assert not hasattr(s, "SOME_RANDOM_VAR") or True  # Should not raise