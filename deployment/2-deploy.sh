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

# Export entry guard variables from .env.production so that docker-compose
# can substitute them into the nextjs service's environment block.
# We parse the file safely instead of using `source` to avoid executing
# comment lines or values with shell metacharacters (spaces, slashes, etc.).
_load_env_safe() {
  local file="$1"
  while IFS= read -r line || [ -n "$line" ]; do
    # Skip blank lines and comments
    [[ "$line" =~ ^[[:space:]]*$ ]] && continue
    [[ "$line" =~ ^[[:space:]]*# ]] && continue
    # Must look like KEY=VALUE (KEY is alphanumeric + underscore)
    if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
      local key="${BASH_REMATCH[1]}"
      local val="${BASH_REMATCH[2]}"
      # Strip surrounding double-quotes from value if present
      if [[ "$val" =~ ^\"(.*)\"$ ]]; then
        val="${BASH_REMATCH[1]}"
      fi
      export "$key=$val"
    fi
  done < "$file"
}

_load_env_safe "$ENV_FILE"

# ── HOTFIX: Disable entry guard for public access ──────────────────────────
# Override ENTRY_SESSION_SECRET to empty to disable the entry guard system
# This allows public access to vertexmonetize.com without referrer restrictions
export ENTRY_SESSION_SECRET=""
echo "Entry guard system disabled for public access"

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