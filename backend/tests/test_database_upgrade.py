"""init_db upgrades pre-v1.1.0 databases whose tool_used CHECK lacks qwen_vl_* values."""

import asyncio
import sqlite3

from app import database

_OLD_QUERIES = database._SCHEMA_SQL.split("CREATE TABLE IF NOT EXISTS queries")[1].replace(
    ", 'qwen_vl_vqa', 'qwen_vl_cap', 'qwen_vl_vg', 'qwen_vl_seg', 'qwen_vl_ccd'", ""
)
_ROW = ("q1", "what?", "[]", "vqa", "{TOOL}", None, "a", 0.5, "none", None, 10, 1, "success", None, "2026-01-01")


def _insert(path, tool):
    row = tuple(tool if v == "{TOOL}" else v for v in _ROW)
    c = sqlite3.connect(path)
    c.execute(f"INSERT INTO queries VALUES ({','.join('?' * len(row))})", row)
    c.commit()
    c.close()


def test_init_db_upgrades_stale_check_and_keeps_rows(tmp_path, monkeypatch):
    db = tmp_path / "satquery.db"
    c = sqlite3.connect(db)
    c.executescript("CREATE TABLE queries" + _OLD_QUERIES)
    c.close()
    _insert(db, "rsunivlm_vqa")

    monkeypatch.setattr(database, "DATABASE_PATH", str(db))
    asyncio.run(database.init_db())
    asyncio.run(database.init_db())  # idempotent

    c = sqlite3.connect(db)
    assert c.execute("SELECT id, tool_used FROM queries").fetchall() == [("q1", "rsunivlm_vqa")]
    c.close()
    _insert_new_id(db)  # a qwen_vl_* row would raise IntegrityError before the upgrade
    assert (tmp_path / "satquery.db.bak-pre-v1.1.0").exists()


def _insert_new_id(path):
    c = sqlite3.connect(path)
    row = ("q2",) + tuple("qwen_vl_cap" if v == "{TOOL}" else v for v in _ROW[1:])
    c.execute(f"INSERT INTO queries VALUES ({','.join('?' * len(row))})", row)
    c.commit()
    c.close()
