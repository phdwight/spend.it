# syntax=docker/dockerfile:1.6
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    SPENDIT_DB_PATH=/data/spendit.db \
    APP_PORT=61700

WORKDIR /app

COPY requirements.txt ./
RUN pip install -r requirements.txt

COPY app ./app

# Persistent volume for the SQLite database.
RUN mkdir -p /data
VOLUME ["/data"]

# Run as a non-root user.
RUN useradd --create-home --uid 1000 spendit \
    && chown -R spendit:spendit /app /data
USER spendit

# Documentation only — the actual listening port is APP_PORT (default 61700).
EXPOSE 61700

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import os,sys,urllib.request;\
sys.exit(0 if urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"APP_PORT\"]}/api/health',timeout=3).status==200 else 1)"

# Shell form so $APP_PORT is expanded at container start.
CMD uvicorn app.main:app --host 0.0.0.0 --port "$APP_PORT"
