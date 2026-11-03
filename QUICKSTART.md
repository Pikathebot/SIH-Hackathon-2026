# 🛰️ SatQuery AI — Quick Start

Three ways to run it, from lightest to heaviest:

| | Needs | Command |
|---|---|---|
| **A. Native, mock** | Python 3.11, Node 22 | `.\start_dev.ps1` with `AI_SERVICE_MODE=mock` |
| **B. Native, real GPU** | + NVIDIA GPU ≥12 GB, model files | `.\start_dev.ps1` with `AI_SERVICE_MODE=real` |
| **C. Docker** | Docker Desktop (WSL 2 engine for GPU) | `docker compose up --build` |

Every option serves the app at **http://localhost:3000**. Sign up with any email and a password of 10+ characters.

---

## 1. One-time setup

```powershell
git clone https://github.com/Pikathebot/SIH-Hackathon-2026.git
cd SIH-Hackathon-2026
Copy-Item .env.example .env
```

### Python environment (A and B)
```powershell
uv venv --python 3.11 .venv
# A: backend + mock engines only (fast, ~60 packages)
uv pip install -r backend/requirements.lock
# B: full GPU stack (torch 2.11 cu128, transformers 4.46, RSUniVLM, Qwen client)
uv pip install -r requirements.lock --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match
```
The `*.lock` files pin exactly the versions the test suite passed on. Regenerate them with `scripts\lock_deps.ps1` after changing a `requirements*.txt`.

### Frontend
```powershell
cd frontend; npm ci; cd ..
```

### Model files (B and C only; all paths are git-ignored)
| What | Where | From |
|---|---|---|
| llama.cpp CUDA build (native only) | `tools/llama.cpp/` | [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases): `llama-bXXXX-bin-win-cuda-13.x-x64.zip` + cudart zip |
| Qwen3-VL-8B GGUF + mmproj | `tools/models/Qwen3VL-8B-Instruct-Q4_K_M.gguf`, `tools/models/mmproj-Qwen3VL-8B-Instruct-Q8_0.gguf` | [Qwen/Qwen3-VL-8B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct-GGUF) |
| RSUniVLM weights | `ai_service/rsunivlm/checkpoints/RSUniVLM/` | [liux-cyber/RSUniVLM](https://huggingface.co/liux-cyber/RSUniVLM) |

The SigLIP vision tower (`google/siglip-so400m-patch14-384`, ~3.3 GB) downloads into the Hugging Face cache the first time RSUniVLM is needed (the first segmentation/mask query). On a slow link that query can take 10+ minutes and return 504 while the download continues.

---

## 2. Run

### A / B — native
```powershell
.\start_dev.ps1           # backend :8000 (auto-reload), frontend :3000
.\start_dev.ps1 -NoVlm    # never start llama-server
```
With `AI_SERVICE_MODE=real` and `AI_ENGINE=hybrid` (or `qwen`) in `.env`, the script also starts llama-server on :8080 and waits for it.

**Before a real run, close other GPU apps (ComfyUI, LM Studio, games).** Hybrid peaks at about 11.8 GB of the 5070's 12.2 GB. If llama-server is down, the backend falls back to RSUniVLM alone.

Manual equivalent, one terminal each:
```powershell
.\scripts\start_vlm_server.ps1                                                        # B only
.\.venv\Scripts\python -m uvicorn app.main:app --app-dir backend --port 8000 --reload
cd frontend; npm run dev
```

### C — Docker
```powershell
docker compose up --build                                                    # GPU: llama.cpp + hybrid backend + nginx
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up --build    # no GPU, mock engine
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build    # hot reload
```
- **GPU containers need Docker Desktop's WSL 2 engine** (Settings → General → *Use the WSL 2 based engine*). The Hyper-V engine has no GPU passthrough. It also caps the VM at 2 GB of RAM, which is too little to load RSUniVLM. Check with `docker run --rm --gpus all busybox true`.
- The backend is published on `127.0.0.1:8000` only. Browsers go through nginx on :3000.
- Data lives in the `satquery_satquery-data` volume, separate from the native `backend/data/`. To reuse your existing Hugging Face cache, set `HF_CACHE_DIR=C:/Users/<you>/.cache/huggingface` in `.env`. Without it the container downloads SigLIP (~3.3 GB) again on its first mask query.

---

## 3. Check it works

```powershell
curl http://localhost:8000/api/v1/ready      # {"status":"ready","checks":{"database":true,"engine":true}}
curl http://localhost:8000/api/v1/health     # engine, VLM reachability, queue, GPU memory
.\.venv\Scripts\python smoke_test.py --url http://localhost:8000      # 8 end-to-end scenarios (Docker: :3000)
.\.venv\Scripts\python -m pytest ai_service/common ai_service/rsunivlm/tests ai_service/fusion/tests ai_service/qwen_vl/tests backend/tests
```

---

## 4. Things to try in the browser

1. **Explore Sample Scenarios** in the top bar loads VQA, captioning, boxes, a flood mask, bi-temporal change and optical+SAR fusion examples from `sample_data/`.
2. **Upload** a GeoTIFF or JPEG 2000 file. It stays in your account, and history thumbnails survive a page refresh.
3. Open the **execution summary** under each answer to see the engine, tool, parameters and latency.

---

## 5. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `503 QUEUE_FULL` | More than `GPU_CONCURRENCY + GPU_QUEUE_MAX` (1 + 4) queries in flight. Wait and retry, or raise `GPU_QUEUE_MAX`. |
| `504 INFERENCE_TIMEOUT` | A job ran past `GPU_TASK_TIMEOUT_S` (300 s). Usually VRAM contention from another app. |
| `429 RATE_LIMITED` | `RATE_LIMIT_AUTH` / `RATE_LIMIT_QUERY` exceeded. Set `RATE_LIMIT_ENABLED=false` for local load tests. |
| CUDA out of memory | Close other GPU apps. `nvidia-smi` should show about 1–2 GB used before you start. |
| `/health` shows `"vlm_available": false` | llama-server is not on `VLM_SERVER_URL`. Start `scripts\start_vlm_server.ps1`. |
| An error shows a *Request ID* | Search the backend log for that id (`LOG_FORMAT=json` makes this easy). The full traceback is there. |
