"""
Soak test: a steady mixed workload against a running stack for a fixed time, to catch
leaks and slow degradation that a single e2e pass cannot.

Each simulated user loops over: upload a sample, query it (task mix below), read its
history and preview, sometimes delete an asset or a session, and occasionally refresh its
token. A sampler records the backend's memory (RSS, by --pid or by listening port),
GPU memory (/health) and queue depth.

    python tests/soak/soak.py --minutes 30 --users 3                 # real engine via :3000
    python tests/soak/soak.py --base http://127.0.0.1:8000 --minutes 5 --users 8 --port 8000

Pass criteria (exit 1 otherwise):
  - no unexpected statuses (anything but 2xx, and 429/503/504 which are backpressure);
  - backpressure under --max-backpressure (default 20 %) of requests;
  - RSS in the last quarter of the run at most --max-rss-growth (default 25 %) above
    the second quarter (the first is warm-up: model loads, caches);
  - p95 query latency in the last quarter at most --max-slowdown (default 2x) the second's.
  - with --data-dir (the backend's DATA_DIR, SQLite only): no upload file without its
    database row, and no evidence file without its query (deletes must not leak disk).
A JSON report with every sample goes to --report.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import threading
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
SD = ROOT / "sample_data"

SINGLE = [
    ("optical/real_sentinel2_austria_tci.tif", "optical", ["Describe this scene.", "Is there a river in this image?",
                                                          "Highlight the water bodies in this image."]),
    ("optical/naip_port_long_beach.tif", "optical", ["Is there a ship berthed at the terminal?",
                                                     "Locate the ship and the gantry cranes."]),
    ("optical/naip_airbase_davis_monthan.tif", "optical", ["Locate all aircraft."]),
    ("sar/sar_port_rotterdam.tif", "sar", ["Are there bright metallic targets?"]),
]
PAIRS = [
    (("bitemporal_change/urban_expansion_t1_2021.tif", "optical", "2021-01-01"),
     ("bitemporal_change/urban_expansion_t2_2024.tif", "optical", "2024-01-01"), "What changed between these dates?"),
    (("cross_modal_fusion/cloudy_optical_scene.tif", "optical", None),
     ("cross_modal_fusion/penetrating_sar_scene.tif", "sar", None), "Classify land cover under the clouds."),
]
BACKPRESSURE = {429, 503, 504}


class Stats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.calls: list[tuple[float, str, int, float]] = []  # (t, op, status, seconds)
        self.samples: list[dict] = []
        self.errors: list[str] = []

    def add(self, t: float, op: str, status: int, dt: float, info: str = "") -> None:
        with self.lock:
            self.calls.append((t, op, status, dt))
            if status not in BACKPRESSURE and not 200 <= status < 300:
                self.errors.append(f"{op} -> {status} {info[:200]}")


def find_pid(port: int) -> int | None:
    import psutil
    for conn in psutil.net_connections(kind="tcp"):
        if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN and conn.pid:
            return conn.pid
    return None


def rss_mb(pid: int | None) -> float | None:
    if not pid:
        return None
    import psutil
    try:
        p = psutil.Process(pid)
        return round(sum(x.memory_info().rss for x in [p, *p.children(recursive=True)]) / 2**20, 1)
    except psutil.Error:
        return None


def sampler(base: str, pid: int | None, stats: Stats, t0: float, stop: threading.Event, every: float) -> None:
    while not stop.is_set():
        s: dict = {"t": round(time.time() - t0, 1), "rss_mb": rss_mb(pid)}
        try:
            h = httpx.get(base + "/api/v1/health", timeout=10).json()
            s["queue_waiting"] = h["queue"]["waiting"]
            s["queue_running"] = h["queue"]["running"]
            s["gpu_used_mb"] = (h.get("gpu") or {}).get("memory_used_mb")
        except Exception as exc:
            s["health_error"] = type(exc).__name__
        with stats.lock:
            stats.samples.append(s)
        stop.wait(every)


def user_loop(uid: int, base: str, deadline: float, stats: Stats, t0: float, timeout: float, seed: int) -> None:
    rng = random.Random(seed * 1000 + uid)
    c = httpx.Client(base_url=base + "/api/v1", timeout=timeout)

    def call(op: str, method: str, path: str, **kw) -> httpx.Response | None:
        start = time.time()
        try:
            r = c.request(method, path, **kw)
        except httpx.HTTPError as exc:
            stats.add(start - t0, op, 0, time.time() - start, type(exc).__name__)
            return None
        stats.add(start - t0, op, r.status_code, time.time() - start, r.text)
        return r

    r = call("register", "POST", "/auth/register",
             json={"email": f"soak-{uid}-{uuid.uuid4().hex[:6]}@example.com", "password": "soak-password-123"})
    if r is None or r.status_code != 201:
        return
    c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    sid = call("session", "POST", "/sessions", json={"title": f"soak {uid}"}).json()["id"]
    assets: list[str] = []

    def upload(rel: str) -> str | None:
        p = SD / rel
        r = call("upload", "POST", "/upload", files={"file": (p.name, p.read_bytes())})
        if r is not None and r.status_code == 200:
            assets.append(r.json()["asset_id"])
            return r.json()["asset_id"]
        return None

    while time.time() < deadline:
        if rng.random() < 0.7:
            rel, mod, qs = rng.choice(SINGLE)
            aid = upload(rel)
            if aid:
                call("query", "POST", "/query", json={"query": rng.choice(qs), "session_id": sid,
                                                      "images": [{"id": "a", "modality": mod, "asset_id": aid}]})
        else:
            (r1, m1, d1), (r2, m2, d2), q = rng.choice(PAIRS)
            a1, a2 = upload(r1), upload(r2)
            if a1 and a2:
                im = [{"id": "a", "modality": m1, "asset_id": a1}, {"id": "b", "modality": m2, "asset_id": a2}]
                for d, i in ((d1, im[0]), (d2, im[1])):
                    if d:
                        i["date"] = d
                call("query", "POST", "/query", json={"query": q, "session_id": sid, "images": im})
        call("history", "GET", f"/sessions/{sid}/queries")
        call("sessions", "GET", "/sessions")
        if assets:
            call("preview", "GET", f"/assets/{rng.choice(assets)}/preview")
        call("storage", "GET", "/storage")
        if len(assets) > 6:  # keep each user's footprint bounded; exercises delete under load
            call("delete_asset", "DELETE", f"/assets/{assets.pop(0)}")
        if rng.random() < 0.1:
            call("delete_session", "DELETE", f"/sessions/{sid}")
            sid = call("session", "POST", "/sessions", json={"title": f"soak {uid}"}).json()["id"]
        if rng.random() < 0.1:
            r = call("refresh", "POST", "/auth/refresh")
            if r is not None and r.status_code == 200:
                c.headers["Authorization"] = "Bearer " + r.json()["access_token"]
    for aid in assets:
        call("delete_asset", "DELETE", f"/assets/{aid}")


def orphan_files(data_dir: Path) -> dict[str, list[str]]:
    """Files under uploads/ and evidence/ that no database row points at."""
    import sqlite3
    db = sqlite3.connect(f"file:{data_dir / 'satquery.db'}?mode=ro", uri=True)
    images = {r[0] for r in db.execute("SELECT id FROM images")}
    queries = {r[0] for r in db.execute("SELECT id FROM queries")}
    out = {"uploads": [], "evidence": []}
    for f in (data_dir / "uploads").rglob("*"):
        if f.is_file() and f.name.split(".")[0] not in images:
            out["uploads"].append(f.relative_to(data_dir).as_posix())
    for f in (data_dir / "evidence").rglob("*"):
        if f.is_file() and f.name.split(".")[0] not in queries:
            out["evidence"].append(f.relative_to(data_dir).as_posix())
    return out


def pct(xs: list[float], p: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(p / 100 * len(xs)))], 3)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--minutes", type=float, default=10)
    ap.add_argument("--users", type=int, default=3)
    ap.add_argument("--pid", type=int, help="backend process id, for RSS")
    ap.add_argument("--port", type=int, help="find the backend pid by its listening port (e.g. 8000)")
    ap.add_argument("--sample-every", type=float, default=5)
    ap.add_argument("--timeout", type=float, default=600)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--max-backpressure", type=float, default=0.20)
    ap.add_argument("--max-rss-growth", type=float, default=0.25)
    ap.add_argument("--max-slowdown", type=float, default=2.0)
    ap.add_argument("--data-dir", type=Path, help="backend DATA_DIR: also check for orphaned files")
    ap.add_argument("--report", type=Path, default=Path("soak_report.json"))
    args = ap.parse_args()

    base = args.base.rstrip("/")
    pid = args.pid or (find_pid(args.port) if args.port else None)
    print(f"soak: {args.users} users x {args.minutes} min against {base}; backend pid={pid or 'unknown (no RSS)'}")
    stats, stop = Stats(), threading.Event()
    t0 = time.time()
    deadline = t0 + args.minutes * 60
    smp = threading.Thread(target=sampler, args=(base, pid, stats, t0, stop, args.sample_every), daemon=True)
    smp.start()
    users = [threading.Thread(target=user_loop, args=(i, base, deadline, stats, t0, args.timeout, args.seed))
             for i in range(args.users)]
    for u in users:
        u.start()
        time.sleep(0.5)
    last_print = 0.0
    while any(u.is_alive() for u in users):
        time.sleep(1)
        if time.time() - last_print > 30:
            last_print = time.time()
            with stats.lock:
                n, s = len(stats.calls), (stats.samples[-1] if stats.samples else {})
            print(f"  t={int(time.time() - t0)}s calls={n} rss={s.get('rss_mb')} MB "
                  f"gpu={s.get('gpu_used_mb')} MB queue={s.get('queue_waiting')}", flush=True)
    stop.set()
    smp.join(timeout=15)
    duration = time.time() - t0

    # ----- analysis -----
    calls = stats.calls
    q = duration / 4
    by_op: dict[str, list[float]] = defaultdict(list)
    for _, op, st, dt in calls:
        if 200 <= st < 300:
            by_op[op].append(dt)
    status_counts = Counter(st for _, _, st, _ in calls)
    bp = sum(v for k, v in status_counts.items() if k in BACKPRESSURE)
    q_lat = {i: [dt for t, op, st, dt in calls if op == "query" and 200 <= st < 300 and i * q <= t < (i + 1) * q]
             for i in range(4)}
    rss = {i: [s["rss_mb"] for s in stats.samples if s.get("rss_mb") and i * q <= s["t"] < (i + 1) * q] for i in range(4)}

    report = {
        "args": {k: str(v) for k, v in vars(args).items()}, "duration_s": round(duration, 1), "calls": len(calls),
        "status_counts": dict(status_counts),
        "latency_s": {op: {"n": len(v), "p50": pct(v, 50), "p95": pct(v, 95), "max": round(max(v), 3)}
                      for op, v in sorted(by_op.items())},
        "query_p95_by_quarter": {i: pct(v, 95) for i, v in q_lat.items()},
        "rss_mb_mean_by_quarter": {i: round(statistics.mean(v), 1) if v else None for i, v in rss.items()},
        "unexpected": stats.errors[:50], "samples": stats.samples,
    }
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n{len(calls)} calls in {duration:.0f} s; statuses {dict(status_counts)}")
    for op, v in report["latency_s"].items():
        print(f"  {op:15s} n={v['n']:5d} p50={v['p50']}s p95={v['p95']}s max={v['max']}s")
    print(f"  query p95 by quarter: {report['query_p95_by_quarter']}")
    print(f"  RSS MB by quarter:    {report['rss_mb_mean_by_quarter']}")

    fails = []
    if stats.errors:
        fails.append(f"{len(stats.errors)} unexpected responses, e.g. {stats.errors[:3]}")
    if calls and bp / len(calls) > args.max_backpressure:
        fails.append(f"backpressure {bp}/{len(calls)} > {args.max_backpressure:.0%}")
    r1, r3 = report["rss_mb_mean_by_quarter"][1], report["rss_mb_mean_by_quarter"][3]
    if r1 and r3 and r3 > r1 * (1 + args.max_rss_growth):
        fails.append(f"RSS grew {r1} -> {r3} MB (> {args.max_rss_growth:.0%})")
    p1, p3 = report["query_p95_by_quarter"][1], report["query_p95_by_quarter"][3]
    if p1 and p3 and p3 > p1 * args.max_slowdown:
        fails.append(f"query p95 slowed {p1} -> {p3} s (> {args.max_slowdown}x)")
    if args.data_dir:
        orphans = orphan_files(args.data_dir)
        report["orphans"] = orphans
        args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"  orphaned files: uploads={len(orphans['uploads'])} evidence={len(orphans['evidence'])}")
        if orphans["uploads"] or orphans["evidence"]:
            fails.append(f"orphaned files: {orphans['uploads'][:3] + orphans['evidence'][:3]}")
    if not by_op.get("query"):
        fails.append("no successful queries")
    print("\nPASS" if not fails else "\nFAIL:\n  " + "\n  ".join(fails), f"(report: {args.report})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
