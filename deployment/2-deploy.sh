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

# Portal hostnames for the Next.js middleware gate. The first entry is used
# as the Host header for the frontend health check below — probes to
# http://localhost would otherwise be 404'd by the portal-hostname gate.
export PORTAL_HOSTNAMES="${PORTAL_HOSTNAMES:-maxpayads.com,www.maxpayads.com,vertexmonetize.com,www.vertexmonetize.com}"
FRONTEND_PROBE_HOST="${PORTAL_HOSTNAMES%%,*}"

# ── Create uploads directory ─────────────────────────────────────────────────
mkdir -p "$APP_DIR/ppc-backend/uploads"

# ── Validate Compose ─────────────────────────────────────────────────────────
echo "Validating Docker Compose configuration..."

docker compose -f docker-compose.prod.yml config >/dev/null

echo "Docker Compose configuration: OK"

# ── Build and start containers ───────────────────────────────────────────────
echo "Building Docker images..."

docker compose -f docker-compose.prod.yml up -d --build --remove-orphans

# ── Force nginx restart with new configuration ─────────────────────────────────
echo "Restarting nginx to ensure new configuration is loaded..."
docker compose -f docker-compose.prod.yml restart nginx
sleep 5

# ── Verify nginx is using new configuration ────────────────────────────────────
echo "Testing nginx configuration..."
if docker exec ppc_nginx nginx -t; then
  echo "nginx configuration: VALID"
else
  echo "nginx configuration: INVALID - deployment will likely fail"
fi

# ── Wait for services to be fully ready ────────────────────────────────────────
echo "Waiting for services to initialize..."
echo "FastAPI initialization can take up to 60 seconds due to database seeding and ML model training..."
sleep 30

# ── HTTP health check ─────────────────────────────────────────────────────────
wait_for_http() {
  local url="$1"
  local label="$2"
  local attempts=24  # Reduced from 36 (2 minutes instead of 3)
  local i=1

  echo "Waiting for $label..."
  echo "Testing URL: $url"

  while [ "$i" -le "$attempts" ]; do
    echo "  Attempt $i/$attempts..."
    
    # Test with verbose output for first few attempts
    if [ "$i" -le 3 ]; then
      if curl -fsS -m 10 "$url" >/dev/null; then
        echo "$label: OK"
        return 0
      else
        echo "  Test failed, checking nginx and fastapi status..."
        
        # Quick diagnostic checks
        echo "  nginx status: $(docker exec ppc_nginx ps aux | grep nginx | wc -l) processes"
        echo "  fastapi response: $(docker exec ppc_fastapi curl -s http://localhost:8000/health 2>/dev/null | head -c 50 || echo 'FAILED')"
        echo "  nginx -> fastapi: $(docker exec ppc_nginx curl -s http://fastapi:8000/health 2>/dev/null | head -c 50 || echo 'FAILED')"
      fi
    else
      # Silent attempts after first 3
      if curl -fsS -m 10 "$url" >/dev/null 2>&1; then
        echo "$label: OK"
        return 0
      fi
    fi

    i=$((i + 1))
    sleep 5
  done

  echo "$label: NOT READY after $(($attempts * 5)) seconds (2 minutes)"
  
  # Final diagnostic on failure
  echo ""
  echo "=== FINAL DIAGNOSTIC ==="
  echo "Container status:"
  docker compose -f docker-compose.prod.yml ps | head -10
  echo ""
  echo "  nginx error logs:"
  docker logs ppc_nginx --tail 5 2>/dev/null || echo "Cannot fetch nginx logs"
  echo ""
  echo "  FastAPI logs:"  
  docker logs ppc_fastapi --tail 10 2>/dev/null || echo "Cannot fetch FastAPI logs"
  echo ""
  echo "  FastAPI container inspection:"
  docker exec ppc_fastapi ps aux 2>/dev/null || echo "Cannot inspect FastAPI container"
  echo ""
  echo "  FastAPI port check:"
  docker exec ppc_fastapi netstat -tlnp 2>/dev/null | grep :8000 || echo "Port 8000 not listening"
  echo ""
  echo "Direct health check tests:"
  echo "  FastAPI direct: $(docker exec ppc_fastapi curl -s -m 5 http://localhost:8000/health 2>/dev/null || echo 'TIMEOUT')"
  echo "  nginx->FastAPI: $(docker exec ppc_nginx curl -s -m 5 http://fastapi:8000/health 2>/dev/null || echo 'TIMEOUT')"
  echo "  External: $(curl -s -m 5 http://localhost/health 2>/dev/null || echo 'TIMEOUT')"
  
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
# Probe through nginx with a portal hostname — the Next.js portal gate only
# serves portal pages for hosts in PORTAL_HOSTNAMES, and localhost isn't one.
if curl -fsS --resolve "${FRONTEND_PROBE_HOST}:80:127.0.0.1" "https://${FRONTEND_PROBE_HOST}" >/dev/null 2>&1; then
  echo "Frontend: OK"
else
  # Fallback: retry with plain http via the resolve trick
  if curl -fsS --resolve "${FRONTEND_PROBE_HOST}:80:127.0.0.1" "http://${FRONTEND_PROBE_HOST}" >/dev/null 2>&1; then
    echo "Frontend: OK"
  else
    echo "Frontend: NOT READY after probing http://${FRONTEND_PROBE_HOST} (and https)"
    exit 1
  fi
fi

echo ""
echo "========================================="
echo "  Deployment complete!"
echo "========================================="