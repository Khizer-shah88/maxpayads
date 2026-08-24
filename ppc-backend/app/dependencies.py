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
    """Ensure the current user is an active publisher (not suspended or pending)."""
    if current_user.get("role") == "admin":
        return current_user  # Admins can access publisher endpoints
    if current_user.get("status") == "suspended":
        raise ForbiddenError("Account is suspended")
    if current_user.get("status") == "pending":
        raise ForbiddenError("Account is pending approval")
    return current_user
