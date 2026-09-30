# Nginx Configuration for Unknown Domain Blocking

## Problem
Domains not added in the admin panel (e.g., `check4.clicklyspot.icu`) currently show a 404 error from Nginx. This reveals the server exists. 

**Goal:** Domains not in the system should receive **NO response** (connection refused/dropped), not even a 404.

## Solution

Configure Nginx to only respond to known domains and drop all other connections silently.

---

## Nginx Configuration

### Option 1: Drop Connection (Recommended)
This immediately closes the connection without any response.

```nginx
# Default server block - catches all unknown domains
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    
    # Dummy SSL certificate (required for 443, but connection will be dropped)
    ssl_certificate /etc/nginx/ssl/dummy.crt;
    ssl_certificate_key /etc/nginx/ssl/dummy.key;
    
    # Drop connection immediately for any unknown domain
    return 444;  # Nginx special code: close connection without response
}

# Your actual domains (only these will respond)
server {
    listen 80;
    listen [::]:80;
    listen 443 ssl;
    listen [::]:443 ssl;
    
    # ONLY respond to domains added in your system
    server_name anchor1.trustedbi1.com anchor2.trustedbi1.com *.clicklyspot.icu vertexmonetize.com;
    
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    
    # Your normal application proxy
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### Option 2: Silent Timeout (More Stealthy)
Makes the server appear completely offline to unauthorized domains.

```nginx
# Default server block - catches all unknown domains
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    
    ssl_certificate /etc/nginx/ssl/dummy.crt;
    ssl_certificate_key /etc/nginx/ssl/dummy.key;
    
    # Make the request hang and timeout (appears like server is offline)
    location / {
        # Delay response indefinitely until client times out
        proxy_read_timeout 1s;
        proxy_connect_timeout 1s;
        return 444;
    }
}
```

### Option 3: Return Empty Response
Returns nothing, not even a proper HTTP response.

```nginx
# Default server block
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    
    ssl_certificate /etc/nginx/ssl/dummy.crt;
    ssl_certificate_key /etc/nginx/ssl/dummy.key;
    
    # Close connection after sending nothing
    location / {
        return 444;
    }
}
```

---

## Dynamic Configuration (Automatically Update from Database)

If you want Nginx to automatically know which domains are active without manual updates, you can:

### Method 1: Generate Nginx Config from Database

Create a script that generates the `server_name` list from your database:

```python
# scripts/generate_nginx_domains.py
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings

async def get_active_domains():
    """Get all active domains from database"""
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DB_NAME]
    
    domains = await db.redirection_domains.find({
        "status": "active"
    }, {"domain": 1}).to_list(length=None)
    
    domain_list = [d["domain"] for d in domains if d.get("domain")]
    return domain_list

async def generate_nginx_config():
    """Generate Nginx server_name directive"""
    domains = await get_active_domains()
    
    # Add your admin/frontend domain
    domains.append("vertexmonetize.com")
    domains.append("www.vertexmonetize.com")
    
    server_name = " ".join(domains)
    
    config = f"""
# Auto-generated from database - DO NOT EDIT MANUALLY
# Generated: {datetime.now().isoformat()}

server {{
    listen 80;
    listen [::]:80;
    listen 443 ssl;
    listen [::]:443 ssl;
    
    # Active domains from database
    server_name {server_name};
    
    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/vertexmonetize.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vertexmonetize.com/privkey.pem;
    
    # Your application
    location / {{
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""
    
    # Write to Nginx config
    with open("/etc/nginx/sites-available/ppc-domains.conf", "w") as f:
        f.write(config)
    
    print("✅ Nginx config generated")
    print(f"📝 Active domains: {len(domains)}")

if __name__ == "__main__":
    from datetime import datetime
    asyncio.run(generate_nginx_config())
```

### Method 2: Use Nginx Map Directive (Most Flexible)

```nginx
# /etc/nginx/conf.d/domain_whitelist.conf

# Map to check if domain is allowed
map $host $allowed_domain {
    default 0;
    
    # Admin/Frontend domain
    vertexmonetize.com 1;
    www.vertexmonetize.com 1;
    
    # Your active domains (update this list from database)
    anchor1.trustedbi1.com 1;
    anchor2.trustedbi1.com 1;
    ~^.*\.clicklyspot\.icu$ 1;  # Wildcard for subdomains
}

# Default server - block unknown domains
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    
    ssl_certificate /etc/nginx/ssl/dummy.crt;
    ssl_certificate_key /etc/nginx/ssl/dummy.key;
    
    # Check if domain is allowed
    if ($allowed_domain = 0) {
        return 444;  # Drop connection
    }
    
    # If we get here, domain is allowed
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Implementation Steps

### Step 1: Create Dummy SSL Certificate

```bash
# Create directory
sudo mkdir -p /etc/nginx/ssl

# Generate dummy self-signed certificate
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/dummy.key \
  -out /etc/nginx/ssl/dummy.crt \
  -subj "/CN=localhost"
```

### Step 2: Update Main Nginx Config

Edit `/etc/nginx/sites-available/default` or your main config file:

```nginx
# /etc/nginx/sites-available/default

# BLOCK ALL UNKNOWN DOMAINS (must be first)
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    listen 443 ssl default_server;
    listen [::]:443 ssl default_server;
    
    ssl_certificate /etc/nginx/ssl/dummy.crt;
    ssl_certificate_key /etc/nginx/ssl/dummy.key;
    
    # Drop connection for any unknown domain
    return 444;
}

# ALLOW ONLY KNOWN DOMAINS
server {
    listen 80;
    listen [::]:80;
    listen 443 ssl;
    listen [::]:443 ssl;
    
    # IMPORTANT: List ONLY domains added in your system
    # Update this when adding/removing domains
    server_name 
        vertexmonetize.com 
        www.vertexmonetize.com
        anchor1.trustedbi1.com 
        anchor2.trustedbi1.com
        file2.rydemacstudio.com
        file232.rydemacstudio.com
        file2.clicksetopfile.cc
        rydemacstudio.com
        clicksetopfile.cc;
    
    # Your SSL certificate
    ssl_certificate /etc/letsencrypt/live/vertexmonetize.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/vertexmonetize.com/privkey.pem;
    
    # SSL configuration
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;
    
    # Proxy to your application
    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### Step 3: Test Configuration

```bash
# Test Nginx config for syntax errors
sudo nginx -t

# If OK, reload Nginx
sudo systemctl reload nginx
```

### Step 4: Verify

```bash
# Test unknown domain (should hang/drop)
curl http://check4.clicklyspot.icu
# Should either:
# - Hang and timeout (connection refused)
# - Close immediately with no response
# - NOT show 404 page

# Test known domain (should work)
curl http://vertexmonetize.com
# Should work normally
```

---

## Automatic Domain Updates

### Option A: Cron Job to Update Nginx

```bash
# Add to crontab
sudo crontab -e

# Run every 5 minutes to update Nginx config from database
*/5 * * * * /usr/bin/python3 /path/to/scripts/generate_nginx_domains.py && /usr/bin/nginx -s reload
```

### Option B: Webhook After Domain Changes

Add webhook call in your domain service:

```python
# app/services/domain_service.py

async def create_domain(db, data):
    # ... existing code ...
    await invalidate_domain_routing()
    
    # Trigger Nginx config update
    await update_nginx_config()
    
    return doc

async def update_nginx_config():
    """Update Nginx configuration with active domains"""
    try:
        # Call script to regenerate Nginx config
        import subprocess
        subprocess.run([
            "python3",
            "/path/to/scripts/generate_nginx_domains.py"
        ], check=True)
        
        # Reload Nginx
        subprocess.run(["nginx", "-s", "reload"], check=True)
        
        logger.info("Nginx config updated successfully")
    except Exception as e:
        logger.error(f"Failed to update Nginx config: {e}")
```

---

## Security Benefits

1. **Hidden Server:** Unknown domains receive NO response, making server invisible
2. **No Information Leakage:** Attackers can't probe different domains to find your server
3. **DDoS Protection:** Invalid domains are dropped immediately at Nginx level
4. **Clean Logs:** Only legitimate domains reach your application logs

---

## Testing

### Test Unknown Domain (Should Not Respond)
```bash
curl -v http://check4.clicklyspot.icu
# Expected: Connection timeout or immediate close, NO 404 page
```

### Test Known Domain (Should Work)
```bash
curl -v http://vertexmonetize.com
# Expected: Normal response
```

---

## Troubleshooting

### Issue: Still seeing 404 for unknown domains
- Check if `default_server` is set correctly
- Verify the default server block comes BEFORE other server blocks
- Reload Nginx: `sudo nginx -s reload`

### Issue: Known domains not working
- Check if domain is in `server_name` list
- Verify SSL certificate paths are correct
- Check Nginx error log: `sudo tail -f /var/log/nginx/error.log`

### Issue: SSL certificate issues
- Ensure dummy certificate exists: `/etc/nginx/ssl/dummy.crt`
- For production domains, ensure Let's Encrypt certs are valid

---

## Quick Implementation (Copy-Paste Ready)

```bash
# 1. Create dummy SSL cert
sudo mkdir -p /etc/nginx/ssl
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/nginx/ssl/dummy.key \
  -out /etc/nginx/ssl/dummy.crt \
  -subj "/CN=localhost"

# 2. Edit Nginx config
sudo nano /etc/nginx/sites-available/default

# 3. Add the configuration from "Step 2" above

# 4. Test and reload
sudo nginx -t && sudo systemctl reload nginx
```

---

## Summary

- ✅ Unknown domains get **NO response** (connection dropped)
- ✅ Only whitelisted domains work
- ✅ Protects against domain scanning
- ✅ Can be automated with database sync
- ✅ No application code changes needed

This is a **server-level** configuration, not application code, so it's implemented in Nginx configuration files.
