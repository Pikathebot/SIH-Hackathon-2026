"""
Auth endpoints: /api/v1/auth/register|login|refresh|logout|me (API_CONTRACT.md §5).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Cookie, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.errors import ApiError
from app.models.api import AuthResponse, LoginRequest, RegisterRequest, UserOut
from app.models.db import RefreshToken, User, utc_now
from app.ratelimit import AuthRateLimit
from app.security import (
    REFRESH_COOKIE,
    REFRESH_COOKIE_PATH,
    CurrentUser,
    DbSession,
    create_access_token,
    hash_password,
    hash_refresh_token,
    new_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, role=user.role, created_at=user.created_at)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


async def _issue_tokens(db: DbSession, user: User, response: Response) -> AuthResponse:
    raw, token_hash, expires = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=_iso(expires)))
    await db.commit()
    response.set_cookie(
        REFRESH_COOKIE, raw,
        max_age=settings.refresh_token_days * 86400,
        httponly=True, secure=settings.cookie_secure, samesite="lax", path=REFRESH_COOKIE_PATH,
    )
    return AuthResponse(access_token=create_access_token(user),
                        expires_in=settings.access_token_minutes * 60, user=_user_out(user))


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_COOKIE_PATH, httponly=True,
                           secure=settings.cookie_secure, samesite="lax")


@router.post("/register", dependencies=[AuthRateLimit], response_model=AuthResponse, status_code=201)
async def register(body: RegisterRequest, response: Response, db: DbSession) -> AuthResponse:
    if not settings.allow_registration:
        raise ApiError(403, "FORBIDDEN", "Registration is disabled on this server.")
    email = body.email.strip().lower()
    user = User(email=email, password_hash=hash_password(body.password), role="user")
    db.add(user)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise ApiError(409, "CONFLICT", "An account with this email already exists.")
    return await _issue_tokens(db, user, response)


@router.post("/login", dependencies=[AuthRateLimit], response_model=AuthResponse)
async def login(body: LoginRequest, response: Response, db: DbSession) -> AuthResponse:
    user = (await db.execute(select(User).where(User.email == body.email.strip().lower()))).scalar_one_or_none()
    if not verify_password(body.password, user.password_hash if user else None):
        raise ApiError(401, "UNAUTHORIZED", "Incorrect email or password.")
    return await _issue_tokens(db, user, response)


@router.post("/refresh", dependencies=[AuthRateLimit], response_model=AuthResponse)
async def refresh(response: Response, db: DbSession,
                  satquery_refresh: Optional[str] = Cookie(default=None)) -> AuthResponse:
    if not satquery_refresh:
        raise ApiError(401, "UNAUTHORIZED", "Sign in to continue.")
    token = (await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(satquery_refresh))
    )).scalar_one_or_none()
    now = utc_now()
    if token is None or token.revoked_at is not None or token.expires_at <= now:
        if token is not None and token.revoked_at is not None:
            # A rotated token was presented again: treat as theft and end every session.
            await db.execute(update(RefreshToken)
                             .where(RefreshToken.user_id == token.user_id, RefreshToken.revoked_at.is_(None))
                             .values(revoked_at=now))
            await db.commit()
        _clear_cookie(response)
        raise ApiError(401, "UNAUTHORIZED", "Your session has expired. Please sign in again.",
                       headers={"set-cookie": response.headers.get("set-cookie", "")})
    user = await db.get(User, token.user_id)
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "Account no longer exists.")
    token.revoked_at = now  # rotate
    return await _issue_tokens(db, user, response)


@router.post("/logout", status_code=204)
async def logout(response: Response, db: DbSession,
                 satquery_refresh: Optional[str] = Cookie(default=None)) -> Response:
    if satquery_refresh:
        await db.execute(update(RefreshToken)
                         .where(RefreshToken.token_hash == hash_refresh_token(satquery_refresh),
                                RefreshToken.revoked_at.is_(None))
                         .values(revoked_at=utc_now()))
        await db.commit()
    response.status_code = 204
    _clear_cookie(response)
    return response


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return _user_out(user)
