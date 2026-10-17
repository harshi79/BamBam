-- ═══════════════════════════════════════════════════════════════
-- YoriNetflix — Migration 002: Rewards, referrals, point ledger
-- ═══════════════════════════════════════════════════════════════
-- Adds daily reward claims, referral tracking, and a point
-- transaction ledger. All constraints prevent duplicate rewards.
-- ═══════════════════════════════════════════════════════════════

-- ─────────────────────────────────────────────────────────────
-- Daily Claims
-- One claim per user per UTC calendar day, enforced by DB.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS daily_claims (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    claimed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    points      INTEGER NOT NULL,
    claim_date  DATE NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')::DATE,
    CONSTRAINT uq_daily_claim UNIQUE (user_id, claim_date)
);

CREATE INDEX IF NOT EXISTS idx_claims_user_date
    ON daily_claims (user_id, claim_date);

-- ─────────────────────────────────────────────────────────────
-- Referrals
-- Each user can only be referred once (UNIQUE on referred_id).
-- Self-referral prevented by CHECK constraint.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS referrals (
    id              BIGSERIAL PRIMARY KEY,
    referrer_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    referred_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reward_credited BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_referred UNIQUE (referred_id),
    CONSTRAINT uq_referral_pair UNIQUE (referrer_id, referred_id),
    CONSTRAINT chk_no_self_referral CHECK (referrer_id != referred_id)
);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer
    ON referrals (referrer_id);

-- ─────────────────────────────────────────────────────────────
-- Point Transactions (Ledger)
-- Every point change is recorded. Balance can be reconciled.
-- ─────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS point_transactions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    amount      INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    reference   TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ptx_user
    ON point_transactions (user_id);

CREATE INDEX IF NOT EXISTS idx_ptx_time
    ON point_transactions (created_at);