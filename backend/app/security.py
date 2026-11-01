"""
Authentication primitives (API_CONTRACT.md §5).

- Passwords: argon2id via pwdlib.
- Access tokens: HS256 JWT, `settings.access_token_minutes` long, sent as a Bearer header.
- Refresh tokens: opaque random strings in an httpOnly cookie. Only their SHA-256 is
  stored (`refresh_tokens.token_hash`), they are rotated on every refresh and revoked
  on logout, so a stolen cookie stops working once the real user refreshes.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pwdlib import PasswordHash
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.errors import ApiError
from app.models.db import User

JWT_ALGORITHM = "HS256"
REFRESH_COOKIE = "satquery_refresh"
REFRESH_COOKIE_PATH = "/api/v1/auth"

_password_hash = PasswordHash.recommended()
# Verified against when the email is unknown, so login timing does not reveal which emails exist.
_DUMMY_HASH = _password_hash.hash("not-a-real-password-just-for-timing")
_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)
        return False
    return _password_hash.verify(password, password_hash)


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user.id,
        "role": user.role,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALGORITHM],
                            options={"require": ["sub", "exp", "type"]})
    except jwt.PyJWTError as exc:
        raise ApiError(401, "UNAUTHORIZED", "Your session has expired. Please sign in again.") from exc
    if claims.get("type") != "access":
        raise ApiError(401, "UNAUTHORIZED", "Invalid access token.")
    return claims


def new_refresh_token() -> tuple[str, str, datetime]:
    """Return (raw token for the cookie, sha256 hex to store, expiry)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_refresh_token(raw), datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days)


def hash_refresh_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def get_current_user(
    creds: Annotated[Optional[HTTPAuthorizationCredentials], Depends(_bearer)],
    db: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise ApiError(401, "UNAUTHORIZED", "Sign in to continue.")
    claims = decode_access_token(creds.credentials)
    user = await db.get(User, claims["sub"])
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "Account no longer exists.")
    return user


async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "admin":
        raise ApiError(403, "FORBIDDEN", "Administrator access required.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
