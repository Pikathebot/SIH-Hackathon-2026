# ARCHITECTURE.md — System Overview

**Version:** 1.0.0
**Companion reading:** `SatQuery-AI-Architecture-and-Team-Plan-v2.md` for the team/timeline plan this architecture supports.

---

## 1. Component diagram

```
┌─────────────────┐        HTTPS/JSON         ┌──────────────────────────┐
│   Frontend       │ ───── POST /api/v1/query ─▶│   Backend (FastAPI)      │
│   (React)        │◀──── JSON response ────────│   + Agent Orchestrator   │
│   Person 4       │                            │   Person 3               │
└─────────────────┘                            └──────────┬───────────────┘
                                                            │ in-process Python calls
                                                            │ (see §3 — not network calls)
                                        ┌───────────────────┴───────────────────┐
                                        ▼                                       ▼
                          ┌─────────────────────────┐             ┌─────────────────────────┐
                          │ ai_service/rsunivlm      │             │ ai_service/fusion        │
                          │ Person 1                 │             │ Person 2                 │
                          │ run_vqa / run_captioning  │             │ run_fusion                │
                          │ run_detection / run_change│             │                           │
                          └─────────────────────────┘             └─────────────────────────┘
                                        │                                       │
                                        ▼                                       ▼
                              RSUniVLM checkpoint +                  fusion classifier +
                              LoRA adapter (filesystem)               shared encoder (filesystem)

                          ┌─────────────────────────┐
                          │  SQLite (satquery.db)    │◀── query log, image metadata (backend/data/)
                          └─────────────────────────┘
```

## 2. Request lifecycle

1. User uploads 1–2 images and types a query in the React frontend.
2. Frontend sends one `POST /api/v1/query` request per `API_CONTRACT.md`.
3. Backend validates image count/modality against the query, per the rules in `API_CONTRACT.md` §1.
4. Orchestrator classifies intent → one of `vqa | captioning | detection | change_detection | fusion` (`CONTRACT.md` §5).
5. Orchestrator calls the matching function from `AI_SERVICE_CONTRACT.md` — either the RSUniVLM wrapper (4 of the 5 tasks) or the fusion wrapper.
6. The called function returns a typed result including `meta` (tool used, params, latency).
7. Backend assembles the API response (`answer`, `confidence`, `task`, `visual_evidence`, `execution_summary`), optionally logs the query row to SQLite, returns JSON.
8. Frontend renders answer text, confidence, map/image overlay (if any), and the execution-trace panel.

## 3. Why AI functions are in-process, not microservices

For this sprint, `ai_service/rsunivlm` and `ai_service/fusion` are Python packages imported directly by the FastAPI backend process — **not** separate HTTP services. Reasons:

- One model load (RSUniVLM checkpoint) shared in memory across all 4 of its task functions, rather than 4x network round-trips to a separate service.
- No need to stand up, Dockerize, and network 3 separate services under a 4-day clock — this was an explicit lesson from the original team plan (see `SatQuery-AI-Architecture-and-Team-Plan-v2.md` §1.3).
- The contracts in `AI_SERVICE_CONTRACT.md` are still written as clean function boundaries (typed inputs/outputs, no shared mutable state, explicit error types) specifically so this **can** be split into real microservices later without changing the interface — only the call mechanism (`function()` → `http.post()`) would change, not the shapes.

If a future iteration does split these into services, `AI_SERVICE_CONTRACT.md`'s `TypedDict`s map directly onto JSON request/response bodies with no redesign needed.

## 4. Deployment shape (sprint)

- `docker-compose.yml` at repo root with 2 services: `backend` (includes both AI modules in-process) and `frontend`. SQLite file lives on a mounted volume so it survives container restarts during rehearsal.
- No GPU orchestration complexity assumed beyond what's needed to run RSUniVLM inference — document actual GPU/CPU requirements in `ai_service/rsunivlm/README.md` once Person 1 confirms them (Colab/Kaggle T4 during development; local demo machine spec to be confirmed before Day 4).
- No auth, no multi-tenancy, no rate limiting — explicitly out of scope for a hackathon prototype. Do not let anyone spend sprint time on these.

## 5. Data flow ownership (who's allowed to touch what, at runtime)

| Data | Written by | Read by |
|---|---|---|
| Uploaded image files | Backend (on request receipt) | AI service functions (as `PIL.Image`, passed in-memory, not re-read from disk by AI modules) |
| RSUniVLM checkpoint / LoRA adapter | Person 1 (offline, training) | `ai_service/rsunivlm/wrapper.py` only |
| Fusion classifier weights | Person 2 (offline, training) | `ai_service/fusion/wrapper.py` only |
| `queries` / `images` DB rows | Backend only | Backend only (frontend never queries SQLite directly) |

## 6. Non-goals for this sprint (explicitly out of scope)

- Horizontal scaling / load balancing.
- User accounts, auth, multi-user isolation.
- Persisting model outputs beyond the lightweight query log described in `DATABASE_CONTRACT.md`.
- Supporting image formats beyond what's in `API_CONTRACT.md` (GeoTIFF/TIFF for the real evaluation set, PNG/JPEG for benchmark/demo images) — do not add speculative format support.
