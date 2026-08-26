# DATABASE_CONTRACT.md — Persistence Schema

**Version:** 1.0.0
**Owner:** Person 3 (backend) — schema changes go through the same PR process as `CONTRACT.md` §6.
**Engine (sprint default):** SQLite via SQLAlchemy, file at `backend/data/satquery.db`. Swappable to Postgres post-hackathon without schema changes (types below are chosen to be portable).

Persistence is **not** required for the core demo to function — the API is stateless per-request. This schema exists for: (a) a "recent queries" panel if Person 4 has time, (b) the judges' Q&A benefit of showing a query log, (c) debugging during integration. Do not let DB work block the critical path.

---

## 1. Tables

### `images`

Metadata for uploaded/reference images. The binary/base64 payload itself is **not** stored in this table — store it on disk under `backend/data/images/<id>.<ext>` and keep only the path here.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `TEXT` | PK, UUID v4 | Matches the `id` used in the API request's `images[].id` for the duration of one query — regenerated per upload, not stable across requests |
| `modality` | `TEXT` | NOT NULL, enum: `optical`\|`sar` | Matches `CONTRACT.md` §5 |
| `capture_date` | `TEXT` | NULL | ISO-8601 date string, nullable — only present for change-detection inputs |
| `storage_path` | `TEXT` | NOT NULL | Relative path under `backend/data/images/` |
| `checksum` | `TEXT` | NOT NULL | SHA-256 of the file, used to dedupe re-uploads within the same demo session |
| `created_at` | `TEXT` | NOT NULL | ISO-8601 timestamp, UTC |

### `queries`

One row per `POST /api/v1/query` call — the audit log the execution-summary panel and judges' Q&A can be sourced from.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `TEXT` | PK, UUID v4 | |
| `query_text` | `TEXT` | NOT NULL | Raw user query string |
| `image_ids` | `TEXT` | NOT NULL | JSON-encoded array of `images.id` foreign keys, e.g. `["a1b2...","c3d4..."]` |
| `selected_task` | `TEXT` | NOT NULL, enum from `CONTRACT.md` §5 | |
| `tool_used` | `TEXT` | NOT NULL, enum from `CONTRACT.md` §5 | |
| `parameters` | `TEXT` | NULL | JSON-encoded object, opaque per-tool params |
| `answer` | `TEXT` | NULL | The natural-language answer returned |
| `confidence` | `REAL` | NOT NULL | Float in `[0.0, 1.0]` |
| `visual_evidence_type` | `TEXT` | NOT NULL, enum: `none`\|`bbox`\|`mask` | |
| `visual_evidence_ref` | `TEXT` | NULL | Path to a saved overlay/mask image on disk, if any (do not store base64 blobs in the DB row) |
| `latency_ms` | `INTEGER` | NOT NULL | |
| `inputs_validated` | `INTEGER` | NOT NULL, boolean 0/1 | SQLite has no native boolean |
| `status` | `TEXT` | NOT NULL, enum: `success`\|`error` | |
| `error_code` | `TEXT` | NULL | Populated only when `status = 'error'`, matches `API_CONTRACT.md` §1 error codes |
| `created_at` | `TEXT` | NOT NULL | ISO-8601 timestamp, UTC |

**No foreign key enforcement required in SQLite for the sprint**, but `image_ids` values must correspond to real `images.id` rows if you want the "recent queries" UI to be able to re-render thumbnails.

---

## 2. Naming rules specific to this schema

- Table names: snake_case, plural (`images`, `queries`) — matches `CONTRACT.md` §3.
- No column is ever named `data`, `info`, `value`, or `json` — every JSON-encoded column has a name describing its actual content (`parameters`, `image_ids`).
- Timestamps are always `TEXT` in ISO-8601 UTC (`2026-08-26T14:03:00Z`), never Unix epoch integers — keeps SQLite rows human-readable during debugging.
- Enum-valued columns must only ever contain values from the canonical lists in `CONTRACT.md` §5. If the backend writes a value not on that list, that's a bug, not a new valid value.

## 3. What explicitly does NOT belong in the database

- Model checkpoints, LoRA adapter weights → filesystem, referenced by path in code/config, not DB rows.
- Base64 image payloads or full-resolution overlay images → filesystem, referenced by path.
- Session/auth state → out of scope for this sprint (no auth planned).

## 4. Migration policy for the sprint

Given the timeline, use SQLAlchemy's `create_all()` against this schema directly rather than standing up Alembic migrations. If the schema changes mid-sprint, delete and recreate `satquery.db` locally — do not attempt to hand-migrate. This is acceptable only because the DB holds no data that isn't reproducible from a fresh demo run.
