# Optical–SAR Fusion Module

**Owner:** Person 2 (Fusion ML Specialist)  
**Contract Reference:** `docs/AI_SERVICE_CONTRACT.md §3`  
**Conformance Suite:** `ai_service/common/test_contract_conformance.py`

---

## 1. Overview & Problem Statement

Optical satellite sensors provide rich spectral reflectance (chlorophyll, water absorption, visual texture) but are hindered by cloud cover and lack structural penetration. Synthetic Aperture Radar (SAR) sensors provide day-and-night microwave backscatter measurements that capture surface roughness, moisture, and dielectric double-bounce signatures.

The **Optical–SAR Fusion module** combines both modalities to perform multi-sensor classification without requiring heavy multi-modal network training during the hackathon.

---

## 2. Classification Methodology

The module uses stacked spectral-index and radar-backscatter analysis:

1. **Optical Spectral Processing:**
   * **Vegetation (Visible Green Index / VDVI proxy):** \((2G - R - B) / (2G + R + B)\) identifies high chlorophyll reflectance.
   * **Water (Blue-Green Dominance):** \((B - R) / (B + R)\) combined with low overall brightness identifies water absorption.
2. **SAR Radar Backscatter Processing:**
   * **High Backscatter (\(> 0.60\)):** Double-bounce corner reflectors characteristic of dense urban buildings, bridges, and metal structures.
   * **Low Backscatter (\(< 0.22\)):** Specular scattering off smooth surfaces characteristic of calm water bodies and flat tarmac.
   * **Intermediate Backscatter (\(0.22 - 0.60\)):** Volume scattering from tree canopies and vegetation surface roughness.
3. **Multi-Sensor Decision Fusion:**
   * Pixel-wise voting combining spectral and radar evidence to classify:
     * **Built-up** (Crimson Red: `[220, 20, 60]`)
     * **Vegetation** (Forest Green: `[34, 139, 34]`)
     * **Water** (Dodger Blue: `[30, 144, 255]`)

---

## 3. Function Interface & Output Contract

```python
from ai_service.fusion import run_fusion
from PIL import Image

optical_img = Image.open("optical_scene.png")
sar_img = Image.open("sar_scene.png")

result = run_fusion(
    optical_image=optical_img,
    sar_image=sar_img,
    query="Identify built-up and water-covered regions."
)
```

### Response Structure (`FusionResult`)
```json
{
  "answer": "Multi-sensor optical-SAR fusion classified the scene into: 34.2% Built-up infrastructure, 41.5% Vegetation canopy, and 24.3% Water bodies...",
  "classified_regions_base64": "iVBORw0KGgo...",
  "sar_only_reading": "SAR Backscatter Analysis (mean intensity: 0.54): Strong double-bounce reflections identified across 31.0% of pixels indicative of metallic/dense built-up structures...",
  "confidence": 0.75,
  "meta": {
    "tool_used": "fusion_classifier",
    "parameters": {
      "method": "spectral_radar_backscatter_fusion",
      "urban_coverage_pct": 34.2,
      "vegetation_coverage_pct": 41.5,
      "water_coverage_pct": 24.3,
      "confidence_source": "heuristic"
    },
    "latency_ms": 140
  }
}
```

* **Standalone SAR Requirement:** `sar_only_reading` provides a genuine standalone SAR analysis that satisfies the PS requirement without requiring a second model.
* **Latency:** Executes in **< 1 second** on CPU/GPU.
