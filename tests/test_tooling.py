"""Unit tests for the pure helpers in the live test tooling (quality regression, soak)."""

import base64
import io
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "quality"))
sys.path.insert(0, str(HERE / "soak"))

import quality_regression as qr  # noqa: E402
import soak  # noqa: E402


def test_iou():
    assert qr.iou([0, 0, 10, 10], [0, 0, 10, 10]) == 1.0
    assert qr.iou([0, 0, 10, 10], [10, 10, 20, 20]) == 0.0
    assert qr.iou([0, 0, 10, 10], [5, 0, 15, 10]) == pytest.approx(1 / 3)
    assert qr.iou([10, 10, 0, 0], [0, 0, 10, 10]) == 1.0  # corner order does not matter
    assert qr.iou([0, 0, 0, 0], [0, 0, 0, 0]) == 0.0


def test_recall_is_one_to_one_and_scales_grids():
    gold = [[0, 0, 10, 10], [20, 20, 30, 30]]
    assert qr.recall(gold, [[0, 0, 10, 10]], None, None) == 0.5
    assert qr.recall(gold, [[0, 0, 10, 10], [0, 0, 10, 10]], None, None) == 0.5  # one box cannot match twice
    # The new run used a half-size grid: its boxes are scaled up before matching
    assert qr.recall(gold, [[0, 0, 5, 5], [10, 10, 15, 15]], (100, 100), (50, 50)) == 1.0
    assert qr.recall([], [], None, None) == 1.0


def test_mask_fraction():
    a = np.zeros((10, 10), np.uint8)
    a[:5] = 255
    buf = io.BytesIO()
    Image.fromarray(a).save(buf, "PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    assert qr.mask_fraction(b64) == 0.5
    assert qr.mask_fraction("data:image/png;base64," + b64) == 0.5
    assert qr.mask_fraction(None) is None


def _ok(**kw):
    out = {"status": 200, "task": "detection", "evidence": "bbox", "answer": "Located.", "confidence": 0.8,
           "boxes": [[1, 1, 5, 5]] * 13, "image_size": [100, 100], "mask_frac": None, "wall_s": 2.0}
    out.update(kw)
    return out


def test_evaluate_hard_and_soft_checks():
    sc = qr.SCENARIOS["airbase_locate"]
    assert qr.evaluate("airbase_locate", sc, _ok(), None) == ([], [])
    hard, _ = qr.evaluate("airbase_locate", sc, _ok(boxes=[[1, 1, 5, 5]] * 3), None)
    assert any("3 boxes" in m for m in hard)
    hard, _ = qr.evaluate("airbase_locate", sc, _ok(boxes=[[1, 1, 500, 5]] * 13), None)
    assert any("outside the image" in m for m in hard)
    hard, _ = qr.evaluate("airbase_locate", sc, _ok(task="vqa"), None)
    assert any("task vqa" in m for m in hard)
    # Golden comparison: boxes elsewhere fail recall; slow is only soft
    gold = _ok(boxes=[[50, 50, 60, 60]] * 13, wall_s=0.5)
    hard, soft = qr.evaluate("airbase_locate", sc, _ok(wall_s=20.0), gold)  # > 3 x 0.5 s + 5 s slack
    assert any("recall" in m for m in hard) and any("slow" in m for m in soft)


def test_evaluate_fusion_percentages():
    sc = qr.SCENARIOS["fusion_cloud_water"]
    good = _ok(task="fusion", evidence="mask", boxes=[], mask_frac=0.5,
               answer="43.0% of the optical image is cloud-covered. Classes: 52.1% Water, 47.9% Built-up.")
    assert qr.evaluate("fusion_cloud_water", sc, good, None)[0] == []
    bad = dict(good, answer="75.7% Built-up; 10% of the optical image is cloud-covered, 5% Water.")
    hard, _ = qr.evaluate("fusion_cloud_water", sc, bad, None)
    assert any("water_pct" in m for m in hard) and any("cloud_pct" in m for m in hard)


def test_evaluate_reports_http_errors():
    hard, _ = qr.evaluate("x", qr.SCENARIOS["port_vqa_yes"], {"status": 503, "error": "QUEUE_FULL"}, None)
    assert hard == ["HTTP 503: QUEUE_FULL"]


def test_soak_percentile():
    assert soak.pct([], 95) is None
    assert soak.pct([3, 1, 2], 50) == 2
    assert soak.pct(list(range(100)), 95) == 95


def test_soak_orphan_files(tmp_path):
    db = sqlite3.connect(tmp_path / "satquery.db")
    db.execute("CREATE TABLE images (id TEXT)")
    db.execute("CREATE TABLE queries (id TEXT)")
    db.execute("INSERT INTO images VALUES ('keep')")
    db.execute("INSERT INTO queries VALUES ('q1')")
    db.commit()
    db.close()
    (tmp_path / "uploads" / "u1").mkdir(parents=True)
    (tmp_path / "evidence" / "u1").mkdir(parents=True)
    for name in ("keep.tif", "keep.preview.png", "gone.tif", "gone.preview.png"):
        (tmp_path / "uploads" / "u1" / name).write_bytes(b"x")
    for name in ("q1.json", "q2.json"):
        (tmp_path / "evidence" / "u1" / name).write_bytes(b"{}")
    out = soak.orphan_files(tmp_path)
    assert sorted(out["uploads"]) == ["uploads/u1/gone.preview.png", "uploads/u1/gone.tif"]
    assert out["evidence"] == ["evidence/u1/q2.json"]
