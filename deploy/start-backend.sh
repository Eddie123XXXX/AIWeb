#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/aiweb/backend}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"

cd "$APP_DIR"

export AIWEB_ENV_FILE="$ENV_FILE"

exec "$PYTHON_BIN" -m uvicorn main:app \
  --host "${HOST:-127.0.0.1}" \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
