# syntax=docker/dockerfile:1.7
# --------------------------------------------------------------------------
# SatQuery AI — backend image (FastAPI + in-process AI service)
#
#   FLAVOR=gpu  (default) full stack from requirements.lock: torch cu128, RSUniVLM, Qwen client.
#               Needs the NVIDIA container runtime and the checkpoints mounted (see compose).
#   FLAVOR=slim backend/requirements.lock only: mock engine, or AI_ENGINE=qwen against llama-server.
#
# Build (from repo root):  docker build -f backend/Dockerfile --build-arg FLAVOR=slim -t satquery-backend:slim .
# The usual entry point is docker compose (docker-compose.yml).
# --------------------------------------------------------------------------
ARG PYTHON_VERSION=3.11

# ── Builder: resolve nothing, install exactly the lock into /opt/venv ───────
FROM python:${PYTHON_VERSION}-slim-bookworm AS builder
ARG FLAVOR=gpu
COPY --from=ghcr.io/astral-sh/uv:0.11.19 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /build
COPY requirements.lock ./requirements.lock
COPY backend/requirements.lock ./backend.lock
RUN --mount=type=cache,target=/root/.cache/uv \
    uv venv /opt/venv && \
    if [ "$FLAVOR" = "gpu" ]; then \
        uv pip install --python /opt/venv/bin/python -r requirements.lock \
            --extra-index-url https://download.pytorch.org/whl/cu128 --index-strategy unsafe-best-match; \
    elif [ "$FLAVOR" = "slim" ]; then \
        uv pip install --python /opt/venv/bin/python -r backend.lock; \
    else \
        echo "FLAVOR must be gpu or slim (got $FLAVOR)" >&2; exit 1; \
    fi

# ── Runtime ─────────────────────────────────────────────────────────────────
FROM python:${PYTHON_VERSION}-slim-bookworm
# libgomp1: OpenMP runtime (scikit-learn / opencv wheels); libexpat1: needed by rasterio's bundled GDAL
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libexpat1 && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --uid 10001 --create-home --shell /usr/sbin/nologin satquery

COPY --from=builder /opt/venv /opt/venv
# Fail the build, not the first request, if a native library is missing
RUN /opt/venv/bin/python -c "import rasterio, rasterio.io, pyproj, cv2, PIL.Image, numpy; print('native deps OK')"
WORKDIR /app
COPY ai_service/ ./ai_service/
COPY backend/ ./backend/
RUN mkdir -p /app/backend/data /app/ai_service/rsunivlm/checkpoints /home/satquery/.cache/huggingface && \
    chown -R satquery:satquery /app/backend/data /home/satquery/.cache

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app:/app/backend" \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/app/backend/data \
    LOG_FORMAT=json \
    # Trust X-Forwarded-For from the nginx container so per-IP rate limits see real clients.
    # Safe only while :8000 is not reachable from outside (compose binds it to 127.0.0.1).
    FORWARDED_ALLOW_IPS="*"

USER satquery
EXPOSE 8000
VOLUME ["/app/backend/data"]

# Liveness only (/health is 200 while the process runs); compose gates the frontend on it.
# start-period covers RSUniVLM + SigLIP loading on first start.
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status == 200 else 1)"]

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
