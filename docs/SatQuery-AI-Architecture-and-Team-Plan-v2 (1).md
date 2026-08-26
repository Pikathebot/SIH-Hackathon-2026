# SatQuery AI — Architecture & Team Execution Plan (v2 — RSUniVLM-based)

**Team size:** 4 (+2 presentation)
**Problem statement:** SatQuery AI — agentic vision-language assistant for single/paired remote-sensing imagery
**Deadline:** 20 September 2026 (prototype) — sprint plan below assumes an emergency 4-day timeline; adjust dates if you have the full runway

**What changed from v1:** RSUniVLM (https://rsunivlm.github.io/, arXiv:2412.05679) is a unified RS vision-language model — image-level (VQA/captioning), region-level (grounding/detection), and pixel-level (segmentation) tasks, plus **native multi-image change detection/captioning** — all in one ~1B-parameter LLaVA-NeXT-based model with working demo code and downloadable checkpoints. It replaces the separate VQA+captioning model, the pretrained detector, and Person 2's hand-built change-diff pipeline with **one wrapped model**. It does **not** cover SAR, so optical–SAR fusion stays a standalone component.

**Day 1 verification: PASSED.** All five task modes were smoke-tested against the base checkpoint before any fine-tuning:

| Task | Prompt tag | Result | Latency |
|---|---|---|---|
| Change captioning | `[CCD]` | Coherent, accurate change description on a real before/after pair | 3.95s |
| Change segmentation (buildings) | `[SEG]` | Correct localized change mask | 28.43s |
| Change segmentation (roads) | `[SEG]` | Correct localized change mask | 25.82s |
| Land-cover captioning | `[CAP]` | Coherent single-image caption | 1.27s |
| Visual QA | `[VQA]` | Correct count answer | 0.42s |

**Follow-up test: generic object grounding/segmentation — PASSED, and better than expected.** Testing arbitrary prompts ("water body," "bridge," "windmill," "basketball court," "built-up area") surfaced a fifth mode not in the original test batch:

| Query mode | Example prompt | Output | Latency |
|---|---|---|---|
| **`[VG]` — bounding box grounding** | `"[VG] Where is the water body?"` | Normalized bbox coords, e.g. `[51, 384, 235, 506]` | **~1.7–1.9s** |
| **`[SEG]` — pixel segmentation** | `"[SEG] water."` or natural-sentence form | Pixel mask, 42–60% coverage depending on target | **~29–36s** |

Both handle generic/arbitrary categories without hallucinating, and both accept short keywords or natural sentences. This resolves the "does `run_detection()` handle arbitrary PS queries like 'highlight the water body'" open question from before — yes, cleanly.

**This changes the segmentation-latency risk from "mitigate with pre-caching" to "mostly avoid by design":** route fast "locate/find/where is X" queries to `[VG]` (~2s, good enough for live judging), and reserve the slow `[SEG]` pixel mask for when the query explicitly asks to "highlight/segment/mask" something. Pre-caching `[SEG]` outputs for the demo script is still worth doing as a belt-and-suspenders backup, but it's no longer the only lever.

---

## 1. System Architecture

### 1.1 Components

| Layer | Component | Owner |
|---|---|---|
| Presentation | React frontend (upload UI, map viewer, results panel) | Person 4 |
| API | FastAPI backend + Agent Orchestrator | Person 3 |
| Specialist tool | **RSUniVLM wrapper** — VQA, captioning, grounding/detection, change detection & change captioning (LoRA-adapted) | Person 1 |
| Specialist tool | Optical–SAR fusion + SAR-only interpretation | Person 2 |
| Data | RSUniVLM checkpoint, LoRA adapter, fusion training patches | Shared (Persons 1 & 2 produce, Person 3 serves) |

Dropped from v1: separate pretrained detector, separate feature-diff change pipeline. RSUniVLM's grounding/segmentation head covers "highlight/locate X," and its multi-image mode covers change detection/captioning natively.

### 1.2 Request lifecycle

Unchanged from v1 — frontend → `POST /query` → Agent Orchestrator classifies intent → routes to `run_vqa`/`run_captioning`/`run_detection`/`run_change_detection` (all RSUniVLM) or `run_fusion` (Person 2's model) → structured JSON response.

### 1.3 Why this shape

- Consolidating four tools into one wrapped model removes the integration risk of stitching together three separate ML pipelines (VLM + detector + diff pipeline) under a 4-day clock — now there's one model to load, one checkpoint to manage, one inference path to debug.
- The orchestrator is still the "agentic" differentiator judges score — unaffected by this change, still the most polished piece of the system.
- LoRA fine-tuning on a small BigEarthNet/RSVQA subset is still mandatory — now applied on top of RSUniVLM (already RS-pretrained) rather than a general VLM, which is arguably a *stronger* domain-adaptation story: you're specializing an RS-specific foundation model further for the ISRO/SAC evaluation set, not bolting RS knowledge onto a generic model from scratch.
- **Risk to flag honestly in the feasibility slide:** RSUniVLM's training data appears optical/RGB-focused with no clear SAR support — confirm this against the paper before the demo. This is exactly why fusion stays a separate, dedicated component rather than folding into RSUniVLM.

---

## 2. API Contract (unchanged externally — only the backing implementation of 4 of 5 tools changes)

### `POST /query`

Request/response schema is identical to v1 (see below) — this matters because Person 3 and Person 4 do not need to change anything about the contract, only Person 1's internal implementation changes.

**Request**
```json
{
  "query": "What changed between these two dates, and where did the change occur?",
  "images": [
    { "id": "img1", "modality": "optical", "date": "2023-01-15", "url_or_base64": "..." },
    { "id": "img2", "modality": "optical", "date": "2024-03-02", "url_or_base64": "..." }
  ]
}
```

**Response**
```json
{
  "answer": "Built-up area increased in the northeast quadrant between the two dates.",
  "confidence": 0.78,
  "task": "change_detection",
  "visual_evidence": {
    "type": "mask",
    "overlay_url_or_base64": "..."
  },
  "execution_summary": {
    "selected_task": "change_detection",
    "tool_used": "rsunivlm_change",
    "parameters": { "threshold": 0.35 },
    "inputs_validated": true
  }
}
```

### Specialist function signatures

```python
# All four of these are now backed by the SAME loaded RSUniVLM model/checkpoint —
# different prompts/modes into one inference call, not four separate models.

def run_vqa(image: Image, question: str) -> dict:
    """RSUniVLM image-level QA. Returns {answer, confidence}"""

def run_captioning(image: Image) -> dict:
    """RSUniVLM image-level captioning. Returns {caption, confidence}"""

def run_detection(image: Image, query: str, mode: str = "auto") -> dict:
    """RSUniVLM region-level grounding ([VG], ~2s) or pixel-level segmentation ([SEG], ~30s).
    Route by query phrasing: 'locate/find/where is X' -> [VG] bounding box (fast, live-demo-safe);
    'highlight/segment/mask X' -> [SEG] pixel mask (slower, richer visual).
    Returns {boxes: [[x1,y1,x2,y2],...] (VG) OR mask_base64 (SEG), overlay_base64, confidence}"""

def run_change_detection(image_before: Image, image_after: Image, query: str = None) -> dict:
    """RSUniVLM native multi-image mode. Returns {answer, confidence, mask_base64 (if available)}"""

# Unchanged — still a separate model, RSUniVLM does not cover SAR
def run_fusion(optical_image: Image, sar_image: Image, query: str) -> dict:
    """Returns {answer, confidence, classified_regions_base64}"""
```

Agree this on day 1 as before — the contract hasn't moved, so if you already locked it under v1, nothing needs re-syncing with Person 3/4.

---

## 3. Per-Person Plan

### Person 1 — RSUniVLM Wrapper: VQA, Captioning, Grounding & Change Detection (ML)

**Owns:** `run_vqa()`, `run_captioning()`, `run_detection()`, `run_change_detection()` — all via one model

| Days | Task |
|---|---|
| 1 | ✅ **Done.** RSUniVLM cloned, env set up, checkpoint loaded, all five task modes (`[CCD]`, `[SEG]` x2, `[CAP]`, `[VQA]`) smoke-tested and passed — see verification table above. |
| 2 | Wrap all four functions (`run_vqa`→`[VQA]`, `run_captioning`→`[CAP]`, `run_detection`→`[SEG]` with a generic object prompt, `run_change_detection`→`[CCD]`/`[SEG]`) against the base checkpoint, hand a *real* (not stubbed) version to Person 3 today. Start LoRA fine-tuning job (via `peft`, following their LLaVA-NeXT training path) on a tiny BigEarthNet/RSVQA subset (200–500 samples, 1 epoch) — must be running by end of today. **Also start pre-computing/caching the `[SEG]` outputs for whichever image pairs go into the live demo script**, since a 28s wait per segmentation call is a live-demo liability, not just a nice-to-have optimization. |
| 3 | LoRA training should finish — swap the fine-tuned adapter into all four wrapped functions. Tune prompts per task (grounding needs a different instruction template than free-form VQA). Add confidence scores (model logit/softmax if exposed, else a simple heuristic). Hand final versions to Person 3. |
| 4 | Buffer/bug-fixing. Support Person 2 if the fusion classifier wants to reuse RSUniVLM's vision encoder as a frozen feature extractor (saves them building one from scratch). Write 3–4 sample query/answer pairs per tool for the demo script. |

**Deliverable:** `rsunivlm_wrapper.py` exposing all four functions, the LoRA adapter checkpoint, and a short note on what RSUniVLM's SAR support actually is (confirm/deny for the feasibility slide and judges' Q&A — don't guess).

---

### Person 2 — Optical–SAR Fusion (ML)

**Owns:** `run_fusion()` only (freed from change detection — see Key Risk section)

| Days | Task |
|---|---|
| 1 | Set up a frozen pretrained encoder — check with Person 1 whether RSUniVLM's vision encoder can be reused for the optical side (saves compute/time vs. standing up a separate ResNet). Start labeling a handful of optical–SAR patches (built-up/water/vegetation). |
| 2 | Build the fusion approach: stack optical bands + SAR backscatter as extra channels, train a small classifier (logistic regression on stacked bands is fine for a sprint — judges care more about "uses both modalities" than model sophistication here). Wrap into `run_fusion()`, including a SAR-only reading as part of the same output (covers "SAR Analysis" without a second model). |
| 3 | Hand off to Person 3. Generate mask/overlay images Person 4 needs for the map UI. Since change detection is off your plate, use this freed time to stress-test fusion on a wider variety of patch pairs — this was the weakest-scoped component in v1 and now gets the attention it needs. |
| 4 | Buffer/bug-fixing, support end-to-end testing. |

**Deliverable:** `fusion.py` (includes SAR-only field), sample mask/overlay images for the demo.

---

### Person 3 — Backend & Agent Orchestrator (Dev)

Unchanged from v1 in structure — only the tool count/backing changes (4 tools still routed to, just 4 of them share one loaded model now, which actually simplifies deployment: one model to load into memory instead of two).

| Days | Task |
|---|---|
| 1 | Scaffold FastAPI project, define `/query` contract, stub all 5 logical tasks (vqa/captioning/grounding/change/fusion) with mock responses so Person 4 can start immediately. |
| 2 | Build orchestrator (LLM function-calling or lightweight classifier) for intent classification + input validation. |
| 3 | Wire in Person 1's RSUniVLM wrapper (single model load, four call paths) and Person 2's fusion function as they land. Build execution summary generator. |
| 4 | End-to-end testing, error handling for malformed input combos, Dockerize, support demo rehearsal. |

**Deliverable:** working FastAPI service, orchestrator module, Dockerfile, routing-logic doc.

---

### Person 4 — Frontend & Geospatial Visualization (Dev)

Unchanged from v1 — the frontend never needed to know how many models sit behind the API, only the contract, which hasn't moved.

**Deliverable:** working React app, Dockerfile/build config, demo script walkthrough.

---

## 4. Scripted Demo Flow (fixed — do not improvise live)

Unchanged from v1:
1. Upload single optical image → "Describe the land cover" → captioning (RSUniVLM)
2. Same image → specific VQA question → VQA (RSUniVLM), confidence shown
3. Upload single optical image → "Highlight the water bodies" → detection: `[SEG]` fires, pixel mask shown on the map (or use "Locate the water bodies" to demo the fast `[VG]` bounding-box path instead — worth deciding which one goes in the live script vs. which stays as a backup-video-only scenario, given the latency gap)
4. Upload optical + SAR pair → "Identify built-up and water-covered regions" → fusion (Person 2's model)
5. Upload two images, different dates → "What changed here?" → change detection (RSUniVLM, or fallback pipeline)
6. End on the execution summary panel

---

## 5. Key Risks (updated)

1. **SAR support gap.** RSUniVLM appears optical/RGB-trained with no confirmed SAR capability — this is exactly why fusion stays separate. Verify this claim against the arXiv paper before the demo, and never let RSUniVLM touch SAR inputs directly in the pitch.
2. **~~Change-detection mode unverified~~ — RESOLVED.** Day 1 testing confirmed `[CCD]` and `[SEG]` both work well on real bi-temporal pairs. No fallback needed.
3. **Segmentation latency (~29–36s per call) for `[SEG]` specifically.** Mitigated by design, not just caching: route "locate/find/where is X" queries to the fast `[VG]` mode (~1.7–2s, confirmed on generic/arbitrary object categories) and reserve `[SEG]` for explicit "highlight/segment/mask" requests. Still worth pre-caching the `[SEG]` output for whichever demo scenario uses it, as a backup.
4. **LoRA fine-tune is still the credibility anchor.** Must be real, must be running by end of Day 1/start of Day 2 now that verification is already done (a day earlier than originally planned, since Day 1 didn't need to be spent on a go/no-go decision). It's the one piece the PS explicitly disqualifies you for skipping.
5. **Checkpoint download size/time.** RSUniVLM's checkpoint is hosted on Google Drive — already downloaded per Day 1 results, but flag actual size/load time in Person 1's handoff notes so Person 3 knows what to expect when deploying/Dockerizing.

---

## 6. Timeline Summary (4-day sprint)

| Day | Milestone |
|---|---|
| 1 | ✅ API contract locked. ✅ Person 1 got RSUniVLM running and verified all 5 task modes pass. Person 2 starts fusion data labeling. Person 3/4 scaffold against stubs. LoRA fine-tune job kicked off. |
| 2 | LoRA fine-tune done, wrapped into all four functions, handed to Person 3. Person 2 builds fusion classifier. Person 1 starts pre-caching `[SEG]` outputs for the demo script's specific image pairs. |
| 3 | Full integration: real RSUniVLM + fusion wired into orchestrator and frontend. Confirm cached segmentation results render correctly in the map overlay. |
| 4 | End-to-end testing across all 5 demo scenarios, backup video recorded (with pre-rendered `[SEG]` segments to avoid 28s live waits), PPT locked with real screenshots. |

## 7. Presentation Team (Persons 5 & 6)

Unchanged from v1 — same responsibilities. One addition: the Technical Approach slide should now cite RSUniVLM (Liu & Lian, Pattern Recognition 2026 / arXiv:2412.05679) as the foundation model being fine-tuned, which is a stronger, more specific claim than "a pretrained VLM" — use it, and add it to the References slide.
