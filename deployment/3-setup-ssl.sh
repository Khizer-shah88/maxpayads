#!/bin/bash
# ============================================================================
# Step 3: Install Cloudflare Origin Certificate
# ----------------------------------------------------------------------------
# nginx.prod.conf terminates TLS with a Cloudflare Origin certificate at:
#   /etc/ssl/certs/origin.crt   <-  deployment/certs/origin.crt
#   /etc/ssl/private/origin.key <-  deployment/certs/origin.key
#
# Generate the cert in the Cloudflare dashboard:
#   SSL/TLS -> Origin Server -> Create Certificate
#   - Include ALL hostnames served here:
#       maxpayads.com, *.maxpayads.com,
#       browsmac.org, *.browsmac.org,
#       clickspot.icu, *.clickspot.icu,
#       clickfilesetup.info, *.clickfilesetup.info,
#       rydestudio.info, *.rydestudio.info
#   - Copy the certificate  -> deployment/certs/origin.crt
#   - Copy the private key   -> deployment/certs/origin.key
# Then set the Cloudflare SSL/TLS mode to "Full (strict)" for each domain.
#
# Usage:
#   1) Place origin.crt and origin.key in deployment/certs/  (scp or paste)
#   2) bash deployment/3-setup-ssl.sh
# ============================================================================
set -e

APP_DIR="/home/deploy/maxpayads"
CERT_DIR="$APP_DIR/deployment/certs"
CRT="$CERT_DIR/origin.crt"
KEY="$CERT_DIR/origin.key"

echo "========================================="
echo "  Cloudflare Origin Certificate — install"
echo "========================================="

mkdir -p "$CERT_DIR"

if [ ! -f "$CRT" ] || [ ! -f "$KEY" ]; then
  echo "ERROR: certificate files not found."
  echo "  Expected:"
  echo "    $CRT"
  echo "    $KEY"
  echo ""
  echo "  Create them in the Cloudflare dashboard (SSL/TLS -> Origin Server),"
  echo "  then copy both files into deployment/certs/ and re-run this script."
  echo "  See deployment/certs/README.md for details."
  exit 1
fi

# ── Validate the certificate/key are readable and match ──────────────────────
if ! openssl x509 -in "$CRT" -noout >/dev/null 2>&1; then
  echo "ERROR: $CRT is not a valid PEM certificate."
  exit 1
fi
if ! openssl pkey -in "$KEY" -noout >/dev/null 2>&1; then
  echo "ERROR: $KEY is not a valid PEM private key."
  exit 1
fi

CRT_MOD=$(openssl x509 -in "$CRT" -noout -modulus 2>/dev/null | openssl md5)
KEY_MOD=$(openssl pkey -in "$KEY" -noout -modulus 2>/dev/null | openssl md5)
if [ "$CRT_MOD" != "$KEY_MOD" ]; then
  echo "ERROR: origin.crt and origin.key do not match (modulus mismatch)."
  exit 1
fi

# ── Lock down permissions on the private key ─────────────────────────────────
chmod 644 "$CRT"
chmod 600 "$KEY"

echo "Certificate valid. Covered hostnames:"
openssl x509 -in "$CRT" -noout -text | grep -A1 "Subject Alternative Name" | tail -1 | sed 's/^/  /'

# ── Reload nginx if the stack is running, otherwise just report ready ─────────
cd "$APP_DIR"
if docker ps --format '{{.Names}}' | grep -q '^ppc_nginx$'; then
  echo "Reloading nginx..."
  docker exec ppc_nginx nginx -t && docker exec ppc_nginx nginx -s reload
  echo "nginx reloaded with new certificate."
else
  echo "nginx not running yet — cert is in place for the next 'docker compose up'."
fi

echo ""
echo "========================================="
echo "  Origin certificate installed."
echo "  Set Cloudflare SSL/TLS mode to 'Full (strict)'."
echo "========================================="
