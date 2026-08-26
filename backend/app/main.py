"""
SatQuery AI — FastAPI application entry point.

Assembles the app with CORS, routers, DB startup, and global error handling.
Run with: uvicorn app.main:app --reload --port 8000
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.database import init_db
from app.models.api import ErrorDetail, ErrorResponse
from app.routers import health_router, query_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("satquery")


# ---------------------------------------------------------------------------
# Lifespan — startup/shutdown events
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager — init DB on startup."""
    logger.info("Starting SatQuery AI backend...")

    # Ensure data directories exist
    data_dir = Path("backend/data/images")
    data_dir.mkdir(parents=True, exist_ok=True)

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Add project root to sys.path so ai_service imports work
    project_root = str(Path(__file__).resolve().parent.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    logger.info("SatQuery AI backend ready")
    yield
    logger.info("Shutting down SatQuery AI backend")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
app = FastAPI(
    title="SatQuery AI",
    description="Satellite image analysis API powered by RSUniVLM",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow frontend dev server per API_CONTRACT.md §4
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------
app.include_router(health_router)
app.include_router(query_router)


# ---------------------------------------------------------------------------
# Root route — redirect to interactive API docs
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to Swagger UI for easy browser access."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


# ---------------------------------------------------------------------------
# Global exception handler — ensures no bare 500 without JSON body
# (API_CONTRACT.md §1: "the backend must never let an unhandled exception
# produce a bare 500 with no JSON body")
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for any unhandled exception."""
    logger.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error=ErrorDetail(
                code="INTERNAL_ERROR",
                message="An unexpected internal error occurred.",
                detail=str(exc),
            )
        ).model_dump(),
    )


# ---------------------------------------------------------------------------
# Direct run support
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    from app.config import BACKEND_PORT

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=BACKEND_PORT,
        reload=True,
    )
