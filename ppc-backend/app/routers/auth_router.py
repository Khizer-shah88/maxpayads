from fastapi import APIRouter, Depends, HTTPException
from app.schemas.auth_schema import RegisterRequest, LoginRequest, TokenResponse, RefreshTokenRequest
from app.services.publisher_service import create_publisher, get_publisher_by_email
from app.core.security import verify_password, create_access_token, create_refresh_token, decode_token, blacklist_token
from app.core.exceptions import ConflictError, UnauthorizedError
from app.dependencies import get_db, get_redis_client, get_current_user
from bson import ObjectId
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=201)
async def register(data: RegisterRequest, db=Depends(get_db)):
    """Register a new publisher account."""
    existing = await get_publisher_by_email(data.email, db)
    if existing:
        raise ConflictError("Email already registered")

    publisher_data = {
        "name": data.name,
        "email": data.email,
        "password": data.password,
    }
    publisher_id = await create_publisher(publisher_data, db)

    # Create website if domain provided
    if data.website_domain:
        website = {
            "publisher_id": publisher_id,
            "domain": data.website_domain.strip().lower().replace("https://", "").replace("http://", ""),
            "name": data.website_domain,
            "status": "active",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
        await db.websites.insert_one(website)

    return {
        "success": True,
        "message": "Registration successful. Your account is pending admin approval.",
        "publisher_id": publisher_id,
    }


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db=Depends(get_db)):
    """Login with email and password, receive JWT tokens."""
    publisher = await get_publisher_by_email(data.email, db)
    if not publisher:
        raise UnauthorizedError("Invalid email or password")

    if not verify_password(data.password, publisher.get("password_hash", "")):
        raise UnauthorizedError("Invalid email or password")

    token_data = {"sub": publisher["id"], "role": publisher.get("role", "publisher")}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    # Update last login — publisher id is a string; the stored `_id` is an
    # ObjectId, so try both shapes (mirrors get_current_user's lookup).
    try:
        last_login_filter = {"_id": ObjectId(publisher["id"])}
    except Exception:
        last_login_filter = {"_id": publisher["id"]}
    result = await db.publishers.update_one(
        last_login_filter,
        {"$set": {"last_login": datetime.utcnow()}}
    )
    if result.matched_count == 0:
        await db.publishers.update_one(
            {"_id": publisher["id"]},
            {"$set": {"last_login": datetime.utcnow()}}
        )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        publisher_id=publisher["id"],
        name=publisher["name"],
        email=publisher["email"],
        role=publisher.get("role", "publisher"),
        status=publisher.get("status", "active"),
    )


@router.post("/refresh")
async def refresh_token(data: RefreshTokenRequest):
    """Refresh access token using refresh token."""
    payload = decode_token(data.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise UnauthorizedError("Invalid refresh token")

    token_data = {"sub": payload["sub"], "role": payload.get("role", "publisher")}
    new_access_token = create_access_token(token_data)
    return {"access_token": new_access_token, "token_type": "bearer"}


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user), redis=Depends(get_redis_client)):
    """Logout and blacklist current token."""
    token = current_user.get("_token", "")
    if token and redis:
        await blacklist_token(token, redis)
    return {"success": True, "message": "Logged out successfully"}


@router.get("/me")
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user info."""
    user_safe = {k: v for k, v in current_user.items() if k not in ["password_hash", "_token"]}
    return {"success": True, "user": user_safe}
