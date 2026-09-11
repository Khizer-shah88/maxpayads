from fastapi import Depends, Header, HTTPException
from typing import Optional
from bson import ObjectId
from app.core.security import decode_token, is_token_blacklisted
from app.core.exceptions import UnauthorizedError, ForbiddenError
from app.database import get_database
from app.cache.redis_client import get_redis


async def get_db():
    return get_database()


async def get_redis_client():
    return get_redis()


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db=Depends(get_db),
    redis=Depends(get_redis_client),
) -> dict:
    """Extract and validate JWT token, return current user."""
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid authorization header")

    token = authorization[7:]
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise UnauthorizedError("Invalid or expired token")

    # Type confusion guard: only access tokens authenticate API calls. Without
    # this check, the long-lived refresh token (30 days) could be replayed as
    # an access credential, defeating the short access-token lifetime.
    if payload.get("type") != "access":
        raise UnauthorizedError("Invalid or expired token")

    # Check token blacklist
    if redis:
        try:
            if await is_token_blacklisted(token, redis):
                raise UnauthorizedError("Token has been revoked")
        except Exception:
            pass

    publisher_id = payload["sub"]
    # Try ObjectId first (new publishers), fall back to string (legacy/admin)
    publisher = None
    try:
        publisher = await db.publishers.find_one({"_id": ObjectId(publisher_id)})
    except Exception:
        pass
    if not publisher:
        publisher = await db.publishers.find_one({"_id": publisher_id})
    if not publisher:
        raise UnauthorizedError("User not found")

    publisher["id"] = str(publisher.pop("_id"))
    publisher.pop("password_hash", None)
    publisher["_token"] = token
    return publisher


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Ensure the current user is an admin."""
    if current_user.get("role") != "admin":
        raise ForbiddenError("Admin access required")
    return current_user


async def get_current_active_publisher(current_user: dict = Depends(get_current_user)) -> dict:
    """Ensure the current user is an active publisher (not suspended/pending/banned/removed)."""
    if current_user.get("role") == "admin":
        return current_user  # Admins can access publisher endpoints
    status = current_user.get("status")
    if status == "suspended":
        raise ForbiddenError("Account is suspended")
    if status == "pending":
        raise ForbiddenError("Account is pending approval")
    # Banned/removed publishers lose panel access. Their Smartlinks keep
    # redirecting (public /click flow), but they cannot log in.
    if status in ("banned", "removed"):
        raise ForbiddenError("Account is no longer available")
    return current_user
