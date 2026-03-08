#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/aiweb/backend}"
ENV_FILE="${ENV_FILE:-$APP_DIR/.env.production}"
PYTHON_BIN="${PYTHON_BIN:-$APP_DIR/.venv/bin/python}"

cd "$APP_DIR"
export AIWEB_ENV_FILE="$ENV_FILE"

exec "$PYTHON_BIN" -m db.run_schema
