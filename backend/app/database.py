"""
Database module — SQLite via aiosqlite.

Schema matches DATABASE_CONTRACT.md v1.0.0 exactly.
Uses create_all() approach per DATABASE_CONTRACT.md §4 (no Alembic for sprint).
"""

import shutil
from pathlib import Path

import aiosqlite

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
);
"""


_QUERIES_COLUMNS = (
    "id, query_text, image_ids, selected_task, tool_used, parameters, answer, confidence, "
    "visual_evidence_type, visual_evidence_ref, latency_ms, inputs_validated, status, "
    "error_code, created_at"
)


async def _upgrade_queries_tool_used_check(db: aiosqlite.Connection, db_path: Path) -> None:
    """Rebuild `queries` if it predates the DATABASE_CONTRACT v1.1.0 `qwen_vl_*` tool_used values.

    `CREATE TABLE IF NOT EXISTS` never alters an existing table and SQLite cannot change a
    CHECK constraint in place, so databases created before v1.1.0 reject every Qwen-engine
    row. Rows are copied across unchanged; the file is backed up once beforehand. Stopgap
    until Alembic migrations land.
    """
    async with db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='queries'") as cur:
        row = await cur.fetchone()
    if not row or "qwen_vl_vqa" in row[0]:
        return
    backup = db_path.with_name(db_path.name + ".bak-pre-v1.1.0")
    if not backup.exists():
        shutil.copy2(db_path, backup)
    await db.execute("ALTER TABLE queries RENAME TO queries_pre_v110")
    await db.executescript(_SCHEMA_SQL)
    await db.execute(
        f"INSERT INTO queries ({_QUERIES_COLUMNS}) SELECT {_QUERIES_COLUMNS} FROM queries_pre_v110"
    )
    await db.execute("DROP TABLE queries_pre_v110")


async def init_db() -> None:
    """Create tables if they don't exist (and upgrade stale ones). Safe to call on every startup."""
    db_path = Path(DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(str(db_path)) as db:
        await db.executescript(_SCHEMA_SQL)
        await _upgrade_queries_tool_used_check(db, db_path)
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
