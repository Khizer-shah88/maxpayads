"""
Secure Prelander Service
=========================
Server-side template rendering with signed redirect context validation.

Security Features:
- Signed short-lived redirect tokens (HMAC-SHA256)
- Template sandboxing (no arbitrary code execution)
- Safe placeholder substitution only
- Server-side validation (no JavaScript tricks)
"""

import hmac
import hashlib
import time
import re
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from jinja2 import Environment, BaseLoader, TemplateSyntaxError, select_autoescape
from jinja2.sandbox import SandboxedEnvironment

from app.core.constants import DOMAIN_TYPE_PRELANDER
from app.core.glossary import domain_type_filter

logger = logging.getLogger(__name__)

# Secret key for signing redirect context
# Sourced from settings/env (REDIRECT_SECRET_KEY); falls back to the app-wide
# JWT secret so tokens stay verifiable even when the dedicated key is unset.
import os
from app.config import get_settings

def _resolve_redirect_secret() -> str:
    configured = (get_settings().REDIRECT_SECRET_KEY or "").strip()
    if configured:
        return configured
    if os.getenv("REDIRECT_SECRET_KEY", "").strip():
        return os.getenv("REDIRECT_SECRET_KEY").strip()
    return get_settings().SECRET_KEY

REDIRECT_SECRET = _resolve_redirect_secret()

# Token expiration (5 minutes)
TOKEN_EXPIRATION_SECONDS = 300

# Allowed placeholders (whitelist for security)
ALLOWED_PLACEHOLDERS = {
    "CAMPAIGN_URL",
    "CLICK_ID", 
    "PUBLISHER_ID",
    "SITE_ID",
    "COUNTRY",
    "OS",
    "DEVICE_TYPE",
    "TIMESTAMP",
}


class RedirectContext:
    """
    Secure redirect context with signed token validation.
    Prevents unauthorized access to prelanders.
    """
    
    def __init__(
        self,
        click_id: str,
        campaign_url: str,
        publisher_id: Optional[str] = None,
        site_id: Optional[str] = None,
        country: Optional[str] = None,
        os: Optional[str] = None,
        device_type: Optional[str] = None,
        timestamp: Optional[int] = None,
    ):
        self.click_id = click_id
        self.campaign_url = campaign_url
        self.publisher_id = publisher_id or ""
        self.site_id = site_id or ""
        self.country = country or ""
        self.os = os or ""
        self.device_type = device_type or ""
        self.timestamp = timestamp or int(time.time())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "click_id": self.click_id,
            "campaign_url": self.campaign_url,
            "publisher_id": self.publisher_id,
            "site_id": self.site_id,
            "country": self.country,
            "os": self.os,
            "device_type": self.device_type,
            "timestamp": self.timestamp,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RedirectContext":
        """Create from dictionary."""
        return cls(
            click_id=data.get("click_id", ""),
            campaign_url=data.get("campaign_url", ""),
            publisher_id=data.get("publisher_id"),
            site_id=data.get("site_id"),
            country=data.get("country"),
            os=data.get("os"),
            device_type=data.get("device_type"),
            timestamp=data.get("timestamp"),
        )
    
    def sign(self) -> str:
        """Generate signed token for this context."""
        # Serialize context data
        data_parts = [
            self.click_id,
            self.campaign_url,
            self.publisher_id,
            self.site_id,
            self.country,
            self.os,
            str(self.timestamp),
        ]
        data_string = "|".join(data_parts)
        
        # Create HMAC signature
        signature = hmac.new(
            REDIRECT_SECRET.encode(),
            data_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        # Combine data and signature
        import base64
        token_data = f"{data_string}:{signature}"
        token = base64.urlsafe_b64encode(token_data.encode()).decode()
        
        return token
    
    @classmethod
    def verify(cls, token: str) -> Optional["RedirectContext"]:
        """
        Verify and decode a signed token.
        Returns None if invalid or expired.
        """
        try:
            import base64
            
            # Decode token
            token_data = base64.urlsafe_b64decode(token.encode()).decode()
            
            if ":" not in token_data:
                logger.warning("Invalid token format: missing separator")
                return None
            
            data_string, provided_signature = token_data.rsplit(":", 1)
            
            # Verify signature
            expected_signature = hmac.new(
                REDIRECT_SECRET.encode(),
                data_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if not hmac.compare_digest(expected_signature, provided_signature):
                logger.warning("Token signature verification failed")
                return None
            
            # Parse data
            parts = data_string.split("|")
            if len(parts) < 7:
                logger.warning(f"Invalid token data: expected 7 parts, got {len(parts)}")
                return None
            
            click_id, campaign_url, publisher_id, site_id, country, os, timestamp_str = parts
            timestamp = int(timestamp_str)
            
            # Check expiration
            if time.time() - timestamp > TOKEN_EXPIRATION_SECONDS:
                logger.warning(f"Token expired: age={time.time() - timestamp}s")
                return None
            
            # Create context
            return cls(
                click_id=click_id,
                campaign_url=campaign_url,
                publisher_id=publisher_id or None,
                site_id=site_id or None,
                country=country or None,
                os=os or None,
                timestamp=timestamp,
            )
            
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None


class PrelanderTemplateEngine:
    """
    Secure template rendering engine with sandboxing.
    Prevents arbitrary code execution from templates.
    """
    
    def __init__(self):
        # Use sandboxed Jinja2 environment
        self.env = SandboxedEnvironment(
            loader=BaseLoader(),
            autoescape=select_autoescape(['html', 'xml']),
        )
        
        # Disable dangerous features
        self.env.globals.clear()
        self.env.filters.clear()
        
        # Add only safe filters
        self.env.filters['upper'] = str.upper
        self.env.filters['lower'] = str.lower
        self.env.filters['title'] = str.title
    
    def render(
        self,
        template_html: str,
        context: RedirectContext,
    ) -> str:
        """
        Render template with safe placeholder substitution.
        
        Only allowed placeholders are replaced.
        Template cannot execute arbitrary code.
        """
        try:
            # Validate template syntax
            self._validate_template_placeholders(template_html)
            
            # Prepare safe context data
            safe_context = {
                "CAMPAIGN_URL": context.campaign_url,
                "CLICK_ID": context.click_id,
                "PUBLISHER_ID": context.publisher_id or "",
                "SITE_ID": context.site_id or "",
                "COUNTRY": context.country or "",
                "OS": context.os or "",
                "DEVICE_TYPE": context.device_type or "",
                "TIMESTAMP": str(context.timestamp),
            }
            
            # Render template in sandbox
            template = self.env.from_string(template_html)
            rendered = template.render(**safe_context)
            
            return rendered
            
        except TemplateSyntaxError as e:
            logger.error(f"Template syntax error: {e}")
            raise ValueError(f"Invalid template syntax: {e}")
        except Exception as e:
            logger.error(f"Template rendering error: {e}")
            raise ValueError(f"Template rendering failed: {e}")
    
    def _validate_template_placeholders(self, template_html: str):
        """
        Validate that template only uses allowed placeholders.
        Raises ValueError if invalid placeholders found.
        """
        # Find all Jinja2 variable references
        pattern = r'\{\{\s*([A-Z_]+)\s*\}\}'
        placeholders = set(re.findall(pattern, template_html))
        
        # Check for disallowed placeholders
        invalid = placeholders - ALLOWED_PLACEHOLDERS
        if invalid:
            raise ValueError(f"Template contains disallowed placeholders: {invalid}")
    
    def validate_template(self, template_html: str) -> Dict[str, Any]:
        """
        Validate template syntax and security.
        Returns dict with validation result.
        """
        try:
            self._validate_template_placeholders(template_html)
            
            # Try to compile template
            self.env.from_string(template_html)
            
            # Extract used placeholders
            pattern = r'\{\{\s*([A-Z_]+)\s*\}\}'
            used_placeholders = set(re.findall(pattern, template_html))
            
            return {
                "valid": True,
                "message": "Template is valid",
                "used_placeholders": list(used_placeholders),
            }
            
        except ValueError as e:
            return {
                "valid": False,
                "message": str(e),
                "used_placeholders": [],
            }
        except TemplateSyntaxError as e:
            return {
                "valid": False,
                "message": f"Syntax error: {e}",
                "used_placeholders": [],
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"Validation error: {e}",
                "used_placeholders": [],
            }


async def get_template_for_domain(db, domain: str) -> Optional[Dict[str, Any]]:
    """
    Get active template assigned to a Prelander domain.
    Returns None if domain not found or no template assigned.
    """
    from app.services.domain_service import normalize_domain
    
    normalized = normalize_domain(domain)
    
    # Find domain
    domain_doc = await db.redirection_domains.find_one({
        "domain": normalized,
        "domain_type": domain_type_filter(DOMAIN_TYPE_PRELANDER),
        "status": "active",
    })
    
    if not domain_doc:
        return None
    
    template_id = domain_doc.get("template_id")
    if not template_id:
        return None
    
    # Get template
    from bson import ObjectId
    try:
        template = await db.prelander_templates.find_one({
            "_id": ObjectId(template_id),
            "status": "active",
        })
        return template
    except Exception:
        return None


async def get_default_template(db) -> Optional[Dict[str, Any]]:
    """Get the default active template."""
    return await db.prelander_templates.find_one({
        "is_default": True,
        "status": "active",
    })


def generate_fallback_html(message: str = "Loading...") -> str:
    """Generate safe fallback HTML when template unavailable."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Loading</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }}
        .container {{
            text-align: center;
            color: white;
        }}
        .spinner {{
            border: 4px solid rgba(255,255,255,0.3);
            border-radius: 50%;
            border-top: 4px solid white;
            width: 40px;
            height: 40px;
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
        <div class="spinner"></div>
        <h1>{message}</h1>
    </div>
</body>
</html>"""
