"""
SatQuery AI — FastAPI application entry point.

Assembles the app with CORS, routers, DB startup, and global error handling.
Run with: uvicorn app.main:app --reload --port 8000
"""

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path

# Ensure project root is in sys.path immediately
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.errors import install_error_handlers
from app.observability import RequestContextMiddleware, configure_logging
from app.routers import (
    auth_router, health_router, preview_router, query_router, sessions_router, upload_router,
)

# ---------------------------------------------------------------------------
# Logging — text or JSON (LOG_FORMAT), every line tagged with the request id
# ---------------------------------------------------------------------------
configure_logging()
logger = logging.getLogger("satquery")


# ---------------------------------------------------------------------------
# Lifespan — startup/shutdown events
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager — init DB on startup."""
    logger.info("Starting SatQuery AI backend...")

    # Ensure data directories exist
    from app.config import EVIDENCE_DIR, IMAGES_DIR, UPLOADS_DIR
    for d in (IMAGES_DIR, UPLOADS_DIR, EVIDENCE_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # Bring the database to the latest Alembic revision (adopts legacy DBs in place)
    await init_db()
    settings.jwt_secret  # resolve (or generate) the signing key at startup, not on first login
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
    description="Satellite image analysis API (Qwen3-VL + RSUniVLM hybrid engine)",
    version="2.3.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — explicit origins from CORS_ORIGINS, never "*" (API_CONTRACT.md §4)
# ---------------------------------------------------------------------------
install_error_handlers(app)
# Request id, body-size limit, security headers and the catch-all 500 (app/observability.py).
# Added before CORS so CORS stays outermost and its headers reach every response, errors included.
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)

# ---------------------------------------------------------------------------
# Include routers
# ---------------------------------------------------------------------------
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(sessions_router)
app.include_router(query_router)
app.include_router(preview_router)
app.include_router(upload_router)


# ---------------------------------------------------------------------------
# Root route — redirect to interactive API docs
# ---------------------------------------------------------------------------
@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to Swagger UI for easy browser access."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")


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
