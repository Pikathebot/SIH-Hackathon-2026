"""Routers package — re-exports for router registration."""

from app.routers.health import router as health_router  # noqa: F401
from app.routers.query import router as query_router  # noqa: F401
from app.routers.preview import router as preview_router  # noqa: F401
