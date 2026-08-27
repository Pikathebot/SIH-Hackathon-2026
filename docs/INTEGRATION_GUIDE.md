# INTEGRATION_GUIDE.md — Working in Parallel Without Breaking Each Other

**Version:** 1.0.0

This doc is the practical "how do I not block on someone else's unfinished module" guide. Read this before writing any code, alongside the relevant contract file for your module.

---

## 1. Repo layout (lock this on Day 1)

```
satquery-ai/
├── docs/                          # contract files — see CONTRACT.md
├── AGENTS.md
├── frontend/                      # Person 4
├── backend/                       # Person 3
│   ├── app/
│   ├── data/                      # sqlite db + stored images, gitignored
│   └── tests/
├── ai_service/
│   ├── common/                    # shared types/errors — see AI_SERVICE_CONTRACT.md §1
│   ├── rsunivlm/                  # Person 1
│   │   ├── wrapper.py             # real implementation
│   │   ├── mock.py                # required Day 1
│   │   └── tests/
│   └── fusion/                    # Person 2
│       ├── wrapper.py
│       ├── mock.py
│       └── tests/
└── docker-compose.yml
```

Every module owner works only inside their directory plus `ai_service/common/types.py` (additive changes only, via PR, since it's shared).

## 2. The mock-first workflow (this is what prevents blocking)

**Day 1, before any real model/backend logic is written:**

1. Person 3 writes the FastAPI app against `API_CONTRACT.md` and `AI_SERVICE_CONTRACT.md`, importing from `ai_service.rsunivlm.mock` and `ai_service.fusion.mock`.
2. Person 1 and Person 2 each write their `mock.py` — hardcoded returns matching the exact `TypedDict` shapes in `AI_SERVICE_CONTRACT.md` §1, with a `time.sleep()` matching realistic latency (e.g. mock `[SEG]` sleeps ~30s) so downstream UI/timeout code gets tested against real-ish conditions from day one.
3. Person 4 builds the frontend against the running mock-backed backend — a fully working end-to-end request/response loop exists by end of Day 1, with fake but correctly-shaped data everywhere.
4. As real implementations land (Day 2–3), Person 3 flips `AI_SERVICE_MODE=real` for that module — **no other code changes needed**, because the real `wrapper.py` and the `mock.py` expose identical signatures.

This means nobody is ever blocked waiting for someone else's model to finish training — every integration point has a working stand-in from hour one.

## 3. Environment / config contract

Single `.env.example` at repo root, copied to `.env` locally (gitignored):

```
AI_SERVICE_MODE=real          # mock | real
RSUNIVLM_CHECKPOINT_PATH=./ai_service/rsunivlm/checkpoints/RSUniVLM
RSUNIVLM_LORA_ADAPTER_PATH=./ai_service/rsunivlm/checkpoints/lora_adapter
FUSION_MODEL_PATH=./ai_service/fusion/checkpoints/classifier.pkl
BACKEND_PORT=8000
FRONTEND_PORT=3000
DATABASE_PATH=./backend/data/satquery.db
```

Nobody hardcodes a path, port, or checkpoint location in application code — everything reads from these variables. This is what lets `AI_SERVICE_MODE` swap mock↔real without touching call sites.

## 4. Contract conformance checks

- Both `ai_service/rsunivlm/mock.py` and `wrapper.py` must pass the **same** shared test suite (`ai_service/common/test_contract_conformance.py`) that asserts return shapes match the `TypedDict`s. Same for fusion. This is the mechanism that catches "the real implementation quietly returns a different shape than the mock" before it reaches integration.
- Add a lightweight `pytest` check on the backend side that fires a real `POST /api/v1/query` against a running mock-backed server and asserts the response validates against `API_CONTRACT.md`'s JSON shape (a simple `jsonschema` check is enough — don't over-engineer this for a 4-day sprint).
- Run these checks before every merge to `main`, not just before the final demo.

## 5. Branching & merge discipline

- `main` must always run end-to-end against mocks, even mid-sprint. Nobody merges something that breaks the mock-backed integration loop.
- Feature branches per person: `person1/rsunivlm-wrapper`, `person2/fusion`, `person3/orchestrator`, `person4/frontend-*`.
- Merge to `main` at least once per day (end of each sprint day) — do not let branches diverge for multiple days, there's no time to resolve a large conflict on Day 4.
- Contract file changes (`docs/*.md`) always merge in their own PR, before any implementation PR that depends on them — see `CONTRACT.md` §6.

## 6. When an AI coding agent (Codex/Claude/Antigravity) is doing the work

See `AGENTS.md` for the full rules. Short version: point the agent at the specific contract file(s) for the module it's working on, plus this guide, and tell it explicitly which directory it owns. Do not let an agent "helpfully" touch files outside its module's directory or the shared `ai_service/common/types.py` without a human reviewing that diff specifically.

## 7. Demo-day integration order (mirrors the timeline in the architecture plan)

1. Verify mock-backed end-to-end loop still works (regression check before swapping anything to real).
2. Swap `AI_SERVICE_MODE=real` for RSUniVLM only, re-test all 4 RSUniVLM-backed scenarios.
3. Swap fusion to real, re-test the fusion scenario.
4. Full 5-scenario rehearsal with both real, record backup video.
5. Freeze `main` — no more changes once the backup video is recorded, other than critical bug fixes re-tested immediately.
