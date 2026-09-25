# Domain Access Control System

## ✅ System Overview

The MaxPayAds platform implements **strict role-based domain access control**. Each domain can only be used for its assigned role and will receive **404 responses** for any unauthorized routes.

### Core Principle
> **One domain, one role. No cross-functional access.**

---

## 🏗️ Domain Roles & Responsibilities

### 1. **Portal Domains** (`role: "portal"`)
**Purpose**: Admin panel and publisher dashboard access

**Allowed Routes**:
- `/` - Main portal homepage
- `/admin/*` - Full admin panel access
- `/publisher/*` - Publisher dashboard access  
- `/clean-shell` - Shell interface
- Static assets (`/_next/*`, `/uploads/*`, `.js`, `.css`, etc.)
- All other administrative routes

**Examples**: `admin.maxpayads.com`, `portal.company.com`

**Blocked**: Cannot access click tracking, prelanders, or stats

---

### 2. **Anchor Domains** (`role: "anchor"`)
**Purpose**: Initial click entry point for traffic

**Allowed Routes**:
- `/` - Landing page for the anchor domain
- `/click` - Click tracking endpoint
- `/go` - Redirect endpoint
- `/go/*` - Parameterized redirect routes
- `/ad.js` - JavaScript tracking
- Static assets

**Examples**: `track.ads.com`, `click.network.com`

**Blocked**: Cannot access admin, stats, or prelander content

---

### 3. **Inter Domains** (`role: "inter"`)  
**Purpose**: Intermediate redirect in the chain

**Allowed Routes**:
- `/d/*` - Redirect chain progression
- `/prelander/hop/*` - Chain advancement
- `/prelander/*` - Some prelander utilities
- Static assets

**Examples**: `hop1.network.com`, `bridge.ads.com`

**Blocked**: Cannot access admin, stats, or direct click tracking

---

### 4. **Prelander Domains** (`role: "prelander"`)
**Purpose**: Display landing pages before final offers

**Allowed Routes**:
- `/` - Prelander homepage  
- `/d/*` - Redirect chain continuation
- `/prelander/*` - Full prelander functionality
- `/_auth/*` - Prelander authentication
- `/clean-shell` - Debug interface
- Static assets

**Examples**: `lander.offers.com`, `page.network.com`

**Blocked**: Cannot access admin, click tracking, or stats

---

### 5. **Stats Domains** (`role: "stats"`)
**Purpose**: Public statistics display ONLY

**Allowed Routes**:
- `/public-stats/*` - **ONLY** public stats pages
- Static assets (for rendering stats pages)

**Examples**: `stats.company.com`, `fisherhub.net`

**Blocked**: Cannot access ANYTHING except public stats

---

## 🔒 Security Enforcement

### Backend Protection
**File**: `app/middleware/domain_access_middleware.py`

```python
class DomainAccessMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        allowed = await allow_path(get_database(), 
                                 request.headers.get('host', ''), 
                                 request.url.path)
        if not allowed:
            return Response(status_code=404)  # Unauthorized access
        return await call_next(request)
```

### Domain Role Resolution
**File**: `app/services/domain_access_service.py`

```python
async def domain_role(db, host):
    """Determine what role a domain has"""
    # 1. Check if it's a portal domain
    # 2. Check redirection_domains table for anchor/inter/prelander
    # 3. Check if it's a stats domain (global or per-publisher)
    # 4. Return None if unauthorized
```

### Path Validation
```python
async def allow_path(db, host, path):
    """Allow access only if domain role matches required route role"""
    role = await domain_role(db, host)
    if not role:
        return None  # Unknown domain = 404
    
    # Route-specific validation
    if path.startswith('/public-stats/'):
        return role if role == 'stats' else None
    if path.startswith('/admin/'):
        return role if role == 'portal' else None
    # ... more validations
```

---

## 📋 Domain Management

### Adding New Domains

#### Portal Domains
```bash
# Add to environment variable
PORTAL_HOSTNAMES=admin.company.com,portal.company.com
```

#### Redirection Domains (Anchor/Inter/Prelander)
```sql
-- Via Admin Panel: Admin → Redirection Domains
INSERT INTO redirection_domains (
    domain: "click.network.com",
    domain_type: "anchor",  -- or "inter" or "prelander"
    status: "active"
)
```

#### Stats Domains
```sql
-- Global stats domain
INSERT INTO system_settings (key: "stats_domain", value: "stats.company.com")

-- Per-publisher stats domain  
UPDATE direct_links SET stats_domain = "fisherhub.net" WHERE publisher_id = "..."
```

---

## 🚫 Unauthorized Access Behavior

### What Happens to Unauthorized Domains?

**Scenario**: Someone points `unauthorized.com` to your server

**Result**: 
```
HTTP/1.1 404 Not Found
Cache-Control: no-store

(Empty response body)
```

### What Happens to Wrong Routes?

**Scenario**: Try to access admin on a stats domain

**Request**: `https://stats.company.com/admin/dashboard`

**Result**:
```
HTTP/1.1 404 Not Found  
Cache-Control: no-store

(Empty response body)
```

---

## ✅ Benefits of This System

### 1. **Security Isolation**
- Admin panel can never be accessed via tracking domains
- Stats domains can't be used for malicious redirects
- Each domain has a single, specific purpose

### 2. **SEO Protection**  
- Tracking domains won't serve content that could hurt SEO
- Stats domains stay focused on their public stats purpose
- No mixed content concerns

### 3. **Clean Analytics**
- Each domain role has predictable traffic patterns
- Easy to monitor and analyze domain-specific metrics
- Clear separation of concerns

### 4. **Scalability**
- Add new domains for specific roles without conflicts
- Easy to distribute traffic across multiple domains
- Role-based load balancing possible

---

## 🧪 Testing Domain Access Control

### Manual Testing
```bash
# Test unauthorized domain
curl -H "Host: unauthorized.com" https://your-server.com/admin/
# Expected: 404

# Test wrong route for domain role  
curl -H "Host: stats.company.com" https://your-server.com/admin/
# Expected: 404

# Test correct access
curl -H "Host: stats.company.com" https://your-server.com/public-stats/abc123
# Expected: 200 (if share ID exists)
```

### Automated Testing
The system includes comprehensive tests in `tests/test_domain_access.py` that verify:
- ✅ Each domain role can access its allowed routes
- ✅ Each domain role is blocked from unauthorized routes  
- ✅ Unknown domains get 404 for everything
- ✅ Path validation works correctly

---

## 🔧 Configuration Files

### Key Files
- `app/services/domain_access_service.py` - Core domain role logic
- `app/middleware/domain_access_middleware.py` - Request filtering
- `app/config.py` - Portal domain configuration
- `app/main.py` - Middleware registration

### Database Collections
- `redirection_domains` - Anchor/Inter/Prelander domains
- `system_settings` - Global stats domain  
- `direct_links` - Per-publisher stats domains

---

## 📖 Summary

The domain access control system ensures that:

1. **Portal domains** = Admin/Publisher access only
2. **Anchor domains** = Click tracking only  
3. **Inter domains** = Chain hopping only
4. **Prelander domains** = Landing pages only
5. **Stats domains** = Public stats only
6. **Unauthorized domains** = Nothing (404)

This creates a secure, scalable, and maintainable system where each domain has a single, well-defined purpose and cannot be abused for unintended functionality.