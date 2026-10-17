# BamBam / YoriNetflix — container image
# The deploy platform builds from the repository root and requires `Dockerfile` here.
#
# Runtime selection (see docker-entrypoint.sh):
#   - YoriNetflix production app (yorinetflix/) when BOT_TOKEN, ADMIN_IDS and
#     DATABASE_URL are all set
#   - otherwise the standalone bot (main.py)
#
# Multi-stage-free slim build with cached dependency layer.

FROM python:3.11-slim

# Prevent Python from buffering stdout/stderr (important for logging).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first (layer caching).
#   requirements-standalone.txt -> root main.py (aiogram, aiosqlite)
#   requirements-yorinetflix.txt -> yorinetflix/ production app
COPY requirements.txt ./requirements-standalone.txt
COPY yorinetflix/requirements.txt ./requirements-yorinetflix.txt
RUN pip install -r requirements-standalone.txt -r requirements-yorinetflix.txt

# Copy application code.
COPY main.py ./
COPY yorinetflix/ ./yorinetflix/
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Run as non-root user for security; own /app so the bots can write
# their SQLite database, logs and backups at runtime.
RUN useradd --create-home appuser \
    && chown -R appuser:appuser /app
USER appuser

# Default command.
CMD ["docker-entrypoint.sh"]
