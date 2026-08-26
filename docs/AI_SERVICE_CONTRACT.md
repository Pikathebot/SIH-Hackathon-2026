# AI_SERVICE_CONTRACT.md — Orchestrator ↔ AI Modules Contract

**Version:** 1.0.0
**Consumer:** `backend/` orchestrator (Person 3)
**Producers:** `ai_service/rsunivlm/` (Person 1), `ai_service/fusion/` (Person 2)

These are **Python function contracts**, called in-process (see `ARCHITECTURE.md` §3 for why). Person 1 and Person 2 may implement whatever is behind these functions however they want — model choice, prompt engineering, caching, batching — as long as the signature, return shape, and error behavior below are honored exactly. Person 3 codes against this contract and must never need to read Person 1/2's internals to call these correctly.

---

## 1. Shared types

Define these once in `ai_service/common/types.py` and import everywhere — do not redefine locally in either module.

```python
from typing import TypedDict, Literal, Optional
from PIL import Image

Modality = Literal["optical", "sar"]

class ExecutionMeta(TypedDict):
    tool_used: str          # canonical value from CONTRACT.md §5, e.g. "rsunivlm_vqa"
    parameters: dict        # opaque per-tool params, e.g. {"prompt_tag": "[VQA]"}
    latency_ms: int

class VQAResult(TypedDict):
    answer: str
    confidence: float       # 0.0-1.0
    meta: ExecutionMeta

class CaptioningResult(TypedDict):
    caption: str
    confidence: float
    meta: ExecutionMeta

class DetectionResult(TypedDict):
    mode: Literal["bbox", "mask"]
    boxes: Optional[list[list[int]]]      # [[x1,y1,x2,y2], ...], present iff mode == "bbox"
    mask_base64: Optional[str]            # present iff mode == "mask"
    overlay_base64: Optional[str]         # present iff mode == "mask"
    confidence: float
    meta: ExecutionMeta

class ChangeResult(TypedDict):
    answer: str
    mask_base64: Optional[str]
    overlay_base64: Optional[str]
    confidence: float
    meta: ExecutionMeta

class FusionResult(TypedDict):
    answer: str
    classified_regions_base64: str
    sar_only_reading: str            # required — the standalone SAR interpretation, not just a fused answer
    confidence: float
    meta: ExecutionMeta
```

Every result dict **must** include `meta.latency_ms` and `meta.tool_used` — this is what flows straight into the API's `execution_summary`. Person 3 does not compute latency independently; he trusts the value each function reports (measured by the function itself, wall-clock, around the actual model call).

---

## 2. Function contracts — RSUniVLM module (Person 1)

Module path: `ai_service/rsunivlm/wrapper.py`

```python
def run_vqa(image: Image.Image, question: str) -> VQAResult:
    """Prompt tag: [VQA]. Typical latency ~0.4-2s."""

def run_captioning(image: Image.Image) -> CaptioningResult:
    """Prompt tag: [CAP]. Typical latency ~1-2s."""

def run_detection(image: Image.Image, query: str, mode: Literal["auto","bbox","mask"] = "auto") -> DetectionResult:
    """
    mode='auto' routing rule (must be implemented exactly, it's load-bearing for demo latency):
      - query contains any of: 'where', 'locate', 'find', 'box'  -> use [VG] bounding box (~1.7-2s)
      - query contains any of: 'highlight', 'segment', 'mask'    -> use [SEG] pixel mask (~29-36s)
      - otherwise default to [VG] (fast path) unless query explicitly requests a mask
    Caller may force mode='bbox' or mode='mask' to bypass the heuristic.
    """

def run_change_detection(image_before: Image.Image, image_after: Image.Image, query: Optional[str] = None) -> ChangeResult:
    """Prompt tag: [CCD] for the answer text; [SEG] on the pair if a mask is requested/needed.
    Typical latency: [CCD] ~4s, [SEG]-based mask ~26-36s."""
```

**Confidence heuristic (must be documented in code comments, not hardcoded silently):** if RSUniVLM does not expose a usable logit/softmax score for a given mode, use a fixed, explicitly-labeled heuristic value (e.g. `0.75` for successful `[VG]`/`[SEG]` calls with no hallucination check) and note this in the `meta.parameters` as `{"confidence_source": "heuristic"}` vs `{"confidence_source": "model_softmax"}`. The backend and frontend may choose to display heuristic-based confidence differently — they can only do that if this field is honest.

**Error behavior:** on model failure (OOM, malformed image, checkpoint not loaded), raise `AIServiceError(code="MODEL_INFERENCE_FAILED", message=...)` (defined in `ai_service/common/errors.py`) — do not return a result dict with a fabricated low-confidence answer. The orchestrator catches this and maps it to the `MODEL_INFERENCE_FAILED` API error code.

---

## 3. Function contract — Fusion module (Person 2)

Module path: `ai_service/fusion/wrapper.py`

```python
def run_fusion(optical_image: Image.Image, sar_image: Image.Image, query: str) -> FusionResult:
    """
    Must classify at minimum: built-up / water / vegetation regions using both inputs.
    `sar_only_reading` must be a genuine SAR-only interpretation (not just a copy of `answer`) —
    this is what covers the PS's standalone SAR-analysis expectation without a second model.
    Typical latency target: <10s (rule-based/logistic classifier, no heavy inference expected).
    """
```

**Error behavior:** same `AIServiceError` contract as above. If given two images of the same modality (caller error, should have been caught upstream by the orchestrator's input validation), raise `AIServiceError(code="INVALID_MODALITY_COMBINATION", ...)` rather than silently proceeding.

---

## 4. Orchestrator responsibilities (Person 3, not delegated)

- Input validation (image count, modality match per task — see `API_CONTRACT.md` §1) happens **before** calling any `ai_service` function. Neither AI module should have to re-validate what the orchestrator already guarantees, except as a defensive last line (see fusion's modality check above).
- Intent classification (which task the query maps to) is the orchestrator's job, not the AI modules'. The AI modules only ever receive a call to the specific function that matches the already-decided task.
- The orchestrator is responsible for mapping `AIServiceError` → the correct HTTP error code/status from `API_CONTRACT.md` §1. AI modules never construct HTTP responses.
- The orchestrator is responsible for base64-encoding/decoding at the API boundary — AI modules work with `PIL.Image.Image` objects, never raw base64 strings, keeping them testable in isolation.

## 5. Mock implementations (required, Day 1 deliverable)

Both Person 1 and Person 2 must provide a `mock.py` alongside `wrapper.py` in their module (`ai_service/rsunivlm/mock.py`, `ai_service/fusion/mock.py`) implementing the exact same function signatures with hardcoded/fast fake responses. Person 3 imports whichever is configured via `AI_SERVICE_MODE=mock|real` env var, so backend and frontend integration is never blocked waiting on real models. See `INTEGRATION_GUIDE.md` §2.
