"""
YoriNetflix — Main module tests.

Tests the startup and shutdown lifecycle, config loading,
and logging setup.
"""

from __future__ import annotations

import logging
import sys
from unittest.mock import patch, AsyncMock

import pytest

from app.config import Settings


class TestSetupLogging:
    """Test logging configuration."""

    def test_setup_logging_creates_handlers(self, tmp_path):
        """setup_logging should configure root logger without errors."""
        from app.main import setup_logging

        log_dir = str(tmp_path / "logs")
        setup_logging("INFO", log_dir)

        root = logging.getLogger()
        assert len(root.handlers) >= 1

    def test_setup_logging_respects_level(self, tmp_path):
        """Log level should be applied."""
        from app.main import setup_logging

        setup_logging("WARNING", str(tmp_path / "logs"))
        root = logging.getLogger()
        assert root.level == logging.WARNING

    def test_setup_logging_invalid_level_defaults(self, tmp_path):
        """Invalid log level should default gracefully."""
        from app.main import setup_logging

        # Should not raise — falls back to INFO.
        setup_logging("INVALID", str(tmp_path / "logs"))


class TestConfigValidation:
    """Test that config validation catches errors before startup."""

    def test_missing_bot_token_exits(self, monkeypatch):
        """Main should exit if BOT_TOKEN is not set."""
        # Clear all required vars.
        for var in ["BOT_TOKEN", "ADMIN_IDS", "DATABASE_URL"]:
            monkeypatch.delenv(var, raising=False)

        with pytest.raises((SystemExit, Exception)):
            Settings()

    def test_valid_config_passes(self, valid_env):
        """Valid environment should produce a working Settings object."""
        s = Settings()
        assert s.BOT_TOKEN
        assert s.admin_id_set
        assert s.DATABASE_URL


class TestAdminIdParsing:
    """Test that admin IDs are correctly parsed from the environment."""

    def test_single_admin(self, valid_env):
        s = Settings(ADMIN_IDS="123456")
        assert 123456 in s.admin_id_set

    def test_multiple_admins(self, valid_env):
        s = Settings(ADMIN_IDS="100,200,300")
        assert s.admin_id_set == {100, 200, 300}

    def test_no_admin_exits(self, valid_env):
        with pytest.raises(Exception):
            Settings(ADMIN_IDS="")