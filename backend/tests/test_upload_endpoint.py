"""
Integration tests for the file upload endpoint (POST /api/v1/upload and GET /api/v1/assets/{asset_id}).
"""

import io
import numpy as np
from PIL import Image
import pytest
from fastapi.testclient import TestClient
import rasterio
import rasterio.transform

from app.main import app
from app.routers.upload import cleanup_expired_uploads, UPLOAD_DIR


def _create_synthetic_geotiff_bytes(width: int = 500, height: int = 500) -> bytes:
    """Helper to create an in-memory 3-band GeoTIFF."""
    arr = np.random.randint(10, 240, (3, height, width), dtype=np.uint8)
    transform = rasterio.transform.from_bounds(77.0, 28.0, 77.2, 28.2, width, height)
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


def test_upload_geotiff_success():
    """Verify multipart upload of a GeoTIFF returns asset ID, dimensions, preview, and geospatial metadata."""
    tiff_bytes = _create_synthetic_geotiff_bytes(600, 400)
    client = TestClient(app)

    files = {"file": ("satellite_scene.tif", tiff_bytes, "image/tiff")}
    response = client.post("/api/v1/upload", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"].startswith("ast_")
    assert data["filename"] == "satellite_scene.tif"
    assert data["format"] == "geotiff"
    assert data["width"] == 600
    assert data["height"] == 400
    assert data["preview_base64"].startswith("data:image/png;base64,")
    assert data["geospatial"] is not None
    assert data["geospatial"]["crs"] == "EPSG:4326"

    # Verify asset retrieval
    asset_url = data["url"]
    get_res = client.get(asset_url)
    assert get_res.status_code == 200
    assert len(get_res.content) == len(tiff_bytes)


def test_upload_standard_image():
    """Verify upload of a standard PNG."""
    img = Image.new("RGB", (300, 200), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()

    client = TestClient(app)
    files = {"file": ("test_optical.png", png_bytes, "image/png")}
    response = client.post("/api/v1/upload", files=files)

    assert response.status_code == 200
    data = response.json()
    assert data["asset_id"].startswith("ast_")
    assert data["format"] == "standard"
    assert data["width"] == 300
    assert data["height"] == 200
    assert data["geospatial"] is None


def test_asset_not_found():
    """Verify 404 for invalid asset ID."""
    client = TestClient(app)
    response = client.get("/api/v1/assets/ast_nonexistent999.tif")
    assert response.status_code == 404
