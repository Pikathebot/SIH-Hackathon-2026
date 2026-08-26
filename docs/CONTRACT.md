# CONTRACT.md — SatQuery AI Single Source of Truth

**Status:** LOCKED for sprint (v1.0.0) — see "How to change this contract" before editing anything.
**Applies to:** all humans and AI coding agents (Codex, Claude, Antigravity, etc.) working on any module of SatQuery AI.

This document is the root of the contract set. If any other doc, any code comment, or any agent's assumption disagrees with these files, **these files win.** Code is wrong until the contract is updated; the contract is never silently overridden by code.

---

## 1. Purpose

Four+ people and multiple AI coding agents are building four independently-developed modules in parallel:

| Module | Owner | Repo path |
|---|---|---|
| Frontend (React) | Person 4 | `frontend/` |
| Backend + Orchestrator (FastAPI) | Person 3 | `backend/` |
| AI Service — RSUniVLM wrapper (VQA/captioning/detection/change) | Person 1 | `ai_service/rsunivlm/` |
| AI Service — Optical–SAR Fusion | Person 2 | `ai_service/fusion/` |

Without a written contract, each of these will independently invent endpoint names, field names, enum values, and error shapes — and integration on Day 3–4 will fail. This file set exists so that **no two people (or agents) ever need to talk to each other to agree on an interface** — they read the contract instead.

## 2. The contract file set

| File | Defines |
|---|---|
| `CONTRACT.md` (this file) | Ownership, naming conventions, glossary, change process |
| `docs/API_CONTRACT.md` | The HTTP API between frontend and backend |
| `docs/DATABASE_CONTRACT.md` | Schema for anything persisted (query log, image metadata) |
| `docs/AI_SERVICE_CONTRACT.md` | Python function contracts between the orchestrator and the two AI modules |
| `docs/INTEGRATION_GUIDE.md` | How to build against a contract before the real thing exists, and how to verify conformance |
| `docs/ARCHITECTURE.md` | System diagram, request lifecycle, deployment shape |
| `AGENTS.md` | Operating rules specifically for AI coding agents working in this repo |

## 3. Canonical naming conventions (apply everywhere, no exceptions)

| Context | Convention | Example |
|---|---|---|
| HTTP URL paths | lowercase, kebab-case, versioned | `/api/v1/query` |
| JSON field names (requests & responses) | snake_case | `execution_summary`, `image_ids` |
| Python identifiers | snake_case functions/vars, PascalCase classes | `run_vqa()`, `class QueryRequest` |
| TypeScript/React identifiers | camelCase vars/functions, PascalCase components/types | `queryResult`, `ResultsPanel` |
| Database tables | snake_case, plural | `queries`, `images` |
| Database columns | snake_case | `created_at`, `tool_used` |
| Enum-like string values (task types, tool names) | lowercase snake_case, defined once in §5 | `change_detection`, `rsunivlm_seg` |
| Environment variables | UPPER_SNAKE_CASE | `RSUNIVLM_CHECKPOINT_PATH` |
| IDs | UUID v4 strings, field name always `id` or `<noun>_id` | `image_id: "3f9e..."` |

**Never** invent a new casing style, abbreviate a field name to save keystrokes, or use a synonym for a term already defined in §5. If a term you need isn't defined, that's a contract gap — flag it (see §6), don't guess.

## 4. Module boundaries (what each owner may change without asking)

- **Frontend (Person 4):** everything inside `frontend/`. May freely change UI, state management, component structure. **May not** change request/response shapes — those live in `API_CONTRACT.md`.
- **Backend/Orchestrator (Person 3):** everything inside `backend/`, including intent-classification logic and routing rules. **May not** change the external `/api/v1/query` contract or the internal AI service function signatures without a contract change (§6).
- **AI Service — RSUniVLM (Person 1):** everything inside `ai_service/rsunivlm/`, including prompt engineering, LoRA training code, checkpoint management. **Must** expose exactly the function signatures in `AI_SERVICE_CONTRACT.md` — internal implementation is otherwise unconstrained.
- **AI Service — Fusion (Person 2):** everything inside `ai_service/fusion/`, same rule as above for `run_fusion()`.
- **No module reaches into another module's internals.** Frontend never imports backend Python. Backend never imports AI-service internals beyond the contracted function calls. All cross-module communication goes through the contracts in this file set.

## 5. Glossary — canonical enum values (defined once, used everywhere)

### `task` (selected_task / task field in API responses)
`vqa` | `captioning` | `detection` | `change_detection` | `fusion`

### `tool_used` (which underlying model/mode actually ran)
`rsunivlm_vqa` | `rsunivlm_cap` | `rsunivlm_vg` | `rsunivlm_seg` | `rsunivlm_ccd` | `fusion_classifier`

### `modality` (image field)
`optical` | `sar`

### `visual_evidence.type`
`none` | `bbox` | `mask`

If you need a value not on these lists, propose an addition via the change process in §6 — do not invent a new string and ship it.

## 6. How to change this contract

1. Open a PR that edits the relevant `docs/*.md` file(s) only — no application code in the same PR.
2. Title it `[CONTRACT CHANGE] <short description>`.
3. Tag all four module owners. Requires at least one explicit approval from the owner of each module the change affects.
4. Bump the version number at the top of the affected file(s) (semver: breaking change = major, additive/backward-compatible = minor).
5. Only after merge may implementation PRs depend on the new shape.

Mid-sprint, breaking changes should be treated as expensive — prefer additive changes (new optional field, new enum value) over renames or removals.

## 7. Non-negotiables

- The AI functions run **in-process** (direct Python calls within the FastAPI backend), not as separate network services, for this sprint. Contracts are still written as if they were service boundaries so the code stays swappable later — see `ARCHITECTURE.md` §3.
- Every response the backend sends to the frontend must include `execution_summary` — this is the visible proof of "agentic orchestration" the judges score. No shortcuts that drop it, even in error paths.
- `confidence` is always a float in `[0.0, 1.0]`. If a tool has no real confidence signal, use a documented heuristic (see `AI_SERVICE_CONTRACT.md`) — never omit the field or hardcode `1.0`.
