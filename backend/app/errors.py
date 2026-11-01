"""
API errors in the contracted shape (API_CONTRACT.md §1):
    {"error": {"code": ..., "message": ..., "detail": ...}}
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.models.api import ErrorDetail, ErrorResponse

_STATUS_CODES = {400: "VALIDATION_ERROR", 401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND",
                 405: "VALIDATION_ERROR", 409: "CONFLICT", 413: "PAYLOAD_TOO_LARGE", 422: "VALIDATION_ERROR"}


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str, detail: Optional[str] = None,
                 headers: Optional[dict] = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.detail = detail
        self.headers = headers


def error_response(status_code: int, code: str, message: str, detail: Optional[str] = None,
                   headers: Optional[dict] = None) -> JSONResponse:
    body = ErrorResponse(error=ErrorDetail(code=code, message=message, detail=detail)).model_dump()
    return JSONResponse(status_code=status_code, content=body, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        headers = exc.headers
        if exc.status_code == 401:
            headers = {"WWW-Authenticate": "Bearer", **(headers or {})}
        return error_response(exc.status_code, exc.code, exc.message, exc.detail, headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        errors = exc.errors()
        first = errors[0] if errors else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        msg = f"{where}: {first.get('msg')}" if where else str(first.get("msg", "Invalid request."))
        return error_response(422, "VALIDATION_ERROR", msg, detail=str(errors)[:2000])

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = _STATUS_CODES.get(exc.status_code, "INTERNAL_ERROR")
        return error_response(exc.status_code, code, str(exc.detail), headers=getattr(exc, "headers", None))
