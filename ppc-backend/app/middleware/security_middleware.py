"""
Security Middleware
===================

Comprehensive security middleware for:
- Security headers
- IDOR protection
- Session security
- Request validation
- Security event logging
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from fastapi import status
import logging
import time

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Add comprehensive security headers to all responses.
    """
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # Prevent clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Enable XSS filter
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Content Security Policy
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'",  # Adjust as needed
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "font-src 'self' data:",
            "connect-src 'self'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)
        
        # Permissions Policy (formerly Feature-Policy)
        permissions = [
            "geolocation=()",
            "microphone=()",
            "camera=()",
            "payment=()",
            "usb=()",
        ]
        response.headers["Permissions-Policy"] = ", ".join(permissions)
        
        # Strict Transport Security (HTTPS only)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """
    Validate requests for common attack patterns.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Check for SQL injection patterns in query params
        query_string = str(request.url.query)
        if query_string:
            sql_patterns = [
                r"union.*select", r"drop.*table", r"insert.*into",
                r"delete.*from", r"update.*set", r"exec\(",
                r"execute\(", r"'.*or.*'.*=.*'",
            ]
            
            import re
            for pattern in sql_patterns:
                if re.search(pattern, query_string, re.IGNORECASE):
                    logger.warning(f"SQL injection attempt detected: {query_string}")
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={"detail": "Invalid request"}
                    )
        
        # Check for path traversal
        path = str(request.url.path)
        if "../" in path or "..%2F" in path or "..%5C" in path:
            logger.warning(f"Path traversal attempt detected: {path}")
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid request"}
            )
        
        # Check request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 10 * 1024 * 1024:  # 10MB limit
            logger.warning(f"Request too large: {content_length} bytes")
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail": "Request too large"}
            )
        
        response = await call_next(request)
        return response


class SecurityAuditMiddleware(BaseHTTPMiddleware):
    """
    Audit security-relevant requests.
    """
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        # Log authentication attempts
        if "/auth/" in request.url.path:
            logger.info(
                f"Auth attempt: {request.method} {request.url.path} "
                f"from {request.client.host if request.client else 'unknown'}"
            )
        
        response = await call_next(request)
        
        # Log failed authentication
        if "/auth/" in request.url.path and response.status_code in [401, 403]:
            duration = time.time() - start_time
            logger.warning(
                f"Failed auth: {request.method} {request.url.path} "
                f"status={response.status_code} duration={duration:.3f}s "
                f"ip={request.client.host if request.client else 'unknown'}"
            )
        
        # Log admin operations
        if "/admin/" in request.url.path and request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            duration = time.time() - start_time
            logger.info(
                f"Admin operation: {request.method} {request.url.path} "
                f"status={response.status_code} duration={duration:.3f}s"
            )
        
        return response


def validate_object_id(obj_id: str) -> bool:
    """
    Validate MongoDB ObjectId format.
    Used for IDOR protection.
    """
    import re
    return bool(re.match(r'^[a-f0-9]{24}$', obj_id, re.IGNORECASE))


def check_resource_ownership(
    user_id: str,
    resource_user_id: str,
    is_admin: bool = False,
) -> bool:
    """
    Check if user owns a resource or is admin.
    Used for IDOR protection.
    """
    if is_admin:
        return True
    
    return str(user_id) == str(resource_user_id)


class RateLimitExceeded(Exception):
    """Exception raised when rate limit is exceeded."""
    pass


async def check_endpoint_rate_limit(
    request: Request,
    redis,
    endpoint: str,
    limit: int,
    window_seconds: int,
):
    """
    Check rate limit for a specific endpoint.
    """
    if not redis:
        return
    
    # Use IP + endpoint as key
    client_ip = request.client.host if request.client else "unknown"
    key = f"rate_limit:{endpoint}:{client_ip}"
    
    try:
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
        
        if count > limit:
            raise RateLimitExceeded(f"Rate limit exceeded: {limit} requests per {window_seconds}s")
            
    except RateLimitExceeded:
        raise
    except Exception as e:
        logger.error(f"Rate limit check error: {e}")


def sanitize_error_message(error: Exception) -> str:
    """
    Sanitize error messages to prevent information leakage.
    """
    error_str = str(error)
    
    # Remove internal paths
    import re
    error_str = re.sub(r'/[a-zA-Z0-9_/.-]+\.py', '[file]', error_str)
    
    # Remove MongoDB details
    error_str = re.sub(r'ObjectId\(["\']?[a-f0-9]{24}["\']?\)', '[id]', error_str)
    
    # Generic database errors
    if "duplicate key error" in error_str.lower():
        return "Resource already exists"
    
    if "cast to objectid failed" in error_str.lower():
        return "Invalid ID format"
    
    # Generic error for unknown types
    if len(error_str) > 200:
        return "An error occurred processing your request"
    
    return error_str


class SessionSecurityMiddleware(BaseHTTPMiddleware):
    """
    Enhance session security.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Check for session fixation attempts
        session_id = request.cookies.get("session_id")
        if session_id:
            # Validate session format
            if len(session_id) < 32 or not session_id.isalnum():
                logger.warning(f"Invalid session ID format: {session_id[:10]}...")
                # Clear invalid session
                response = JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid session"}
                )
                response.delete_cookie("session_id")
                return response
        
        response = await call_next(request)
        
        # Add secure cookie attributes
        try:
            if "Set-Cookie" in response.headers:
                # Note: FastAPI handles this, but we ensure it
                cookies = response.headers.getlist("Set-Cookie")
                new_cookies = []
                for cookie in cookies:
                    # mpf_tab_ok (mpa_tab_ok) is the ONE-TIME 60s tab bridge: the
                    # prelander page must READ it via document.cookie to consume
                    # it (expire) and set the per-tab sessionStorage marker —
                    # HttpOnly would make it invisible to the page and the
                    # authorized visitor's first load rendered a BLANK page
                    # (isSameTab never became true). It carries no secret (a
                    # literal "1" valid for one request) so JS-readable is safe;
                    # every OTHER cookie gets the HttpOnly hardening.
                    is_tab_bridge = cookie.startswith("mpa_tab_ok=")
                    if "HttpOnly" not in cookie and not is_tab_bridge:
                        cookie += "; HttpOnly"
                    if "SameSite" not in cookie:
                        cookie += "; SameSite=Lax"
                    if request.url.scheme == "https" and "Secure" not in cookie:
                        cookie += "; Secure"
                    new_cookies.append(cookie)
                
                # Replace cookies. MutableHeaders has no .pop() — the previous
                # response.headers.pop("Set-Cookie") raised AttributeError on
                # EVERY response that carried a Set-Cookie header (e.g. /click
                # setting the prelander authorization reference), crashing the
                # request AFTER the endpoint had succeeded and turning it into
                # a 500. __delitem__ removes all values for the key; append
                # re-adds each cookie preserving duplicates.
                del response.headers["Set-Cookie"]
                for cookie in new_cookies:
                    response.headers.append("Set-Cookie", cookie)
        except Exception as e:
            # Header manipulation must never break a response the endpoint
            # already produced successfully.
            logger.warning(f"Cookie hardening skipped: {e}")
        
        return response


def check_csrf_token(request: Request, token: str) -> bool:
    """
    Check CSRF token validity.
    """
    # Get token from header or form data
    header_token = request.headers.get("X-CSRF-Token")
    
    if not header_token:
        return False
    
    # Constant-time comparison
    import hmac
    return hmac.compare_digest(token, header_token)


class APISecurityMiddleware(BaseHTTPMiddleware):
    """
    API-specific security checks.
    """
    
    async def dispatch(self, request: Request, call_next):
        # Check for API key in headers (if using API keys)
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # Validate API key format
            if len(api_key) < 32:
                return JSONResponse(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    content={"detail": "Invalid API key"}
                )
        
        # Check content type for POST/PUT/PATCH
        if request.method in ["POST", "PUT", "PATCH"]:
            content_type = request.headers.get("content-type", "").lower()
            
            # Require proper content type
            if content_type and not any(ct in content_type for ct in ["application/json", "multipart/form-data", "application/x-www-form-urlencoded"]):
                logger.warning(f"Unexpected content type: {content_type}")
        
        # Add request ID for tracking
        import uuid
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        
        response = await call_next(request)
        
        # Add request ID to response
        response.headers["X-Request-ID"] = request_id
        
        return response
