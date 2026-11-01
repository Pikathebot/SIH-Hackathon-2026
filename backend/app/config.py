"""
Configuration module — loads environment variables from .env file.

All config values come from environment variables per INTEGRATION_GUIDE.md §3.
Nothing is hardcoded — AI_SERVICE_MODE switches mock↔real without code changes.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from backend/app/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_project_root = PROJECT_ROOT  # backward-compatible alias
load_dotenv(PROJECT_ROOT / ".env")


def _resolve(path_str: str) -> Path:
    """Resolve a path from env/config: relative paths anchor at PROJECT_ROOT,
    so the server behaves the same regardless of the current working directory."""
    p = Path(path_str).expanduser()
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


# ---------------------------------------------------------------------------
# Data directories (single source of truth — never use cwd-relative paths)
# ---------------------------------------------------------------------------
DATA_DIR: Path = _resolve(os.getenv("DATA_DIR", "backend/data"))
IMAGES_DIR: Path = DATA_DIR / "images"
UPLOADS_DIR: Path = DATA_DIR / "uploads"

# ---------------------------------------------------------------------------
# AI Service
# ---------------------------------------------------------------------------
AI_SERVICE_MODE: str = os.getenv("AI_SERVICE_MODE", "mock")

RSUNIVLM_CHECKPOINT_PATH: str = str(_resolve(os.getenv(
    "RSUNIVLM_CHECKPOINT_PATH",
    "ai_service/rsunivlm/checkpoints/RSUniVLM",
)))
RSUNIVLM_LORA_ADAPTER_PATH: str = str(_resolve(os.getenv(
    "RSUNIVLM_LORA_ADAPTER_PATH",
    "ai_service/rsunivlm/checkpoints/lora_adapter",
)))
FUSION_MODEL_PATH: str = str(_resolve(os.getenv(
    "FUSION_MODEL_PATH",
    "ai_service/fusion/checkpoints/classifier.pkl",
)))

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_PATH: str = str(_resolve(os.getenv("DATABASE_PATH", str(DATA_DIR / "satquery.db"))))

# ---------------------------------------------------------------------------
# Engine selection (see app/engines.py)
# ---------------------------------------------------------------------------
# hybrid = Qwen3-VL (llama-server) for language/grounding + RSUniVLM for masks.
# Falls back to rsunivlm at startup if llama-server is not reachable (real mode).
AI_ENGINE: str = os.getenv("AI_ENGINE", "hybrid")
# Use the VLM to classify single-image intent (qwen/hybrid engines, real mode);
# the keyword classifier remains the fallback.
LLM_INTENT_ENABLED: bool = os.getenv("LLM_INTENT_ENABLED", "true").lower() in ("1", "true", "yes")
