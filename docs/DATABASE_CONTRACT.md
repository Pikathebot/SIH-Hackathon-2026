# DATABASE_CONTRACT.md — Persistence Schema

**Version:** 1.1.0 (additive: users, analysis_sessions and refresh_tokens tables, ownership columns, Alembic migrations; see §5)
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
- Passwords in any reversible form. Only argon2 hashes go in `users.password_hash`.
- Raw refresh tokens. Only their SHA-256 hash goes in `refresh_tokens.token_hash`.

## 4. Migration policy for the sprint

Given the timeline, use SQLAlchemy's `create_all()` against this schema directly rather than standing up Alembic migrations. If the schema changes mid-sprint, delete and recreate `satquery.db` locally — do not attempt to hand-migrate. This is acceptable only because the DB holds no data that isn't reproducible from a fresh demo run.

---

## 5. v1.1.0: accounts and ownership (replaces §4)

**Engine.** SQLAlchemy 2 (async). The connection URL comes from `DATABASE_URL`, which defaults to `sqlite+aiosqlite:///<DATA_DIR>/satquery.db`. Switching to Postgres only requires changing that URL. IDs are still UUID v4 `TEXT`, and timestamps are still ISO-8601 UTC `TEXT`.

**Migrations.** Alembic, in `backend/alembic/`.
- Revision `0001` is the v1.0.0 schema, including the v1.1.0 `tool_used` values.
- Revision `0002` adds the tables and columns below.
- On startup the backend runs `alembic upgrade head`.
- If a database already has the `0001` tables but no `alembic_version` row, it is marked as `0001` first. Existing local databases are therefore upgraded in place instead of being deleted.

§4's "delete and recreate" policy no longer applies.

### `users` (new)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `TEXT` | PK, UUID v4 | |
| `email` | `TEXT` | NOT NULL, UNIQUE | Stored in lower case |
| `password_hash` | `TEXT` | NOT NULL | argon2id via `pwdlib` |
| `role` | `TEXT` | NOT NULL, enum: `user`\|`admin`, default `user` | |
| `created_at` | `TEXT` | NOT NULL | |

### `analysis_sessions` (new)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `TEXT` | PK, UUID v4 | |
| `user_id` | `TEXT` | NOT NULL, FK `users.id` ON DELETE CASCADE, indexed | |
| `title` | `TEXT` | NOT NULL | |
| `created_at` | `TEXT` | NOT NULL | |
| `updated_at` | `TEXT` | NOT NULL | Updated whenever a query is added |

### `refresh_tokens` (new)
| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | `TEXT` | PK, UUID v4 | |
| `user_id` | `TEXT` | NOT NULL, FK `users.id` ON DELETE CASCADE, indexed | |
| `token_hash` | `TEXT` | NOT NULL, UNIQUE | SHA-256 hex of the cookie value |
| `expires_at` | `TEXT` | NOT NULL | |
| `revoked_at` | `TEXT` | NULL | Set when the token is replaced or the user logs out |
| `created_at` | `TEXT` | NOT NULL | |

### New columns on existing tables
All new columns allow NULL, so rows from before v1.1.0 stay valid.

| Table | Column | Type | Notes |
|---|---|---|---|
| `images` | `user_id` | `TEXT`, indexed | Owner. NULL for older rows |
| `images` | `filename` | `TEXT` | Original upload filename |
| `images` | `size_bytes` | `INTEGER` | |
| `queries` | `user_id` | `TEXT`, indexed | |
| `queries` | `session_id` | `TEXT`, indexed | `analysis_sessions.id`. Deleting a session deletes its queries |

**Storage paths.** Both paths are relative to `DATA_DIR`.
- `images.storage_path`: uploads are stored at `uploads/<user_id>/<image_id>.<ext>`.
- `queries.visual_evidence_ref`: points to a JSON file at `evidence/<user_id>/<query_id>.json` of the form `{"visual_evidence": {...}, "images": [{"asset_id", "modality", "date"}]}`. The `images` list records the per-query modality and date of each input. Files written before API v2.2.0 hold the bare `visual_evidence` object. History can then be shown again without storing base64 in the database.
