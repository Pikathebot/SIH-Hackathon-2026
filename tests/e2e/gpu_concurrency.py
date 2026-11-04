"""
Real-GPU concurrency check: concurrent queries serialise through the GPU queue without
running out of memory, and overflow is refused cleanly with 503 QUEUE_FULL.

Needs AI_SERVICE_MODE=real on the machine running the backend, with nvidia-smi on PATH
if you want VRAM numbers (otherwise /health's NVML figure is used).

    python tests/e2e/gpu_concurrency.py                          # 2 queries (VQA + mask) via :3000
    python tests/e2e/gpu_concurrency.py --extra 6                # + 6 captions: some must get 503
    python tests/e2e/gpu_concurrency.py --base http://127.0.0.1:8000

Pass: no 5xx other than 503 QUEUE_FULL, the queue never runs more jobs than its
concurrency, the first two jobs both succeed, and peak VRAM stays below --max-vram-frac
(default 0.98) of the card. Exits 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

import httpx

SD = Path(__file__).resolve().parents[2] / "sample_data"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--extra", type=int, default=0, help="extra concurrent caption queries, to probe QUEUE_FULL")
    ap.add_argument("--max-vram-frac", type=float, default=0.98)
    args = ap.parse_args()
    base = args.base.rstrip("/")

    c = httpx.Client(base_url=base, timeout=900)
    r = c.post("/api/v1/auth/register", json={"email": f"gpu-{uuid.uuid4().hex[:8]}@example.com",
                                               "password": "correct-horse-battery"})
    r.raise_for_status()
    c.headers["Authorization"] = "Bearer " + r.json()["access_token"]

    def upload(p: Path) -> str:
        res = c.post("/api/v1/upload", files={"file": (p.name, p.read_bytes(), "application/octet-stream")})
        res.raise_for_status()
        return res.json()["asset_id"]

    port = upload(SD / "optical" / "naip_port_long_beach.tif")
    lake = upload(SD / "optical" / "real_sentinel2_austria_tci.tif")
    jobs = [("vqa", "Is there a ship berthed at the terminal?", port),
            ("seg", "Segment all water bodies in this image.", lake)]
    jobs += [(f"extra{i}", "Describe this image.", port) for i in range(args.extra)]

    smi = shutil.which("nvidia-smi")
    vram: list[int] = []
    total_mb: list[int] = []
    queue: list[dict] = []
    stop = threading.Event()

    def sampler() -> None:
        while not stop.is_set():
            if smi:
                out = subprocess.run([smi, "--query-gpu=memory.used,memory.total", "--format=csv,noheader,nounits"],
                                     capture_output=True, text=True).stdout.strip().splitlines()
                if out:
                    used, tot = (int(x) for x in out[0].split(","))
                    vram.append(used)
                    total_mb[:] = [tot]
            try:
                h = httpx.get(base + "/api/v1/health", timeout=10).json()
                queue.append(h["queue"])
                g = h.get("gpu") or {}
                if not smi and g.get("memory_used_mb"):
                    vram.append(g["memory_used_mb"])
                    total_mb[:] = [g["memory_total_mb"]]
            except Exception:
                pass
            stop.wait(0.5)

    results: dict[str, dict] = {}
    t0 = time.perf_counter()

    def run(name: str, q: str, aid: str) -> None:
        s = time.perf_counter() - t0
        res = c.post("/api/v1/query", headers={"X-Request-ID": f"gpu-{name}"},
                     json={"query": q, "images": [{"id": "img1", "modality": "optical", "asset_id": aid}]})
        body = res.json()
        results[name] = {"status": res.status_code, "start": round(s, 2), "end": round(time.perf_counter() - t0, 2),
                         "task": body.get("task"), "tool": (body.get("execution_summary") or {}).get("tool_used"),
                         "evidence": (body.get("visual_evidence") or {}).get("type"),
                         "error": (body.get("error") or {}).get("code")}

    th = threading.Thread(target=sampler, daemon=True)
    th.start()
    time.sleep(1.0)
    idle = vram[-1] if vram else None
    threads = [threading.Thread(target=run, args=j) for j in jobs]
    for t in threads:
        t.start()
        time.sleep(0.05)
    for t in threads:
        t.join()
    time.sleep(1)
    stop.set()

    print(json.dumps(results, indent=2))
    peak = max(vram) if vram else None
    conc = queue[0]["concurrency"] if queue else 1
    print(f"VRAM idle {idle} MiB, peak {peak} MiB of {total_mb[0] if total_mb else '?'}; "
          f"max running {max((q['running'] for q in queue), default=None)} (concurrency {conc}), "
          f"max waiting {max((q['waiting'] for q in queue), default=None)}")

    fails = []
    bad = {k: v for k, v in results.items() if v["status"] >= 500 and not (v["status"] == 503 and v["error"] == "QUEUE_FULL")}
    if bad:
        fails.append(f"unexpected 5xx: {bad}")
    if any(results[k]["status"] != 200 for k in ("vqa", "seg")):
        fails.append("the first two jobs did not both succeed")
    if queue and max(q["running"] for q in queue) > conc:
        fails.append("the queue ran more jobs than its concurrency")
    if peak and total_mb and peak > args.max_vram_frac * total_mb[0]:
        fails.append(f"peak VRAM {peak} MiB > {args.max_vram_frac:.0%} of {total_mb[0]}")
    if args.extra and not any(v["status"] == 503 for v in results.values()) and len(jobs) > 1 + 4:
        print("note: no 503 seen; GPU_QUEUE_MAX may be larger than the burst")
    print("PASS" if not fails else "FAIL:\n  " + "\n  ".join(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
