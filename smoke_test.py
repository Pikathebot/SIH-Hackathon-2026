"""
SatQuery AI — Interactive Smoke Test Suite

Runs end-to-end verification against the FastAPI backend.
Works both standalone (in-process via TestClient) or against a live server.

Usage:
    uv run python smoke_test.py [--url http://localhost:8000]
"""

import sys
import os
import argparse
import base64
import io
from pathlib import Path
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

def run_tests(base_url: str = None):
    print("=" * 65)
    print("         SatQuery AI — System Verification & Smoke Test")
    print("=" * 65)

    if base_url:
        import httpx
        client = httpx.Client(base_url=base_url, timeout=30.0)
        print(f"[*] Testing against live server: {base_url}\n")
    else:
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        print("[*] Testing in-process via FastAPI TestClient (AI_SERVICE_MODE=mock)\n")

    img_optical_1 = create_sample_image_base64(color=(60, 120, 80))
    img_optical_2 = create_sample_image_base64(color=(80, 140, 100))
    img_sar = create_sample_image_base64(color=(150, 150, 150))

    scenarios = [
        {
            "name": "1. Health Check (GET /api/v1/health)",
            "endpoint": "/api/v1/health",
            "method": "GET",
            "payload": None,
            "validate": lambda r: r.status_code == 200 and r.json().get("status") == "ok",
        },
        {
            "name": "2. Visual Q&A (VQA)",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "How many aircraft are visible on the runway?",
                "images": [{"id": "img-1", "modality": "optical", "url_or_base64": img_optical_1}],
            },
            "validate": lambda r: r.status_code == 200 and r.json().get("task") == "vqa",
        },
        {
            "name": "3. Image Captioning",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Describe this satellite scene in detail",
                "images": [{"id": "img-1", "modality": "optical", "url_or_base64": img_optical_1}],
            },
            "validate": lambda r: r.status_code == 200 and r.json().get("task") == "captioning",
        },
        {
            "name": "4. Object Detection (Bounding Boxes)",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Locate and detect all ships in the harbor",
                "images": [{"id": "img-1", "modality": "optical", "url_or_base64": img_optical_1}],
            },
            "validate": lambda r: r.status_code == 200 and r.json().get("task") == "detection" and r.json()["visual_evidence"]["type"] == "bbox",
        },
        {
            "name": "5. Segmentation Mask Detection",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Segment the flood boundaries and water bodies",
                "images": [{"id": "img-1", "modality": "optical", "url_or_base64": img_optical_1}],
            },
            "validate": lambda r: r.status_code == 200 and r.json().get("task") == "detection" and r.json()["visual_evidence"]["type"] == "mask",
        },
        {
            "name": "6. Temporal Change Detection",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "What changed between these two dates?",
                "images": [
                    {"id": "img-pre", "modality": "optical", "date": "2023-01-01", "url_or_base64": img_optical_1},
                    {"id": "img-post", "modality": "optical", "date": "2023-06-01", "url_or_base64": img_optical_2},
                ],
            },
            "validate": lambda r: r.status_code == 200 and r.json().get("task") == "change_detection",
        },
        {
            "name": "7. Optical-SAR Fusion",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Analyze urban infrastructure fusing optical and radar sensors",
                "images": [
                    {"id": "opt-1", "modality": "optical", "url_or_base64": img_optical_1},
                    {"id": "sar-1", "modality": "sar", "url_or_base64": img_sar},
                ],
            },
            "validate": lambda r: r.status_code == 200 and r.json().get("task") == "fusion",
        },
        {
            "name": "8. Error Guardrail — Invalid Modality Combo (2 SAR images)",
            "endpoint": "/api/v1/query",
            "method": "POST",
            "payload": {
                "query": "Analyze these",
                "images": [
                    {"id": "sar-1", "modality": "sar", "url_or_base64": img_sar},
                    {"id": "sar-2", "modality": "sar", "url_or_base64": img_sar},
                ],
            },
            "validate": lambda r: r.status_code == 400 and r.json().get("error", {}).get("code") == "INVALID_MODALITY_COMBINATION",
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
                if "answer" in data:
                    print(f"    • Task:       {data.get('task')}")
                    print(f"    • Answer:     {data.get('answer')[:75]}...")
                    print(f"    • Confidence: {data.get('confidence'):.2f}")
                    print(f"    • Tool Used:  {data.get('execution_summary', {}).get('tool_used')}")
                    print(f"    • Latency:    {data.get('execution_summary', {}).get('latency_ms')} ms")
                elif "status" in data:
                    print(f"    • Status:     {data.get('status')} (RSUniVLM: {data.get('rsunivlm_loaded')}, Fusion: {data.get('fusion_loaded')})")
                elif "error" in data:
                    print(f"    • Error Code: {data.get('error', {}).get('code')} -> {data.get('error', {}).get('message')}")
            else:
                print(f"  \033[91m✘ FAIL\033[0m: Status {resp.status_code}, Body: {resp.text[:120]}")
        except Exception as e:
            print(f"  \033[91m✘ EXCEPTION\033[0m: {e}")
        print()

    print("=" * 65)
    print(f"Results: {passed} / {len(scenarios)} passed.")
    if passed == len(scenarios):
        print("\033[92mALL TESTS PASSED! System is fully functional.\033[0m")
    else:
        print("\033[91mSome tests failed. Check logs above.\033[0m")
    print("=" * 65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SatQuery AI Smoke Test")
    parser.add_argument("--url", default=None, help="Live server URL, e.g. http://localhost:8000")
    args = parser.parse_args()
    run_tests(args.url)
