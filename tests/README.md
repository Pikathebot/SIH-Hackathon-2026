# Tests

| Layer | Where | Needs | Runs in CI |
|---|---|---|---|
| Backend unit + integration (incl. upload fuzz/security) | `backend/tests/`, `ai_service/*/tests` | venv | yes |
| Frontend unit (vitest + Testing Library) | `frontend/src/**/*.test.ts(x)` | `npm ci` | yes |
| Tooling helpers | `tests/test_tooling.py` | venv | yes |
| Live API end-to-end | `tests/e2e/e2e_live.py` | a running stack | yes, mock engine on the CPU compose stack |
| Browser demo rehearsal | `tests/browser/demo_rehearsal.mjs` | stack + Chrome | no |
| GPU queue / VRAM under concurrency | `tests/e2e/gpu_concurrency.py` | real engine on a GPU | no |
| Model-quality regression | `tests/quality/quality_regression.py` | real engine | no |
| Soak (leaks, degradation, orphaned files) | `tests/soak/soak.py` | a running stack | no |

The last four talk to a running stack over HTTP. Their default base URL is `http://localhost:3000`,
which is the Vite dev proxy or the nginx container. Pass `--base http://127.0.0.1:8000` to talk to the backend directly.

## Unit suites

```powershell
.venv\Scripts\python -m pytest ai_service/common ai_service/rsunivlm/tests ai_service/fusion/tests ai_service/qwen_vl/tests backend/tests tests/test_tooling.py
cd frontend; npm test
```

(Bare `pytest` also collects `ai_service/rsunivlm/vendor`, which breaks. List the suites as above.)

## Live suites

Start a stack first: `.\start_dev.ps1` (real), `docker compose up` (GPU), or
`docker compose -f docker-compose.yml -f docker-compose.cpu.yml up` (mock). A mock backend
started with `MOCK_FAST_MODE=1` skips the simulated model latency.

```powershell
# API journey: register, 12 uploads, one query per task, isolation, deletes, logout
.venv\Scripts\python tests\e2e\e2e_live.py            # add --mock against a mock backend

# Browser: docs/DEMO_SCRIPT.md step by step (screenshots in tests/browser/out)
cd tests\browser; npm install; node demo_rehearsal.mjs   # --mock skips content checks

# Quality: fixed scenarios vs. human-verified facts and a recorded golden run
.venv\Scripts\python tests\quality\quality_regression.py
.venv\Scripts\python tests\quality\quality_regression.py --record   # after an intended model change

# GPU: two concurrent jobs serialise; a burst gets 503 QUEUE_FULL, never a crash
.venv\Scripts\python tests\e2e\gpu_concurrency.py --extra 6

# Soak: steady mixed load; checks memory growth, latency drift, orphaned files
.venv\Scripts\python tests\soak\soak.py --minutes 30 --users 3 --port 8000 --data-dir backend\data
```

### Quality regression

Hard checks come from facts a person verified on the images. The NAIP airbase chip has 13 parked
aircraft (±2 allowed). The Long Beach chip has one berthed ship and 4 gantry cranes (3–7 boxes). The
Austria scene has no river. The fusion scene is about 43 % cloud with about 52 % water under it.

`golden_hybrid.json` is a recorded known-good run. New runs must find at least 75 % of its boxes
(IoU ≥ 0.3) and keep mask areas within 10 points of it. Latency more than 3× the golden run is
reported but does not fail the run.

Re-record the golden file only after you have looked at the outputs. `--record` refuses to
write one from a run that fails the hard checks.

Free-text counting ("How many aircraft…") is deliberately left out. It is unreliable with this
model, see `docs/DEMO_SCRIPT.md` §3.
