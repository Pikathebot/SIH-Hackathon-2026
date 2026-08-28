"""
SatQuery AI — Interactive Smoke Test Suite (Real & Mock AI Modes)

Runs end-to-end verification against the FastAPI backend, including
TIFF preview conversion, Austrian Sentinel-2 GeoTIFF scenes,
Sentinel-1 SAR water backscatter scenes, and dual-GeoTIFF metadata retention.

Usage:
    python smoke_test.py [--url http://localhost:8000]
"""

import argparse
import base64
import io
import os
import sys
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image

# Ensure project root is in path
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
backend_dir = project_root / "backend"
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))


def create_sample_image_base64(color=(100, 150, 200), size=(256, 256)) -> str:
    """Create a sample base64 PNG data URL."""
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64}"


def create_austrian_sentinel2_geotiff_base64(
    bounds: Tuple[float, float, float, float] = (16.30, 48.15, 16.45, 48.25),
    size: Tuple[int, int] = (256, 256),
    include_change: bool = False,
) -> str:
    """Creates a georeferenced Austrian Sentinel-2 optical GeoTIFF in EPSG:4326."""
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.transform import from_bounds

    w, h = size
    min_lon, min_lat, max_lon, max_lat = bounds
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)

    r = np.full((h, w), 0.15, dtype=np.float32)
    g = np.full((h, w), 0.18, dtype=np.float32)
    b = np.full((h, w), 0.14, dtype=np.float32)
    nir = np.full((h, w), 0.20, dtype=np.float32)

    # Vegetation zone
    g[50:180, 20:100] = 0.45
    nir[50:180, 20:100] = 0.70
    r[50:180, 20:100] = 0.05
    b[50:180, 20:100] = 0.06

    # Danube river channel
    for y in range(h):
        center_x = int(128 + 40 * np.sin(y / 40.0))
        river_width = 24 if not include_change else 36
        x_min = max(0, center_x - river_width // 2)
        x_max = min(w, center_x + river_width // 2)
        r[y, x_min:x_max] = 0.02
        g[y, x_min:x_max] = 0.08
        b[y, x_min:x_max] = 0.35
        nir[y, x_min:x_max] = 0.01

    if include_change:
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


def create_sentinel1_sar_geotiff_base64(
    bounds: Tuple[float, float, float, float] = (16.30, 48.15, 16.45, 48.25),
    size: Tuple[int, int] = (256, 256),
) -> str:
    """Creates a Sentinel-1 SAR GeoTIFF with specular water and double-bounce urban."""
    import rasterio
    from rasterio.io import MemoryFile
    from rasterio.transform import from_bounds

    w, h = size
    min_lon, min_lat, max_lon, max_lat = bounds
    transform = from_bounds(min_lon, min_lat, max_lon, max_lat, w, h)

    vv = np.full((h, w), 0.35, dtype=np.float32)
    vh = np.full((h, w), 0.25, dtype=np.float32)

    for y in range(h):
        center_x = int(128 + 40 * np.sin(y / 40.0))
        river_width = 24
        x_min = max(0, center_x - river_width // 2)
        x_max = min(w, center_x + river_width // 2)
        vv[y, x_min:x_max] = 0.05  # Specular water
        vh[y, x_min:x_max] = 0.03

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


def run_tests(base_url: str = None):
    ai_mode = os.environ.get("AI_SERVICE_MODE", "real")
    print("=" * 70)
    print("         SatQuery AI — System Verification & Smoke Test")
    print(f"         AI Inference Mode: {ai_mode.upper()}")
    print("=" * 70)

    if base_url:
        import httpx
        client = httpx.Client(base_url=base_url, timeout=45.0)
        print(f"[*] Testing against live server: {base_url}\n")
    else:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        print(f"[*] Testing in-process via FastAPI TestClient (AI_SERVICE_MODE={ai_mode})\n")

    # Generate test fixtures
    s2_optical_tif = create_austrian_sentinel2_geotiff_base64()
    s2_optical_tif_change = create_austrian_sentinel2_geotiff_base64(include_change=True)
    s1_sar_tif = create_sentinel1_sar_geotiff_base64()
    std_png = create_sample_image_base64(color=(60, 120, 80))

    scenarios = [
        {
            "name": "1. Health Check (GET /api/v1/health)",
            "endpoint": "/api/v1/health",
            "method": "GET",
            "payload": None,
            "validate": lambda r: r.status_code == 200 and r.json().get("status") == "ok",
        },
        {
            "name": "2. GeoTIFF Browser Preview Conversion (POST /api/v1/preview)",
            "endpoint": "/api/v1/preview",
            "method": "POST",
            "payload": {"url_or_base64": s2_optical_tif},
            "validate": lambda r: (
                r.status_code == 200
                and r.json().get("format") == "geotiff"
                and r.json().get("preview_base64", "").startswith("data:image/png;base64,")
                and r.json().get("geospatial", {}).get("crs") is not None
            ),
        },
        {
            "name": "3. Visual Q&A on Austrian Sentinel-2 GeoTIFF",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Is there a river crossing through this satellite scene?",
                "images": [{"id": "s2-vienna", "modality": "optical", "url_or_base64": s2_optical_tif}],
            },
            "validate": lambda r: (
                r.status_code == 200
                and r.json().get("task") == "vqa"
                and len(r.json().get("answer", "")) > 0
                and r.json().get("visual_evidence", {}).get("geospatial") is not None
            ),
        },
        {
            "name": "4. Object Detection (Bounding Boxes)",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Locate and detect all ships in the harbor",
                "images": [{"id": "opt-1", "modality": "optical", "url_or_base64": std_png}],
            },
            "validate": lambda r: (
                r.status_code == 200
                and r.json().get("task") == "detection"
                and r.json()["visual_evidence"]["type"] == "bbox"
            ),
        },
        {
            "name": "5. Danube River & Water Body Segmentation Mask",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Segment the Danube river channel and water bodies",
                "images": [{"id": "s2-danube", "modality": "optical", "url_or_base64": s2_optical_tif}],
            },
            "validate": lambda r: (
                r.status_code == 200
                and r.json().get("task") == "detection"
                and r.json()["visual_evidence"]["type"] == "mask"
                and r.json()["visual_evidence"]["mask_base64"] is not None
            ),
        },
        {
            "name": "6. Temporal Change Detection with Dual GeoTIFF Metadata",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "What infrastructure changed between these two dates?",
                "images": [
                    {"id": "img-2023", "modality": "optical", "date": "2023-04-01", "url_or_base64": s2_optical_tif},
                    {"id": "img-2024", "modality": "optical", "date": "2024-05-01", "url_or_base64": s2_optical_tif_change},
                ],
            },
            "validate": lambda r: (
                r.status_code == 200
                and r.json().get("task") == "change_detection"
                and r.json()["visual_evidence"]["geospatial"]["secondary_image_bounds"] is not None
            ),
        },
        {
            "name": "7. Optical-SAR Radar Fusion (Sentinel-2 + Sentinel-1)",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Fuse optical and SAR radar imagery to classify built-up and water bodies",
                "images": [
                    {"id": "opt-1", "modality": "optical", "url_or_base64": s2_optical_tif},
                    {"id": "sar-1", "modality": "sar", "url_or_base64": s1_sar_tif},
                ],
            },
            "validate": lambda r: (
                r.status_code == 200
                and r.json().get("task") == "fusion"
                and r.json().get("execution_summary", {}).get("tool_used") == "fusion_classifier"
                and r.json().get("execution_summary", {}).get("parameters", {}).get("water_coverage_pct") is not None
            ),
        },
        {
            "name": "8. Error Guardrail — Invalid Modality Combo (2 SAR images)",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Analyze these",
                "images": [
                    {"id": "sar-1", "modality": "sar", "url_or_base64": s1_sar_tif},
                    {"id": "sar-2", "modality": "sar", "url_or_base64": s1_sar_tif},
                ],
            },
            "validate": lambda r: (
                r.status_code == 400
                and r.json().get("error", {}).get("code") == "INVALID_MODALITY_COMBINATION"
            ),
        },
    ]

    passed = 0
    for s in scenarios:
        name = s["name"]
        print(f"▶ {name}")
        try:
            if s["method"] == "GET":
                resp = client.get(s["endpoint"])
            else:
                resp = client.post(s["endpoint"], json=s["payload"])

            if s["validate"](resp):
                passed += 1
                data = resp.json()
                print(f"  \033[92m✔ PASS\033[0m (Status: {resp.status_code})")
                if data.get("task"):
                    print(f"    • Task:        {data.get('task')}")
                    if data.get("answer"):
                        print(f"    • Answer:      {data.get('answer')[:75]}...")
                    elif data.get("visual_evidence", {}).get("boxes"):
                        print(f"    • Boxes Found: {len(data['visual_evidence']['boxes'])}")
                    elif data.get("visual_evidence", {}).get("mask_base64"):
                        print(f"    • Mask Size:   Binary mask generated")
                    print(f"    • Confidence:  {data.get('confidence'):.2f} (Source: {data.get('execution_summary', {}).get('parameters', {}).get('confidence_source', 'heuristic')})")
                    print(f"    • Tool Used:   {data.get('execution_summary', {}).get('tool_used')}")
                    print(f"    • Latency:     {data.get('execution_summary', {}).get('latency_ms')} ms")
                    if data.get("visual_evidence", {}).get("geospatial"):
                        geo = data["visual_evidence"]["geospatial"]
                        print(f"    • CRS:         {geo.get('crs')}")
                        print(f"    • Bounds (WGS84): {geo.get('image_bounds')}")
                        if geo.get("secondary_image_bounds"):
                            print(f"    • Secondary Bounds: {geo.get('secondary_image_bounds')}")
                elif "preview_base64" in data:
                    print(f"    • Format:      {data.get('format')}")
                    print(f"    • Dimension:   {data.get('width')}x{data.get('height')}")
                    print(f"    • CRS:         {data.get('geospatial', {}).get('crs')}")
                elif "status" in data:
                    print(f"    • Status:      {data.get('status')} (RSUniVLM: {data.get('rsunivlm_loaded')}, Fusion: {data.get('fusion_loaded')})")
                elif "error" in data:
                    print(f"    • Error Code:  {data.get('error', {}).get('code')} -> {data.get('error', {}).get('message')}")
            else:
                print(f"  \033[91m✘ FAIL\033[0m: Status {resp.status_code}, Body: {resp.text[:140]}")
        except Exception as e:
            print(f"  \033[91m✘ EXCEPTION\033[0m: {e}")
        print()

    print("=" * 70)
    print(f"Results: {passed} / {len(scenarios)} passed.")
    if passed == len(scenarios):
        print("\033[92mALL SCENARIOS PASSED! System is fully functional.\033[0m")
    else:
        print("\033[91mSome scenarios failed. Check logs above.\033[0m")
    print("=" * 70)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SatQuery AI Smoke Test")
    parser.add_argument("--url", default=None, help="Live server URL, e.g. http://localhost:8000")
    args = parser.parse_args()
    run_tests(args.url)
