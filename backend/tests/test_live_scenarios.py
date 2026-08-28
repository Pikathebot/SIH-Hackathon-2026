"""
Live end-to-end scenario tests for Austrian Sentinel-2 optical and Sentinel-1 SAR scenes.
Validates GeoTIFF preview conversion, dual-GeoTIFF metadata retention,
water/river segmentation mask extraction, and Optical-SAR fusion in Real AI Mode.
"""

import base64
import io
import os
import sys
from pathlib import Path
from typing import Tuple

import numpy as np
import pytest
import pytest_asyncio
import rasterio
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from httpx import ASGITransport, AsyncClient

# Ensure project root is in sys.path
_project_root = str(Path(__file__).resolve().parent.parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from app.main import app


def create_austrian_sentinel2_geotiff_base64(
    bounds: Tuple[float, float, float, float] = (16.30, 48.15, 16.45, 48.25),
    size: Tuple[int, int] = (256, 256),
    include_expanded_change: bool = False,
) -> str:
    """
    Creates an Austrian Sentinel-2 optical GeoTIFF (Vienna Danube Corridor) in WGS84 (EPSG:4326).
    Bands: 1: Red (B4), 2: Green (B3), 3: Blue (B2), 4: NIR (B8).
    Includes a distinct Danube river channel with high water absorption.
    """
    w, h = size
    min_lon, min_lat, max_lon, max_lat = bounds
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)

    # Initialize bands as float32 reflectance [0.0, 1.0]
    r = np.full((h, w), 0.15, dtype=np.float32)  # Base urban/soil
    g = np.full((h, w), 0.18, dtype=np.float32)
    b = np.full((h, w), 0.14, dtype=np.float32)
    nir = np.full((h, w), 0.20, dtype=np.float32)

    # Vegetation zone (Vienna Woods / Prater Park)
    g[50:180, 20:100] = 0.45
    nir[50:180, 20:100] = 0.70
    r[50:180, 20:100] = 0.05
    b[50:180, 20:100] = 0.06

    # Danube River channel (curving blue water body)
    for y in range(h):
        center_x = int(128 + 40 * np.sin(y / 40.0))
        river_width = 24 if not include_expanded_change else 36
        x_min = max(0, center_x - river_width // 2)
        x_max = min(w, center_x + river_width // 2)
        r[y, x_min:x_max] = 0.02
        g[y, x_min:x_max] = 0.08
        b[y, x_min:x_max] = 0.35
        nir[y, x_min:x_max] = 0.01  # Strong NIR water absorption

    # If expanded change (e.g. new bridge/construction site)
    if include_expanded_change:
        r[110:140, 180:230] = 0.55
        g[110:140, 180:230] = 0.50
        b[110:140, 180:230] = 0.48

    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=h,
            width=w,
            count=4,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(r, 1)
            dst.write(g, 2)
            dst.write(b, 3)
            dst.write(nir, 4)
        raw_bytes = mem.read()

    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:image/tiff;base64,{b64_str}"


def create_sentinel1_sar_water_geotiff_base64(
    bounds: Tuple[float, float, float, float] = (16.30, 48.15, 16.45, 48.25),
    size: Tuple[int, int] = (256, 256),
) -> str:
    """
    Creates a Sentinel-1 SAR GeoTIFF (VV + VH amplitude backscatter).
    Water bodies exhibit specular reflection with very low backscatter (< 0.15).
    """
    w, h = size
    min_lon, min_lat, max_lon, max_lat = bounds
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)

    # Base volume scattering
    vv = np.full((h, w), 0.35, dtype=np.float32)
    vh = np.full((h, w), 0.25, dtype=np.float32)

    # Danube river specular backscatter
    for y in range(h):
        center_x = int(128 + 40 * np.sin(y / 40.0))
        river_width = 24
        x_min = max(0, center_x - river_width // 2)
        x_max = min(w, center_x + river_width // 2)
        vv[y, x_min:x_max] = 0.05  # Specular water
        vh[y, x_min:x_max] = 0.03

    # Urban double-bounce structures
    vv[180:240, 160:240] = 0.85
    vh[180:240, 160:240] = 0.70

    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            height=h,
            width=w,
            count=2,
            dtype="float32",
            crs="EPSG:4326",
            transform=transform,
        ) as dst:
            dst.write(vv, 1)
            dst.write(vh, 2)
        raw_bytes = mem.read()

    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
    return f"data:image/tiff;base64,{b64_str}"


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestLiveSentinelScenarios:
    """Live scenarios testing Sentinel-2 optical and Sentinel-1 SAR scenes."""

    @pytest.mark.asyncio
    async def test_preview_endpoint_austrian_sentinel2(self, client):
        """POST /api/v1/preview renders a normalized PNG data URL for an Austrian Sentinel-2 GeoTIFF."""
        s2_tif = create_austrian_sentinel2_geotiff_base64()
        resp = await client.post("/api/v1/preview", json={"url_or_base64": s2_tif})
        assert resp.status_code == 200

        data = resp.json()
        assert data["format"] == "geotiff"
        assert data["preview_base64"].startswith("data:image/png;base64,")
        assert data["width"] == 256
        assert data["height"] == 256
        assert data["geospatial"] is not None
        assert "EPSG:4326" in data["geospatial"]["crs"]
        assert len(data["geospatial"]["image_bounds"]) == 4

    @pytest.mark.asyncio
    async def test_vqa_austrian_sentinel2(self, client):
        """POST /api/v1/query with an Austrian Sentinel-2 GeoTIFF returns VQA response with CRS bounds."""
        s2_tif = create_austrian_sentinel2_geotiff_base64()
        payload = {
            "query": "Is there a river crossing through this satellite scene?",
            "images": [{"id": "s2_austria", "modality": "optical", "url_or_base64": s2_tif}],
        }
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 200

        data = resp.json()
        assert data["task"] == "vqa"
        assert len(data["answer"]) > 0
        assert data["visual_evidence"]["geospatial"] is not None
        assert "EPSG:4326" in data["visual_evidence"]["geospatial"]["crs"]

    @pytest.mark.asyncio
    async def test_water_segmentation_austrian_sentinel2(self, client):
        """POST /api/v1/query with a water body query generates a water segmentation mask and overlay."""
        s2_tif = create_austrian_sentinel2_geotiff_base64()
        payload = {
            "query": "Segment the Danube river and water bodies in this region",
            "images": [{"id": "s2_austria", "modality": "optical", "url_or_base64": s2_tif}],
        }
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 200

        data = resp.json()
        assert data["task"] == "detection"
        assert data["visual_evidence"]["type"] == "mask"
        assert data["visual_evidence"]["mask_base64"] is not None
        assert data["visual_evidence"]["overlay_base64"] is not None
        assert data["visual_evidence"]["geospatial"] is not None

    @pytest.mark.asyncio
    async def test_dual_geotiff_change_detection_preserves_both_bounds(self, client):
        """Bi-temporal change detection with two GeoTIFFs preserves primary and secondary bounds."""
        s2_pre = create_austrian_sentinel2_geotiff_base64(
            bounds=(16.30, 48.15, 16.45, 48.25),
            include_expanded_change=False,
        )
        s2_post = create_austrian_sentinel2_geotiff_base64(
            bounds=(16.30, 48.15, 16.45, 48.25),
            include_expanded_change=True,
        )
        payload = {
            "query": "What infrastructure changes occurred between these two dates?",
            "images": [
                {"id": "s2_2023", "modality": "optical", "date": "2023-04-10", "url_or_base64": s2_pre},
                {"id": "s2_2024", "modality": "optical", "date": "2024-05-15", "url_or_base64": s2_post},
            ],
        }
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 200

        data = resp.json()
        assert data["task"] == "change_detection"
        assert data["visual_evidence"]["geospatial"] is not None
        geo = data["visual_evidence"]["geospatial"]
        assert len(geo["image_bounds"]) == 4
        assert geo["secondary_image_bounds"] is not None
        assert len(geo["secondary_image_bounds"]) == 4

    @pytest.mark.asyncio
    async def test_optical_sar_water_fusion(self, client):
        """Optical + SAR fusion fuses spectral reflectance with radar specular backscatter."""
        s2_opt = create_austrian_sentinel2_geotiff_base64()
        s1_sar = create_sentinel1_sar_water_geotiff_base64()

        payload = {
            "query": "Fuse optical and SAR radar imagery to classify water bodies and urban structures",
            "images": [
                {"id": "s2_optical", "modality": "optical", "url_or_base64": s2_opt},
                {"id": "s1_radar", "modality": "sar", "url_or_base64": s1_sar},
            ],
        }
        resp = await client.post("/api/v1/query", json=payload)
        assert resp.status_code == 200

        data = resp.json()
        assert data["task"] == "fusion"
        assert data["visual_evidence"]["type"] == "mask"
        assert data["visual_evidence"]["overlay_base64"] is not None
        assert data["execution_summary"]["tool_used"] == "fusion_classifier"
        assert "water_coverage_pct" in data["execution_summary"]["parameters"]
        assert data["execution_summary"]["parameters"]["water_coverage_pct"] > 0
