"""
GPU work queue (API_CONTRACT.md §6, v2.3.0).

At most GPU_CONCURRENCY model jobs run at once, with up to GPU_QUEUE_MAX more waiting;
beyond that a request fails fast with 503 QUEUE_FULL. A job running longer than
GPU_TASK_TIMEOUT_S returns 504 INFERENCE_TIMEOUT to its caller.

A worker thread cannot be killed, so a timed-out (or client-abandoned) job keeps its
GPU slot until the thread actually finishes. Releasing early would let the next job
start on a GPU that is still busy, which is exactly the OOM this queue exists to prevent.

In-process by design; a cloud deployment can swap this for Redis + ARQ workers behind
the same `gpu_queue.run(...)` call.
"""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Callable
from typing import Any

from app.config import settings
from app.errors import ApiError

logger = logging.getLogger(__name__)


class GpuQueue:
    def __init__(self, concurrency: int, max_waiting: int, timeout_s: float) -> None:
        self.concurrency = concurrency
        self.max_waiting = max_waiting
        self.timeout_s = timeout_s
        self.running = 0
        self.waiting = 0
        self._sem: asyncio.Semaphore | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _semaphore(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        if self._sem is None or self._loop is not loop:  # new loop (tests, reload): fresh state
            self._sem, self._loop = asyncio.Semaphore(self.concurrency), loop
            self.running = self.waiting = 0
        return self._sem

    def stats(self) -> dict:
        return {"running": self.running, "waiting": self.waiting,
                "concurrency": self.concurrency, "max_waiting": self.max_waiting}

    async def run(self, fn: Callable[..., Any], *args: Any) -> Any:
        sem = self._semaphore()
        if self.running + self.waiting >= self.concurrency + self.max_waiting:
            retry = max(5, math.ceil(self.timeout_s / 10))
            raise ApiError(503, "QUEUE_FULL",
                           "The analysis queue is full. Please try again shortly.",
                           headers={"Retry-After": str(retry)})

        self.waiting += 1
        try:
            await sem.acquire()
        finally:
            self.waiting -= 1
        self.running += 1

        job = asyncio.ensure_future(asyncio.to_thread(fn, *args))

        def _release(_fut: asyncio.Future) -> None:
            self.running -= 1
            sem.release()
            exc = None if _fut.cancelled() else _fut.exception()  # also marks it retrieved
            if exc is not None and getattr(_fut, "_abandoned", False):
                logger.warning("Abandoned GPU job finished with %r", exc)

        job.add_done_callback(_release)
        try:
            return await asyncio.wait_for(asyncio.shield(job), timeout=self.timeout_s)
        except TimeoutError:
            job._abandoned = True  # type: ignore[attr-defined]
            logger.error("GPU job exceeded %.0f s; returning 504 (slot held until it finishes)",
                         self.timeout_s)
            raise ApiError(504, "INFERENCE_TIMEOUT",
                           f"The analysis took longer than {self.timeout_s:.0f} s and was abandoned.") from None
        except asyncio.CancelledError:
            job._abandoned = True  # type: ignore[attr-defined]
            raise


gpu_queue = GpuQueue(settings.gpu_concurrency, settings.gpu_queue_max, settings.gpu_task_timeout_s)
