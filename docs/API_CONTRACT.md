# API_CONTRACT.md — Frontend ↔ Backend HTTP Contract

**Version:** 2.2.0 (2.2.0 adds `HistoryEntry.images`; 2.1.0 adds `GET /assets/{asset_id}/preview`; 2.0.0 made `/query`, `/upload`, `/assets` and `/preview` require authentication; see §5)
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
Authorization: Bearer <access_token>      (v2.0.0, required; see §5)
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
      "url_or_base64": "string — an https URL, a base64-encoded image payload (optionally a data: URI), or an asset URL '/api/v1/assets/<asset_id>'",
      "asset_id": "string, optional (v2.0.0) — id returned by POST /api/v1/upload; use instead of url_or_base64"
    }
  ],
  "session_id": "string, optional (v2.0.0) — attach this query to one of the caller's analysis sessions"
}
```

*(v2.0.0)* Each image needs exactly one of `url_or_base64` or `asset_id`. An asset must belong to the caller; if it doesn't, the API returns `404` so asset ids can't be probed. Remote URLs must resolve to public internet addresses. Loopback, private, link-local and reserved addresses are rejected with `UNSUPPORTED_FORMAT`. Local filesystem paths are not accepted. An unknown `session_id`, or one belonging to another user, returns `404 NOT_FOUND`.

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
    "code": "INVALID_IMAGE_COUNT | INVALID_MODALITY_COMBINATION | UNSUPPORTED_FORMAT | MODEL_INFERENCE_FAILED | INTERNAL_ERROR | UNAUTHORIZED | FORBIDDEN | NOT_FOUND | CONFLICT | VALIDATION_ERROR | PAYLOAD_TOO_LARGE",
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
| `UNAUTHORIZED` *(v2.0.0)* | 401 |
| `FORBIDDEN` *(v2.0.0)* | 403 |
| `NOT_FOUND` *(v2.0.0)* | 404 |
| `CONFLICT` *(v2.0.0)* | 409 |
| `VALIDATION_ERROR` *(v2.0.0)* | 422 |
| `PAYLOAD_TOO_LARGE` *(v2.0.0)* | 413 |

The backend must **never** let an unhandled exception produce a bare 500 with no JSON body — every error path returns this shape. This matters because the frontend's error-handling code is written once against this contract and should never need a try/catch around JSON parsing itself.

### `GET /api/v1/health`

Trivial liveness check for local dev / demo rehearsal, no auth.

**Response — 200 OK**
```json
{ "status": "ok", "rsunivlm_loaded": true, "fusion_loaded": true }
```

*(v1.2.0, additive)* The response also includes an optional `engine` object, for example `{"engine": "hybrid", "mode": "real", "notes": [], "vlm_server": "http://127.0.0.1:8080", "vlm_model": "qwen3-vl-8b", "vlm_available": true}`. The `vlm_*` keys are present only for the `qwen` and `hybrid` engines in real mode.

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
- CORS: origins come from the `CORS_ORIGINS` setting, a comma-separated list that defaults to `http://localhost:3000,http://127.0.0.1:3000`. Never use `*`, because credentials are allowed.

---

## 5. Authentication, sessions, uploads and history *(v2.0.0)*

All endpoints below are under `/api/v1`. They use JSON with snake_case fields and return the §1 error shape on failure.

Every endpoint requires `Authorization: Bearer <access_token>`, except `GET /health` and `POST /auth/register`, `/auth/login`, `/auth/refresh` and `/auth/logout`. A missing, expired or invalid token returns `401 UNAUTHORIZED`. Users only ever see their own sessions, queries and assets. Another user's id behaves exactly like a missing one and returns `404 NOT_FOUND`.

**Tokens.**
- `access_token` is a JWT valid for 15 minutes. It is sent in the `Authorization` header. The frontend keeps it in memory, never in `localStorage`.
- The refresh token is an opaque value in a cookie named `satquery_refresh`. The cookie is `httpOnly` and `SameSite=Lax`, is scoped to the path `/api/v1/auth`, and is valid for 14 days.
- The refresh token is replaced on every refresh, and logout revokes it on the server.

### Auth

| Method & path | Body | 2xx response |
|---|---|---|
| `POST /auth/register` | `{"email": str, "password": str (10-128 chars)}` | `201` `AuthResponse` plus the refresh cookie. An email that is already registered returns `409 CONFLICT`. When `ALLOW_REGISTRATION=false`, returns `403 FORBIDDEN` |
| `POST /auth/login` | `{"email": str, "password": str}` | `200` `AuthResponse` plus the refresh cookie. A wrong email or password returns `401 UNAUTHORIZED`, with the same message for both |
| `POST /auth/refresh` | none (uses the cookie) | `200` `AuthResponse` plus a new cookie. A missing, expired or revoked cookie returns `401` |
| `POST /auth/logout` | none (uses the cookie) | `204`. Revokes the refresh token and clears the cookie. Safe to call more than once |
| `GET /auth/me` | none | `200` `User` |

```json
// AuthResponse
{ "access_token": "eyJ...", "token_type": "bearer", "expires_in": 900,
  "user": { "id": "uuid", "email": "a@example.com", "role": "user | admin", "created_at": "2026-11-01T12:00:00Z" } }
```

### Analysis sessions

| Method & path | Body | 2xx response |
|---|---|---|
| `GET /sessions` | none | `200` `[Session]`, most recently updated first |
| `POST /sessions` | `{"title": str (1-200)}`, optional; defaults to `"New analysis"` | `201` `Session` |
| `GET /sessions/{session_id}` | none | `200` `Session` |
| `PATCH /sessions/{session_id}` | `{"title": str (1-200)}` | `200` `Session` |
| `DELETE /sessions/{session_id}` | none | `204`. Also deletes the session's queries |
| `GET /sessions/{session_id}/queries` | none | `200` `[HistoryEntry]`, oldest first |

```json
// Session
{ "id": "uuid", "title": "Rotterdam port", "created_at": "...", "updated_at": "...", "query_count": 3 }
// HistoryEntry: enough to show a past exchange again
{ "id": "uuid", "query_text": "Locate all ships", "created_at": "...", "status": "success | error",
  "error_code": null, "image_asset_ids": ["uuid"],
  "images": [{ "asset_id": "uuid", "modality": "optical | sar", "date": "2024-03-02 or null" }],
  "response": { /* the full QueryResponse body from §1, or null when status = "error" */ } }
```

*(v2.2.0)* `images` lists each submitted image in request order, with the `modality` and `date` given in that query. For queries stored before v2.2.0, `modality` and `date` are `null`. `image_asset_ids` stays for compatibility and equals `images[].asset_id`.

### Uploads and assets

`POST /upload` takes `multipart/form-data` with one `file` field. Accepted types are GeoTIFF, JPEG 2000, PNG and JPEG. The type is checked from the file's magic bytes, not its extension. A file larger than `MAX_UPLOAD_MB` returns `413 PAYLOAD_TOO_LARGE`. Any other type returns `400 UNSUPPORTED_FORMAT`. A successful upload returns `200`:
```json
{ "asset_id": "uuid", "filename": "scene.tif", "url": "/api/v1/assets/<asset_id>",
  "preview_base64": "data:image/png;base64,...", "format": "geotiff | standard",
  "width": 10980, "height": 10980, "size_bytes": 123456789, "geospatial": null }
```

`GET /assets/{asset_id}` returns the original file. Only the owner can fetch it; anyone else gets `404`.

`GET /assets/{asset_id}/preview` *(v2.1.0)* returns a browser-renderable `image/png` preview of the asset, at most 1024 px on its longest side, with the same radiometric normalisation as `/upload`. Only the owner can fetch it; anyone else gets `404`. The frontend uses it to show images from history, including GeoTIFF and JPEG 2000 uploads that browsers cannot display.

`POST /preview` keeps the same body and response. It now requires authentication and follows the same URL rules as `/query`.
