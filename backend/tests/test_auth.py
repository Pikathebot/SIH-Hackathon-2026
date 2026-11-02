"""Auth: registration, login, protected endpoints, refresh-token rotation and logout."""

import uuid

import jwt
import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.security import REFRESH_COOKIE
from tests.conftest import TEST_PASSWORD, register_user


def _email():
    return f"auth-{uuid.uuid4().hex[:10]}@example.com"


def test_register_returns_token_user_and_httponly_cookie(sync_client):
    email = _email()
    res = sync_client.post("/api/v1/auth/register", json={"email": email.upper(), "password": TEST_PASSWORD})
    assert res.status_code == 201
    body = res.json()
    assert body["token_type"] == "bearer" and body["expires_in"] == settings.access_token_minutes * 60
    assert body["user"]["email"] == email  # stored lower-cased
    assert body["user"]["role"] == "user"
    cookie = res.headers["set-cookie"]
    assert REFRESH_COOKIE in cookie and "HttpOnly" in cookie and "Path=/api/v1/auth" in cookie
    assert "password" not in res.text


def test_duplicate_email_conflicts(sync_client):
    email = _email()
    register_user(sync_client, email)
    res = sync_client.post("/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert res.status_code == 409 and res.json()["error"]["code"] == "CONFLICT"


@pytest.mark.parametrize("payload", [
    {"email": "not-an-email", "password": TEST_PASSWORD},
    {"email": "short@example.com", "password": "short"},
])
def test_register_validation(sync_client, payload):
    res = sync_client.post("/api/v1/auth/register", json=payload)
    assert res.status_code == 422 and res.json()["error"]["code"] == "VALIDATION_ERROR"


def test_registration_can_be_disabled(sync_client, monkeypatch):
    monkeypatch.setattr(settings, "allow_registration", False)
    res = sync_client.post("/api/v1/auth/register", json={"email": _email(), "password": TEST_PASSWORD})
    assert res.status_code == 403 and res.json()["error"]["code"] == "FORBIDDEN"


def test_login_and_me(sync_client):
    email = _email()
    register_user(sync_client, email)
    res = sync_client.post("/api/v1/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert res.status_code == 200
    token = res.json()["access_token"]
    me = sync_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == email


def test_wrong_password_and_unknown_email_look_the_same(sync_client):
    email = _email()
    register_user(sync_client, email)
    a = sync_client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-password-123"})
    b = sync_client.post("/api/v1/auth/login", json={"email": _email(), "password": "wrong-password-123"})
    assert a.status_code == b.status_code == 401
    strip = lambda r: {k: v for k, v in r.json()["error"].items() if k != "request_id"}  # noqa: E731
    assert strip(a) == strip(b)


@pytest.mark.parametrize("method,path", [
    ("get", "/api/v1/auth/me"),
    ("get", "/api/v1/sessions"),
    ("post", "/api/v1/sessions"),
    ("post", "/api/v1/query"),
    ("post", "/api/v1/upload"),
    ("post", "/api/v1/preview"),
    ("get", f"/api/v1/assets/{uuid.uuid4()}"),
])
def test_protected_endpoints_require_a_token(sync_client, method, path):
    res = getattr(sync_client, method)(path)
    assert res.status_code == 401
    assert res.json()["error"]["code"] == "UNAUTHORIZED"
    assert res.headers.get("www-authenticate") == "Bearer"


def test_health_stays_public(sync_client):
    assert sync_client.get("/api/v1/health").status_code == 200


@pytest.mark.parametrize("token", [
    "garbage",
    jwt.encode({"sub": "x", "type": "access", "exp": 1}, settings.jwt_secret, algorithm="HS256"),  # expired
    jwt.encode({"sub": "x", "type": "access", "exp": 9999999999}, "some-other-key-of-sufficient-length!", algorithm="HS256"),
])
def test_bad_tokens_are_rejected(sync_client, token):
    res = sync_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_refresh_rotates_and_reuse_revokes_everything():
    with TestClient(app) as c:
        register_user(c)
        old_cookie = c.cookies.get(REFRESH_COOKIE)
        r1 = c.post("/api/v1/auth/refresh")
        assert r1.status_code == 200 and r1.json()["access_token"]
        new_cookie = c.cookies.get(REFRESH_COOKIE)
        assert new_cookie and new_cookie != old_cookie

        # Replaying the rotated-out cookie is treated as theft: it fails and kills the live one too.
        with TestClient(app) as attacker:
            attacker.cookies.set(REFRESH_COOKIE, old_cookie, path="/api/v1/auth")
            assert attacker.post("/api/v1/auth/refresh").status_code == 401
        assert c.post("/api/v1/auth/refresh").status_code == 401


def test_refresh_without_cookie_is_401(sync_client):
    assert sync_client.post("/api/v1/auth/refresh").status_code == 401


def test_logout_revokes_refresh_token():
    with TestClient(app) as c:
        register_user(c)
        cookie = c.cookies.get(REFRESH_COOKIE)
        assert c.post("/api/v1/auth/logout").status_code == 204
        assert c.post("/api/v1/auth/logout").status_code == 204  # idempotent
        with TestClient(app) as again:
            again.cookies.set(REFRESH_COOKIE, cookie, path="/api/v1/auth")
            assert again.post("/api/v1/auth/refresh").status_code == 401
