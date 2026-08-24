#!/bin/bash
# ============================================================================
# Step 2: Deploy Application (Run as 'deploy' user on the server)
# Usage: bash 2-deploy.sh
# ============================================================================
set -e

APP_DIR="/home/deploy/maxpayads"
cd "$APP_DIR"

echo "========================================="
echo "  Max Pay Ads — Deploying"
echo "========================================="

# ── Preflight: required files must exist ─────────────────────────────────────
# These are bind-mounted into containers. If a source file is missing, Docker
# would create a DIRECTORY in its place and break the container — so fail early.
missing=0

if [ ! -f "$APP_DIR/.env.production" ]; then
  echo "ERROR: .env.production not found!"
  echo "  Copy it first: scp deployment/.env.production deploy@SERVER:~/maxpayads/"
  missing=1
fi

if [ ! -f "$APP_DIR/deployment/certs/origin.crt" ] || [ ! -f "$APP_DIR/deployment/certs/origin.key" ]; then
  echo "ERROR: Cloudflare origin cert/key missing in deployment/certs/"
  echo "  Run: bash deployment/3-setup-ssl.sh   (see deployment/certs/README.md)"
  missing=1
fi

if [ ! -f "$APP_DIR/ppc-backend/GeoLite2-Country.mmdb" ]; then
  echo "ERROR: GeoLite2-Country.mmdb missing in ppc-backend/"
  echo "  Download from MaxMind (free) and place it at ppc-backend/GeoLite2-Country.mmdb"
  echo "  See deployment/README.md."
  missing=1
fi

if [ "$missing" -ne 0 ]; then
  echo ""
  echo "Aborting — provide the files above and re-run."
  exit 1
fi

echo "Validating Compose configuration..."
docker compose -f docker-compose.prod.yml config >/dev/null

# ── Copy .env.production into backend .env ───────────────────────────────────
cp "$APP_DIR/.env.production" "$APP_DIR/ppc-backend/.env"
chmod 600 "$APP_DIR/ppc-backend/.env"

# ── Create uploads directory ─────────────────────────────────────────────────
mkdir -p "$APP_DIR/ppc-backend/uploads"

# ── Build and start all containers ───────────────────────────────────────────
echo "Building Docker images..."
docker compose -f docker-compose.prod.yml up -d --build --remove-orphans

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

  echo "$label: not ready after $(($attempts * 5)) seconds"
  return 1
}

# ── Check health ─────────────────────────────────────────────────────────────
echo ""
echo "--- Container Status ---"
docker compose -f docker-compose.prod.yml ps

echo ""
echo "--- Health Check ---"
wait_for_http http://localhost/health "Backend"
wait_for_http http://localhost "Frontend"

echo ""
echo "========================================="
echo "  Deployment complete!"
echo "  Access: http://YOUR_SERVER_IP"
echo "  Admin:  http://YOUR_SERVER_IP/admin/auth"
echo ""
echo "  Useful commands:"
echo "  docker compose -f docker-compose.prod.yml logs -f"
echo "  docker compose -f docker-compose.prod.yml restart"
echo "  docker compose -f docker-compose.prod.yml down"
echo "========================================="
