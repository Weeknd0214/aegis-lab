#!/usr/bin/env bash
# Build HSAP frontend from platform/web/ → platform/ui-hsap/dist/
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "[web] Installing dependencies..."
cd "$ROOT/platform/web"
npm ci --silent

echo "[web] Building..."
npm run build

DIST="$ROOT/platform/ui-hsap/dist"
rm -rf "$DIST/annotate"

echo "[web] Build complete → $DIST"
ls -lh "$DIST/index.html" "$DIST/assets/" | head -8
