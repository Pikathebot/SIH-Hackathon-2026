"""
Request tracing, logging and the outermost HTTP guard (API_CONTRACT.md §6, v2.3.0).

`RequestContextMiddleware` is a pure ASGI middleware that, for every HTTP request:
- assigns a request id (reusing a valid client `X-Request-ID`) and echoes it back;
- rejects JSON bodies over MAX_REQUEST_MB with 413 (Content-Length or streamed count);
- adds security headers;
- turns any unhandled exception into a contracted 500 body carrying only the request id,
  while the full traceback goes to the server log under that id;
- writes one access-log line with status and duration.
"""

from __future__ import annotations

import contextvars
import json
import logging
import re
import sys
import time
import traceback
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException

from app.config import settings

logger = logging.getLogger("satquery.http")

request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)

_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
# Paths whose body size is enforced by their own handler (streamed multi-GB uploads)
_BODY_LIMIT_EXEMPT = ("/api/v1/upload",)
_SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"cross-origin-opener-policy", b"same-origin"),
]


def current_request_id() -> str | None:
    return request_id_var.get()


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    _SKIP = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "request_id"}

    def format(self, record: logging.LogRecord) -> str:
        doc = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }
        # Structured extras passed via logger.info(..., extra={...})
        for k, v in vars(record).items():
            if k not in self._SKIP and not k.startswith("_"):
                doc[k] = v if isinstance(v, (str, int, float, bool, type(None))) else str(v)
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, ensure_ascii=False)


def configure_logging() -> None:
    # A redirected stdout on Windows is cp1252; without this any non-ASCII text in a
    # log line (a user's query, a filename) makes logging print a traceback instead.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    except (AttributeError, ValueError):  # not a TextIOWrapper (e.g. captured by pytest)
        pass
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_RequestIdFilter())
    if settings.log_format.lower() == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s [%(request_id)s]: %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.log_level.upper())


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
class _BodyTooLarge(HTTPException):
    """An HTTPException so FastAPI's body parser re-raises it (as 413) instead of turning it into a 400."""

    def __init__(self) -> None:
        super().__init__(413, f"Request body is larger than {settings.max_request_mb} MB.")


def _json_error(status: int, code: str, message: str, request_id: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message, "detail": None,
                                 "request_id": request_id}}).encode()


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        headers = dict(scope.get("headers") or [])
        incoming = headers.get(b"x-request-id", b"").decode("latin-1")
        rid = incoming if _VALID_ID.match(incoming) else uuid.uuid4().hex
        # Not reset afterwards: each request runs in its own task/context, and
        # handlers further out (CORS, server error) should still see the id.
        request_id_var.set(rid)

        start = time.perf_counter()
        status_holder = {"status": 500, "started": False}
        path = scope.get("path", "")

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                status_holder["started"] = True
                hdrs = list(message.get("headers") or [])
                present = {k.lower() for k, _ in hdrs}
                hdrs.append((b"x-request-id", rid.encode()))
                hdrs.extend(h for h in _SECURITY_HEADERS if h[0] not in present)
                message = {**message, "headers": hdrs}
            await send(message)

        limit = settings.max_request_mb * 1024 * 1024
        guarded_receive = receive
        if not path.startswith(_BODY_LIMIT_EXEMPT) and scope.get("method") in ("POST", "PUT", "PATCH"):
            try:
                declared = int(headers.get(b"content-length", b"0") or 0)
            except ValueError:
                declared = 0
            if declared > limit:
                await self._send_json(send_wrapper, 413, "PAYLOAD_TOO_LARGE",
                                      f"Request body is larger than {settings.max_request_mb} MB.", rid)
                self._access_log(scope, 413, start)
                return
            seen = 0

            async def guarded_receive():
                nonlocal seen
                message = await receive()
                if message["type"] == "http.request":
                    seen += len(message.get("body", b""))
                    if seen > limit:
                        raise _BodyTooLarge()
                return message

        try:
            await self.app(scope, guarded_receive, send_wrapper)
        except _BodyTooLarge:
            if not status_holder["started"]:
                await self._send_json(send_wrapper, 413, "PAYLOAD_TOO_LARGE",
                                      f"Request body is larger than {settings.max_request_mb} MB.", rid)
        except Exception as exc:
            logger.error("Unhandled exception on %s %s: %s\n%s", scope.get("method"), path,
                         type(exc).__name__, "".join(traceback.format_exception(exc)))
            if not status_holder["started"]:
                await self._send_json(send_wrapper, 500, "INTERNAL_ERROR",
                                      f"An unexpected internal error occurred (request id {rid}).", rid)
        finally:
            self._access_log(scope, status_holder["status"], start)

    @staticmethod
    async def _send_json(send, status: int, code: str, message: str, rid: str) -> None:
        body = _json_error(status, code, message, rid)
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json"),
                                (b"content-length", str(len(body)).encode())]})
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    def _access_log(scope, status: int, start: float) -> None:
        logger.info("%s %s -> %d (%.0f ms)", scope.get("method"), scope.get("path"), status,
                    (time.perf_counter() - start) * 1000,
                    extra={"http_status": status, "duration_ms": round((time.perf_counter() - start) * 1000)})
