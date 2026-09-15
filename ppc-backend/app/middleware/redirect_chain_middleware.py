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
    """
    
    async def dispatch(self, request: Request, call_next):
        try:
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
        """
        if not chain.get("session_validation", True):
            # Session validation disabled, pass through
            return await self._redirect_to_next_hop(request, chain, db, "inter")
        
        chain_id = str(chain["_id"])
        cookie_name = f"rcs_{chain_id}"
        session_token = request.cookies.get(cookie_name)
        
        if not session_token:
            return await self._block_request(request, chain, db, "missing_session_cookie")
        
        # Validate session in Redis
        session_key = f"redirect_chain_session:{session_token}"
        session_data = await redis.get(session_key)
        
        if not session_data:
            return await self._block_request(request, chain, db, "session_expired")
        
        # Parse session data
        try:
            import ast
            session_info = ast.literal_eval(session_data.decode() if isinstance(session_data, bytes) else session_data)
        except:
            return await self._block_request(request, chain, db, "invalid_session_data")
        
        # Validate IP and User-Agent for basic fingerprinting
        visitor_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        if (session_info.get("visitor_ip") != visitor_ip or 
            session_info.get("user_agent") != user_agent):
            return await self._block_request(request, chain, db, "fingerprint_mismatch")
        
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
        """
        if not chain.get("session_validation", True):
            # Session validation disabled, pass through
            return await self._redirect_to_next_hop(request, chain, db, f"extra_{hop_index}")
        
        chain_id = str(chain["_id"])
        cookie_name = f"rcs_{chain_id}"
        session_token = request.cookies.get(cookie_name)
        
        if not session_token:
            return await self._block_request(request, chain, db, "missing_session_cookie")
        
        # Validate session in Redis
        session_key = f"redirect_chain_session:{session_token}"
        session_data = await redis.get(session_key)
        
        if not session_data:
            return await self._block_request(request, chain, db, "session_expired")
        
        # Parse session data
        try:
            import ast
            session_info = ast.literal_eval(session_data.decode() if isinstance(session_data, bytes) else session_data)
        except:
            return await self._block_request(request, chain, db, "invalid_session_data")
        
        # Validate IP and User-Agent
        visitor_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        if (session_info.get("visitor_ip") != visitor_ip or 
            session_info.get("user_agent") != user_agent):
            return await self._block_request(request, chain, db, "fingerprint_mismatch")
        
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
        """
        if not chain.get("session_validation", True):
            # Session validation disabled, serve content normally
            return await self._serve_prelander_content(request, chain, db)
        
        chain_id = str(chain["_id"])
        cookie_name = f"rcs_{chain_id}"
        session_token = request.cookies.get(cookie_name)
        
        if not session_token:
            return await self._block_request(request, chain, db, "missing_session_cookie")
        
        # Validate session
        session_key = f"redirect_chain_session:{session_token}"
        session_data = await redis.get(session_key)
        
        if not session_data:
            return await self._block_request(request, chain, db, "session_expired")
        
        try:
            import ast
            session_info = ast.literal_eval(session_data.decode() if isinstance(session_data, bytes) else session_data)
        except:
            return await self._block_request(request, chain, db, "invalid_session_data")
        
        # Final validation
        visitor_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        
        if (session_info.get("visitor_ip") != visitor_ip or 
            session_info.get("user_agent") != user_agent):
            return await self._block_request(request, chain, db, "fingerprint_mismatch")
        
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
        Serve the pre-lander content. This could be:
        1. A redirect to the final offer URL
        2. A pre-lander template page
        3. Pass through to the original handler
        """
        # For now, just pass through to the original handler
        # In a real implementation, you might serve a template or redirect to an offer
        
        # You could also implement template serving here
        template_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Loading...</title>
            <meta http-equiv="refresh" content="2;url=https://example.com/offer">
        </head>
        <body>
            <div style="text-align: center; padding: 50px; font-family: Arial;">
                <h1>Preparing your exclusive offer...</h1>
                <p>You will be redirected automatically.</p>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=template_content)
    
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