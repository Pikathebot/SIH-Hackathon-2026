# RSUniVLM AI Service Module

**Owner:** Person 1 (ML Specialist)  
**Contract Reference:** `docs/AI_SERVICE_CONTRACT.md §2`  
**Conformance Suite:** `ai_service/common/test_contract_conformance.py`

---

## 1. Overview & Architecture

RSUniVLM (*A Unified Vision-Language Model for Remote Sensing*, Liu & Lian, Pattern Recognition 2026 / arXiv:2412.05679) is a foundation model tailored for remote-sensing multi-granularity tasks. It consolidates four distinct remote sensing tasks into **a single loaded model instance**:

1. **Visual Question Answering (VQA)**: Single-image reasoning and object counting (`[VQA]`).
2. **Land-Cover Captioning**: Free-form natural language scene description (`[CAP]`).
3. **Visual Grounding / Object Detection**: Bounding-box localization (`[VG]`).
4. **Semantic Segmentation**: Dense pixel-level masking (`[SEG]`).
5. **Change Detection & Captioning**: Bi-temporal multi-image change analysis (`[CCD]` / `[SEG]`).

### Model Specifications
* **Architecture:** LLaVA-NeXT with Granularity-oriented Mixture of Experts (G-MoE).
* **Vision Backbone:** `google/siglip-so400m-patch14-384`.
* **Language Backbone:** Qwen-1.5 (~1B params).
* **VRAM Footprint:** ~3.3 GB in `float16` precision (runs comfortably on 6GB+ GPUs like RTX 4060).

---

## 2. Granularity Routing & Latency Profiles

Measured wall-clock latency on local NVIDIA GeForce RTX 4060 Laptop GPU:

| Mode / Task | Prompt Tag | Granularity | Output Evidence | Typical Latency |
|---|---|---|---|---|
| **VQA** | `[VQA]` | 0 | `answer` text | **~0.4 – 2.0s** |
| **Captioning** | `[CAP]` | 0 | `caption` text | **~1.2 – 1.8s** |
| **BBox Grounding** | `[VG]` | 1 | `boxes: [[x1, y1, x2, y2]]` | **~1.7 – 2.2s** |
| **Pixel Mask** | `[SEG]` | 2 | `mask_base64`, `overlay_base64` | **~15 – 30s** |
| **Change Detection** | `[CCD]` | 0 | `answer`, `overlay_base64` | **~1.7 – 4.0s** |

### Automated Detection Routing Rule
When `run_detection(image, query, mode="auto")` is called:
* Queries containing `"where"`, `"locate"`, `"find"`, `"box"` route to the **fast BBox path (`[VG]`, ~1.8s)**.
* Queries containing `"highlight"`, `"segment"`, `"mask"` route to the **dense pixel mask path (`[SEG]`, ~16-30s)**.
* Otherwise, defaults to the fast BBox path for live judging responsiveness.

---

## 3. Function Signatures & Contract Compliance

All functions return strongly-typed dictionaries matching `ai_service/common/types.py`:

```python
from ai_service.rsunivlm import run_vqa, run_captioning, run_detection, run_change_detection
from PIL import Image

# 1. VQA
vqa_res = run_vqa(image, "How many basketball courts?")
# Returns: {"answer": "2", "confidence": 0.85, "meta": {"tool_used": "rsunivlm_vqa", "latency_ms": 1820, ...}}

# 2. Captioning
cap_res = run_captioning(image)
# Returns: {"caption": "Urban commercial sector...", "confidence": 0.80, "meta": {"tool_used": "rsunivlm_cap", ...}}

# 3. Detection
det_res = run_detection(image, "Where is the water body?", mode="auto")
# Returns: {"mode": "bbox", "boxes": [[35, 172, 155, 265]], "confidence": 0.75, "meta": {"tool_used": "rsunivlm_vg", ...}}

# 4. Change Detection
change_res = run_change_detection(img_before, img_after, query="What changed between dates?")
# Returns: {"answer": "Commercial development expanded...", "mask_base64": "...", "confidence": 0.78, "meta": {"tool_used": "rsunivlm_ccd", ...}}
```

---

## 4. Checkpoint & LoRA Adapter Setup

Checkpoints are ignored in Git (`.gitignore`) and stored locally under `checkpoints/`:

```bash
# Weights location
ai_service/rsunivlm/checkpoints/RSUniVLM/
├── config.json
├── model.safetensors (~3.3 GB)
└── tokenizer.json

# Optional LoRA adapter location
ai_service/rsunivlm/checkpoints/lora_adapter/
├── adapter_config.json
└── adapter_model.safetensors
```

### Environment Variables
* `AI_SERVICE_MODE`: `mock` or `real` (switches exports dynamically).
* `RSUNIVLM_CHECKPOINT_PATH`: `./ai_service/rsunivlm/checkpoints/RSUniVLM`
* `RSUNIVLM_LORA_ADAPTER_PATH`: `./ai_service/rsunivlm/checkpoints/lora_adapter` (optional)
