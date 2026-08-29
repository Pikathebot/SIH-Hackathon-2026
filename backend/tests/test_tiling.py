"""
Unit and integration tests for sliding-window chip tiling, coordinate translation, and NMS.
"""

import io
import numpy as np
from PIL import Image
import pytest
import rasterio
import rasterio.transform

from app.tiling import (
    generate_sliding_windows,
    calculate_iou,
    translate_box_to_global,
    apply_nms,
    run_tiled_detection,
)


def _create_synthetic_geotiff(width: int = 3000, height: int = 2000) -> bytes:
    """Helper to create an in-memory multi-band GeoTIFF."""
    arr = np.random.randint(20, 200, (3, height, width), dtype=np.uint8)
    transform = rasterio.transform.from_bounds(78.0, 17.0, 78.5, 17.5, width, height)
    buf = io.BytesIO()
    with rasterio.open(
        buf,
        "w",
        driver="GTiff",
        height=height,
        width=width,
        count=3,
        dtype=arr.dtype,
        crs="EPSG:4326",
        transform=transform,
    ) as dst:
        dst.write(arr)
    return buf.getvalue()


def test_generate_sliding_windows():
    """Verify window generation covers boundaries without gaps."""
    width = 2500
    height = 1800
    chip_size = 1024
    overlap = 0.15

    windows = generate_sliding_windows(width, height, chip_size=chip_size, overlap_ratio=overlap)
    assert len(windows) > 0

    # Ensure the top-left starts at 0, 0
    assert windows[0].col_off == 0
    assert windows[0].row_off == 0

    # Ensure coverage extends to the rightmost and bottommost edges
    max_right = max(w.col_off + w.width for w in windows)
    max_bottom = max(w.row_off + w.height for w in windows)
    assert max_right == width
    assert max_bottom == height


def test_calculate_iou():
    """Verify IoU calculation for non-overlapping, partially overlapping, and identical boxes."""
    # Identical
    b1 = [10, 10, 100, 100]
    assert pytest.approx(calculate_iou(b1, b1), 0.01) == 1.0

    # Non-overlapping
    b2 = [200, 200, 300, 300]
    assert calculate_iou(b1, b2) == 0.0

    # Half overlap
    b3 = [55, 10, 145, 100]
    iou = calculate_iou(b1, b3)
    assert 0.3 < iou < 0.4


def test_translate_box_to_global():
    """Verify coordinate translation from local chip space to full scene."""
    local_box = [50, 60, 150, 160]
    col_off = 1000
    row_off = 500

    global_box = translate_box_to_global(local_box, col_off=col_off, row_off=row_off)
    assert global_box == [1050, 560, 1150, 660]


def test_apply_nms():
    """Verify NMS deduplication and bounding box union merging across tile seams."""
    boxes = [
        [100, 100, 200, 200],  # Box A
        [105, 102, 208, 204],  # Box A duplicate on seam
        [500, 500, 600, 600],  # Box B distinct
    ]
    confs = [0.90, 0.85, 0.75]

    filtered, filtered_confs = apply_nms(boxes, confidences=confs, iou_threshold=0.40, merge_overlapping=True)
    assert len(filtered) == 2
    # The merged box should span the union of [100, 100, 200, 200] and [105, 102, 208, 204]
    assert filtered[0] == [100, 100, 208, 204]
    assert filtered[1] == [500, 500, 600, 600]


def test_run_tiled_detection_mock():
    """Verify end-to-end sliding window detection on a synthetic large GeoTIFF."""
    tiff_bytes = _create_synthetic_geotiff(width=2200, height=1500)

    # Stub detection function returning a simulated object in each chip
    def stub_detector(chip: Image.Image, query: str):
        return {
            "mode": "bbox",
            "boxes": [[100, 100, 200, 200]],
            "confidence": 0.88,
            "meta": {"tool_used": "rsunivlm_det", "latency_ms": 50},
        }

    res = run_tiled_detection(
        raster_source=tiff_bytes,
        query="locate storage tanks",
        detection_fn=stub_detector,
        chip_size=1024,
        overlap_ratio=0.15,
    )

    assert res["mode"] == "bbox"
    assert len(res["boxes"]) > 0
    assert res["meta"]["tool_used"] in ("rsunivlm_vg", "rsunivlm_seg")
    assert res["meta"]["parameters"]["tiling"]["total_chips"] > 1
