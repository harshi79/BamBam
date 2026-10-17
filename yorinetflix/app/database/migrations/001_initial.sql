-- ═══════════════════════════════════════════════════════════════
-- YoriNetflix — Migration 001: Core tables
-- ═══════════════════════════════════════════════════════════════
-- Creates the foundational tables for users, cookies/inventory,
-- and generation history. Preserves all data relationships from
-- the original SQLite schema while adding PostgreSQL best practices.
-- ═══════════════════════════════════════════════════════════════

-- Track which migrations have been applied.
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ─────────────────────────────────────────────────────────────
-- Users
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    user_id          BIGINT PRIMARY KEY,
    username         TEXT NOT NULL DEFAULT '',
    full_name        TEXT NOT NULL DEFAULT '',
    joined_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_gen_time    TIMESTAMPTZ,
    total_generated  INTEGER NOT NULL DEFAULT 0,
    points           INTEGER NOT NULL DEFAULT 0,
    referrer_id      BIGINT,
    referral_count   INTEGER NOT NULL DEFAULT 0,
    is_banned        BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_users_referrer
    ON users (referrer_id)
    WHERE referrer_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_last_gen
    ON users (last_gen_time)
    WHERE last_gen_time IS NOT NULL;

-- ─────────────────────────────────────────────────────────────
-- Cookies / Inventory
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cookies (
    id                 BIGSERIAL PRIMARY KEY,
    country            TEXT NOT NULL,
    raw_text           TEXT NOT NULL,
    pc_url             TEXT NOT NULL DEFAULT '',
    phone_url          TEXT NOT NULL DEFAULT '',
    tv_url             TEXT NOT NULL DEFAULT '',
    netflix_id         TEXT NOT NULL DEFAULT '',
    secure_netflix_id  TEXT NOT NULL DEFAULT '',
    cookie_hash        TEXT NOT NULL,
    added_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cookie_hash UNIQUE (cookie_hash)
);

CREATE INDEX IF NOT EXISTS idx_cookies_country
    ON cookies (country);

CREATE INDEX IF NOT EXISTS idx_cookies_added
    ON cookies (added_at);

-- ─────────────────────────────────────────────────────────────
-- Generation History
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS generation_history (
    id            BIGSERIAL PRIMARY KEY,
    user_id       BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    country       TEXT NOT NULL,
    cookie_id     BIGINT REFERENCES cookies(id) ON DELETE SET NULL,
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_user
    ON generation_history (user_id);

CREATE INDEX IF NOT EXISTS idx_history_time
    ON generation_history (generated_at);

-- ─────────────────────────────────────────────────────────────
-- Deferred foreign key: users.referrer_id → users.user_id
-- Added after users table exists to allow self-reference.
-- ─────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'fk_users_referrer'
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT fk_users_referrer
            FOREIGN KEY (referrer_id) REFERENCES users(user_id)
            ON DELETE SET NULL;
    END IF;
END $$;