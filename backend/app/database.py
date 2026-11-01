"""
Database: SQLAlchemy 2 (async) + Alembic, per DATABASE_CONTRACT.md v1.1.0 §5.

- `engine` / `SessionLocal` come from `settings.resolved_database_url`
  (SQLite by default; Postgres by changing DATABASE_URL only).
- `get_session` is the FastAPI dependency for a request-scoped AsyncSession.
- `init_db()` runs on startup: it brings any database to `alembic upgrade head`,
  adopting pre-Alembic databases in place (stamp 0001) instead of recreating them.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path
from typing import AsyncIterator

from alembic import command
from alembic.config import Config
from sqlalchemy import event, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent

_is_sqlite = settings.resolved_database_url.startswith("sqlite")
# SQLite: no pool (connections are cheap and never shared across event loops, e.g. in
# tests or alembic's own loop). Postgres: the default pool.
engine = create_async_engine(settings.resolved_database_url,
                             **({"poolclass": NullPool} if _is_sqlite else {"pool_pre_ping": True}))
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

if engine.dialect.name == "sqlite":
    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def alembic_config(url: str | None = None) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url or settings.resolved_database_url)
    return cfg


# ---------------------------------------------------------------------------
# Adopting pre-Alembic databases
# ---------------------------------------------------------------------------
_QUERIES_COLUMNS = (
    "id, query_text, image_ids, selected_task, tool_used, parameters, answer, confidence, "
    "visual_evidence_type, visual_evidence_ref, latency_ms, inputs_validated, status, "
    "error_code, created_at"
)


def _sqlite_db_path(url: str) -> Path | None:
    prefix = "sqlite+aiosqlite:///"
    return Path(url[len(prefix):]) if url.startswith(prefix) else None


def _inspect_legacy(conn: Connection) -> tuple[bool, bool, str | None]:
    insp = inspect(conn)
    tables = set(insp.get_table_names())
    queries_sql = None
    if "queries" in tables and conn.dialect.name == "sqlite":
        queries_sql = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='queries'")
        ).scalar()
    return "queries" in tables, "alembic_version" in tables, queries_sql


# The 0001 `queries` table, as SQLite DDL (this path only ever runs on SQLite).
_QUERIES_0001_DDL = """
CREATE TABLE queries (
    id                      TEXT PRIMARY KEY,
    query_text              TEXT NOT NULL,
    image_ids               TEXT NOT NULL,
    selected_task           TEXT NOT NULL CHECK(selected_task IN ('vqa', 'captioning', 'detection', 'change_detection', 'fusion')),
    tool_used               TEXT NOT NULL CHECK(tool_used IN ('rsunivlm_vqa', 'rsunivlm_cap', 'rsunivlm_vg', 'rsunivlm_seg', 'rsunivlm_ccd', 'qwen_vl_vqa', 'qwen_vl_cap', 'qwen_vl_vg', 'qwen_vl_seg', 'qwen_vl_ccd', 'fusion_classifier')),
    parameters              TEXT,
    answer                  TEXT,
    confidence              REAL NOT NULL,
    visual_evidence_type    TEXT NOT NULL CHECK(visual_evidence_type IN ('none', 'bbox', 'mask')),
    visual_evidence_ref     TEXT,
    latency_ms              INTEGER NOT NULL,
    inputs_validated        INTEGER NOT NULL CHECK(inputs_validated IN (0, 1)),
    status                  TEXT NOT NULL CHECK(status IN ('success', 'error')),
    error_code              TEXT,
    created_at              TEXT NOT NULL
)
"""


def _rebuild_queries_v110(conn: Connection) -> None:
    """Pre-v1.1.0 SQLite `queries` rejects qwen_vl_* values and SQLite cannot alter a CHECK.

    Rebuild the table from the 0001 definition, copying every row unchanged.
    """
    conn.execute(text("ALTER TABLE queries RENAME TO queries_pre_v110"))
    conn.execute(text(_QUERIES_0001_DDL))
    conn.execute(text(f"INSERT INTO queries ({_QUERIES_COLUMNS}) SELECT {_QUERIES_COLUMNS} FROM queries_pre_v110"))
    conn.execute(text("DROP TABLE queries_pre_v110"))


async def _adopt_legacy_database() -> None:
    async with engine.begin() as conn:
        has_queries, has_version, queries_sql = await conn.run_sync(_inspect_legacy)
        if not has_queries or has_version:
            return
        if queries_sql is not None and "qwen_vl_vqa" not in queries_sql:
            db_path = _sqlite_db_path(settings.resolved_database_url)
            if db_path and db_path.exists():
                backup = db_path.with_name(db_path.name + ".bak-pre-v1.1.0")
                if not backup.exists():
                    shutil.copy2(db_path, backup)
            await conn.run_sync(_rebuild_queries_v110)
            logger.info("Rebuilt legacy queries table with the v1.1.0 tool_used CHECK")
    await asyncio.to_thread(command.stamp, alembic_config(), "0001")
    logger.info("Adopted pre-Alembic database at revision 0001")


async def init_db() -> None:
    """Bring the database to the latest schema. Safe to call on every startup."""
    db_path = _sqlite_db_path(settings.resolved_database_url)
    if db_path:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    await _adopt_legacy_database()
    # Alembic's async env.py calls asyncio.run(), so run it outside this event loop.
    await asyncio.to_thread(command.upgrade, alembic_config(), "head")
