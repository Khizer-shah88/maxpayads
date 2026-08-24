#!/bin/bash
# ============================================================================
# Step 2: Deploy Application
# ============================================================================
set -e

APP_DIR="/home/deploy/maxpayads/fahad"
cd "$APP_DIR"

echo "========================================="
echo "  Max Pay Ads — Deploying"
echo "========================================="

# ── Preflight ────────────────────────────────────────────────────────────────
missing=0

ENV_FILE="$APP_DIR/deployment/.env.production"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: deployment/.env.production not found!"
  echo "This file must exist on the VPS and is intentionally excluded from Git."
  missing=1
fi

if [ ! -f "$APP_DIR/deployment/certs/origin.crt" ] || \
   [ ! -f "$APP_DIR/deployment/certs/origin.key" ]; then
  echo "ERROR: Cloudflare origin cert/key missing in deployment/certs/"
  missing=1
fi

if [ ! -f "$APP_DIR/ppc-backend/GeoLite2-Country.mmdb" ]; then
  echo "ERROR: GeoLite2-Country.mmdb missing in ppc-backend/"
  missing=1
fi

if [ "$missing" -ne 0 ]; then
  echo ""
  echo "Aborting — required production files are missing."
  exit 1
fi

echo "Required production files: OK"

# ── Copy production environment ─────────────────────────────────────────────
echo "Preparing backend environment..."

cp "$ENV_FILE" "$APP_DIR/ppc-backend/.env"
chmod 600 "$APP_DIR/ppc-backend/.env"

# ── Create uploads directory ─────────────────────────────────────────────────
mkdir -p "$APP_DIR/ppc-backend/uploads"

# ── Validate Compose ─────────────────────────────────────────────────────────
echo "Validating Docker Compose configuration..."

docker compose -f docker-compose.prod.yml config >/dev/null

echo "Docker Compose configuration: OK"

# ── Build and start containers ───────────────────────────────────────────────
echo "Building Docker images..."

docker compose -f docker-compose.prod.yml up -d --build --remove-orphans

# ── HTTP health check ─────────────────────────────────────────────────────────
wait_for_http() {
  local url="$1"
  local label="$2"
  local attempts=36
  local i=1

  echo "Waiting for $label..."

  while [ "$i" -le "$attempts" ]; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$label: OK"
      return 0
    fi

    i=$((i + 1))
    sleep 5
  done

  echo "$label: NOT READY after $(($attempts * 5)) seconds"
  return 1
}

# ── Container status ─────────────────────────────────────────────────────────
echo ""
echo "--- Container Status ---"

docker compose -f docker-compose.prod.yml ps

# ── Health checks ────────────────────────────────────────────────────────────
echo ""
echo "--- Health Check ---"

wait_for_http "http://localhost/health" "Backend"
wait_for_http "http://localhost" "Frontend"

echo ""
echo "========================================="
echo "  Deployment complete!"
echo "========================================="