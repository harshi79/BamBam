"""
YoriNetflix — Centralized configuration.

All settings are loaded from environment variables.
Required values cause a startup failure if missing.
Optional values have documented defaults.

Usage:
    from app.config import settings
    print(settings.BOT_TOKEN)
"""

from __future__ import annotations

from pathlib import Path
from typing import Set

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables.

    Environment variable names match the field names below (case-insensitive).
    A .env file in the project root is also loaded automatically.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Required: Telegram ──────────────────────────────────────
    BOT_TOKEN: str
    """Telegram Bot API token. No default — must be set."""

    ADMIN_IDS: str
    """Comma-separated Telegram user IDs with admin privileges.
    Example: "123456789,987654321"
    No default — must be set explicitly."""

    # ── Required: Database ──────────────────────────────────────
    DATABASE_URL: str
    """Neon PostgreSQL connection string.
    Example: "postgresql://user:pass@host:5432/dbname?sslmode=require"
    No default — must be set explicitly."""

    # ── Optional: Force Subscription ────────────────────────────
    FORCE_CHANNEL: str = ""
    """Channel username (without @) for force-subscription checks.
    Empty string disables FSUB."""

    FORCE_CHANNEL_URL: str = ""
    """Invite link shown in the Join Channel button.
    Required when FORCE_CHANNEL is set."""

    # ── Optional: Welcome ───────────────────────────────────────
    START_VIDEO_URL: str = ""
    """URL of the welcome video. Empty = text-only welcome."""

    # ── Optional: Limits ────────────────────────────────────────
    COOLDOWN_SECONDS: int = 120
    """Seconds between generations per user."""

    DAILY_GENERATION_LIMIT: int = 5
    """Maximum generations per user per UTC day."""

    DAILY_REWARD_POINTS: int = 10
    """Points awarded for daily reward claim."""

    REFERRAL_REWARD_POINTS: int = 25
    """Points awarded per successful referral."""

    POINTS_PER_GENERATION: int = 0
    """Points earned per generation (0 = no points for generating)."""

    # ── Optional: Throttle ──────────────────────────────────────
    THROTTLE_RATE: float = 0.5
    """Minimum seconds between actions per user (anti-spam)."""

    # ── Optional: FSUB Behavior ─────────────────────────────────
    FSUB_FAIL_OPEN: bool = False
    """If True, allow users through when membership check errors.
    Default False (fail-closed) — safer for production."""

    # ── Optional: Pagination ────────────────────────────────────
    PAGE_SIZE: int = 12
    """Items per page in country selection and history."""

    # ── Optional: Logging ───────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    """Python logging level (DEBUG, INFO, WARNING, ERROR)."""

    LOG_DIR: str = "logs"
    """Directory for log files."""

    BACKUP_DIR: str = "backups"
    """Directory for database backup files."""

    # ── Derived properties ──────────────────────────────────────

    @property
    def admin_id_set(self) -> Set[int]:
        """Parse ADMIN_IDS into a set of integer Telegram user IDs."""
        raw = self.ADMIN_IDS.strip()
        if not raw:
            return set()
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        result: Set[int] = set()
        for p in parts:
            try:
                result.add(int(p))
            except ValueError:
                raise ValueError(
                    f"Invalid ADMIN_ID value: '{p}' is not an integer. "
                    f"ADMIN_IDS must be comma-separated integers."
                )
        return result

    @property
    def db_pool_min(self) -> int:
        """Minimum database connection pool size."""
        return 1

    @property
    def db_pool_max(self) -> int:
        """Maximum database connection pool size."""
        return 5

    # ── Validators ──────────────────────────────────────────────

    @field_validator("BOT_TOKEN")
    @classmethod
    def validate_bot_token(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "BOT_TOKEN is required. "
                "Get one from https://t.me/BotFather"
            )
        token = v.strip()
        # Basic Telegram bot token format: digits:alphanumeric
        if ":" not in token:
            raise ValueError(
                "BOT_TOKEN appears malformed. "
                "Expected format: '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11'"
            )
        return token

    @field_validator("ADMIN_IDS")
    @classmethod
    def validate_admin_ids_raw(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "ADMIN_IDS is required. "
                "Set at least one Telegram user ID (comma-separated)."
            )
        return v.strip()

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError(
                "DATABASE_URL is required. "
                "Use a Neon PostgreSQL connection string."
            )
        url = v.strip()
        if not url.startswith(("postgresql://", "postgres://")):
            raise ValueError(
                "DATABASE_URL must start with 'postgresql://' or 'postgres://'."
            )
        return url

    @field_validator("COOLDOWN_SECONDS")
    @classmethod
    def validate_cooldown(cls, v: int) -> int:
        if v < 0:
            raise ValueError("COOLDOWN_SECONDS must be >= 0.")
        return v

    @field_validator("DAILY_GENERATION_LIMIT")
    @classmethod
    def validate_daily_limit(cls, v: int) -> int:
        if v < 0:
            raise ValueError("DAILY_GENERATION_LIMIT must be >= 0 (0 = unlimited).")
        return v

    @field_validator("DAILY_REWARD_POINTS", "REFERRAL_REWARD_POINTS")
    @classmethod
    def validate_points_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Point values must be >= 0.")
        return v

    @model_validator(mode="after")
    def validate_fsub_consistency(self) -> "Settings":
        """When FORCE_CHANNEL is set, FORCE_CHANNEL_URL should also be set."""
        if self.FORCE_CHANNEL and not self.FORCE_CHANNEL_URL:
            raise ValueError(
                "FORCE_CHANNEL is set but FORCE_CHANNEL_URL is empty. "
                "Users need an invite link to join the channel."
            )
        return self