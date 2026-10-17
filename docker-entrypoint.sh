#!/bin/sh
# YoriNetflix / BamBam — container entrypoint.
# Picks the right bot for the configured environment:
#   1. YoriNetflix production app (yorinetflix/) when its required settings exist
#   2. otherwise the standalone bot (main.py)
set -e

if [ -z "${BOT_TOKEN:-}" ]; then
    echo "ERROR: BOT_TOKEN is not set. Add your Telegram bot token and redeploy." >&2
    exit 1
fi

if [ -n "${ADMIN_IDS:-}" ] && [ -n "${DATABASE_URL:-}" ]; then
    echo "==> Starting YoriNetflix production app (yorinetflix/)"
    cd /app/yorinetflix
    exec python -m app.main
fi

echo "==> Starting standalone bot (main.py)"
cd /app
exec python main.py
