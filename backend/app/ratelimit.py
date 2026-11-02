"""
In-process sliding-window rate limits (API_CONTRACT.md §6, v2.3.0).

Single-process and in-memory by design (local-first, one uvicorn worker owns the GPU).
A multi-worker cloud deployment would move this to Redis behind the same dependencies.

    auth endpoints   → RATE_LIMIT_AUTH per client IP   (dependency: `AuthRateLimit`)
    query / preview  → RATE_LIMIT_QUERY per user id    (dependency: `QueryRateLimit`)

Exceeding a limit raises 429 RATE_LIMITED with Retry-After (seconds).
"""

from __future__ import annotations

import math
import re
import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import Depends, Request

from app.config import settings
from app.errors import ApiError
from app.security import CurrentUser

_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
_SPEC = re.compile(r"^\s*(\d+)\s*/\s*(\d*)\s*(second|minute|hour|day)s?\s*$", re.IGNORECASE)


def parse_limit(spec: str) -> tuple[int, float]:
    """'10/minute' → (10, 60.0); '100/5minutes' → (100, 300.0)."""
    m = _SPEC.match(spec)
    if not m:
        raise ValueError(f"Invalid rate limit {spec!r}; expected e.g. '10/minute'")
    count, mult, unit = int(m.group(1)), int(m.group(2) or 1), m.group(3).lower()
    return count, float(mult * _UNITS[unit])


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def hit(self, key: str, limit: int, window: float, now: float | None = None) -> float:
        """Record a hit. Returns 0 if allowed, else seconds until the next slot frees."""
        now = time.monotonic() if now is None else now
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= now - window:
                q.popleft()
            if len(q) >= limit:
                return max(q[0] + window - now, 0.001)
            q.append(now)
            if len(self._hits) > 10_000:  # bound memory: drop idle keys
                for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - window]:
                    del self._hits[k]
            return 0.0

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()


def _check(bucket: str, key: str, spec: str) -> None:
    if not settings.rate_limit_enabled:
        return
    limit, window = parse_limit(spec)
    wait = limiter.hit(f"{bucket}:{key}", limit, window)
    if wait:
        retry = max(1, math.ceil(wait))
        raise ApiError(429, "RATE_LIMITED", f"Too many requests. Try again in {retry} s.",
                       headers={"Retry-After": str(retry)})


def _client_ip(request: Request) -> str:
    # Behind a proxy, run uvicorn with --proxy-headers/--forwarded-allow-ips so this is the real client.
    return request.client.host if request.client else "unknown"


async def _auth_limit(request: Request) -> None:
    # One bucket per endpoint, so failed logins never lock a user out of token refresh
    _check(f"auth{request.url.path}", _client_ip(request), settings.rate_limit_auth)


async def _query_limit(user: CurrentUser) -> None:
    _check("query", user.id, settings.rate_limit_query)


AuthRateLimit = Depends(_auth_limit)
QueryRateLimit = Depends(_query_limit)
QueryRateLimitDep = Annotated[None, QueryRateLimit]
