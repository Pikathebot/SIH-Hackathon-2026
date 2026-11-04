"""
Configuration: typed settings from environment variables and `.env` (pydantic-settings).

All config values come from the environment per INTEGRATION_GUIDE.md §3; nothing is
hard-coded. `settings` is the single source of truth. The module-level names below
(DATA_DIR, AI_ENGINE, ...) are kept so existing `from app.config import X` imports work.
"""

from __future__ import annotations

import logging
import secrets
from functools import cached_property
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_project_root = PROJECT_ROOT  # backward-compatible alias


def _resolve(path_str: str | Path) -> Path:
    """Relative paths anchor at PROJECT_ROOT, so behaviour never depends on the cwd."""
    p = Path(path_str).expanduser()
    return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    # ── Data & database ────────────────────────────────────────────────
    data_dir: Path = Field(default=Path("backend/data"), alias="DATA_DIR")
    # Empty → sqlite+aiosqlite:///<DATA_DIR>/satquery.db
    database_url: str = Field(default="", alias="DATABASE_URL")

    # ── Auth ───────────────────────────────────────────────────────────
    # Empty → a random key is generated once and kept in <DATA_DIR>/.secret_key
    secret_key: str = Field(default="", alias="SECRET_KEY")
    access_token_minutes: int = Field(default=15, alias="ACCESS_TOKEN_MINUTES")
    refresh_token_days: int = Field(default=14, alias="REFRESH_TOKEN_DAYS")
    allow_registration: bool = Field(default=True, alias="ALLOW_REGISTRATION")
    # Set true when served over HTTPS so the refresh cookie gets the Secure flag
    cookie_secure: bool = Field(default=False, alias="COOKIE_SECURE")

    # ── HTTP ───────────────────────────────────────────────────────────
    cors_origins: str = Field(default="http://localhost:3000,http://127.0.0.1:3000", alias="CORS_ORIGINS")
    max_upload_mb: int = Field(default=4096, alias="MAX_UPLOAD_MB")
    backend_port: int = Field(default=8000, alias="BACKEND_PORT")
    # JSON bodies (e.g. base64 images on /query); /upload is bounded by MAX_UPLOAD_MB instead
    max_request_mb: int = Field(default=64, alias="MAX_REQUEST_MB")
    # Largest raster accepted, in megapixels (decompression-bomb guard); 0 = unlimited.
    # A full Sentinel-2 tile is 120 MP; 1024 MP is 32 768 x 32 768.
    max_image_megapixels: int = Field(default=1024, alias="MAX_IMAGE_MEGAPIXELS")
    # Total size of one user's uploads; 0 = unlimited
    user_quota_mb: int = Field(default=20480, alias="USER_QUOTA_MB")

    # ── Hardening (API_CONTRACT.md §6) ─────────────────────────────────
    rate_limit_enabled: bool = Field(default=True, alias="RATE_LIMIT_ENABLED")
    rate_limit_auth: str = Field(default="10/minute", alias="RATE_LIMIT_AUTH")    # per client IP
    rate_limit_query: str = Field(default="30/minute", alias="RATE_LIMIT_QUERY")  # per user
    gpu_concurrency: int = Field(default=1, ge=1, alias="GPU_CONCURRENCY")
    gpu_queue_max: int = Field(default=4, ge=0, alias="GPU_QUEUE_MAX")
    gpu_task_timeout_s: float = Field(default=300, gt=0, alias="GPU_TASK_TIMEOUT_S")
    log_format: str = Field(default="text", alias="LOG_FORMAT")  # text | json
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # ── AI service ─────────────────────────────────────────────────────
    ai_service_mode: str = Field(default="mock", alias="AI_SERVICE_MODE")
    # hybrid = Qwen3-VL (llama-server) for language/grounding + RSUniVLM for masks.
    # Falls back to rsunivlm at startup if llama-server is not reachable (real mode).
    ai_engine: str = Field(default="hybrid", alias="AI_ENGINE")
    # Use the VLM to classify single-image intent (qwen/hybrid, real mode); keyword fallback stays.
    llm_intent_enabled: bool = Field(default=True, alias="LLM_INTENT_ENABLED")
    rsunivlm_checkpoint_path: Path = Field(default=Path("ai_service/rsunivlm/checkpoints/RSUniVLM"),
                                           alias="RSUNIVLM_CHECKPOINT_PATH")
    rsunivlm_lora_adapter_path: Path = Field(default=Path("ai_service/rsunivlm/checkpoints/lora_adapter"),
                                             alias="RSUNIVLM_LORA_ADAPTER_PATH")
    fusion_model_path: Path = Field(default=Path("ai_service/fusion/checkpoints/classifier.pkl"),
                                    alias="FUSION_MODEL_PATH")

    @field_validator("data_dir", "rsunivlm_checkpoint_path", "rsunivlm_lora_adapter_path",
                     "fusion_model_path", mode="after")
    @classmethod
    def _anchor(cls, v: Path) -> Path:
        return _resolve(v)

    @cached_property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite+aiosqlite:///{(self.data_dir / 'satquery.db').as_posix()}"

    @cached_property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        if "*" in origins:
            raise ValueError("CORS_ORIGINS must not contain '*' (credentials are allowed)")
        return origins

    @cached_property
    def jwt_secret(self) -> str:
        if self.secret_key:
            return self.secret_key
        key_file = self.data_dir / ".secret_key"
        if key_file.exists():
            return key_file.read_text(encoding="utf-8").strip()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_urlsafe(48)
        key_file.write_text(key, encoding="utf-8")
        logger.warning("SECRET_KEY not set; generated one at %s (set SECRET_KEY in production)", key_file)
        return key


settings = Settings()

# ── Backward-compatible module-level names ───────────────────────────────
DATA_DIR: Path = settings.data_dir
IMAGES_DIR: Path = DATA_DIR / "images"
UPLOADS_DIR: Path = DATA_DIR / "uploads"
EVIDENCE_DIR: Path = DATA_DIR / "evidence"
AI_SERVICE_MODE: str = settings.ai_service_mode
AI_ENGINE: str = settings.ai_engine
LLM_INTENT_ENABLED: bool = settings.llm_intent_enabled
RSUNIVLM_CHECKPOINT_PATH: str = str(settings.rsunivlm_checkpoint_path)
RSUNIVLM_LORA_ADAPTER_PATH: str = str(settings.rsunivlm_lora_adapter_path)
FUSION_MODEL_PATH: str = str(settings.fusion_model_path)
BACKEND_PORT: int = settings.backend_port
