# YoriNetflix

A production-ready Telegram bot for distributing authorized digital inventory with user profiles, daily rewards, referral earnings, and comprehensive admin controls.

## Features

- **Inventory Distribution** — Paginated category selection, atomic allocation, instant delivery.
- **Force Subscription** — Channel membership verification with fail-closed behavior.
- **User Profiles** — Generation history, unique categories, cooldown tracking, point balance.
- **Daily Rewards** — Configurable daily point claims with UTC-based reset.
- **Referral System** — Unique referral links, anti-self-referral constraints, automatic reward crediting.
- **Daily Limits** — Per-user generation caps independent of cooldowns.
- **Admin Tools** — Inventory management, statistics, broadcasting, point adjustments, user bans.
- **Rate Limiting** — Throttle middleware to prevent spam and abuse.

## Tech Stack

- **Language:** Python 3.11+
- **Telegram Framework:** aiogram v3
- **Database:** PostgreSQL (Neon)
- **Driver:** asyncpg
- **Config:** Pydantic Settings

## Quick Start

### 1. Prerequisites

- Python 3.11+
- A Telegram bot token (from [@BotFather](https://t.me/BotFather))
- A Neon PostgreSQL database ([neon.tech](https://neon.tech))
- Your Telegram user ID (from [@userinfobot](https://t.me/userinfobot))

### 2. Install dependencies

```bash
cd yorinetflix
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual values
```

**Required variables:**
- `BOT_TOKEN` — Your Telegram bot token
- `ADMIN_IDS` — Comma-separated Telegram user IDs (e.g. `123456789`)
- `DATABASE_URL` — Neon PostgreSQL connection string

### 4. Run database migrations

```bash
python -m app.database.migrations.runner
```

### 5. Start the bot

```bash
python -m app.main
```

Migrations also run automatically at startup, so step 4 is optional for subsequent runs.

## Project Structure

```
yorinetflix/
├── app/
│   ├── main.py                         # Entry point, bot startup, polling
│   ├── config.py                       # Pydantic settings from env vars
│   ├── handlers/
│   │   ├── start.py                    # /start, welcome, FSUB, menu
│   │   ├── generation.py              # Country selection, account delivery
│   │   ├── profile.py                 # /profile
│   │   ├── history.py                 # /history
│   │   ├── leaderboard.py             # /top
│   │   ├── rewards.py                 # /daily, /referral
│   │   └── admin.py                   # All admin commands
│   ├── keyboards/
│   │   └── inline.py                  # All InlineKeyboardMarkup builders
│   ├── services/
│   │   ├── users.py                   # User operations
│   │   ├── inventory.py               # Inventory parsing and allocation
│   │   ├── points.py                  # Point balance and ledger
│   │   ├── referrals.py               # Referral tracking and rewards
│   │   ├── limits.py                  # Cooldowns and daily limits
│   │   └── subscriptions.py           # FSUB verification
│   ├── database/
│   │   ├── connection.py              # asyncpg pool management
│   │   ├── repositories/
│   │   │   ├── user_repo.py           # User CRUD
│   │   │   ├── inventory_repo.py      # Inventory CRUD, atomic pick
│   │   │   ├── history_repo.py        # Generation history
│   │   │   ├── rewards_repo.py        # Daily claims, referrals, ledger
│   │   │   └── config_repo.py         # Runtime config key-value
│   │   └── migrations/
│   │       ├── 001_initial.sql        # Core tables
│   │       ├── 002_rewards.sql        # Rewards and referrals
│   │       ├── 003_config.sql         # Runtime config
│   │       └── runner.py              # Migration runner
│   ├── middleware/
│   │   └── throttle.py                # Rate limiting middleware
│   └── utils/
│       ├── text.py                    # Small-caps, HTML escaping
│       └── formatting.py             # Message builders
├── tests/
│   ├── unit/                          # Pure function tests (no DB)
│   ├── integration/                   # Tests requiring PostgreSQL
│   └── conftest.py                    # Shared fixtures
├── requirements.txt
├── requirements-dev.txt
├── Dockerfile
├── Procfile
├── .env.example
└── README.md
```

## User Commands

| Command | Description |
|---|---|
| `/start` | Start the bot, optional referral parameter |
| `/daily` | Claim daily reward points |
| `/profile` | View your profile and stats |
| `/history` | View generation history |
| `/top` | Top generators leaderboard |
| `/referral` | Get your referral link |

## Admin Commands

| Command | Description |
|---|---|
| `/add` | Add inventory (reply to .txt or inline text) |
| `/stats` | Bot statistics |
| `/stock` | Inventory breakdown by category |
| `/export [category]` | Export inventory to file |
| `/broadcast` | Send message to all users |
| `/clear_country <name>` | Remove inventory for one category |
| `/wipe CONFIRM` | Delete all inventory |
| `/givepoints <id> <amount>` | Adjust user points |
| `/ban <id>` / `/unban <id>` | Ban/unban users |
| `/admin` | Admin help |

## Environment Variables

See [`.env.example`](.env.example) for the full list with descriptions.

## Development

```bash
pip install -r requirements-dev.txt
pytest tests/ -v
```

## License

[GNU AGPL v3](../LICENSE)