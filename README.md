# SatQuery AI 🛰️

[![ISRO Problem Statement](https://img.shields.io/badge/ISRO-Problem_Statement_26167-orange.svg)](docs/PROBLEM_STATEMENT.md)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React 18](https://img.shields.io/badge/React-18.3-61DAFB.svg?logo=react&logoColor=black)](https://reactjs.org)
[![Vite](https://img.shields.io/badge/Vite-6.0-646CFF.svg?logo=vite&logoColor=white)](https://vitejs.dev)
[![TailwindCSS](https://img.shields.io/badge/TailwindCSS-3.4-38B2AC.svg?logo=tailwindcss&logoColor=white)](https://tailwindcss.com)

> **An Interactive Agentic Vision-Language Assistant for Multimodal Remote Sensing Image Analysis through Natural Language Text Queries**  
> Developed for **ISRO (Indian Space Research Organisation)** — Smart India Hackathon (PS ID: 26167, Space Technology Theme).

---

## 📑 Table of Contents

- [Overview & Motivation](#-overview--motivation)
- [Key Capabilities](#-key-capabilities)
- [System Architecture](#-system-architecture)
- [Repository Structure](#-repository-structure)
- [Quick Start Guide](#-quick-start-guide)
  - [Prerequisites](#prerequisites)
  - [1. Clone Repository & Setup Environment](#1-clone-repository--setup-environment)
  - [2. Backend Setup (FastAPI)](#2-backend-setup-fastapi)
  - [3. Frontend Setup (React + Vite)](#3-frontend-setup-react--vite)
  - [4. Single-Command Docker Deployment](#4-single-command-docker-deployment)
- [Evaluation Datasets & Query Guide](#-evaluation-datasets--query-guide)
- [Automated Testing & Verification](#-automated-testing--verification)
- [API Specification](#-api-specification)
- [Contract-First Governance](#-contract-first-governance)
- [License & Acknowledgments](#-license--acknowledgments)

---

## 🌍 Overview & Motivation

Earth observation satellites capture massive volumes of multimodal optical, multispectral, and Synthetic Aperture Radar (SAR) imagery daily. Traditional GIS analysis tools and remote sensing classifiers are isolated, domain-specific, and require deep technical expertise to extract insights.

**SatQuery AI** bridges this gap through a unified, agentic vision-language architecture. Non-expert and operational analysts can upload raw satellite data (GeoTIFF, JPEG 2000, Sentinel-2 SAFE archives) and ask plain English questions. The system dynamically validates geospatial metadata, selects and orchestrates specialized remote sensing AI models (RSUniVLM, optical spectral processors, radar backscatter engines), and synthesizes evidence-grounded answers with interactive visual overlays.

```
                  ┌────────────────────────────────────────────────────────┐
                  │                 Natural Language Query                 │
                  │  "Detect coastal lines and describe terrain changes"   │
                  └───────────────────────────┬────────────────────────────┘
                                              │
                                              ▼
┌───────────────────────────┐   ┌───────────────────────────┐   ┌───────────────────────────┐
│     Optical / Multi-S2    │   │      Radar / SAR (S1)     │   │     Bi-Temporal Pairs     │
│   True Color, NIR, SWIR   │   │   VV/VH Backscatter GRD   │   │   Multi-Year Time Series  │
└─────────────┬─────────────┘   └─────────────┬─────────────┘   └─────────────┬─────────────┘
              │                               │                               │
              └───────────────────────┬───────┴───────────────────────────────┘
                                      │
                                      ▼
             ┌──────────────────────────────────────────────────┐
             │       SatQuery AI Multi-Agent Orchestrator       │
             │   Intent Classification & Mode Routing (VG/SEG)  │
             └────────────────────────┬─────────────────────────┘
                                      │
         ┌────────────────────────────┼────────────────────────────┐
         ▼                            ▼                            ▼
┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
│  RSUniVLM VLM    │        │  Optical/SAR     │        │  Geospatial GIS  │
│  VQA / Grounding │        │  Cross-Fusion    │        │  Reprojection    │
└────────┬─────────┘        └────────┬─────────┘        └────────┬─────────┘
         │                           │                           │
         └───────────────────────────┼───────────────────────────┘
                                     │
                                     ▼
         ┌───────────────────────────────────────────────────────┐
         │ • Natural Language Findings & Confidence Score        │
         │ • Precision Segmentation Masks & Boundary Contours    │
         │ • Synchronized Swipe Split-Slider Comparison          │
         │ • Calibrated Lat/Lon Graticule Frame                  │
         │ • PDF Mission Reports, GeoJSON, & JSON Exports        │
         └───────────────────────────────────────────────────────┘
```

---

## ✨ Key Capabilities

### 1. Geospatial Raster Ingestion & Pre-processing
- **Native Format Support**: Direct ingestion of GeoTIFF (`.tif`/`.tiff`), JPEG 2000 (`.jp2`), and Sentinel-2 `.SAFE` product hierarchies.
- **Dynamic 4-Tier Band Resolution**: Automatically detects band descriptions, color interpretations, and Sentinel-2/Landsat spectral stacks (RGB, NIR, SWIR).
- **Percentile Dynamic Range Normalization**: Robust 2%–98% percentile stretching with nodata masking.
- **Geographic Coordinate Reprojection**: Translates native projected coordinates (e.g., UTM Zone 31N) into standard WGS84 (`EPSG:4326`) bounding boxes and GeoJSON polygons.

### 2. Multi-Modal Vision-Language Inference
- **Visual Question Answering (`[VQA]`)**: Answers complex domain-specific questions about infrastructure, terrain, objects, and environmental conditions.
- **Detailed Scene Description (`[CAP]`)**: Produces comprehensive geographic and land-use scene captions.
- **Object Localization (`[VG]`)**: Pinpoints discrete targets (airplanes, vessels, bridges, storage tanks) with calibrated bounding boxes.
- **Semantic Segmentation (`[SEG]`)**: Generates pixel-accurate binary masks and colored overlays for continuous land covers.

### 3. Precision Environmental & Boundary Delineation
- **Single-Band NIR & SAR Water Extraction**: Identifies dark absorption boundaries in single-channel Sentinel-2 Band 8 (NIR) and Sentinel-1 radar backscatter ($<0.22$ reflectance threshold).
- **Calibrated Multi-Spectral Water Body Detection**: Atmospheric-corrected NDWI proxy identifying shallow rivers, lakes, reservoirs, and deep marine waters.
- **High-Definition Coastline Contours**: Morphological boundary extraction delineating the exact land-water interface contour.
- **Landmass & Terrain Segmentation**: Automatic spatial segmentation of terrestrial landmasses and vegetation extents.

### 4. Interactive Bi-Temporal & Cross-Modal Comparison
- **3-Mode Synchronized Comparison Viewer**:
  - 🎚️ **Swipe Split-Slider**: Real-time draggable divider comparing pre/post change or optical/SAR layers.
  - 🔲 **Side-by-Side**: Dual synchronized pan-and-inspect layout.
  - 👁️ **Opacity Blend**: Continuous cross-fading alpha slider.
- **Fullscreen High-Resolution Inspection**: Dedicated inspection modal for deep visual analysis.

### 5. Calibrated Geospatial Frame & Layer Controls
- **Coordinate Tick Frame**: Sub-pixel graticule frame showing calibrated latitude/longitude ticks and pixel coordinates.
- **Interactive Layer Toggles**: Turn on/off bounding boxes, spatial grid lines, and calibrated coordinate markers on demand.

### 6. Standard Mission Reporting & Export Pipeline
- 📄 **PDF Mission Reports**: Generates professional, multi-page mission briefs containing analysis metadata, confidence indicators, raw vs overlay previews, and technical summaries via standard print pipeline.
- 🌐 **GeoJSON Export (RFC 7946)**: Exports spatial bounding boxes, pixel footprint polygons, and detection metadata in standard `EPSG:4326` format for direct import into QGIS, ArcGIS, or Mapbox.
- 💾 **Machine-Readable JSON**: Complete structured export of analysis findings, model parameters, and execution summaries.

---

## 🏗️ System Architecture

SatQuery AI is built as a modular, contract-first application with clean separation between the user interface, orchestrator, and specialist AI engines:

```
SIH-Hackathon-2026/
├── ai_service/               # Specialist Remote Sensing AI Services
│   ├── common/               # Shared Type definitions, Errors, & Conformance tests
│   │   ├── types.py          # TypedDict shapes (VQAResult, DetectionResult, etc.)
│   │   ├── errors.py         # Standard AIServiceError codes
│   │   └── test_contract_conformance.py # 39+ Automated contract test suite
│   ├── rsunivlm/             # RSUniVLM Vision-Language Foundation Model
│   │   ├── wrapper.py        # Real model inference wrapper (PyTorch/SigLIP/LLaVA)
│   │   ├── mock.py           # Contract-conformant mock for lightweight development
│   │   ├── parsing.py        # Pure geometry, token stream parser, & spectral masks
│   │   ├── inference.py      # Token generation, repetition penalty, & logits
│   │   └── tests/            # RSUniVLM unit test suite (15 tests)
│   └── fusion/               # Optical + SAR Cross-Modal Fusion Engine
│       ├── wrapper.py        # Rule-based spectral & radar backscatter classifier
│       ├── mock.py           # Contract-conformant fusion mock
│       └── tests/            # Fusion unit test suite (5 tests)
│
├── backend/                  # FastAPI Backend & Orchestrator
│   ├── app/
│   │   ├── main.py           # Application entrypoint & CORS middleware
│   │   ├── orchestrator.py   # Intent classification, task dispatch, & SQLite logging
│   │   ├── geotiff.py        # Rasterio GDAL engine, band resolution, & WGS84 reprojection
│   │   ├── models/api.py     # Pydantic v2 request/response schemas
│   │   └── routers/
│   │       ├── query.py      # POST /api/v1/query endpoint
│   │       └── preview.py    # POST /api/v1/preview (fast TIFF/JP2 rendering)
│   ├── requirements.txt      # Python dependencies
│   └── tests/                # 34+ Backend integration & live scenario tests
│
├── frontend/                 # React 18 + Vite + TailwindCSS Single-Page App
│   ├── src/
│   │   ├── components/
│   │   │   ├── CoordinateTickFrame.tsx    # Calibrated lat/lon & pixel ruler frame
│   │   │   ├── DualImageSplitSlider.tsx   # Synchronized Swipe Split-Slider
│   │   │   ├── MapDetectionWorkspace.tsx  # Interactive map & detection view
│   │   │   ├── QueryComposer.tsx          # Multi-image uploader & query bar
│   │   │   └── ReportCard.tsx             # Analysis results & export actions
│   │   ├── services/api.ts                # Axios/Fetch API client
│   │   ├── utils/reportExport.ts          # PDF, GeoJSON, & JSON export utilities
│   │   └── types/contract.ts              # TypeScript interfaces matching API contract
│   ├── package.json
│   └── vite.config.ts
│
├── docs/                     # Strict System & Interface Contracts
│   ├── CONTRACT.md           # Master contract & naming conventions
│   ├── API_CONTRACT.md       # REST API schemas & HTTP error definitions
│   ├── AI_SERVICE_CONTRACT.md# AI module TypedDict specifications
│   ├── DATABASE_CONTRACT.md  # SQLite persistence schema & query logging
│   └── PROBLEM_STATEMENT.md  # Official ISRO PS 26167 definition
│
├── sample_data/              # Curated Optical, SAR, Bi-Temporal, & Fusion Rasters
└── smoke_test.py             # End-to-end interactive CLI verification suite
```

---

## 🚀 Quick Start Guide

### Prerequisites
- **Python**: `3.11+`
- **Node.js**: `18+` and `npm`
- **Docker & Docker Compose** (optional for containerized deployment)
- **GPU (Optional)**: NVIDIA GPU with CUDA 12+ (only required if running real RSUniVLM deep learning weights; all development and testing run smoothly on CPU via contract-conformant mocks).

---

### 1. Clone Repository & Setup Environment

```bash
git clone https://github.com/Pikathebot/SIH-Hackathon-2026.git
cd SIH-Hackathon-2026

# Copy environment variables template
cp .env.example .env
```

---

### 2. Backend Setup (FastAPI)

```bash
# Create and activate a Python virtual environment
python -m venv .venv

# On Linux / macOS:
source .venv/bin/activate
# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# Install backend dependencies
pip install -r backend/requirements.txt

# Start backend in mock mode (Instant startup, full UI features)
export AI_SERVICE_MODE=mock
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

The backend server will start at `http://localhost:8000`.  
API documentation is available at `http://localhost:8000/docs`.

---

### 3. Frontend Setup (React + Vite)

In a separate terminal window:

```bash
cd frontend

# Install Node.js dependencies
npm install

# Start Vite development server
npm run dev
```

The frontend dashboard will be available at `http://localhost:3000` (or `http://localhost:5173`).

---

### 4. Single-Command Docker Deployment

You can run both backend and frontend services containerized with a single command:

```bash
docker-compose up --build
```

---

## 📊 Evaluation Datasets & Query Guide

Pre-configured sample rasters are provided in [`sample_data/`](sample_data/README.md) for demonstration and evaluation:

| Modality / Scenario | Sample File(s) | Recommended Query | Task Triggered |
| :--- | :--- | :--- | :--- |
| **Real Sentinel-2 L2A** | `sample_data/optical/real_sentinel2_austria_tci.tif` | *"Describe the land cover, forests, and terrain characteristics in this satellite image."* | Scene Captioning `[CAP]` |
| **Coastline & Shorelines** | Sentinel-2 `.SAFE` or `optical_sentinel2_lake.jp2` | *"Detect coastal lines and highlight the water bodies in this image."* | Segmentation Mask `[SEG]` |
| **Optical Grounding** | `sample_data/optical/optical_airbase_runway.tif` | *"Where are the aircraft parked on the apron?"* | Bounding Box `[VG]` |
| **Single SAR Radar** | `sample_data/sar/real_sentinel1_sar_grd_vv.tif` | *"Analyze the radar backscatter intensity and identify high-reflectance metallic objects."* | Radar VQA `[VQA]` |
| **Bi-Temporal Change** | `real_sentinel2_change_t1_2022.tif` + `real_sentinel2_change_t2_2024.tif` | *"What changed between these two dates, and where did vegetation change occur?"* | Change Analysis `[CCD]` + Slider |
| **Optical + SAR Fusion** | `cloudy_optical_scene.tif` + `penetrating_sar_scene.tif` | *"Use the optical and SAR images together to detect maritime vessels hidden under cloud cover."* | Cross-Modal Fusion `[FUSION]` |

---

## 🧪 Automated Testing & Verification

SatQuery AI includes a test suite verifying contract conformance, unit functionality, and end-to-end integration:

```bash
# 1. Run full AI Service & Contract Conformance test suite (59 tests)
pytest ai_service/common ai_service/rsunivlm/tests ai_service/fusion/tests -v

# 2. Run Backend & GeoTIFF Integration test suite (34 tests)
pytest backend/tests -v

# 3. Run Interactive End-to-End Smoke Test Suite
python smoke_test.py --url http://localhost:8000
```

---

## 📡 API Specification

### `POST /api/v1/query`
Main vision-language analysis endpoint. Accepts single or multi-image payloads with natural language queries.

#### Request Body
```json
{
  "images": [
    {
      "data": "data:image/tiff;base64,...",
      "modality": "optical",
      "acquisition_date": "2024-08-12"
    }
  ],
  "query": "Detect coastal lines in this image"
}
```

#### Response Body
```json
{
  "query_id": "8f3b2c1a-5d4e-4f3b-8a2c-1e5d4e4f3b8a",
  "task": "detection",
  "answer": "The coastline and contiguous water body have been delineated.",
  "confidence": 0.96,
  "visual_evidence": {
    "mask_base64": "data:image/png;base64,...",
    "overlay_base64": "data:image/png;base64,...",
    "boxes": null
  },
  "geospatial": {
    "is_georeferenced": true,
    "crs": "EPSG:4326",
    "bounds": [16.30, 48.15, 16.45, 48.25],
    "resolution_m_per_px": 10.0
  },
  "execution_summary": {
    "tool_used": "rsunivlm_seg",
    "latency_ms": 1420,
    "parameters": {
      "prompt_tag": "[SEG]",
      "resolved_mode": "mask",
      "confidence_source": "model_softmax"
    }
  }
}
```

### `POST /api/v1/preview`
High-speed pre-render endpoint that converts raw multi-band 16-bit GeoTIFF / JPEG 2000 rasters into normalized web-viewable previews with spatial metadata.

---

## 🔒 Contract-First Governance

SatQuery AI adheres to strict contract-first principles documented in [`docs/`](docs/):
- **`docs/CONTRACT.md`**: Global naming conventions, canonical enum types, and module ownership.
- **`docs/API_CONTRACT.md`**: REST API endpoints, schemas, and standardized HTTP error codes.
- **`docs/AI_SERVICE_CONTRACT.md`**: Strict `TypedDict` shapes and mode-routing specifications for all AI functions.
- **`docs/DATABASE_CONTRACT.md`**: SQLite persistence schema and query logging specifications.

---

## 👥 Acknowledgments & License

- **Theme**: Space Technology
- **Organization**: Indian Space Research Organisation (ISRO) & Ministry of Space
- **Primary Reference Benchmark**: BigEarthNet, VRSBench, RSVQA, CDVQA
- **License**: MIT License. See [LICENSE](LICENSE) for details.
