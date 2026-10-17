# YoriNetflix — Container image
# Multi-stage build for minimal final image.

FROM python:3.11-slim AS base

# Prevent Python from buffering stdout/stderr (important for logging).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (layer caching).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code.
COPY . .

# Run as non-root user for security.
RUN useradd --create-home appuser
USER appuser

# Default command.
CMD ["python", "-m", "app.main"]