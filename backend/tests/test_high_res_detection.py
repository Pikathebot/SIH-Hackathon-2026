"""
End-to-end integration test for high-resolution tiled detection referencing an uploaded asset ID.
"""

import io
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient
import rasterio
import rasterio.transform

from app.main import app


def _create_large_geotiff_bytes(width: int = 2400, height: int = 1800) -> bytes:
    """Helper to create a large synthetic multi-band GeoTIFF."""
    arr = np.random.randint(10, 240, (3, height, width), dtype=np.uint8)
    transform = rasterio.transform.from_bounds(77.0, 28.0, 77.5, 28.5, width, height)
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


def test_high_res_tiled_detection_query():
    """Verify that submitting a query with an uploaded asset ID performs sliding-window detection and returns geo_boxes."""
    tiff_bytes = _create_large_geotiff_bytes(2400, 1800)
    client = TestClient(app)

    # 1. Upload the large GeoTIFF
    files = {"file": ("large_scene.tif", tiff_bytes, "image/tiff")}
    up_res = client.post("/api/v1/upload", files=files)
    assert up_res.status_code == 200
    up_data = up_res.json()
    asset_url = up_data["url"]
    assert up_data["width"] == 2400
    assert up_data["height"] == 1800

    # 2. Run detection query referencing the asset URL
    query_payload = {
        "query": "Where are the solar panels in this scene?",
        "images": [
            {
                "id": "img_001",
                "modality": "optical",
                "url_or_base64": asset_url,
            }
        ],
    }
    res = client.post("/api/v1/query", json=query_payload)
    assert res.status_code == 200
    data = res.json()

    # 3. Assert detection results
    assert data["task"] == "detection"
    assert data["visual_evidence"]["type"] == "bbox"
    assert isinstance(data["visual_evidence"]["boxes"], list)
    assert len(data["visual_evidence"]["boxes"]) > 0

    # 4. Verify geospatial coordinates are computed
    assert data["visual_evidence"]["geospatial"] is not None
    assert data["visual_evidence"]["geospatial"]["crs"] == "EPSG:4326"
    assert "geo_boxes" in data["visual_evidence"]["geospatial"]
    assert len(data["visual_evidence"]["geospatial"]["geo_boxes"]) == len(data["visual_evidence"]["boxes"])

    # 5. Verify execution summary confirms tiled execution
    assert data["execution_summary"]["selected_task"] == "detection"
    assert data["execution_summary"]["tool_used"] in ("rsunivlm_vg", "rsunivlm_seg")
    assert "tiling" in data["execution_summary"]["parameters"]
    assert data["execution_summary"]["parameters"]["tiling"]["total_chips"] > 1
