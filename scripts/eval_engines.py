"""
Side-by-side evaluation of AI engines on the curated sample_data scenarios.

Runs each scenario in-process through every requested engine (no HTTP server
needed) and writes a markdown report with task, answer, boxes, confidence,
confidence source and latency, so the default engine can be chosen on
evidence rather than assumption.

Usage (from repo root, inside the venv):
    python scripts/eval_engines.py --engines rsunivlm qwen hybrid --mode real
    python scripts/eval_engines.py --engines qwen --mode real --out reports/qwen_only.md
"""

from __future__ import annotations

import argparse
import base64
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.engines import build_engine  # noqa: E402
from app.orchestrator import _decode_image  # noqa: E402

S = ROOT / "sample_data"

# (name, task, query, [(path, modality)])
SCENARIOS = [
    ("Sentinel-2 caption", "captioning",
     "Describe the land cover, forests, and terrain characteristics in this satellite image.",
     [(S / "optical/real_sentinel2_austria_tci.tif", "optical")]),
    ("Sentinel-2 VQA", "vqa",
     "Is there a river crossing through this satellite scene?",
     [(S / "optical/real_sentinel2_austria_tci.tif", "optical")]),
    ("Airbase grounding", "detection",
     "Where are the aircraft parked on the apron?",
     [(S / "optical/optical_airbase_runway.tif", "optical")]),
    ("Port grounding", "detection",
     "Locate all ships in the harbour.",
     [(S / "optical/optical_port_rotterdam.tif", "optical")]),
    ("Water segmentation", "detection",
     "Highlight the water bodies in this image.",
     [(S / "optical/real_sentinel2_austria_tci.tif", "optical")]),
    ("SAR VQA", "vqa",
     "Analyze the radar backscatter intensity and identify high-reflectance metallic objects.",
     [(S / "sar/real_sentinel1_sar_grd_vv.tif", "sar")]),
    ("Bi-temporal change", "change_detection",
     "What changed between these two dates, and where did vegetation change occur?",
     [(S / "bitemporal_change/real_sentinel2_change_t1_2022.tif", "optical"),
      (S / "bitemporal_change/real_sentinel2_change_t2_2024.tif", "optical")]),
    ("Urban expansion change", "change_detection",
     "Describe the urban expansion between the two images.",
     [(S / "bitemporal_change/urban_expansion_t1_2021.tif", "optical"),
      (S / "bitemporal_change/urban_expansion_t2_2024.tif", "optical")]),
]


def _load(path: Path):
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    img, _geo = _decode_image(f"data:image/tiff;base64,{b64}")
    return img


def _run(engine, task, query, images):
    if task == "vqa":
        return engine.run_vqa(images[0], query)
    if task == "captioning":
        return engine.run_captioning(images[0])
    if task == "detection":
        return engine.run_detection(images[0], query)
    if task == "change_detection":
        return engine.run_change_detection(images[0], images[1], query)
    raise ValueError(task)


def _summarise(res: dict) -> str:
    text = res.get("answer") or res.get("caption") or ""
    parts = []
    if res.get("mode") == "bbox":
        parts.append(f"{len(res.get('boxes') or [])} box(es)")
    if res.get("mode") == "mask" or res.get("mask_base64"):
        parts.append("mask")
    labels = res.get("meta", {}).get("parameters", {}).get("detected_labels")
    if labels:
        parts.append("labels=" + ",".join(map(str, labels)))
    if text:
        parts.append(text.replace("\n", " ").replace("|", "/")[:400])
    return "; ".join(parts) or "(empty)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engines", nargs="+", default=["rsunivlm", "qwen", "hybrid"])
    ap.add_argument("--mode", default="real", choices=["real", "mock"])
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    print("Decoding sample images ...")
    loaded = {name: [_load(p) for p, _ in imgs] for name, _, _, imgs in SCENARIOS}

    rows = []
    for eng_name in args.engines:
        try:
            engine = build_engine(eng_name, args.mode)
        except Exception as exc:
            print(f"[{eng_name}] failed to load: {exc}")
            rows.append((eng_name, "(engine load)", "-", f"LOAD ERROR: {exc}", "-", "-", "-"))
            continue
        for name, task, query, _ in SCENARIOS:
            t0 = time.perf_counter()
            try:
                res = _run(engine, task, query, loaded[name])
                wall = int((time.perf_counter() - t0) * 1000)
                p = res["meta"].get("parameters", {})
                rows.append((eng_name, name, res["meta"]["tool_used"], _summarise(res),
                             f"{res['confidence']:.2f}", p.get("confidence_source", "?"), str(wall)))
                print(f"[{eng_name}] {name}: {wall} ms")
            except Exception as exc:
                traceback.print_exc()
                rows.append((eng_name, name, "-", f"ERROR: {exc}", "-", "-", "-"))

    out = Path(args.out) if args.out else ROOT / "reports" / f"engine_eval_{datetime.now():%Y%m%d_%H%M}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Engine evaluation — {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Mode: `{args.mode}` · Engines: {', '.join(args.engines)}",
        "",
        "| Engine | Scenario | Tool | Output | Conf | Conf source | Wall ms |",
        "|---|---|---|---|---|---|---|",
    ]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    lines += ["", "Quality must be judged by reading the outputs against the images; "
              "latency and confidence alone do not decide the default engine."]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
