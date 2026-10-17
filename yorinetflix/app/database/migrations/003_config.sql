-- ═══════════════════════════════════════════════════════════════
-- YoriNetflix — Migration 003: Runtime configuration table
-- ═══════════════════════════════════════════════════════════════
-- Stores configurable settings that can be changed at runtime
-- without redeployment. These override or supplement env vars.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS bot_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed default values (won't overwrite if already present).
INSERT INTO bot_config (key, value) VALUES
    ('daily_reward_points',     '10'),
    ('referral_reward_points',  '25'),
    ('daily_generation_limit',  '5'),
    ('cooldown_seconds',        '120'),
    ('points_per_generation',   '0')
ON CONFLICT (key) DO NOTHING;