"""Alembic migrations: fresh databases and in-place adoption of pre-Alembic ones.

Runs `python -m app.migrate` in a subprocess with its own DATA_DIR, so it never
touches the test session's database or the developer's backend/data.
"""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

# A pre-v1.1.0 database as created by the old aiosqlite init_db (no qwen_vl_* values).
_LEGACY_DDL = """
CREATE TABLE images (
    id TEXT PRIMARY KEY, modality TEXT NOT NULL CHECK(modality IN ('optical', 'sar')),
    capture_date TEXT, storage_path TEXT NOT NULL, checksum TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE queries (
    id TEXT PRIMARY KEY, query_text TEXT NOT NULL, image_ids TEXT NOT NULL,
    selected_task TEXT NOT NULL CHECK(selected_task IN ('vqa', 'captioning', 'detection', 'change_detection', 'fusion')),
    tool_used TEXT NOT NULL CHECK(tool_used IN ('rsunivlm_vqa', 'rsunivlm_cap', 'rsunivlm_vg', 'rsunivlm_seg', 'rsunivlm_ccd', 'fusion_classifier')),
    parameters TEXT, answer TEXT, confidence REAL NOT NULL,
    visual_evidence_type TEXT NOT NULL CHECK(visual_evidence_type IN ('none', 'bbox', 'mask')),
    visual_evidence_ref TEXT, latency_ms INTEGER NOT NULL,
    inputs_validated INTEGER NOT NULL CHECK(inputs_validated IN (0, 1)),
    status TEXT NOT NULL CHECK(status IN ('success', 'error')), error_code TEXT, created_at TEXT NOT NULL);
INSERT INTO queries VALUES ('q1', 'what?', '[]', 'vqa', 'rsunivlm_vqa', NULL, 'a', 0.5, 'none', NULL,
                            10, 1, 'success', NULL, '2026-01-01');
"""


def _migrate(data_dir: Path, *args: str) -> None:
    env = {**os.environ, "DATA_DIR": str(data_dir)}
    env.pop("DATABASE_URL", None)
    subprocess.run([sys.executable, "-m", "app.migrate", *args], cwd=BACKEND, env=env, check=True,
                   capture_output=True, text=True)


def _tables(db: Path) -> set[str]:
    with sqlite3.connect(db) as c:
        return {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_fresh_database_upgrades_to_head(tmp_path):
    _migrate(tmp_path, "upgrade", "head")
    db = tmp_path / "satquery.db"
    assert {"users", "analysis_sessions", "refresh_tokens", "images", "queries", "alembic_version"} <= _tables(db)
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT version_num FROM alembic_version").fetchone() == ("0002",)


def test_legacy_database_is_adopted_in_place(tmp_path):
    db = tmp_path / "satquery.db"
    with sqlite3.connect(db) as c:
        c.executescript(_LEGACY_DDL)

    _migrate(tmp_path, "upgrade", "head")
    _migrate(tmp_path, "upgrade", "head")  # idempotent

    assert (tmp_path / "satquery.db.bak-pre-v1.1.0").exists()
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT id, tool_used, user_id, session_id FROM queries").fetchall() == [
            ("q1", "rsunivlm_vqa", None, None)]
        # The rebuilt CHECK now accepts Qwen-engine rows
        c.execute("INSERT INTO queries (id, query_text, image_ids, selected_task, tool_used, confidence, "
                  "visual_evidence_type, latency_ms, inputs_validated, status, created_at) "
                  "VALUES ('q2', 'q', '[]', 'vqa', 'qwen_vl_vqa', 0.9, 'none', 1, 1, 'success', 'x')")


def test_downgrade_then_upgrade_round_trips(tmp_path):
    _migrate(tmp_path, "upgrade", "head")
    _migrate(tmp_path, "downgrade", "0001")
    assert "users" not in _tables(tmp_path / "satquery.db")
    _migrate(tmp_path, "upgrade", "head")
    assert "users" in _tables(tmp_path / "satquery.db")
