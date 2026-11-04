"""
Model-quality regression: run fixed scenarios on the bundled real imagery through the API
of a running stack, and compare the outputs with a recorded known-good run, within
tolerances. Catches a model, quantisation, prompt or pre-processing change that quietly
makes answers worse while every unit test still passes.

    python tests/quality/quality_regression.py                       # check against golden_hybrid.json
    python tests/quality/quality_regression.py --record              # (re)record the golden file
    python tests/quality/quality_regression.py --base http://127.0.0.1:8000 --repeat 3

Needs AI_SERVICE_MODE=real. Each scenario has hard checks (fail the run) and soft checks
(reported only). Hard checks come from what a person verified on the images: the airbase
chip has 13 parked aircraft; the port has one berthed ship and 4 gantry cranes; the Austria
scene has no river; the fusion scene is ~43 % cloud with ~52 % water under it. Golden
comparisons (box IoU matching, mask area, latency) use the recorded run. Exits 1 on any
hard failure.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import re
import sys
import time
import uuid
from pathlib import Path

import httpx
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
SD = HERE.parents[1] / "sample_data"
GOLDEN = HERE / "golden_hybrid.json"

# Tolerances against the golden run
BOX_IOU = 0.3            # a box "matches" a golden box at IoU >= this
BOX_RECALL = 0.75        # share of golden boxes that must be matched
MASK_AREA_ABS = 0.10     # |mask fraction - golden| (fraction of the image)
LATENCY_FACTOR = 3.0     # wall time may be up to 3x the golden run (+ 5 s slack)

# name: (query, [(path, modality, date)], expected task, hard checks, soft checks)
SCENARIOS: dict[str, dict] = {
    "airbase_locate": {
        "query": "Locate all aircraft.",
        "images": [("optical/naip_airbase_davis_monthan.tif", "optical", None)],
        "task": "detection", "evidence": "bbox",
        "boxes": (11, 15),  # 13 aircraft, +-2
    },
    "port_locate": {
        "query": "Locate the ship and the gantry cranes.",
        "images": [("optical/naip_port_long_beach.tif", "optical", None)],
        "task": "detection", "evidence": "bbox",
        "boxes": (3, 7),  # 1 ship + 4 cranes
    },
    "port_vqa_yes": {
        "query": "Is there a ship berthed at the terminal?",
        "images": [("optical/naip_port_long_beach.tif", "optical", None)],
        "task": "vqa", "answer": r"^\s*yes\b",
    },
    "austria_vqa_no": {
        "query": "Is there a river in this image?",
        "images": [("optical/real_sentinel2_austria_tci.tif", "optical", None)],
        "task": "vqa", "answer": r"^\s*no\b",
    },
    "austria_caption": {
        "query": "Describe this scene.",
        "images": [("optical/real_sentinel2_austria_tci.tif", "optical", None)],
        "task": "captioning", "min_len": 60,
        "soft_answer": r"forest|vegetat|water|lake|mountain|field|agricultur|terrain",
    },
    "lake_segment": {
        "query": "Highlight the water bodies in this image.",
        "images": [("optical/optical_sentinel2_lake.jp2", "optical", None)],
        "task": "detection", "evidence": "mask", "mask_frac": (0.02, 0.9),
    },
    "urban_change": {
        "query": "What changed between these two dates, and where did new construction occur?",
        "images": [("bitemporal_change/urban_expansion_t1_2021.tif", "optical", "2021-01-01"),
                   ("bitemporal_change/urban_expansion_t2_2024.tif", "optical", "2024-01-01")],
        "task": "change_detection", "min_len": 60,
        "soft_answer": r"construct|build|urban|expan|road|develop",
    },
    "sea_change_none": {
        "query": "What changed between these two dates?",
        "images": [("bitemporal_change/real_sentinel2_change_t1_2022.tif", "optical", "2022-06-01"),
                   ("bitemporal_change/real_sentinel2_change_t2_2024.tif", "optical", "2024-06-01")],
        "task": "change_detection",
        # Open sea: the honest answer is that nothing concrete changed. Soft: wording varies.
        "soft_answer": r"\bno\b.{0,40}(change|differen)|unchanged|little|minimal|no (significant|notable|concrete|major)",
    },
    "fusion_cloud_water": {
        "query": "Use optical and radar images together to classify land cover under the clouds.",
        "images": [("cross_modal_fusion/cloudy_optical_scene.tif", "optical", None),
                   ("cross_modal_fusion/penetrating_sar_scene.tif", "sar", None)],
        "task": "fusion", "evidence": "mask",
        "answer": r"cloud-covered", "water_pct": (45, 60), "cloud_pct": (38, 48),
    },
}


def iou(a, b) -> float:
    ax1, ay1, ax2, ay2 = min(a[0], a[2]), min(a[1], a[3]), max(a[0], a[2]), max(a[1], a[3])
    bx1, by1, bx2, by2 = min(b[0], b[2]), min(b[1], b[3]), max(b[0], b[2]), max(b[1], b[3])
    iw, ih = max(0.0, min(ax2, bx2) - max(ax1, bx1)), max(0.0, min(ay2, by2) - max(ay1, by1))
    inter = iw * ih
    union = (ax2 - ax1) * (ay2 - ay1) + (bx2 - bx1) * (by2 - by1) - inter
    return inter / union if union > 0 else 0.0


def recall(golden: list, got: list, size_g, size_n) -> float:
    """Share of golden boxes matched one-to-one (greedy by IoU) after scaling to the same grid."""
    if not golden:
        return 1.0
    sx, sy = (size_g[0] / size_n[0], size_g[1] / size_n[1]) if size_g and size_n else (1.0, 1.0)
    got = [[b[0] * sx, b[1] * sy, b[2] * sx, b[3] * sy] for b in got]
    pairs = sorted(((iou(g, n), i, j) for i, g in enumerate(golden) for j, n in enumerate(got)), reverse=True)
    used_g, used_n, matched = set(), set(), 0
    for v, i, j in pairs:
        if v < BOX_IOU:
            break
        if i not in used_g and j not in used_n:
            used_g.add(i)
            used_n.add(j)
            matched += 1
    return matched / len(golden)


def mask_fraction(b64: str | None) -> float | None:
    if not b64:
        return None
    raw = base64.b64decode(b64.split(",", 1)[-1])
    a = np.asarray(Image.open(io.BytesIO(raw)).convert("L"))
    return float((a > 127).mean())


def run_scenario(c: httpx.Client, name: str, sc: dict, assets: dict) -> dict:
    images = []
    for i, (rel, mod, date) in enumerate(sc["images"]):
        d = {"id": "ab"[i], "modality": mod, "asset_id": assets[rel]}
        if date:
            d["date"] = date
        images.append(d)
    t0 = time.perf_counter()
    r = c.post("/query", json={"query": sc["query"], "images": images})
    wall = time.perf_counter() - t0
    if r.status_code != 200:
        return {"status": r.status_code, "error": r.text[:300], "wall_s": round(wall, 2)}
    j = r.json()
    ve = j["visual_evidence"]
    return {
        "status": 200, "wall_s": round(wall, 2), "task": j["task"], "tool": j["execution_summary"]["tool_used"],
        "confidence": j["confidence"], "answer": j["answer"], "evidence": ve["type"],
        "boxes": ve.get("boxes") or [], "image_size": ve.get("image_size"),
        "mask_frac": mask_fraction(ve.get("mask_base64")) if ve["type"] == "mask" else None,
    }


def evaluate(name: str, sc: dict, out: dict, gold: dict | None) -> tuple[list[str], list[str]]:
    hard, soft = [], []
    if out["status"] != 200:
        return [f"HTTP {out['status']}: {out.get('error')}"], soft
    if out["task"] != sc["task"]:
        hard.append(f"task {out['task']} != {sc['task']}")
    if sc.get("evidence") and out["evidence"] != sc["evidence"]:
        hard.append(f"evidence {out['evidence']} != {sc['evidence']}")
    ans = out["answer"] or ""
    if sc.get("answer") and not re.search(sc["answer"], ans, re.I):
        hard.append(f"answer does not match /{sc['answer']}/: {ans[:120]!r}")
    if sc.get("soft_answer") and not re.search(sc["soft_answer"], ans, re.I):
        soft.append(f"answer does not match /{sc['soft_answer']}/: {ans[:120]!r}")
    if sc.get("min_len") and len(ans) < sc["min_len"]:
        hard.append(f"answer only {len(ans)} chars")
    if not 0.0 <= out["confidence"] <= 1.0:
        hard.append(f"confidence {out['confidence']} out of range")
    if "boxes" in sc:
        lo, hi = sc["boxes"]
        n = len(out["boxes"])
        if not lo <= n <= hi:
            hard.append(f"{n} boxes, expected {lo}-{hi}")
        w, h = out["image_size"] or (None, None)
        if w and any(not (-1 <= v <= lim + 1) for b in out["boxes"] for v, lim in zip(b, (w, h, w, h))):
            hard.append("a box lies outside the image")
    if "mask_frac" in sc:
        lo, hi = sc["mask_frac"]
        f = out["mask_frac"]
        if f is None or not lo <= f <= hi:
            hard.append(f"mask fraction {f} outside {lo}-{hi}")
    for key, label in (("water_pct", "Water"), ("cloud_pct", "cloud")):
        if key in sc:
            pat = rf"(\d+(?:\.\d+)?)%\s*{label}" if label == "Water" else r"(\d+(?:\.\d+)?)%\s*of the optical image is cloud"
            m = re.search(pat, ans, re.I)
            v = float(m.group(1)) if m else None
            lo, hi = sc[key]
            if v is None or not lo <= v <= hi:
                hard.append(f"{key} {v} outside {lo}-{hi}")

    if gold and gold.get("status") == 200:
        if sc.get("evidence") == "bbox" and gold["boxes"]:
            rc = recall(gold["boxes"], out["boxes"], gold.get("image_size"), out.get("image_size"))
            (hard if rc < BOX_RECALL else []).append(f"box recall vs golden {rc:.2f} < {BOX_RECALL}")
            out["golden_recall"] = round(rc, 2)
        if out.get("mask_frac") is not None and gold.get("mask_frac") is not None:
            d = abs(out["mask_frac"] - gold["mask_frac"])
            if d > MASK_AREA_ABS:
                hard.append(f"mask area {out['mask_frac']:.3f} vs golden {gold['mask_frac']:.3f}")
        if out["wall_s"] > gold["wall_s"] * LATENCY_FACTOR + 5:
            soft.append(f"slow: {out['wall_s']} s vs golden {gold['wall_s']} s")
    return hard, soft


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--golden", type=Path, default=GOLDEN)
    ap.add_argument("--record", action="store_true", help="write the outputs as the new golden file")
    ap.add_argument("--repeat", type=int, default=1, help="run each scenario N times (stability)")
    ap.add_argument("--only", nargs="*", help="scenario names to run")
    args = ap.parse_args()

    c = httpx.Client(base_url=args.base.rstrip("/") + "/api/v1", timeout=900)
    h = c.get("/health").json()
    eng = h.get("engine") or {}
    print(f"engine: {eng.get('engine')} mode={eng.get('mode')} notes={eng.get('notes')}")
    if eng.get("mode") != "real":
        print("The backend is not in AI_SERVICE_MODE=real; quality checks are meaningless on mock output.")
        return 2
    r = c.post("/auth/register", json={"email": f"quality-{uuid.uuid4().hex[:8]}@example.com", "password": "quality-pass-123"})
    r.raise_for_status()
    c.headers["Authorization"] = "Bearer " + r.json()["access_token"]

    names = args.only or list(SCENARIOS)
    assets: dict[str, str] = {}
    for rel in sorted({p for n in names for p, _, _ in SCENARIOS[n]["images"]}):
        f = SD / rel
        res = c.post("/upload", files={"file": (f.name, f.read_bytes())})
        res.raise_for_status()
        assets[rel] = res.json()["asset_id"]

    golden = {} if args.record or not args.golden.exists() else json.loads(args.golden.read_text(encoding="utf-8"))["scenarios"]
    if not args.record and not golden:
        print(f"No golden file at {args.golden}: only the absolute checks run. Record one with --record.")

    results, n_hard = {}, 0
    for name in names:
        sc = SCENARIOS[name]
        for k in range(args.repeat):
            out = run_scenario(c, name, sc, assets)
            hard, soft = evaluate(name, sc, out, golden.get(name))
            n_hard += bool(hard)
            tag = "FAIL" if hard else "PASS"
            extra = f" boxes={len(out.get('boxes') or [])}" if out.get("boxes") else ""
            extra += f" mask={out['mask_frac']:.3f}" if out.get("mask_frac") is not None else ""
            extra += f" recall={out['golden_recall']}" if "golden_recall" in out else ""
            print(f"{tag} {name}{f' #{k + 1}' if args.repeat > 1 else ''}  {out.get('wall_s')} s{extra}  "
                  f"{(out.get('answer') or '')[:90]!r}".replace("\n", " "))
            for m in hard:
                print(f"     HARD {m}")
            for m in soft:
                print(f"     soft {m}")
            if k == 0:
                results[name] = out

    if args.record:
        if n_hard:
            print(f"\n{n_hard} scenario(s) failed their absolute checks; not recording a golden file from a bad run.")
            return 1
        payload = {"recorded": time.strftime("%Y-%m-%d %H:%M"), "engine": eng, "scenarios": results}
        args.golden.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"\nGolden written to {args.golden}")
        return 0
    print(f"\n{len(names) * args.repeat - n_hard}/{len(names) * args.repeat} scenario runs passed")
    return 1 if n_hard else 0


if __name__ == "__main__":
    sys.exit(main())
