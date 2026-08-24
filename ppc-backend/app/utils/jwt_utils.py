from app.core.security import create_access_token, create_refresh_token, decode_token
from app.core.exceptions import UnauthorizedError
from typing import Optional


def create_tokens(publisher_id: str, role: str) -> dict:
    data = {"sub": publisher_id, "role": role}
    access_token = create_access_token(data)
    refresh_token = create_refresh_token(data)
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
    }


def get_token_payload(token: str) -> dict:
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise UnauthorizedError("Invalid or expired token")
    return payload


def extract_publisher_id(token: str) -> str:
    payload = get_token_payload(token)
    return payload["sub"]


def extract_role(token: str) -> str:
    payload = get_token_payload(token)
    return payload.get("role", "publisher")
