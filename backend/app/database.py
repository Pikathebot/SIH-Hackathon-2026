"""
Database module — SQLite via aiosqlite.

Schema matches DATABASE_CONTRACT.md v1.0.0 exactly.
Uses create_all() approach per DATABASE_CONTRACT.md §4 (no Alembic for sprint).
"""

import aiosqlite
from pathlib import Path

from app.config import DATABASE_PATH


# ---------------------------------------------------------------------------
# Schema DDL — matches DATABASE_CONTRACT.md §1 exactly
# ---------------------------------------------------------------------------
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS images (
    id              TEXT PRIMARY KEY,
    modality        TEXT NOT NULL CHECK(modality IN ('optical', 'sar')),
    capture_date    TEXT,
    storage_path    TEXT NOT NULL,
    checksum        TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS queries (
    id                      TEXT PRIMARY KEY,
    query_text              TEXT NOT NULL,
    image_ids               TEXT NOT NULL,
    selected_task           TEXT NOT NULL CHECK(selected_task IN ('vqa', 'captioning', 'detection', 'change_detection', 'fusion')),
    tool_used               TEXT NOT NULL CHECK(tool_used IN ('rsunivlm_vqa', 'rsunivlm_cap', 'rsunivlm_vg', 'rsunivlm_seg', 'rsunivlm_ccd', 'fusion_classifier')),
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
);
"""


async def init_db() -> None:
    """Create tables if they don't exist. Safe to call on every startup."""
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(_SCHEMA_SQL)
        await db.commit()


async def get_db() -> aiosqlite.Connection:
    """
    Open and return an aiosqlite connection.

    Caller is responsible for closing the connection when done:
        db = await get_db()
        try:
            ...
        finally:
            await db.close()
    """
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    return db
