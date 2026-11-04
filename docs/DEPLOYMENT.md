# DEPLOYMENT.md — Running SatQuery AI beyond one laptop

**Version:** 1.0.0. Local runs are covered in [`QUICKSTART.md`](../QUICKSTART.md). This file covers shared and cloud deployments. Everything here is configuration only, through environment variables and compose files. No code changes are needed.

---

## 1. Topology

```
            HTTPS :443                    :8080 (internal)            :8000 (internal)          :8080 (internal)
 browser ───────────────▶ Caddy / LB ───────────────▶ frontend (nginx) ──/api/──▶ backend ─────────────▶ vlm (llama.cpp)
                                                       static SPA            FastAPI + RSUniVLM         Qwen3-VL GGUF
                                                                             │       (same GPU)
                                                                             ├──▶ Postgres (DATABASE_URL)
                                                                             └──▶ volume: uploads, evidence (DATA_DIR)
```

- **One GPU VM runs everything.** The backend's GPU queue (`GPU_CONCURRENCY=1`) serialises model work on that card. Run a **single backend replica with one uvicorn worker**. Rate limits and the queue are in-process, so a second worker would get its own counters and its own copy of the model in VRAM.
- Scaling out later means moving the queue to Redis + ARQ workers and the rate limits to Redis behind the same interfaces (`app/gpu_queue.py`, `app/ratelimit.py`). The HTTP contract does not change.

## 2. Recommended VM

| | Minimum | Notes |
|---|---|---|
| GPU | 1 × 16 GB, or 24 GB for headroom (L4, A10G, RTX 4000 Ada) | Hybrid peaks at ~11.8 GB. 12 GB cards work only with nothing else on the GPU |
| RAM | 32 GB | RSUniVLM loads ~3.2 GB of weights through host RAM |
| Disk | 60 GB + uploads | GPU backend image ~8 GB, llama.cpp image ~2 GB, models ~9 GB |
| OS | Ubuntu 22.04/24.04 + NVIDIA driver (CUDA 13 capable) + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/) | Check with `docker run --rm --gpus all busybox true` |

## 3. Steps

1. **Copy the models** to the VM: `tools/models/` (Qwen GGUF + mmproj) and `ai_service/rsunivlm/checkpoints/`. Or point `VLM_MODELS_DIR` at a mounted disk.
2. **Write `.env`** (never commit it):
   ```
   AI_SERVICE_MODE=real
   AI_ENGINE=hybrid
   SECRET_KEY=<64+ random chars: python -c "import secrets;print(secrets.token_urlsafe(64))">
   COOKIE_SECURE=true
   CORS_ORIGINS=https://satquery.example.org
   DATABASE_URL=postgresql+asyncpg://satquery:<password>@db:5432/satquery
   ALLOW_REGISTRATION=false        # after creating the accounts you need
   LOG_FORMAT=json
   USER_QUOTA_MB=20480
   ```
   `SECRET_KEY` must be set explicitly in any shared deployment. Otherwise each fresh volume generates its own key and signs everyone out. `asyncpg` is not in the lock yet. Add it to `backend/requirements.txt` and re-lock before switching to Postgres. Migrations run on startup in either case (`python -m app.migrate upgrade` runs them by hand).
3. **Put TLS in front.** A minimal `Caddyfile`:
   ```
   satquery.example.org {
       reverse_proxy frontend:8080
       request_body { max_size 4200MB }
   }
   ```
   Add Caddy (and Postgres) as services in a `docker-compose.prod.yml` override. **Remove the backend's `ports:` mapping** there, so only Caddy is reachable from outside. The backend trusts `X-Forwarded-For` (`FORWARDED_ALLOW_IPS="*"`), which is safe only while nothing but nginx can reach it.
4. `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build`
5. **Gate traffic on readiness:** `GET /api/v1/ready` returns 503 until the DB answers and the engine is configured. RSUniVLM loads lazily: the first mask query downloads SigLIP (~3.3 GB) unless the Hugging Face cache volume is pre-filled, so send one warm-up segmentation query (or copy a cache into the volume) before taking traffic. Liveness is `GET /api/v1/health`.

## 4. Operations

- **Backups:** the Postgres database plus the `satquery-data` volume (`uploads/`, `evidence/`). Uploads are referenced by database rows, so back them up together.
- **Logs:** JSON lines on stdout. Every line carries `request_id`, which the user also sees under error messages and which nginx forwards as `X-Request-ID`.
- **Limits worth tuning:** `RATE_LIMIT_AUTH`, `RATE_LIMIT_QUERY`, `GPU_QUEUE_MAX`, `GPU_TASK_TIMEOUT_S`, `MAX_REQUEST_MB`, `MAX_UPLOAD_MB`, `MAX_IMAGE_MEGAPIXELS`, `USER_QUOTA_MB`. See `.env.example` and `API_CONTRACT.md` §6.
- **Upgrades:** rebuild the images. The locks pin every Python package, and `llama.cpp` is pinned by image tag in `docker-compose.yml`.

## 5. Not covered yet

Kubernetes, multi-GPU scheduling, SSO, and object storage for uploads (S3/GCS instead of a volume).
