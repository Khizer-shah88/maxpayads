#!/bin/bash
# ============================================================================
# Update/Redeploy Script (Run after pushing code changes)
# Usage: bash 5-update.sh
# ============================================================================
set -e

APP_DIR="/home/deploy/maxpayads/fahad"
cd "$APP_DIR"

echo "========================================="
echo "  Max Pay Ads — Updating"
echo "========================================="

# ── Pull latest code ─────────────────────────────────────────────────────────
git pull origin main

# ── Export entry guard env vars so docker-compose picks them up ──────────────
ENV_FILE="$APP_DIR/deployment/.env.production"
if [ -f "$ENV_FILE" ]; then
  set -o allexport
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +o allexport
fi

# ── Rebuild and restart ──────────────────────────────────────────────────────
echo "Rebuilding containers..."
docker compose -f docker-compose.prod.yml build

echo "Restarting services..."
docker compose -f docker-compose.prod.yml up -d

# ── Cleanup old images ───────────────────────────────────────────────────────
docker image prune -f

echo ""
echo "--- Container Status ---"
docker compose -f docker-compose.prod.yml ps

echo ""
echo "========================================="
echo "  Update complete!"
echo "========================================="
