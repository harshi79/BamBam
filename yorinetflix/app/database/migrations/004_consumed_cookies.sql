-- ═══════════════════════════════════════════════════════════════
-- YoriNetflix — Migration 004: Soft-consumed inventory
-- ═══════════════════════════════════════════════════════════════
-- Delivered accounts used to be DELETEd from `cookies` inside the same
-- transaction that recorded them in `generation_history.cookie_id`.
-- Because the row was already gone, the INSERT violated
--   generation_history_cookie_id_fkey (cookie_id REFERENCES cookies(id))
-- and rolled back every generation:
--   ForeignKeyViolationError: Key (cookie_id)=(N) is not present in table "cookies".
--
-- Delivered accounts are now marked `consumed_at` instead of deleted, so
-- generation_history.cookie_id can reference the exact account that was
-- handed out.  Stock queries only count rows WHERE consumed_at IS NULL.
-- Admin wipes (/clear_country, /wipe) still hard-delete rows; the FK's
-- ON DELETE SET NULL keeps history intact when that happens.
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE cookies ADD COLUMN IF NOT EXISTS consumed_at TIMESTAMPTZ;

-- Stock lookups and random allocation only ever want undelivered accounts.
CREATE INDEX IF NOT EXISTS idx_cookies_available
    ON cookies (country)
    WHERE consumed_at IS NULL;
