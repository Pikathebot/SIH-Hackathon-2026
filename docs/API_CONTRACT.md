# API_CONTRACT.md — Frontend ↔ Backend HTTP Contract

**Version:** 1.1.0
**Base URL (local dev):** `http://localhost:8000`
**Consumers:** `frontend/` (Person 4)
**Producers:** `backend/` (Person 3)

This is the *only* interface the frontend is allowed to depend on. If the frontend needs something the backend doesn't return, that's a contract change (see `CONTRACT.md` §6) — the frontend must not scrape, guess, or reach around this contract.

---

## 1. Endpoints

### `POST /api/v1/query`

Submit a natural-language query with 1–2 images. This is the **only** endpoint the demo flow needs.

**Headers**
```
Content-Type: application/json
```

**Request body**
```json
{
  "query": "string, required, 1-2000 chars",
  "images": [
    {
      "id": "string, required, unique within this request, e.g. 'img1'",
      "modality": "optical | sar",
      "date": "ISO-8601 date string, optional, e.g. '2023-01-15'",
      "url_or_base64": "string, required — either an https URL or a raw base64-encoded image payload"
    }
  ]
}
```

Constraints:
- `images` array length must be 1 or 2. Zero or 3+ images → `400` (see §3).
- For `change_detection` intent: exactly 2 images, both `modality: "optical"`, both with a `date`, and dates must differ.
- For `fusion` intent: exactly 2 images, one `modality: "optical"` and one `modality: "sar"`.
- For `vqa` / `captioning` / `detection` intent: exactly 1 image.
- The backend validates these combinations — the frontend should mirror the same validation client-side for fast feedback, but the backend is the source of truth and must reject invalid combos regardless of what the frontend sent.

**Response body — 200 OK**
```json
{
  "answer": "string — natural-language answer or description",
  "confidence": 0.78,
  "task": "vqa | captioning | detection | change_detection | fusion",
  "visual_evidence": {
    "type": "none | bbox | mask",
    "boxes": [[51, 384, 235, 506]],
    "mask_base64": null,
    "overlay_base64": null,
    "geospatial": {
      "crs": "EPSG:4326",
      "image_bounds": [12.720, 48.090, 12.760, 48.130],
      "geo_boxes": [
        [[12.730, 48.100], [12.750, 48.100], [12.750, 48.120], [12.730, 48.120], [12.730, 48.100]]
      ]
    }
  },
  "execution_summary": {
    "selected_task": "change_detection",
    "tool_used": "rsunivlm_ccd",
    "parameters": { "threshold": 0.35 },
    "inputs_validated": true,
    "latency_ms": 3950
  }
}
```

Field notes:
- `visual_evidence.type` determines which of `boxes` / `mask_base64` / `overlay_base64` is populated; the other(s) are `null`. `type: "none"` (e.g. for plain VQA answers) means all three are `null`.
- `boxes` format when present: array of `[x1, y1, x2, y2]` in pixel coordinates relative to the **first** submitted image, one array per detected region (usually length 1 for this PS's use cases).
- `execution_summary` is **always present**, even on paths that return a low-confidence or partial answer. This is the field the frontend renders in the "execution trace panel" — it is a required demo feature, not decoration.
- `tool_used` values are the canonical enum from `CONTRACT.md` §5 — frontend should treat unrecognized values defensively (render the raw string) rather than crash, in case a new tool is added mid-sprint.

**Response body — 4xx/5xx (error)**
```json
{
  "error": {
    "code": "INVALID_IMAGE_COUNT | INVALID_MODALITY_COMBINATION | UNSUPPORTED_FORMAT | MODEL_INFERENCE_FAILED | INTERNAL_ERROR",
    "message": "human-readable string safe to display to the user",
    "detail": "optional string, technical detail for logs — frontend should not display this to end users"
  }
}
```

Status code mapping:
| Code | HTTP status |
|---|---|
| `INVALID_IMAGE_COUNT` | 400 |
| `INVALID_MODALITY_COMBINATION` | 400 |
| `UNSUPPORTED_FORMAT` | 400 |
| `MODEL_INFERENCE_FAILED` | 502 |
| `INTERNAL_ERROR` | 500 |

The backend must **never** let an unhandled exception produce a bare 500 with no JSON body — every error path returns this shape. This matters because the frontend's error-handling code is written once against this contract and should never need a try/catch around JSON parsing itself.

### `GET /api/v1/health`

Trivial liveness check for local dev / demo rehearsal, no auth.

**Response — 200 OK**
```json
{ "status": "ok", "rsunivlm_loaded": true, "fusion_loaded": true }
```

---

## 2. Request/response examples per task type

### VQA
```json
// Request
{ "query": "How many basketball courts?", "images": [{"id":"img1","modality":"optical","url_or_base64":"..."}] }
// Response (excerpt)
{ "answer": "2", "confidence": 0.91, "task": "vqa", "visual_evidence": {"type": "none", "boxes": null, "mask_base64": null, "overlay_base64": null} }
```

### Detection — fast path (bounding box)
```json
// Request
{ "query": "Where is the water body?", "images": [{"id":"img1","modality":"optical","url_or_base64":"..."}] }
// Response (excerpt)
{ "task": "detection", "visual_evidence": {"type": "bbox", "boxes": [[51,384,235,506]], "mask_base64": null, "overlay_base64": null} }
```

### Detection — slow path (pixel mask)
```json
// Request
{ "query": "Highlight the water bodies in this image.", "images": [{"id":"img1","modality":"optical","url_or_base64":"..."}] }
// Response (excerpt)
{ "task": "detection", "visual_evidence": {"type": "mask", "boxes": null, "mask_base64": "iVBORw0...", "overlay_base64": "iVBORw0..."} }
```

### Change detection
```json
// Request
{
  "query": "What changed between these two dates, and where did the change occur?",
  "images": [
    {"id":"img1","modality":"optical","date":"2023-01-15","url_or_base64":"..."},
    {"id":"img2","modality":"optical","date":"2024-03-02","url_or_base64":"..."}
  ]
}
// Response (excerpt)
{ "task": "change_detection", "answer": "a parking lot is built at the top.", "visual_evidence": {"type": "mask", "overlay_base64": "..."} }
```

### Fusion
```json
// Request
{
  "query": "Use the optical and SAR images together to identify built-up and water-covered regions.",
  "images": [
    {"id":"img1","modality":"optical","url_or_base64":"..."},
    {"id":"img2","modality":"sar","url_or_base64":"..."}
  ]
}
// Response (excerpt)
{ "task": "fusion", "visual_evidence": {"type": "mask", "overlay_base64": "..."} }
```

---

## 3. Frontend rules

- The frontend must render **whatever `execution_summary` contains** without assuming specific keys inside `parameters` (that object's shape varies per tool — treat it as an opaque key/value table to render generically).
- The frontend must handle `visual_evidence.type: "none"` gracefully (no broken image icon, no map overlay attempt).
- Do not hardcode latency expectations into UI timeouts below 40 seconds — `[SEG]` calls can take up to ~35s (see `AI_SERVICE_CONTRACT.md`). Show a loading state, not a spinner that gives up early.

## 4. Backend rules

- The backend owns all validation. Never trust the frontend to have pre-validated image counts/modalities.
- The backend must populate `execution_summary` even when returning a degraded/fallback answer (e.g. AI service timeout with a partial result) — set `inputs_validated: true` and note the degradation in `parameters` rather than omitting the summary.
- CORS: allow `http://localhost:3000` (or whatever the frontend dev port is) explicitly during development; do not use `*` once any auth is added later.
