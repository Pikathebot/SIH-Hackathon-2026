"""
Configuration module — loads environment variables from .env file.

All config values come from environment variables per INTEGRATION_GUIDE.md §3.
Nothing is hardcoded — AI_SERVICE_MODE switches mock↔real without code changes.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (two levels up from backend/app/)
_project_root = Path(__file__).resolve().parent.parent.parent
load_dotenv(_project_root / ".env")

# ---------------------------------------------------------------------------
# AI Service
# ---------------------------------------------------------------------------
AI_SERVICE_MODE: str = os.getenv("AI_SERVICE_MODE", "mock")

RSUNIVLM_CHECKPOINT_PATH: str = os.getenv(
    "RSUNIVLM_CHECKPOINT_PATH",
    "./ai_service/rsunivlm/checkpoints/base.pt",
)
RSUNIVLM_LORA_ADAPTER_PATH: str = os.getenv(
    "RSUNIVLM_LORA_ADAPTER_PATH",
    "./ai_service/rsunivlm/checkpoints/lora_adapter.pt",
)
FUSION_MODEL_PATH: str = os.getenv(
    "FUSION_MODEL_PATH",
    "./ai_service/fusion/checkpoints/classifier.pkl",
)

# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
BACKEND_PORT: int = int(os.getenv("BACKEND_PORT", "8000"))

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASE_PATH: str = os.getenv("DATABASE_PATH", "./backend/data/satquery.db")
