# --------------------------------------------------------------------------
# SatQuery AI — Backend Dockerfile
# --------------------------------------------------------------------------
# Build:  docker build -t satquery-backend ./backend
# Run:    docker run -p 8000:8000 -v ./backend/data:/app/backend/data satquery-backend
# --------------------------------------------------------------------------

FROM python:3.11-slim

# System dependencies for Pillow
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libjpeg-dev \
        libpng-dev \
        zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cache-friendly layer)
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application code
COPY ai_service/ ./ai_service/
COPY backend/ ./backend/

# Ensure data directories exist
RUN mkdir -p backend/data/images

# Expose the backend port
EXPOSE 8000

# Run the server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
