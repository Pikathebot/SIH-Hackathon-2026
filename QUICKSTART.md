# 🛰️ SatQuery AI — Quick Start & Testing Guide

## 1. Quick Launch (Recommended for Windows)

Run the automated launcher script from PowerShell:

```powershell
.\start_dev.ps1
```

This starts:
- **FastAPI Backend**: `http://localhost:8000` (API documentation at `http://localhost:8000/docs`)
- **React Frontend**: `http://localhost:3000`

---

## 2. Manual Startup (Two Terminals)

### Terminal 1: Backend
```powershell
# From repository root
uv run uvicorn app.main:app --app-dir backend --port 8000 --reload
```

### Terminal 2: Frontend
```powershell
cd frontend
npm run dev
```

Open your browser at **`http://localhost:3000`**.

---

## 3. Docker Compose Startup

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`

---

## 4. Running Tests

### A. Full Automated Smoke Test (8 End-to-End Scenarios)
```powershell
# Standalone in-process (or with --url http://localhost:8000 for live server)
uv run python smoke_test.py
```

### B. Unit & Conformance Test Suite (29 Tests)
```powershell
uv run pytest backend/tests/ ai_service/common/test_contract_conformance.py -v
```

---

## 5. UI Features to Test in Browser

1. **Demo Preset Selector**: Click the "Explore Sample Scenarios" button in the top bar to instantly test:
   - *Object Counting & VQA* (Optical)
   - *Automated Scene Captioning* (Optical)
   - *Object Detection / Bounding Boxes* (Optical)
   - *Disaster Flood Segmentation Mask* (Optical)
   - *Urban Expansion Temporal Change Detection* (2 Optical images with dates)
   - *All-Weather Optical + Radar (SAR) Fusion* (1 Optical + 1 SAR)
2. **Interactive Lightbox**: Click on any satellite thumbnail to view with pan, zoom, and metadata.
3. **Execution Summary & Latency**: Inspect the `execution_summary` panel for each query to review model routing and inference time.
