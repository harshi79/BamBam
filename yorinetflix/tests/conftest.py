"""
YoriNetflix — Shared test fixtures.
"""

from __future__ import annotations

import os
import pytest


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure each test starts with a clean environment.

    Tests that need specific values should set them explicitly.
    """
    env_vars_to_clear = [
        "BOT_TOKEN", "ADMIN_IDS", "DATABASE_URL",
        "FORCE_CHANNEL", "FORCE_CHANNEL_URL", "START_VIDEO_URL",
        "COOLDOWN_SECONDS", "DAILY_GENERATION_LIMIT",
        "DAILY_REWARD_POINTS", "REFERRAL_REWARD_POINTS",
        "POINTS_PER_GENERATION", "THROTTLE_RATE",
        "FSUB_FAIL_OPEN", "PAGE_SIZE",
        "LOG_LEVEL", "LOG_DIR", "BACKUP_DIR",
    ]
    for var in env_vars_to_clear:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def valid_env(monkeypatch):
    """Set all required environment variables with valid defaults."""
    monkeypatch.setenv("BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
    monkeypatch.setenv("ADMIN_IDS", "111222333")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@host:5432/db?sslmode=require")