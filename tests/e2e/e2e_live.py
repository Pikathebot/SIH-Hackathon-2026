"""
Live end-to-end pass against a running SatQuery stack, over HTTP only.

Covers the whole user journey: register, upload all bundled samples, one query per task
(caption, VQA, grounding, segmentation, SAR, change x2, fusion), history, a second user's
isolation, asset deletion and quota accounting, session deletion, logout.

Works against any deployment:
    python tests/e2e/e2e_live.py                                  # Vite dev proxy / nginx on :3000
    python tests/e2e/e2e_live.py --base http://127.0.0.1:8000     # backend directly
    python tests/e2e/e2e_live.py --mock                           # AI_SERVICE_MODE=mock: routing only
                                                                  # (start it with MOCK_FAST_MODE=1 to skip simulated latency)

In --mock mode the answers are canned, so only routing, contracts and persistence are
checked; without it every task must also produce its kind of evidence. Exits 1 on any failure.
"""

from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "sample_data"

UPLOADS = [
    "optical/real_sentinel2_austria_tci.tif", "optical/naip_airbase_davis_monthan.tif",
    "optical/naip_port_long_beach.tif", "optical/optical_sentinel2_lake.jp2",
    "sar/real_sentinel1_sar_grd_vv.tif", "sar/sar_port_rotterdam.tif",
    "bitemporal_change/real_sentinel2_change_t1_2022.tif", "bitemporal_change/real_sentinel2_change_t2_2024.tif",
    "bitemporal_change/urban_expansion_t1_2021.tif", "bitemporal_change/urban_expansion_t2_2024.tif",
    "cross_modal_fusion/cloudy_optical_scene.tif", "cross_modal_fusion/penetrating_sar_scene.tif",
]


class Run:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.n = 0

    def check(self, name: str, cond: bool, info: str = "") -> bool:
        self.n += 1
        print(("PASS " if cond else "FAIL ") + name + (f"  -- {info}" if info else ""), flush=True)
        if not cond:
            self.fails.append(name)
        return cond


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:3000", help="origin serving /api/v1 (default %(default)s)")
    ap.add_argument("--samples", type=Path, default=SAMPLES)
    ap.add_argument("--mock", action="store_true", help="the backend runs AI_SERVICE_MODE=mock")
    ap.add_argument("--timeout", type=float, default=600, help="per-request timeout, s (first real queries load models)")
    args = ap.parse_args()

    run = Run()
    check = run.check
    c = httpx.Client(base_url=args.base.rstrip("/") + "/api/v1", timeout=args.timeout)

    r = c.get("/health")
    if not check("health", r.status_code == 200, r.text[:200]):
        return 1

    r = c.post("/auth/register", json={"email": f"e2e-{uuid.uuid4().hex[:8]}@example.com", "password": "correct-horse-1"})
    if not check("register", r.status_code == 201, "" if r.status_code == 201 else r.text[:200]):
        return 1
    H = {"Authorization": f"Bearer {r.json()['access_token']}"}
    check("me", c.get("/auth/me", headers=H).status_code == 200)
    check("no token -> 401", c.get("/storage").status_code == 401)

    assets: dict[str, str] = {}
    for f in UPLOADS:
        p = args.samples / f
        t = time.time()
        r = c.post("/upload", headers=H, files={"file": (p.name, p.read_bytes())})
        ok = r.status_code == 200
        check(f"upload {p.name}", ok, f"{r.status_code} {int((time.time() - t) * 1000)} ms " + ("" if ok else r.text[:200]))
        if ok:
            j = r.json()
            assets[p.stem] = j["asset_id"]
            print(f"     {j['format']} {j['width']}x{j['height']} geo={bool(j.get('geospatial'))}")
    if len(assets) != len(UPLOADS):
        print("\nUploads failed; stopping.")
        return 1

    r = c.post("/sessions", headers=H, json={"title": "e2e"})
    check("create session", r.status_code == 201, "" if r.status_code == 201 else r.text[:200])
    sid = r.json()["id"]

    def img(stem: str, mod: str = "optical", date: str | None = None, i: str = "a") -> dict:
        d = {"id": i, "modality": mod, "asset_id": assets[stem]}
        if date:
            d["date"] = date
        return d

    # (name, query, images, expected task, expected evidence type when the engine is real)
    cases = [
        ("caption", "Describe this scene.", [img("real_sentinel2_austria_tci")], "captioning", None),
        ("vqa", "Is there a river in this image?", [img("real_sentinel2_austria_tci")], "vqa", None),
        ("grounding airbase", "Locate all aircraft.", [img("naip_airbase_davis_monthan")], "detection", "bbox"),
        ("grounding port", "Locate the ship and the gantry cranes.", [img("naip_port_long_beach")], "detection", "bbox"),
        ("segmentation", "Segment the water.", [img("optical_sentinel2_lake")], "detection", "mask"),
        ("sar vqa", "Are there bright metallic targets?", [img("real_sentinel1_sar_grd_vv", "sar")], "vqa", None),
        ("change", "What changed between these dates?",
         [img("real_sentinel2_change_t1_2022", date="2022-06-01"),
          img("real_sentinel2_change_t2_2024", date="2024-06-01", i="b")], "change_detection", None),
        ("urban change", "Show urban expansion.",
         [img("urban_expansion_t1_2021", date="2021-01-01"),
          img("urban_expansion_t2_2024", date="2024-01-01", i="b")], "change_detection", None),
        ("fusion", "Classify land cover under the clouds.",
         [img("cloudy_optical_scene"), img("penetrating_sar_scene", "sar", i="b")], "fusion", "mask"),
    ]
    for name, q, images, want_task, want_ev in cases:
        t = time.time()
        r = c.post("/query", headers=H, json={"query": q, "images": images, "session_id": sid})
        ms = int((time.time() - t) * 1000)
        if r.status_code != 200:
            check(f"query {name}", False, f"{r.status_code} {r.text[:300]}")
            continue
        j = r.json()
        ve = j["visual_evidence"]
        nb = len(ve.get("boxes") or [])
        ev = ve["type"] + (f" boxes={nb}" if ve["type"] == "bbox" else "")
        ok = j["task"] == want_task and bool(j["answer"].strip()) and 0.0 <= j["confidence"] <= 1.0
        if not args.mock and want_ev:
            ok = ok and ve["type"] == want_ev and (want_ev != "bbox" or (nb > 0 and bool(ve.get("image_size"))))
        check(f"query {name}", ok,
              f"task={j['task']} tool={j['execution_summary']['tool_used']} conf={j['confidence']:.2f} ev={ev} "
              f"geo={bool(ve.get('geospatial'))} {ms} ms")
        print("     " + j["answer"][:160].replace("\n", " "))

    r = c.get(f"/sessions/{sid}/queries", headers=H)
    n_hist = len(r.json()) if r.status_code == 200 else -1
    check("history", n_hist == len(cases), f"{r.status_code} n={n_hist}")
    r = c.get("/sessions", headers=H)
    check("sessions list", r.status_code == 200 and any(s["id"] == sid for s in r.json()))
    s1 = c.get("/storage", headers=H).json()
    print("     storage", s1)

    # A second user sees nothing of the first
    r = c.post("/auth/register", json={"email": f"e2e-b-{uuid.uuid4().hex[:8]}@example.com", "password": "correct-horse-2"})
    HB = {"Authorization": f"Bearer {r.json()['access_token']}"}
    air = assets["naip_airbase_davis_monthan"]
    check("B cannot read A session", c.get(f"/sessions/{sid}", headers=HB).status_code == 404)
    check("B cannot read A history", c.get(f"/sessions/{sid}/queries", headers=HB).status_code == 404)
    check("B cannot read A asset", c.get(f"/assets/{air}", headers=HB).status_code == 404)
    check("B cannot delete A asset", c.delete(f"/assets/{air}", headers=HB).status_code == 404)
    r = c.post("/query", headers=HB, json={"query": "Describe", "images": [img("naip_airbase_davis_monthan")]})
    check("B cannot query A asset", r.status_code in (403, 404), f"{r.status_code}")

    # Delete an asset: gone, quota freed, history kept
    check("asset preview", c.get(f"/assets/{air}/preview", headers=H).status_code == 200)
    check("delete asset", c.delete(f"/assets/{air}", headers=H).status_code == 204)
    check("deleted asset 404", c.get(f"/assets/{air}", headers=H).status_code == 404)
    r = c.post("/query", headers=H, json={"query": "Describe", "images": [img("naip_airbase_davis_monthan")]})
    check("query deleted asset -> 4xx", 400 <= r.status_code < 500, f"{r.status_code} {r.text[:150]}")
    s2 = c.get("/storage", headers=H).json()
    check("storage shrinks", s2["used_bytes"] < s1["used_bytes"] and s2["asset_count"] == s1["asset_count"] - 1)
    r = c.get(f"/sessions/{sid}/queries", headers=H)
    check("history survives asset delete", r.status_code == 200 and len(r.json()) == len(cases), f"{r.status_code}")

    check("delete session", c.delete(f"/sessions/{sid}", headers=H).status_code == 204)
    check("logout", c.post("/auth/logout", headers=H).status_code == 204)
    check("refresh after logout fails", c.post("/auth/refresh").status_code == 401)

    print(f"\n{run.n - len(run.fails)}/{run.n} checks passed" + (f"; FAILED: {run.fails}" if run.fails else ""))
    return 1 if run.fails else 0


if __name__ == "__main__":
    sys.exit(main())
