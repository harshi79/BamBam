# YoriNetflix — Phase 1: Code Audit & Rebuild Plan

**Repository:** `harshi79/BamBam`
**Audit Date:** 2026-10-17
**Source Commit:** `922be09` (single commit, main branch)
**File:** `main.py` — 1,190 lines, single monolithic module
**License:** AGPL-3.0

---

## 1. Existing Feature Inventory

### 1.1 User-Facing Commands & Flows

| Command / Callback | Behavior | Status |
|---|---|---|
| `/start` | Upserts user → FSUB check → sends video welcome with caption + inline keyboard | ✅ Works |
| `check_join` callback | Re-verifies FSUB membership, edits to welcome screen on success | ✅ Works |
| `menu` callback | Edits message back to welcome text + main menu | ✅ Works |
| `gen:{page}` callback | Paginated country selection (12 per page), shows stock counts | ✅ Works |
| `pick:{country}` callback | Cooldown check → random cookie fetch → DELETE + deliver account → log history | ✅ Works |
| `profile` callback / `/profile` | Shows user name, ID, join date, total generated, unique countries, cooldown timer | ✅ Works |
| `history:{page}` callback / `/history` | Paginated generation history (10 per page) with timestamps | ✅ Works |
| `/top` | Leaderboard of top 10 generators with medal emojis | ✅ Works |
| Fallback handler | Responds to any unhandled text with help hint + menu button | ✅ Works |

### 1.2 Admin Commands

| Command | Behavior |
|---|---|
| `/add` | Parses cookie text from reply (text or .txt file) or inline args. Bulk parsing with duplicate detection via SHA-256 hash. |
| `/stats` | Full bot statistics: stock counts, user counts, generation stats (24h/7d), top 5 countries. |
| `/stock` | Per-country stock breakdown. |
| `/export [country]` | Exports raw cookie text to .txt file (all or filtered by country). |
| `/backup` | SQLite database backup via `aiosqlite.backup()`. |
| `/broadcast` | Reply-based broadcast to all users with progress updates, rate-limit handling. |
| `/clear_country <name>` | Delete all cookies for a specific country. |
| `/wipe CONFIRM` | Delete ALL cookies (requires "CONFIRM" argument). |
| `/admin` | Admin help menu listing all admin commands. |

### 1.3 Infrastructure & Middleware

| Component | Details |
|---|---|
| **ThrottleMiddleware** | In-memory per-user rate limiter (0.5s default). Blocks duplicate messages, shows "slow down" on callbacks. |
| **Small Caps (`sc()`)** | Custom Unicode small-caps transformer with regex-based protection for URLs, HTML tags, entities, and IDs. |
| **`sc_html()`** | HTML-aware variant that splits on tags before transforming. |
| **`safe_edit()`** | Graceful message editing with fallback to fresh message on media/deleted messages. Ignores "not modified" errors. |
| **`safe_answer()`** | Silently swallows TelegramBadRequest on callback answers. |
| **`esc()`** | HTML entity escaping wrapper. |
| **`admin_only`** | Decorator restricting handlers to `ADMIN_ID`. |

### 1.4 Cookie Parser & Display

- Parses structured Netflix account data from text containing: 🌍 Country, PC/Phone/TV Login URLs, 🍪 Cookie (NetflixId), 🔐 SecureNetflixId
- Supports bulk parsing (multiple `📁 Source:` blocks)
- Deduplication via SHA-256 hash of raw text with UNIQUE index
- Strips sensitive lines (URLs, cookies, separators) from the info block for display
- Builds formatted messages with `<blockquote>` for copyable cookie strings
- Provides PC/TV/Mobile login URL buttons

---

## 2. Current Architecture & Dependencies

### 2.1 File Structure

```
BamBam/
├── main.py          # Everything: config, DB, handlers, keyboards, utils, startup
├── .gitignore       # Standard Python template
└── LICENSE          # AGPL-3.0
```

**No** `requirements.txt`, `.env.example`, `README.md`, tests, or configuration files exist.

### 2.2 Python Dependencies (Inferred from Imports)

| Package | Version Constraint | Notes |
|---|---|---|
| `aiogram` | v3.x (uses `DefaultBotProperties`, `BaseMiddleware` from `aiogram`, `F` filters) | Modern async Telegram framework |
| `aiosqlite` | Any | Async SQLite driver |
| `python-dotenv` | **NOT imported** | Secrets loaded via `os.getenv()` only — requires external `.env` loading or shell export |

**Recommendation: RETAIN aiogram v3.** It is modern, actively maintained, well-documented, and already properly used here. Migrating to a different framework would add risk with no benefit.

### 2.3 Database Schema (SQLite)

```sql
CREATE TABLE cookies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    country         TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    pc_url          TEXT,
    phone_url       TEXT,
    tv_url          TEXT,
    netflix_id      TEXT,
    secure_netflix_id TEXT,
    cookie_hash     TEXT,          -- added via migration
    added_at        INTEGER,       -- added via migration
    tv_url          TEXT           -- added via migration (duplicate with above)
);
-- UNIQUE INDEX on cookie_hash
-- INDEX on country

CREATE TABLE users (
    user_id          INTEGER PRIMARY KEY,
    last_gen_time    INTEGER DEFAULT 0,
    total_generated  INTEGER DEFAULT 0,
    username         TEXT,          -- added via migration
    full_name        TEXT,          -- added via migration
    joined_at        INTEGER        -- added via migration
);

CREATE TABLE history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER,
    country        TEXT,
    generated_at   INTEGER
);
-- INDEX on user_id, generated_at
```

### 2.4 Configuration (Environment Variables)

| Variable | Default | Notes |
|---|---|---|
| `BOT_TOKEN` | `""` (empty) | **REQUIRED** — no validation |
| `ADMIN_ID` | `7728424218` | ⚠️ Hardcoded default |
| `DB_NAME` | `netflix_bot.db` | SQLite filename |
| `BACKUP_DIR` | `backups` | |
| `LOG_DIR` | `logs` | |
| `COOLDOWN_SECONDS` | `120` | |
| `FORCE_CHANNEL` | `""` | Channel username |
| `FORCE_CHANNEL_URL` | `https://t.me/+jijXk3MpjIo1NTFl` | ⚠️ Hardcoded invite link |
| `START_VIDEO_URL` | `https://imglink.cc/cdn/GMTRCTX88F.mp4` | ⚠️ External CDN dependency |

---

## 3. Bugs, Security Issues & Risks (Priority-Ordered)

### 🔴 CRITICAL — Security

| # | Issue | Impact | Recommendation |
|---|---|---|---|
| C1 | **Default ADMIN_ID hardcoded** (`7728424218`) | If `ADMIN_ID` env var is unset, anyone with this Telegram ID has admin access. Should fail loudly if not configured. | Remove default; require env var; validate on startup. |
| C2 | **No BOT_TOKEN validation** | Empty token causes silent startup failure. | Fail fast with clear error if missing. |
| C3 | **FSUB is fail-open** | If `get_chat_member()` errors (bot not admin in channel, network issues), users bypass FSUB entirely. | Change to fail-closed for production; add admin override. |
| C4 | **Export/Backup writes to disk without cleanup** | Exported .txt files and .db backups persist on ephemeral hosting. On shared hosting, other processes could read them. | Send as Telegram documents then delete immediately. |
| C5 | **`/add` downloads files to working directory** | Temp files use predictable naming (`temp_{file_id}.txt`). | Use `tempfile` module with automatic cleanup. |

### 🟠 HIGH — Reliability & Data Integrity

| # | Issue | Impact | Recommendation |
|---|---|---|---|
| H1 | **Race condition in cookie generation** | `BEGIN IMMEDIATE` on SQLite ≠ true row-level locking. On PostgreSQL, use `SELECT ... FOR UPDATE SKIP LOCKED` or similar. | Atomic SELECT+DELETE in single transaction with proper isolation. |
| H2 | **No daily generation limits** | Users can generate unlimited accounts (only cooldown prevents rapid abuse). | Implement daily limits with PostgreSQL `DATE`-based tracking. |
| H3 | **ThrottleMiddleware memory leak** | `self.last` dict grows indefinitely — never cleaned. | Use TTL cache (e.g., `cachetools.TTLCache`) or periodic cleanup. |
| H4 | **DB connection per operation** | Every handler opens and closes a new `aiosqlite.connect()`. No connection pooling. | Use async connection pool (`asyncpg` for PostgreSQL). |
| H5 | **`/backup` closes the live database** | `await src.close()` closes the bot's own database connection, potentially corrupting in-flight operations. | Use PostgreSQL logical backups (`pg_dump`) or `COPY TO`. |
| H6 | **`sqlite3`-specific syntax throughout** | `strftime('%s','now')`, `BEGIN IMMEDIATE`, `ON CONFLICT`, `PRAGMA table_info`, `sqlite_master` — all SQLite-only. | Full rewrite of SQL for PostgreSQL compatibility. |

### 🟡 MEDIUM — Functionality Gaps

| # | Issue | Impact | Recommendation |
|---|---|---|---|
| M1 | **No points/rewards system** | No daily rewards, no referral tracking, no point balance. | Implement per design in Section 6. |
| M2 | **No referral system** | No referral links, no referral tracking. | Implement per design in Section 6. |
| M3 | **No daily usage limits** | Only cooldown exists; no per-day cap on generations. | Implement per design in Section 6. |
| M4 | **Duplicate button click protection is only throttle-based** | 0.5s throttle — user can still double-tap within window. | Add per-action locks (e.g., generation in progress flag). |
| M5 | **No loading indicators** | No "please wait" feedback during generation or FSUB check. | Add `⏳ processing...` callback answers for slow operations. |
| M6 | **Hardcoded PAGE_SIZE (12) and THROTTLE_RATE (0.5)** | Not configurable via env. | Move to config. |

### 🔵 LOW — Code Quality

| # | Issue | Impact | Recommendation |
|---|---|---|---|
| L1 | **Single 1190-line file** | Unmaintainable, untestable. | Modularize per Section 4. |
| L2 | **No requirements.txt** | Cannot reproduce environment. | Create with pinned versions. |
| L3 | **No tests** | Zero test coverage. | Implement per Section 9. |
| L4 | **No type hints on most functions** | Reduces IDE support and catches fewer bugs. | Add throughout. |
| L5 | **No `.env.example`** | Onboarding friction. | Create with all variables documented. |
| L6 | **No README** | No documentation. | Create comprehensive README. |
| L7 | **Log rotation at 5MB** | Might be excessive for a small bot; also logs could leak cookie data. | Review log sanitization; ensure no secrets in logs. |

---

## 4. Proposed Modular Project Structure

```
yorinetflix/
├── app/
│   ├── __init__.py
│   ├── main.py                    # Entry point: init, startup, polling
│   ├── config.py                  # All env vars, validation, constants
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py               # /start, welcome, FSUB check/verify, menu
│   │   ├── generation.py          # Country list, pick, cooldown, delivery
│   │   ├── profile.py             # /profile, profile callback
│   │   ├── history.py             # /history, history pagination
│   │   ├── leaderboard.py         # /top
│   │   ├── rewards.py             # /daily, daily reward claim
│   │   ├── referrals.py           # /referral, referral link, referral status
│   │   └── admin.py               # All admin commands
│   ├── keyboards/
│   │   ├── __init__.py
│   │   ├── inline.py              # All InlineKeyboardMarkup builders
│   │   └── callbacks.py           # Callback data constants/prefixes
│   ├── services/
│   │   ├── __init__.py
│   │   ├── subscriptions.py       # FSUB check logic (fail-open/closed config)
│   │   ├── inventory.py           # Cookie CRUD, parsing, stock queries
│   │   ├── points.py              # Points balance, daily rewards, transactions
│   │   ├── referrals.py           # Referral tracking, reward crediting
│   │   ├── limits.py              # Daily generation limits, cooldowns
│   │   └── users.py               # User upsert, profile data aggregation
│   ├── database/
│   │   ├── __init__.py
│   │   ├── connection.py          # asyncpg pool management
│   │   ├── models.py              # Table definitions (SQL or ORM)
│   │   ├── repository.py          # Data access layer (query functions)
│   │   └── migrations/
│   │       ├── __init__.py
│   │       ├── 001_initial.sql    # Core tables
│   │       ├── 002_rewards.sql    # Points, referrals, daily claims
│   │       └── runner.py          # Migration runner
│   ├── middleware/
│   │   ├── __init__.py
│   │   └── throttle.py            # ThrottleMiddleware (TTL-cached)
│   └── utils/
│       ├── __init__.py
│       ├── text.py                # sc(), sc_html(), esc() — small-caps & escaping
│       ├── formatting.py          # Message builders (welcome, account, profile)
│       └── constants.py           # Default URLs, emoji mappings
├── tests/
│   ├── __init__.py
│   ├── conftest.py                # Fixtures: mock DB, mock bot, test users
│   ├── test_config.py
│   ├── test_inventory.py
│   ├── test_limits.py
│   ├── test_points.py
│   ├── test_referrals.py
│   ├── test_text_utils.py
│   ├── test_handlers/
│   │   ├── test_start.py
│   │   ├── test_generation.py
│   │   ├── test_profile.py
│   │   ├── test_history.py
│   │   └── test_admin.py
│   └── test_integration/
│       ├── test_full_flow.py      # End-to-end: start → generate → history
│       └── test_fsub.py           # FSUB enforcement scenarios
├── scripts/
│   ├── seed_test_data.py          # Populate DB with test cookies
│   └── sqlite_to_pg_migration.py  # One-time migration from existing SQLite
├── requirements.txt
├── requirements-dev.txt           # Test dependencies
├── .env.example
├── .gitignore                     # Enhanced (add backups/, logs/, .env, etc.)
├── Procfile                       # For Render/Railway deployment
├── Dockerfile                     # Optional containerized deployment
├── README.md
└── LICENSE
```

### Design Principles

- **Handlers** receive Telegram events, call services, format responses. No direct DB queries.
- **Services** contain business logic. Stateless — receive inputs, call repository, return results.
- **Database/Repository** is the only layer that touches PostgreSQL. All SQL lives here.
- **Keyboards** are pure functions returning `InlineKeyboardMarkup` objects.
- **Middleware** is cross-cutting (throttle, logging).
- **Config** is loaded once at import time, validated, and imported everywhere as `from app.config import settings`.

---

## 5. Proposed PostgreSQL Schema & Migration Plan

### 5.1 Target Schema (Neon PostgreSQL)

```sql
-- ═══════════════════════════════════════════
-- MIGRATION 001: Core tables (existing features)
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS users (
    user_id         BIGINT PRIMARY KEY,
    username        TEXT DEFAULT '',
    full_name       TEXT DEFAULT '',
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_gen_time   TIMESTAMPTZ,
    total_generated INTEGER NOT NULL DEFAULT 0,
    points          INTEGER NOT NULL DEFAULT 0,
    referrer_id     BIGINT REFERENCES users(user_id),
    referral_count  INTEGER NOT NULL DEFAULT 0,
    is_banned       BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE INDEX IF NOT EXISTS idx_users_referrer ON users(referrer_id);
CREATE INDEX IF NOT EXISTS idx_users_last_gen ON users(last_gen_time);

CREATE TABLE IF NOT EXISTS cookies (
    id                BIGSERIAL PRIMARY KEY,
    country           TEXT NOT NULL,
    raw_text          TEXT NOT NULL,
    pc_url            TEXT DEFAULT '',
    phone_url         TEXT DEFAULT '',
    tv_url            TEXT DEFAULT '',
    netflix_id        TEXT DEFAULT '',
    secure_netflix_id TEXT DEFAULT '',
    cookie_hash       TEXT NOT NULL,
    added_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_cookie_hash UNIQUE (cookie_hash)
);

CREATE INDEX IF NOT EXISTS idx_cookies_country ON cookies(country);
CREATE INDEX IF NOT EXISTS idx_cookies_added   ON cookies(added_at);

CREATE TABLE IF NOT EXISTS generation_history (
    id             BIGSERIAL PRIMARY KEY,
    user_id        BIGINT NOT NULL REFERENCES users(user_id),
    country        TEXT NOT NULL,
    cookie_id      BIGINT REFERENCES cookies(id),
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_history_user ON generation_history(user_id);
CREATE INDEX IF NOT EXISTS idx_history_time ON generation_history(generated_at);


-- ═══════════════════════════════════════════
-- MIGRATION 002: Rewards & referrals
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS daily_claims (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(user_id),
    claimed_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    points      INTEGER NOT NULL,
    -- Prevent duplicate claims per UTC day
    claim_date  DATE NOT NULL DEFAULT (NOW() AT TIME ZONE 'UTC')::DATE,
    CONSTRAINT uq_daily_claim UNIQUE (user_id, claim_date)
);

CREATE INDEX IF NOT EXISTS idx_claims_user_date ON daily_claims(user_id, claim_date);

CREATE TABLE IF NOT EXISTS referrals (
    id              BIGSERIAL PRIMARY KEY,
    referrer_id     BIGINT NOT NULL REFERENCES users(user_id),
    referred_id     BIGINT NOT NULL REFERENCES users(user_id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reward_credited BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT uq_referred UNIQUE (referred_id),         -- each user can only be referred once
    CONSTRAINT uq_referral_pair UNIQUE (referrer_id, referred_id),
    CONSTRAINT chk_no_self_referral CHECK (referrer_id != referred_id)
);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_id);

CREATE TABLE IF NOT EXISTS point_transactions (
    id          BIGSERIAL PRIMARY KEY,
    user_id     BIGINT NOT NULL REFERENCES users(user_id),
    amount      INTEGER NOT NULL,    -- positive = credit, negative = debit
    reason      TEXT NOT NULL,        -- 'daily_reward', 'referral_reward', 'generation', 'admin_adjust'
    reference   TEXT,                 -- e.g., referred user_id, or 'daily:2026-10-17'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ptx_user ON point_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_ptx_time ON point_transactions(created_at);


-- ═══════════════════════════════════════════
-- MIGRATION 003: Configuration table (optional)
-- ═══════════════════════════════════════════

CREATE TABLE IF NOT EXISTS bot_config (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed default config values
INSERT INTO bot_config (key, value) VALUES
    ('daily_reward_points', '10'),
    ('referral_reward_points', '25'),
    ('daily_generation_limit', '5'),
    ('cooldown_seconds', '120'),
    ('points_per_generation', '0')
ON CONFLICT (key) DO NOTHING;
```

### 5.2 Key Design Decisions

| Decision | Rationale |
|---|---|
| `TIMESTAMPTZ` everywhere | Timezone-safe; PostgreSQL stores UTC internally. |
| `UNIQUE(user_id, claim_date)` on `daily_claims` | Database-level guarantee against double claims — no race condition possible. |
| `UNIQUE(referred_id)` on `referrals` | Each user can only be referred once. |
| `CHECK (referrer_id != referred_id)` | Database-level self-referral prevention. |
| `point_transactions` ledger | Every point change is logged with reason and reference. Balance is source-of-truth on `users.points`, but can be reconciled from ledger. |
| `bot_config` table | Runtime-configurable settings without redeployment. |
| `BIGINT` for Telegram IDs | Telegram user IDs exceed 32-bit integer range. |
| `cookie_hash` UNIQUE constraint | Preserves existing deduplication behavior. |

### 5.3 Migration Strategy

1. **`scripts/sqlite_to_pg_migration.py`**: One-time script to read existing `netflix_bot.db` and INSERT all rows into PostgreSQL.
2. **`app/database/migrations/runner.py`**: Applies SQL migration files in order, tracking applied migrations in a `schema_migrations` table.
3. **Idempotent migrations**: All SQL uses `IF NOT EXISTS` / `ON CONFLICT DO NOTHING` for safe re-runs.
4. **No ORM**: Use raw SQL via `asyncpg` for performance and clarity. The queries are well-scoped enough that an ORM adds overhead without benefit.

---

## 6. Rewards, Referrals & Daily Limits Design

### 6.1 Daily Points

**Flow:**
1. User sends `/daily` or taps "Daily Reward 🎁" button.
2. Service checks if user has already claimed today (UTC date).
3. If not claimed: INSERT into `daily_claims` with `UNIQUE(user_id, claim_date)` — if concurrent request hits, the DB constraint rejects the duplicate.
4. On success: UPDATE `users.points`, INSERT into `point_transactions`, return success message with new balance.
5. If already claimed: return "Come back tomorrow!" with next-claim time.

**Defaults (proposed for your approval):**
- Daily reward: **10 points**
- Reset period: **UTC midnight** (00:00 UTC each day)
- Timezone note: Users may see "tomorrow" as different from UTC midnight. We can show "resets in X hours" to clarify.

### 6.2 Referrals

**Flow:**
1. Each user gets a referral link: `https://t.me/{bot_username}?start=ref_{user_id}`
2. When a new user starts the bot with `ref_{user_id}`:
   - Validate: referrer exists, is not the same user, new user hasn't been referred before.
   - INSERT into `referrals` table.
   - UPDATE `users.referrer_id` for the new user.
   - Credit referrer: UPDATE `users.points`, INSERT `point_transactions`, UPDATE `users.referral_count`.
3. `/referral` shows: referral link, total referrals, total points earned from referrals.

**Defaults (proposed for your approval):**
- Referral reward: **25 points** per successful referral
- Eligibility: **Immediate** on new user's first `/start`
- No tiered rewards or delayed eligibility (can be added later)

### 6.3 Daily Generation Limits

**Flow:**
1. Before generating, check how many generations the user has today (UTC).
2. Query: `SELECT COUNT(*) FROM generation_history WHERE user_id = $1 AND generated_at >= $today_start`
3. If count >= limit: reject with "Daily limit reached. Resets at midnight UTC."
4. If under limit: proceed with existing cooldown check, then generate.

**Defaults (proposed for your approval):**
- Daily limit: **5 generations per user**
- Independent of cooldown (user could hit daily limit OR cooldown first)
- Configurable via `bot_config` table or environment variable

### 6.4 Points Economy Summary

| Action | Points | Configurable? |
|---|---|---|
| Daily login reward | +10 | Yes (`daily_reward_points`) |
| Successful referral | +25 | Yes (`referral_reward_points`) |
| Account generation | 0 (proposed) | Yes (`points_per_generation`) |
| Admin adjustment | Any | Via `/give_points` admin command |

**Note:** Points are currently for tracking/rewards only. A future phase could add a points store where users spend points on premium features. This is **not** in scope for the initial rebuild unless you request it.

---

## 7. Hosting Recommendation & Limitations

### 7.1 Platform Comparison

| Platform | Persistent Worker | Free Tier | PostgreSQL Support | Sleep Behavior | Recommendation |
|---|---|---|---|---|---|
| **Render** | ✅ Worker/Background process | Free: 750 hrs/mo, **spins down after 15 min inactivity** | ✅ Neon external | Sleeps after 15 min; ~30s cold start | ⚠️ Bot goes offline during sleep |
| **Railway** | ✅ Always-on | $5 credit/mo (trial), then pay-as-you-go | ✅ Neon external | No sleep while running | ✅ Best for always-on bots |
| **Fly.io** | ✅ Always-on | 3 free VMs (shared CPU, 256MB) | ✅ Neon external | No sleep (always-on VMs) | ✅ Good free option |
| **Koyeb** | ✅ Always-on | Free nano instance | ✅ Neon external | May sleep on free tier | ⚠️ Limited |
| **Oracle Cloud Free Tier** | ✅ Always-on VM | Permanent free VM (1/8 OCPU, 1GB RAM) | ✅ Neon external or self-hosted | No sleep | ✅ Most generous, but setup is manual |
| **Vercel/Netlify** | ❌ Serverless only | N/A | N/A | Not suitable | ❌ Cannot run long-lived polling |

### 7.2 Recommendation

**Primary: Railway or Fly.io** — Both support always-on background workers on free/cheap tiers, deploy from GitHub, support environment variables, and connect reliably to Neon PostgreSQL.

**Fallback: Render** — Works but the 15-minute spin-down means the bot goes unresponsive during quiet periods. Telegram polling will simply stop. Users would see no response until the next request wakes the service (~30s delay). This is **acceptable for low-traffic bots** but not ideal.

**Alternative: Oracle Cloud Free Tier** — Best free resources (permanent VM, no sleep), but requires manual server setup and SSH-based deployment. Worth considering if you're comfortable with Linux server management.

### 7.3 Neon PostgreSQL

- Free tier: 512 MB storage, 1 project, compute hours (auto-suspend after 5 min inactivity).
- Connection string format: `postgresql://user:pass@host/db?sslmode=require`
- **Important:** Neon uses connection pooling. Use the `-pooler` endpoint for the application and the direct endpoint for migrations only.
- **Idle connections:** Neon terminates idle connections after a period. The app must handle reconnection gracefully (use `asyncpg.create_pool(min_size=1, max_size=5)` with connection recycling).

---

## 8. Phased Implementation Roadmap

### Phase 1 — Audit & Planning ✅ (This document)

**Deliverable:** Complete audit report with architecture, schema, and roadmap.

---

### Phase 2 — Project Scaffold & Config

**Scope:** Create the project structure, config module, database connection layer, and migration runner. No Telegram handlers yet.

**PR:** `feat/scaffold-project-structure`

- [ ] Create directory structure with all `__init__.py` files
- [ ] `app/config.py` — Pydantic `BaseSettings` loading from env, with validation
- [ ] `app/database/connection.py` — `asyncpg` pool init/close with Neon connection string
- [ ] `app/database/migrations/` — Migration runner + `001_initial.sql`
- [ ] `requirements.txt` and `requirements-dev.txt`
- [ ] `.env.example` with documented placeholders
- [ ] Enhanced `.gitignore`
- [ ] Basic `README.md`

**Tests:** Config validation tests (missing vars, invalid values).

---

### Phase 3 — Database Layer & Core Services

**Scope:** Repository functions for all existing tables + new schema. Core services for users, inventory, and limits.

**PR:** `feat/database-and-core-services`

- [ ] `app/database/repository.py` — All SQL queries (users, cookies, history)
- [ ] `app/services/users.py` — upsert, profile data aggregation
- [ ] `app/services/inventory.py` — cookie CRUD, parsing, stock queries, random pick + delete
- [ ] `app/services/limits.py` — cooldown check, daily generation limit check
- [ ] `app/utils/text.py` — `sc()`, `sc_html()`, `esc()` (preserved exactly)
- [ ] `app/utils/formatting.py` — Message builders (welcome, account, profile, history)
- [ ] SQLite-to-PostgreSQL migration script (`scripts/sqlite_to_pg_migration.py`)

**Tests:** Unit tests for all services (mocked DB), text utility tests, cookie parser tests.

---

### Phase 4 — User Handlers (Start, Profile, History, Leaderboard)

**Scope:** Migrate all existing user-facing handlers. Preserve exact behavior.

**PR:** `feat/user-handlers`

- [ ] `app/handlers/start.py` — `/start` with ref parameter parsing, FSUB check, video welcome
- [ ] `app/handlers/profile.py` — `/profile` + callback
- [ ] `app/handlers/history.py` — `/history` + pagination
- [ ] `app/handlers/leaderboard.py` — `/top`
- [ ] `app/keyboards/inline.py` — All keyboard builders
- [ ] `app/keyboards/callbacks.py` — Callback data constants
- [ ] `app/middleware/throttle.py` — TTL-cached throttle middleware
- [ ] `app/handlers/__init__.py` — Handler registration function

**Tests:** Handler tests with mocked services (aiogram test utilities).

---

### Phase 5 — Generation Flow & Inventory

**Scope:** The core generation workflow — country selection, cooldown enforcement, random cookie delivery.

**PR:** `feat/generation-flow`

- [ ] `app/handlers/generation.py` — Country list pagination, pick flow
- [ ] Integration with `limits.py` for cooldown + daily limit
- [ ] Integration with `inventory.py` for atomic pick-and-delete
- [ ] Preserve exact message formatting and button layout
- [ ] Duplicate-click protection on generation button

**Tests:** Integration tests for full generation flow, concurrent generation attempts, limit enforcement.

---

### Phase 6 — Rewards, Referrals & Daily Limits

**Scope:** New features — daily rewards, referral system, configurable limits.

**PR:** `feat/rewards-referrals-limits`

- [ ] `app/database/migrations/002_rewards.sql`
- [ ] `app/services/points.py` — Daily claim logic, point balance, transactions
- [ ] `app/services/referrals.py` — Referral tracking, reward crediting
- [ ] `app/handlers/rewards.py` — `/daily` command + button
- [ ] `app/handlers/referrals.py` — `/referral` command, start parameter handling
- [ ] `app/database/migrations/003_config.sql` — Runtime config table
- [ ] Wire limits into generation handler from Phase 5

**Tests:** Daily reward double-claim prevention, self-referral prevention, limit enforcement, concurrent reward claims.

---

### Phase 7 — Admin Commands

**Scope:** Migrate and enhance all admin commands.

**PR:** `feat/admin-commands`

- [ ] `app/handlers/admin.py` — All admin commands
- [ ] Preserve: `/add`, `/stats`, `/stock`, `/export`, `/backup`, `/broadcast`, `/clear_country`, `/wipe`, `/admin`
- [ ] Add: `/give_points <user_id> <amount>`, `/ban <user_id>`, `/unban <user_id>`
- [ ] Add: `/config` to view/edit runtime config
- [ ] Proper temp file handling for `/add` file downloads
- [ ] Safe backup using pg_dump or `COPY TO`
- [ ] Admin action logging

**Tests:** Admin authorization tests, cookie parsing edge cases, broadcast simulation.

---

### Phase 8 — FSUB, Polish & Hardening

**Scope:** Harden FSUB, add loading indicators, polish error handling, security review.

**PR:** `feat/fsub-polish-hardening`

- [ ] FSUB fail-closed mode (configurable)
- [ ] "⏳ processing..." callback answers for slow operations
- [ ] Proper error messages for all failure modes
- [ ] Rate limiting review and tuning
- [ ] Log sanitization (no secrets in logs)
- [ ] Connection pool health checks
- [ ] Graceful shutdown with signal handlers
- [ ] Per-action locks for generation (prevent double-submission)

**Tests:** FSUB scenarios (member, non-member, error, bot-not-admin), error handling edge cases.

---

### Phase 9 — Deployment & Documentation

**Scope:** Deployment configs, Dockerfile, CI/CD, comprehensive README.

**PR:** `feat/deployment-docs`

- [ ] `Dockerfile` (Python 3.11+ slim, non-root user)
- [ ] `Procfile` for Render/Railway
- [ ] GitHub Actions CI (lint, test on PR)
- [ ] Comprehensive `README.md` with setup, deployment, and admin guide
- [ ] `.env.example` with all variables documented
- [ ] Deployment guide for Railway/Render/Fly.io
- [ ] SQLite → PostgreSQL migration guide

---

## 9. Test Plan & Acceptance Criteria

### 9.1 Unit Tests

| Test Area | What to Verify |
|---|---|
| `test_text_utils.py` | `sc()` preserves URLs, HTML tags, entities; transforms plain text correctly; handles empty/None input |
| `test_config.py` | Missing required vars raise errors; defaults apply; validation works |
| `test_cookie_parser.py` | Parsing single cookies, bulk cookies, malformed input, missing fields |
| `test_inventory.py` | CRUD operations, deduplication, stock queries |
| `test_limits.py` | Cooldown enforcement, daily limit enforcement, UTC day boundary |
| `test_points.py` | Daily claim success/duplicate, point balance accuracy, transaction logging |
| `test_referrals.py` | Self-referral prevention, duplicate referral prevention, reward crediting |

### 9.2 Integration Tests

| Scenario | What to Verify |
|---|---|
| Full generation flow | Start → country list → pick → account delivered → history updated → cooldown active |
| FSUB enforcement | Non-member blocked → join → verify → access granted |
| Daily limit flow | Generate up to limit → next generation rejected → new UTC day → can generate again |
| Referral flow | User A refers User B → A gets points → B cannot be re-referred |
| Admin flow | Add cookies → stock shows → user generates → stats update |
| Concurrent generation | Two simultaneous requests for last cookie → only one succeeds |

### 9.3 Acceptance Criteria

- [ ] All existing commands produce identical output format (small-caps, emojis, layout)
- [ ] FSUB check works correctly (with configurable fail-open/fail-closed)
- [ ] Cooldowns are enforced server-side
- [ ] Daily limits are enforced server-side with UTC-based reset
- [ ] No duplicate daily rewards possible (DB constraint)
- [ ] No self-referrals possible (DB constraint)
- [ ] All admin commands require authorization
- [ ] No secrets in code, logs, or exported files
- [ ] PostgreSQL is the only production database (no SQLite dependency)
- [ ] Connection pooling with automatic reconnection
- [ ] Graceful shutdown on SIGTERM/SIGINT
- [ ] All tests pass

---

## 10. Questions Requiring Your Approval

### 10.1 Product Decisions

| # | Question | Options | My Recommendation |
|---|---|---|---|
| Q1 | **Daily reward amount?** | 10 points (proposed) / Your value | 10 points |
| Q2 | **Referral reward amount?** | 25 points (proposed) / Your value | 25 points |
| Q3 | **Daily generation limit?** | 5 per day (proposed) / Unlimited (keep cooldown only) / Your value | 5 per day |
| Q4 | **Should generations cost points?** | No (free, limited by count) / Yes (e.g., 5 points per generation) | No — keep it simple |
| Q5 | **Points store / spending?** | Not in Phase 1 / Add later / Define now | Not in Phase 1 |
| Q6 | **FSUB behavior on error?** | Fail-closed (block user) / Fail-open (let through) / Configurable | Configurable, default fail-closed |
| Q7 | **Bot branding name?** | "YoriNetflix" / Other | "YoriNetflix" |
| Q8 | **Welcome message content?** | Keep current text, just rebrand / Redesign | Rebrand with same structure |
| Q9 | **Keep the video welcome?** | Yes (with fallback to text) / Text only | Yes with fallback |
| Q10 | **Admin ID — hard fail if not set?** | Yes (refuse to start) / No (use default) | Hard fail — no default |
| Q11 | **Referral eligibility?** | Immediate on first /start / After first generation / After 24 hours | Immediate on /start |
| Q12 | **Which hosting platform?** | Railway / Fly.io / Render / Oracle Cloud / Your choice | Railway (simplest always-on) |

### 10.2 Technical Decisions

| # | Question | Options | My Recommendation |
|---|---|---|---|
| Q13 | **aiogram version — keep v3?** | Yes (retain) / Migrate to different framework | Keep aiogram v3 |
| Q14 | **ORM or raw SQL?** | Raw SQL (asyncpg) / SQLAlchemy / Tortoise ORM | Raw SQL with asyncpg |
| Q15 | **Config management?** | Pydantic BaseSettings / python-dotenv + dataclass / plain os.getenv | Pydantic BaseSettings |
| Q16 | **Existing SQLite data — migrate?** | Yes, write migration script / Start fresh | Your call — migration script provided either way |
| Q17 | **Points currency name?** | "Points" / "Coins" / "Stars" / Your choice | "Points" (generic) |
| Q18 | **Timezone for daily reset?** | UTC (simplest) / Configurable per-user / Configurable globally | UTC globally |
| Q19 | **Bot command menu additions?** | Add /daily, /referral, /help | Yes, plus existing commands |

### 10.3 Security Clarifications

| # | Question |
|---|---|
| Q20 | The existing `ADMIN_ID` default (`7728424218`) — is this your Telegram user ID? Should it remain as the default, or should we require it to be set via environment variable with no default? |
| Q21 | The `FORCE_CHANNEL_URL` (`https://t.me/+jijXk3MpjIo1NTFl`) — is this still the correct invite link? Should it be in the `.env`? |
| Q22 | The `START_VIDEO_URL` — is this CDN link still active and authorized? Should we host it differently? |
| Q23 | The existing cookie data — is it all authorized for distribution? Any accounts that should be excluded during migration? |

---

## Appendix A: Security Checklist for Deployment

Before going live:

- [ ] Rotate any previously exposed bot tokens
- [ ] Set `BOT_TOKEN`, `ADMIN_ID`, `DATABASE_URL` as environment variables (never in code)
- [ ] Verify `.env` is in `.gitignore`
- [ ] Confirm Neon PostgreSQL connection uses SSL (`sslmode=require`)
- [ ] Ensure bot is admin in the FSUB channel (with "Ban users" permission for member checks)
- [ ] Review all exported files are cleaned up after sending
- [ ] Verify no cookie data appears in application logs
- [ ] Test with a non-admin account to confirm admin commands are blocked
- [ ] Set up log monitoring/alerting for error rates

## Appendix B: Dependency Versions (Proposed)

```
# requirements.txt
aiogram==3.15.0
asyncpg==0.30.0
pydantic==2.10.0
pydantic-settings==2.7.0
python-dotenv==1.0.1

# requirements-dev.txt
-r requirements.txt
pytest==8.3.0
pytest-asyncio==0.24.0
pytest-cov==6.0.0
aioresponses==0.7.7
```

## Appendix C: Environment Variables

```bash
# .env.example

# === REQUIRED ===
BOT_TOKEN=your_telegram_bot_token_here
ADMIN_ID=your_telegram_user_id
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require

# === TELEGRAM ===
FORCE_CHANNEL=@your_channel_username
FORCE_CHANNEL_URL=https://t.me/+your_invite_link
START_VIDEO_URL=https://your-video-hosting-url.mp4

# === LIMITS ===
COOLDOWN_SECONDS=120
DAILY_GENERATION_LIMIT=5
DAILY_REWARD_POINTS=10
REFERRAL_REWARD_POINTS=25
POINTS_PER_GENERATION=0

# === FSUB ===
FSUB_FAIL_OPEN=false

# === THROTTLE ===
THROTTLE_RATE=0.5

# === LOGGING ===
LOG_LEVEL=INFO
```

---

*End of Phase 1 Audit Report. Awaiting review before proceeding to implementation.*