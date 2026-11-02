"""
Health and readiness — GET /api/v1/health, GET /api/v1/ready (API_CONTRACT.md §1, v2.3.0).

/health is liveness: always 200 while the process runs, with dependency details.
/ready is readiness: 503 until the database answers and the AI engine is initialised.
"""

import asyncio
import logging
import sys

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import orchestrator
from app.database import engine as db_engine
from app.engines import engine_health
from app.gpu_queue import gpu_queue
from app.models.api import HealthResponse
from app.orchestrator import is_fusion_loaded, is_rsunivlm_loaded

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["health"])


async def _database_ok() -> bool:
    try:
        async with db_engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=3)
        return True
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return False


def _nvml_memory():
    """Device-wide (all processes) memory via NVML, or None. torch.cuda.mem_get_info under-reports
    on Windows/WDDM (5 GB vs 11.7 GB measured), so it is not used for this number."""
    try:
        import pynvml  # nvidia-ml-py, GPU requirements only
        pynvml.nvmlInit()
        try:
            mem = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
            return round(mem.used / 2**20), round(mem.total / 2**20)
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        return None


def _gpu_info():
    """CUDA usage if torch is already loaded by an engine; never imports torch itself (mock mode)."""
    torch = sys.modules.get("torch")
    if torch is None:
        return None
    try:
        if not torch.cuda.is_available():
            return None
        nvml = _nvml_memory()
        return {"name": torch.cuda.get_device_name(0),
                "memory_used_mb": nvml[0] if nvml else None,
                "memory_total_mb": nvml[1] if nvml else round(torch.cuda.get_device_properties(0).total_memory / 2**20),
                "process_reserved_mb": round(torch.cuda.memory_reserved() / 2**20)}
    except Exception:
        return None


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """GET /api/v1/health → {"status": "ok", "rsunivlm_loaded": ..., "fusion_loaded": ..., ...}"""
    return HealthResponse(
        status="ok",
        rsunivlm_loaded=is_rsunivlm_loaded(),
        fusion_loaded=is_fusion_loaded(),
        engine=(await asyncio.to_thread(engine_health, orchestrator.ENGINE)) if orchestrator.ENGINE else None,
        database=await _database_ok(),
        queue=gpu_queue.stats(),
        gpu=_gpu_info(),
    )


@router.get("/ready", responses={503: {"description": "Not ready"}})
async def readiness() -> JSONResponse:
    checks = {"database": await _database_ok(), "engine": orchestrator.ENGINE is not None}
    ready = all(checks.values())
    return JSONResponse(status_code=200 if ready else 503,
                        content={"status": "ready" if ready else "not_ready", "checks": checks})
