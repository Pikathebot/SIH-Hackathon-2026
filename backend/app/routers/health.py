"""
Health endpoint — GET /api/v1/health

Trivial liveness check for local dev / demo rehearsal.
Response shape per API_CONTRACT.md §1.
"""

from fastapi import APIRouter

from app.models.api import HealthResponse
from app.orchestrator import is_fusion_loaded, is_rsunivlm_loaded

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    GET /api/v1/health → {"status": "ok", "rsunivlm_loaded": true, "fusion_loaded": true}
    """
    return HealthResponse(
        status="ok",
        rsunivlm_loaded=is_rsunivlm_loaded(),
        fusion_loaded=is_fusion_loaded(),
    )
