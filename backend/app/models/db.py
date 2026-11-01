"""
SQLAlchemy ORM models: DATABASE_CONTRACT.md v1.1.0.

Internal to the backend and never returned directly from the API. IDs are UUID v4
TEXT and timestamps are ISO-8601 UTC TEXT, per the contract (portable to Postgres).
The schema itself is owned by the Alembic migrations in backend/alembic/versions;
these classes must stay in step with them.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Float, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

TOOL_USED_VALUES = (
    "rsunivlm_vqa", "rsunivlm_cap", "rsunivlm_vg", "rsunivlm_seg", "rsunivlm_ccd",
    "qwen_vl_vqa", "qwen_vl_cap", "qwen_vl_vg", "qwen_vl_seg", "qwen_vl_ccd",
    "fusion_classifier",
)
TASK_VALUES = ("vqa", "captioning", "detection", "change_detection", "fusion")
ROLE_VALUES = ("user", "admin")


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _in(col: str, values: tuple) -> str:
    return f"{col} IN ({', '.join(repr(v) for v in values)})"


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", ROLE_VALUES), name="ck_users_role"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(Text, nullable=False, default="user")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now)


class AnalysisSession(Base):
    __tablename__ = "analysis_sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now)


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(Text, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[str] = mapped_column(Text, nullable=False)
    revoked_at: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now)


class ImageRecord(Base):
    """`images` table: uploaded files and images submitted inline with a query."""
    __tablename__ = "images"
    __table_args__ = (CheckConstraint("modality IN ('optical', 'sar')", name="ck_images_modality"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_id)
    modality: Mapped[str] = mapped_column(Text, nullable=False)
    capture_date: Mapped[Optional[str]] = mapped_column(Text)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)  # relative to DATA_DIR
    checksum: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now)
    # v1.1.0
    user_id: Mapped[Optional[str]] = mapped_column(Text, index=True)
    filename: Mapped[Optional[str]] = mapped_column(Text)
    size_bytes: Mapped[Optional[int]] = mapped_column(Integer)


class QueryRecord(Base):
    """`queries` table: one row per successful POST /api/v1/query."""
    __tablename__ = "queries"
    __table_args__ = (
        CheckConstraint(_in("selected_task", TASK_VALUES), name="ck_queries_selected_task"),
        CheckConstraint(_in("tool_used", TOOL_USED_VALUES), name="ck_queries_tool_used"),
        CheckConstraint("visual_evidence_type IN ('none', 'bbox', 'mask')", name="ck_queries_ve_type"),
        CheckConstraint("inputs_validated IN (0, 1)", name="ck_queries_inputs_validated"),
        CheckConstraint("status IN ('success', 'error')", name="ck_queries_status"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True, default=new_id)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    image_ids: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array of images.id
    selected_task: Mapped[str] = mapped_column(Text, nullable=False)
    tool_used: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[Optional[str]] = mapped_column(Text)
    answer: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    visual_evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    visual_evidence_ref: Mapped[Optional[str]] = mapped_column(Text)  # relative to DATA_DIR
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    inputs_validated: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    error_code: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default=utc_now)
    # v1.1.0
    user_id: Mapped[Optional[str]] = mapped_column(Text, index=True)
    session_id: Mapped[Optional[str]] = mapped_column(Text, index=True)
