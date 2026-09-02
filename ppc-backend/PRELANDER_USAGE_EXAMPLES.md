# Prelander System Usage Examples

## Quick Start Guide

### 1. Generate Signed Token (Server-Side)

```python
from app.services.prelander_service import RedirectContext

# Create context from click data
context = RedirectContext(
    click_id="click_abc123",
    campaign_url="https://offers.example.com/download",
    publisher_id="pub_456",
    site_id="site_789",
    country="US",
    os="Windows",
    device_type="desktop",
)

# Sign token (5-minute expiration)
token = context.sign()
# Returns: "eyJjbGlja19pZCI6ImNsaWNrX2FiYzEyMyIsImNhbXBhaWduX3VybCI..."

# Redirect user to prelander
prelander_url = f"https://prelander1.com/p/render?token={token}"
```

### 2. Create Template (Admin)

```python
import httpx

# Admin creates template
response = httpx.post(
    "https://api.example.com/prelander-templates",
    headers={"Authorization": f"Bearer {admin_token}"},
    json={
        "name": "Windows Download Template",
        "description": "Blue gradient design for Windows users",
        "os_type": "windows",
        "status": "active",
        "full_html_template": """
<!DOCTYPE html>
<html>
<head>
    <title>Download Ready</title>
    <style>
        body {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
        }
        .card {
            background: white;
            border-radius: 20px;
            padding: 40px;
            max-width: 500px;
            text-align: center;
        }
        .button {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 15px 40px;
            border-radius: 50px;
            text-decoration: none;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="card">
        <h1>Your Download is Ready!</h1>
        <p>System: {{ OS }}</p>
        <p>Location: {{ COUNTRY }}</p>
        <a href="{{ CAMPAIGN_URL }}" class="button">Download Now</a>
        <p><small>Click ID: {{ CLICK_ID }}</small></p>
    </div>
</body>
</html>
        """
    }
)

template_id = response.json()["template_id"]
```

### 3. Assign Template to Domain

```python
import httpx

# Admin assigns template to prelander domain
response = httpx.put(
    f"https://api.example.com/admin/redirection-domains/{domain_id}",
    headers={"Authorization": f"Bearer {admin_token}"},
    json={
        "template_id": template_id
    }
)
```

### 4. Validate Template Before Saving

```python
import httpx

# Validate HTML template
response = httpx.post(
    "https://api.example.com/prelander-templates/validate-html",
    headers={"Authorization": f"Bearer {admin_token}"},
    json={
        "html": """
        <html>
        <body>
            <h1>{{ CLICK_ID }}</h1>
            <a href="{{ CAMPAIGN_URL }}">Download</a>
        </body>
        </html>
        """
    }
)

result = response.json()
# {
#   "success": true,
#   "validation": {
#     "valid": true,
#     "message": "Template is valid",
#     "used_placeholders": ["CLICK_ID", "CAMPAIGN_URL"]
#   }
# }
```

### 5. Integration with Click Tracking

```python
from app.services.prelander_service import RedirectContext
from app.routers.click_router import track_click

@router.get("/click")
async def handle_click(
    request: Request,
    pub: str,
    site: str,
    db = Depends(get_db),
):
    # Track click
    click_data = await track_click(pub, site, request, db)
    
    # Create signed redirect context
    context = RedirectContext(
        click_id=str(click_data["_id"]),
        campaign_url=click_data["destination_url"],
        publisher_id=pub,
        site_id=site,
        country=click_data.get("country", ""),
        os=click_data.get("os", ""),
        device_type=click_data.get("device_type", ""),
    )
    
    # Sign token
    token = context.sign()
    
    # Get prelander domain for this publisher
    prelander_domain = await get_prelander_domain(db, pub)
    
    # Redirect to prelander
    return RedirectResponse(
        url=f"https://{prelander_domain}/p/render?token={token}"
    )
```

---

## Advanced Examples

### Multi-Domain Setup with Different Templates

```python
# Template A: For Windows users
template_a = {
    "name": "Windows Blue",
    "os_type": "windows",
    "full_html_template": "<!-- Windows-specific design -->"
}

# Template B: For Mac users
template_b = {
    "name": "Mac Dark",
    "os_type": "mac",
    "full_html_template": "<!-- Mac-specific design -->"
}

# Domain 1: Windows prelander
domain_1 = {
    "domain": "win-download.com",
    "domain_type": "last",
    "template_id": template_a_id,
    "status": "active"
}

# Domain 2: Mac prelander
domain_2 = {
    "domain": "mac-download.com",
    "domain_type": "last",
    "template_id": template_b_id,
    "status": "active"
}
```

### Conditional Content Based on Country

```python
template_html = """
<!DOCTYPE html>
<html>
<body>
    <h1>Download Ready</h1>
    
    {% if COUNTRY == "US" %}
        <p>Download for United States users</p>
    {% elif COUNTRY == "UK" %}
        <p>Download for United Kingdom users</p>
    {% else %}
        <p>International download</p>
    {% endif %}
    
    <a href="{{ CAMPAIGN_URL }}">Download Now</a>
</body>
</html>
"""
```

### Template with Auto-Redirect

```python
template_html = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Loading...</title>
    <style>
        body {
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            background: #667eea;
            color: white;
            font-family: Arial;
        }
        .spinner {
            border: 4px solid rgba(255,255,255,0.3);
            border-top: 4px solid white;
            border-radius: 50%;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
    </style>
</head>
<body>
    <div>
        <div class="spinner"></div>
        <p>Preparing your download...</p>
    </div>
    
    <script>
        // Auto-redirect after 3 seconds
        setTimeout(function() {
            window.location.href = "{{ CAMPAIGN_URL }}";
        }, 3000);
    </script>
</body>
</html>
"""
```

---

## API Integration Examples

### cURL Examples

#### Create Template
```bash
curl -X POST "https://api.example.com/prelander-templates" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Template",
    "os_type": "both",
    "status": "active",
    "full_html_template": "<html><body>{{ CAMPAIGN_URL }}</body></html>"
  }'
```

#### Validate Template
```bash
curl -X POST "https://api.example.com/prelander-templates/validate-html" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "html": "<html><body>{{ CLICK_ID }}</body></html>"
  }'
```

#### List Templates
```bash
curl "https://api.example.com/prelander-templates?status=active" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

#### Get Template Assigned Domains
```bash
curl "https://api.example.com/prelander-templates/TEMPLATE_ID/assigned-domains" \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Python HTTPx Examples

```python
import httpx

async def create_and_assign_template():
    async with httpx.AsyncClient() as client:
        # Create template
        template_response = await client.post(
            "https://api.example.com/prelander-templates",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "Premium Template",
                "os_type": "both",
                "status": "active",
                "full_html_template": template_html
            }
        )
        template_id = template_response.json()["template_id"]
        
        # Assign to domain
        domain_response = await client.put(
            f"https://api.example.com/admin/redirection-domains/{domain_id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"template_id": template_id}
        )
        
        return template_id
```

---

## Testing Examples

### Unit Test: Token Generation
```python
def test_token_generation():
    context = RedirectContext(
        click_id="test_click",
        campaign_url="https://example.com/offer",
    )
    
    token = context.sign()
    assert len(token) > 50
    
    verified = RedirectContext.verify(token)
    assert verified is not None
    assert verified.click_id == "test_click"
```

### Integration Test: Full Flow
```python
async def test_full_prelander_flow(db):
    # 1. Create template
    template_id = await create_template(db)
    
    # 2. Create domain with template
    domain_id = await create_domain(db, template_id)
    
    # 3. Generate token
    context = RedirectContext(
        click_id="integration_test",
        campaign_url="https://example.com/offer",
    )
    token = context.sign()
    
    # 4. Render prelander
    response = await client.get(f"/p/render?token={token}")
    assert response.status_code == 200
    assert "integration_test" in response.text
```

---

## Security Examples

### Generate Strong Secret Key
```python
import secrets

# Generate 256-bit secret key
secret_key = secrets.token_hex(32)
print(f"REDIRECT_SECRET_KEY={secret_key}")
# Output: REDIRECT_SECRET_KEY=a1b2c3d4e5f6...
```

### Verify Token Age
```python
context = RedirectContext.verify(token)
if context:
    age = time.time() - context.timestamp
    print(f"Token age: {age} seconds")
    
    if age > 300:
        print("Token expired (>5 minutes)")
    else:
        print(f"Token valid ({300 - age} seconds remaining)")
```

### Safe Template Validation
```python
from app.services.prelander_service import PrelanderTemplateEngine

engine = PrelanderTemplateEngine()

# This template is SAFE
safe_template = """
<html>
<body>
    <h1>{{ CLICK_ID }}</h1>
    <a href="{{ CAMPAIGN_URL }}">Download</a>
</body>
</html>
"""

result = engine.validate_template(safe_template)
assert result["valid"] is True

# This template is UNSAFE (disallowed placeholder)
unsafe_template = """
<html>
<body>
    {{ EVIL_PLACEHOLDER }}
</body>
</html>
"""

result = engine.validate_template(unsafe_template)
assert result["valid"] is False
assert "disallowed" in result["message"]
```

---

## Troubleshooting Examples

### Debug Token Issues
```python
from app.services.prelander_service import RedirectContext
import logging

logging.basicConfig(level=logging.DEBUG)

# Create context
context = RedirectContext(
    click_id="debug_test",
    campaign_url="https://example.com/offer",
)

# Sign token
token = context.sign()
print(f"Generated token: {token[:50]}...")

# Verify token
verified = RedirectContext.verify(token)
if verified:
    print("✅ Token valid")
    print(f"  Click ID: {verified.click_id}")
    print(f"  Campaign URL: {verified.campaign_url}")
    print(f"  Timestamp: {verified.timestamp}")
else:
    print("❌ Token invalid or expired")
```

### Test Template Rendering
```python
from app.services.prelander_service import PrelanderTemplateEngine, RedirectContext

engine = PrelanderTemplateEngine()
context = RedirectContext(
    click_id="test",
    campaign_url="https://example.com/offer",
    country="US",
    os="Windows",
)

template_html = """
<html>
<body>
    <h1>Click: {{ CLICK_ID }}</h1>
    <p>Country: {{ COUNTRY }}</p>
    <p>OS: {{ OS }}</p>
    <a href="{{ CAMPAIGN_URL }}">Download</a>
</body>
</html>
"""

try:
    rendered = engine.render(template_html, context)
    print("✅ Template rendered successfully")
    print(rendered)
except Exception as e:
    print(f"❌ Template rendering failed: {e}")
```

### Verify Domain-Template Assignment
```python
from app.services.prelander_service import get_template_for_domain

async def verify_domain_template(db):
    domain = "prelander1.com"
    template = await get_template_for_domain(db, domain)
    
    if template:
        print(f"✅ Domain '{domain}' has template:")
        print(f"  Template ID: {template['_id']}")
        print(f"  Template Name: {template.get('name')}")
        print(f"  Status: {template.get('status')}")
    else:
        print(f"❌ No template found for domain '{domain}'")
```

---

## Performance Optimization Examples

### Cache Rendered Templates (Future Enhancement)
```python
import redis
import hashlib

async def get_rendered_template_cached(template_id: str, context: RedirectContext):
    # Generate cache key from context
    cache_key = hashlib.md5(
        f"{template_id}:{context.to_dict()}".encode()
    ).hexdigest()
    
    # Check cache
    cached = await redis_client.get(cache_key)
    if cached:
        return cached
    
    # Render template
    template = await db.prelander_templates.find_one({"_id": template_id})
    engine = PrelanderTemplateEngine()
    rendered = engine.render(template["full_html_template"], context)
    
    # Cache for 5 minutes
    await redis_client.setex(cache_key, 300, rendered)
    
    return rendered
```

---

## Monitoring Examples

### Log Token Usage
```python
import logging

logger = logging.getLogger("prelander")

def track_token_usage(context: RedirectContext, success: bool):
    logger.info(
        "Token usage",
        extra={
            "click_id": context.click_id,
            "publisher_id": context.publisher_id,
            "country": context.country,
            "success": success,
            "token_age": time.time() - context.timestamp,
        }
    )
```

### Monitor Template Performance
```python
import time

async def render_with_timing(template_html: str, context: RedirectContext):
    start = time.time()
    
    engine = PrelanderTemplateEngine()
    rendered = engine.render(template_html, context)
    
    elapsed = (time.time() - start) * 1000
    
    logger.info(f"Template rendered in {elapsed:.2f}ms")
    
    if elapsed > 50:
        logger.warning(f"Slow template rendering: {elapsed:.2f}ms")
    
    return rendered
```

---

## Best Practices

### 1. Always Validate Templates Before Saving
```python
# Good
validation = engine.validate_template(template_html)
if validation["valid"]:
    await save_template(template_html)
else:
    raise ValueError(validation["message"])

# Bad
await save_template(template_html)  # No validation!
```

### 2. Use Environment Variable for Secret Key
```python
# Good
import os
REDIRECT_SECRET = os.getenv("REDIRECT_SECRET_KEY")

# Bad
REDIRECT_SECRET = "hardcoded-secret"  # Never do this!
```

### 3. Set Reasonable Token Expiration
```python
# Good: 5 minutes (current default)
TOKEN_EXPIRATION_SECONDS = 300

# Bad: Too short (user may not click in time)
TOKEN_EXPIRATION_SECONDS = 10

# Bad: Too long (security risk)
TOKEN_EXPIRATION_SECONDS = 3600
```

### 4. Handle Template Not Found Gracefully
```python
# Good
template = await get_template_for_domain(db, domain)
if not template:
    template = await get_default_template(db)
if not template:
    return generate_fallback_html("No template configured")

# Bad
template = await get_template_for_domain(db, domain)
return render_template(template)  # May crash if None!
```

---

## Conclusion

This prelander system provides:
- ✅ Secure server-side validation
- ✅ Flexible template management
- ✅ Easy domain assignment
- ✅ Safe placeholder system
- ✅ Comprehensive testing

For more information, see:
- `PRELANDER_SYSTEM_IMPLEMENTATION_REPORT.md` - Full implementation details
- `tests/test_prelander_system.py` - Test examples
- API documentation at `/docs`
