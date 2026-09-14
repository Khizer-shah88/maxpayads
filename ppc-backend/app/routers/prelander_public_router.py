"""
Public Prelander Rendering Router
===================================
Serves prelander templates to end users with server-side signed context validation.

Security:
- Requires valid signed redirect token
- No direct access without valid context
- Short-lived tokens (5 minutes)
- Server-side validation only (no JavaScript tricks)
"""

import logging
from fastapi import APIRouter, Request, Query, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional

from app.dependencies import get_db
from app.services.prelander_service import (
    RedirectContext,
    PrelanderTemplateEngine,
    get_template_for_domain,
    get_default_template,
    generate_fallback_html,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/p", tags=["Prelander Public"])


@router.get("/render")
async def render_prelander(
    request: Request,
    token: str = Query(..., description="Signed redirect context token"),
    db=Depends(get_db),
):
    """
    Render prelander template with signed context validation.
    
    This is the secure endpoint that validates server-side signed tokens
    and renders the appropriate prelander template.
    
    **Security:**
    - Token must be signed by server
    - Token expires after 5 minutes
    - No direct access without valid token
    - Templates sandboxed (no arbitrary code execution)
    """
    # Verify token and extract context
    context = RedirectContext.verify(token)
    if not context:
        logger.warning(f"Invalid or expired prelander token from IP: {request.client.host}")
        return HTMLResponse(
            content=generate_fallback_html("Access Denied"),
            status_code=403,
        )
    
    # Get template based on domain or use default
    host = request.headers.get("host", "").split(":")[0].lower()
    template_doc = None
    
    if host:
        template_doc = await get_template_for_domain(db, host)
    
    if not template_doc:
        # Fall back to the OS Default Template. The hint must be an OS name
        # ("windows"/"mac"/"both"), NOT the hostname — passing the host here
        # made the OS-specific default lookup never match.
        from app.core.glossary import normalize_os
        os_hint = normalize_os(context.os, default=None)
        template_doc = await get_default_template(db, os_hint=os_hint)
    
    if not template_doc or not template_doc.get("full_html_template"):
        # Fallback: Generate simple prelander
        return HTMLResponse(
            content=_generate_simple_prelander(context),
            status_code=200,
        )
    
    # Render template with context
    try:
        engine = PrelanderTemplateEngine()
        rendered_html = engine.render(
            template_doc["full_html_template"],
            context,
        )
        return HTMLResponse(content=rendered_html, status_code=200)
    
    except Exception as e:
        logger.error(f"Template rendering error: {e}")
        return HTMLResponse(
            content=generate_fallback_html("Template Error"),
            status_code=500,
        )


@router.get("/direct-access-test")
async def direct_access_test(
    request: Request,
    campaign_url: Optional[str] = None,
):
    """
    Test endpoint to demonstrate that direct access is NOT allowed.
    This returns an error page showing the security works.
    
    **For testing/demo only** - Remove in production or restrict to admin.
    """
    return HTMLResponse(
        content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Access Denied</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .container {
            text-align: center;
            color: white;
            max-width: 600px;
            padding: 40px;
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
        }
        h1 { font-size: 48px; margin: 0 0 20px 0; }
        p { font-size: 18px; line-height: 1.6; }
        .code { 
            background: rgba(0,0,0,0.3); 
            padding: 10px; 
            border-radius: 5px;
            font-family: monospace;
            margin: 20px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🔒 Access Denied</h1>
        <p>Direct access to prelanders is not allowed.</p>
        <p>Prelanders can only be accessed with a valid server-side signed token.</p>
        <div class="code">
            Security: Server-side validation<br>
            Token lifetime: 5 minutes<br>
            No JavaScript tricks or source hiding
        </div>
        <p><small>This is a security feature to prevent unauthorized access and scraping.</small></p>
    </div>
</body>
</html>
        """,
        status_code=403,
    )


def _generate_simple_prelander(context: RedirectContext) -> str:
    """
    Generate a simple default prelander when no template is configured.
    Uses safe placeholder substitution.
    """
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Preparing Your Download</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}
        
        .container {{
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 500px;
            width: 100%;
            padding: 40px;
            text-align: center;
        }}
        
        .icon {{
            font-size: 64px;
            margin-bottom: 20px;
        }}
        
        h1 {{
            color: #333;
            font-size: 28px;
            margin-bottom: 10px;
        }}
        
        p {{
            color: #666;
            font-size: 16px;
            line-height: 1.6;
            margin-bottom: 30px;
        }}
        
        .button {{
            display: inline-block;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            padding: 15px 40px;
            border-radius: 50px;
            font-size: 18px;
            font-weight: 600;
            transition: transform 0.2s, box-shadow 0.2s;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }}
        
        .button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(102, 126, 234, 0.6);
        }}
        
        .info {{
            margin-top: 30px;
            padding-top: 30px;
            border-top: 1px solid #eee;
            color: #999;
            font-size: 12px;
        }}
        
        .spinner {{
            border: 4px solid rgba(102, 126, 234, 0.1);
            border-radius: 50%;
            border-top: 4px solid #667eea;
            width: 50px;
            height: 50px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }}
        
        @keyframes spin {{
            0% {{ transform: rotate(0deg); }}
            100% {{ transform: rotate(360deg); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">📦</div>
        <h1>Your File is Ready!</h1>
        <p>Click the button below to proceed to your download.</p>
        
        <div class="spinner"></div>
        
        <a href="{context.campaign_url}" class="button">Continue to Download</a>
        
        <div class="info">
            Click ID: {context.click_id}<br>
            Secure delivery powered by Max Pay Ads
        </div>
    </div>
    
    <script>
        // Auto-redirect after 3 seconds
        setTimeout(function() {{
            window.location.href = "{context.campaign_url}";
        }}, 3000);
    </script>
</body>
</html>"""
