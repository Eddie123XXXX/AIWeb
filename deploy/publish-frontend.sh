#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="${FRONTEND_DIR:-/opt/aiweb/frontend}"
TARGET_DIR="${TARGET_DIR:-/var/www/aiweb/current}"

cd "$FRONTEND_DIR"
npm ci
npm run build

mkdir -p "$TARGET_DIR"
rsync -av --delete dist/build/ "$TARGET_DIR"/
