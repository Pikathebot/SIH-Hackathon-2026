"""
Shared test setup.

Settings are read when `app.config` is first imported, so the environment is set
here at module import time, before any test module imports the app. Every test run
gets a throwaway DATA_DIR (database, uploads, evidence), never backend/data.
"""

import asyncio
import os
import shutil
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

_TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="satquery-test-"))
os.environ["DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ.pop("DATABASE_URL", None)
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production-use-0123456789"
os.environ.setdefault("AI_SERVICE_MODE", "mock")
os.environ["ALLOW_REGISTRATION"] = "true"
os.environ["RATE_LIMIT_ENABLED"] = "false"  # tests register many users from one IP; test_hardening enables it

_backend = Path(__file__).resolve().parent.parent
for p in (str(_backend), str(_backend.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

asyncio.run(init_db())

TEST_PASSWORD = "correct-horse-battery"


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TEST_DATA_DIR, ignore_errors=True)


def register_user(client: TestClient, email: str | None = None) -> tuple[dict, dict]:
    """Register a fresh user; return (auth headers, response body)."""
    email = email or f"user-{uuid.uuid4().hex[:10]}@example.com"
    res = client.post("/api/v1/auth/register", json={"email": email, "password": TEST_PASSWORD})
    assert res.status_code == 201, res.text
    body = res.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body


@pytest.fixture
def sync_client() -> TestClient:
    """Unauthenticated in-process client (cookies persist across its requests)."""
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_headers(sync_client) -> dict:
    headers, _ = register_user(sync_client)
    return headers


@pytest.fixture
def authed_client(auth_headers) -> TestClient:
    """In-process client already signed in as a fresh user."""
    with TestClient(app, headers=auth_headers) as c:
        yield c
