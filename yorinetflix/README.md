# YoriNetflix

A polished, production-ready Telegram bot for distributing Netflix accounts with user profiles, daily rewards, referral earnings, and comprehensive admin controls.

## Features

- **Account Distribution** — Paginated country selection, random inventory pick, instant delivery.
- **Force Subscription** — Channel membership verification with configurable fail-closed behavior.
- **User Profiles** — Generation history, unique countries, cooldown tracking.
- **Daily Rewards** — Configurable daily point claims with UTC-based reset.
- **Referral System** — Unique referral links, anti-self-referral constraints, automatic reward crediting.
- **Daily Limits** — Per-user generation caps independent of cooldowns.
- **Admin Tools** — Inventory management, statistics, broadcasting, backup, export.
- **Rate Limiting** — Throttle middleware to prevent spam and abuse.

## Tech Stack

- **Language:** Python 3.11+
- **Telegram Framework:** aiogram v3
- **Database:** PostgreSQL (Neon)
- **Driver:** asyncpg

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

## Project Structure

```
yorinetflix/
├── app/
│   ├── main.py                    # Entry point
│   ├── config.py                  # Settings from environment
│   ├── handlers/                  # Telegram command & callback handlers
│   ├── keyboards/                 # Inline keyboard builders
│   ├── services/                  # Business logic (stateless)
│   ├── database/
│   │   ├── connection.py          # asyncpg pool management
│   │   ├── repository.py          # Data access queries  (Phase 3)
│   │   └── migrations/            # SQL migration files + runner
│   ├── middleware/                 # Throttle, logging middleware
│   └── utils/                     # Text formatting, constants
├── tests/                         # Unit & integration tests
├── scripts/                       # Maintenance scripts
├── requirements.txt               # Production dependencies
├── requirements-dev.txt           # Dev/test dependencies
├── .env.example                   # Documented env template
└── README.md
```

## Admin Commands

| Command | Description |
|---|---|
| `/add` | Add cookies (reply to .txt or inline text) |
| `/stats` | Bot statistics |
| `/stock` | Inventory breakdown by country |
| `/export [country]` | Export cookies to file |
| `/backup` | Download database snapshot |
| `/broadcast` | Send message to all users |
| `/clear_country <name>` | Remove inventory for one country |
| `/wipe CONFIRM` | Delete all inventory |
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