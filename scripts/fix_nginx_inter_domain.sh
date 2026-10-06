#!/bin/bash

# This script updates Nginx configuration to handle inter/prelander domains
# Run this on your server as root or with sudo

echo "Fixing Nginx configuration for inter/prelander domain handling..."

# Backup existing Nginx config
NGINX_CONF="/etc/nginx/sites-available/default"
if [ ! -f "$NGINX_CONF" ]; then
    NGINX_CONF="/etc/nginx/nginx.conf"
fi

if [ -f "$NGINX_CONF" ]; then
    cp "$NGINX_CONF" "${NGINX_CONF}.backup.$(date +%Y%m%d_%H%M%S)"
    echo "✓ Backed up Nginx config"
fi

# Create a new server block for catch-all domains
cat > /etc/nginx/sites-available/catch-all-domains << 'EOF'
# Catch-all server block for unregistered or inter/prelander domains
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    
    # Dummy SSL certificate (replace with your actual cert)
    ssl_certificate /etc/ssl/certs/ssl-cert-snakeoil.pem;
    ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;
    
    server_name _;
    
    # Pass ALL requests to FastAPI backend
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Original-URI $request_uri;
    }
}
EOF

# Enable the catch-all config
ln -sf /etc/nginx/sites-available/catch-all-domains /etc/nginx/sites-enabled/catch-all-domains

# Test Nginx configuration
nginx -t

if [ $? -eq 0 ]; then
    echo "✓ Nginx configuration is valid"
    echo "Reloading Nginx..."
    systemctl reload nginx
    echo "✓ Nginx reloaded successfully"
    echo ""
    echo "Now restart your FastAPI backend:"
    echo "  pm2 restart ppc-backend"
    echo "  OR"
    echo "  systemctl restart ppc-backend"
else
    echo "✗ Nginx configuration has errors. Please fix them manually."
    exit 1
fi
