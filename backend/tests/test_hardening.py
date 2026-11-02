"""
Phase 3 hardening (API_CONTRACT.md §6, v2.3.0): request ids, the safe 500, rate limits,
body-size limits, the GPU queue, health/ready and the per-user upload quota.
"""

import asyncio
import base64
import io
import threading
import time

import numpy as np
import pytest
from app import orchestrator
from app.config import settings
from app.errors import ApiError
from app.gpu_queue import GpuQueue, gpu_queue
from app.main import app
from app.ratelimit import limiter, parse_limit
from fastapi.testclient import TestClient
from PIL import Image

from tests.conftest import register_user


def _png_bytes(size=(64, 64), noise=False) -> bytes:
    buf = io.BytesIO()
    if noise:
        arr = np.random.randint(0, 255, (size[1], size[0], 3), dtype=np.uint8)
        Image.fromarray(arr).save(buf, format="PNG")
    else:
        Image.new("RGB", size, (30, 90, 160)).save(buf, format="PNG")
    return buf.getvalue()


def _query_body(text="What is in this image?"):
    b64 = "data:image/png;base64," + base64.b64encode(_png_bytes()).decode()
    return {"query": text, "images": [{"id": "img1", "modality": "optical", "url_or_base64": b64}]}


@pytest.fixture
def rate_limits(monkeypatch):
    """Enable rate limiting with tiny windows for one test."""
    limiter.reset()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_auth", "3/minute")
    monkeypatch.setattr(settings, "rate_limit_query", "2/minute")
    yield
    limiter.reset()


# ── Request ids and the safe 500 ────────────────────────────────────────
def test_every_response_has_request_id_and_security_headers(sync_client):
    res = sync_client.get("/api/v1/health")
    assert len(res.headers["x-request-id"]) == 32
    assert res.headers["x-content-type-options"] == "nosniff"
    assert res.headers["x-frame-options"] == "DENY"


def test_valid_client_request_id_is_reused_and_invalid_one_replaced(sync_client):
    assert sync_client.get("/api/v1/health", headers={"X-Request-ID": "abc.123-x"}).headers["x-request-id"] == "abc.123-x"
    rid = sync_client.get("/api/v1/health", headers={"X-Request-ID": "bad id\n<script>"}).headers["x-request-id"]
    assert rid != "bad id\n<script>" and len(rid) == 32


def test_error_body_carries_request_id(sync_client):
    res = sync_client.get("/api/v1/auth/me", headers={"X-Request-ID": "trace-401"})
    assert res.status_code == 401
    assert res.json()["error"]["request_id"] == "trace-401"


def test_forced_exception_returns_json_with_request_id_and_no_stack_text(authed_client, monkeypatch, caplog):
    secret = "C:\\secret\\path\\model.bin exploded"

    async def boom(*_a, **_k):
        raise RuntimeError(secret)

    monkeypatch.setattr("app.routers.query.process_query", boom)
    res = authed_client.post("/api/v1/query", json=_query_body(), headers={"X-Request-ID": "force-500"})
    assert res.status_code == 500
    err = res.json()["error"]
    assert err["code"] == "INTERNAL_ERROR"
    assert err["request_id"] == "force-500" == res.headers["x-request-id"]
    assert secret not in res.text and "Traceback" not in res.text and "RuntimeError" not in res.text
    # ...but the server log has the full traceback under the request id
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert secret in logged and "Traceback" in logged


def test_inference_failure_does_not_leak_exception_text(authed_client, monkeypatch):
    def broken(*_a, **_k):
        raise ValueError("CUDA error at /home/build/kernel.cu:42")

    monkeypatch.setattr(orchestrator, "_dispatch_ai_sync", broken)
    res = authed_client.post("/api/v1/query", json=_query_body())
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "MODEL_INFERENCE_FAILED"
    assert "kernel.cu" not in res.text


def test_error_responses_keep_cors_headers(authed_client, monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("x")

    monkeypatch.setattr("app.routers.query.process_query", boom)
    res = authed_client.post("/api/v1/query", json=_query_body(), headers={"Origin": "http://localhost:3000"})
    assert res.status_code == 500
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"


# ── Rate limits ─────────────────────────────────────────────────────────
def test_parse_limit():
    assert parse_limit("10/minute") == (10, 60.0)
    assert parse_limit("100/5minutes") == (100, 300.0)
    with pytest.raises(ValueError):
        parse_limit("ten per minute")


def test_login_rate_limit_returns_429_with_retry_after(sync_client, rate_limits):
    body = {"email": "nobody@example.com", "password": "wrong-password-123"}
    codes = [sync_client.post("/api/v1/auth/login", json=body).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    res = sync_client.post("/api/v1/auth/login", json=body)
    assert res.json()["error"]["code"] == "RATE_LIMITED"
    assert int(res.headers["retry-after"]) >= 1


def test_query_rate_limit_is_per_user(rate_limits):
    limiter.reset()
    with TestClient(app) as anon:
        a, _ = register_user(anon)
        b, _ = register_user(anon)
    with TestClient(app, headers=a) as ca, TestClient(app, headers=b) as cb:
        assert [ca.post("/api/v1/query", json=_query_body()).status_code for _ in range(3)] == [200, 200, 429]
        assert cb.post("/api/v1/query", json=_query_body()).status_code == 200  # B has its own budget


def test_sliding_window_frees_slots():
    lim = type(limiter)()
    assert lim.hit("k", 2, 10, now=0) == 0
    assert lim.hit("k", 2, 10, now=1) == 0
    assert lim.hit("k", 2, 10, now=2) == pytest.approx(8)
    assert lim.hit("k", 2, 10, now=10.5) == 0  # first hit has aged out


# ── Body size ───────────────────────────────────────────────────────────
def test_oversized_json_body_returns_413(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "max_request_mb", 1)
    big = _query_body()
    big["images"][0]["url_or_base64"] = "data:image/png;base64," + "A" * (2 * 1024 * 1024)
    res = authed_client.post("/api/v1/query", json=big)
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


def test_oversized_chunked_body_returns_413(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "max_request_mb", 1)

    def gen():  # no Content-Length → streamed and counted by the middleware
        yield b'{"query": "x", "images": [{"id": "a", "modality": "optical", "url_or_base64": "'
        for _ in range(3):
            yield b"A" * (1024 * 1024)
        yield b'"}]}'

    res = authed_client.post("/api/v1/query", content=gen(), headers={"Content-Type": "application/json"})
    assert res.status_code == 413


def test_upload_is_exempt_from_json_body_limit(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "max_request_mb", 1)
    data = _png_bytes((900, 900), noise=True)
    assert len(data) > 1024 * 1024
    res = authed_client.post("/api/v1/upload", files={"file": ("big.png", data, "image/png")})
    assert res.status_code == 200, res.text


# ── GPU queue ───────────────────────────────────────────────────────────
class _Probe:
    def __init__(self, delay=0.2):
        self.delay, self.active, self.peak = delay, 0, 0
        self.lock = threading.Lock()

    def __call__(self, value=None):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        time.sleep(self.delay)
        with self.lock:
            self.active -= 1
        return value


def test_queue_runs_jobs_one_at_a_time():
    probe, q = _Probe(), GpuQueue(concurrency=1, max_waiting=4, timeout_s=10)

    async def main():
        return await asyncio.gather(*(q.run(probe, i) for i in range(3)))

    assert asyncio.run(main()) == [0, 1, 2]
    assert probe.peak == 1
    assert q.stats()["running"] == q.stats()["waiting"] == 0


def test_queue_full_returns_503():
    probe, q = _Probe(0.3), GpuQueue(concurrency=1, max_waiting=1, timeout_s=10)

    async def main():
        t1 = asyncio.create_task(q.run(probe))
        t2 = asyncio.create_task(q.run(probe))
        await asyncio.sleep(0.05)
        with pytest.raises(ApiError) as ei:
            await q.run(probe)
        await asyncio.gather(t1, t2)
        return ei.value

    err = asyncio.run(main())
    assert (err.status_code, err.code) == (503, "QUEUE_FULL")
    assert int(err.headers["Retry-After"]) >= 1


def test_timed_out_job_returns_504_and_keeps_slot_until_thread_ends():
    slow, fast = _Probe(0.5), _Probe(0.0)
    q = GpuQueue(concurrency=1, max_waiting=2, timeout_s=0.1)

    async def main():
        with pytest.raises(ApiError) as ei:
            await q.run(slow)
        assert q.stats()["running"] == 1  # thread still on the GPU
        t0 = time.perf_counter()
        q.timeout_s = 5
        await q.run(fast)  # must wait for the abandoned job to finish
        return ei.value, time.perf_counter() - t0

    err, waited = asyncio.run(main())
    assert (err.status_code, err.code) == (504, "INFERENCE_TIMEOUT")
    assert waited >= 0.3


def test_two_concurrent_queries_run_serially_on_the_gpu(auth_headers, monkeypatch):
    probe = _Probe(0.3)
    real = orchestrator._dispatch_ai_sync
    monkeypatch.setattr(orchestrator, "_dispatch_ai_sync", lambda *a: (probe(), real(*a))[1])
    results = []
    with TestClient(app, headers=auth_headers) as c:
        threads = [threading.Thread(target=lambda: results.append(c.post("/api/v1/query", json=_query_body())))
                   for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    assert [r.status_code for r in results] == [200, 200]
    assert probe.peak == 1


def test_query_returns_503_when_queue_is_full(authed_client, monkeypatch):
    monkeypatch.setattr(gpu_queue, "concurrency", 0)  # nothing can run → nothing can be admitted
    monkeypatch.setattr(gpu_queue, "max_waiting", 0)
    res = authed_client.post("/api/v1/query", json=_query_body())
    assert res.status_code == 503
    assert res.json()["error"]["code"] == "QUEUE_FULL"
    assert "retry-after" in res.headers


# ── Health / ready ──────────────────────────────────────────────────────
def test_health_reports_database_and_queue(sync_client):
    body = sync_client.get("/api/v1/health").json()
    assert body["status"] == "ok" and body["database"] is True
    assert body["queue"]["concurrency"] >= 1
    assert "gpu" in body


def test_ready_ok_and_not_ready(sync_client, monkeypatch):
    res = sync_client.get("/api/v1/ready")
    assert res.status_code == 200 and res.json() == {"status": "ready", "checks": {"database": True, "engine": True}}
    monkeypatch.setattr(orchestrator, "ENGINE", None)
    res = sync_client.get("/api/v1/ready")
    assert res.status_code == 503 and res.json()["checks"]["engine"] is False


# ── Storage quota ───────────────────────────────────────────────────────
def test_upload_quota(authed_client, monkeypatch):
    monkeypatch.setattr(settings, "user_quota_mb", 1)
    data = _png_bytes((420, 420), noise=True)  # ~530 KB
    assert 512 * 1024 < len(data) < 1024 * 1024
    assert authed_client.post("/api/v1/upload", files={"file": ("a.png", data, "image/png")}).status_code == 200
    res = authed_client.post("/api/v1/upload", files={"file": ("b.png", data, "image/png")})
    assert res.status_code == 413
    assert res.json()["error"]["code"] == "QUOTA_EXCEEDED"
    res = authed_client.post("/api/v1/upload", files={"file": ("c.png", _png_bytes(), "image/png")})
    assert res.status_code == 200  # a small file still fits


def test_quota_is_per_user(monkeypatch):
    monkeypatch.setattr(settings, "user_quota_mb", 1)
    data = _png_bytes((420, 420), noise=True)
    with TestClient(app) as anon:
        a, _ = register_user(anon)
        b, _ = register_user(anon)
    with TestClient(app, headers=a) as ca, TestClient(app, headers=b) as cb:
        assert ca.post("/api/v1/upload", files={"file": ("a.png", data, "image/png")}).status_code == 200
        assert cb.post("/api/v1/upload", files={"file": ("b.png", data, "image/png")}).status_code == 200
