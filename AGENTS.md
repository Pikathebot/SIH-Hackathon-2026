# AGENTS.md — Rules for AI Coding Agents Working on SatQuery AI

If you are Codex, Claude, Antigravity, or any other AI coding agent picking up work in this repository: **read this file fully before writing or editing any code.** It tells you what you're allowed to touch, what you must never invent, and what to do when something is ambiguous.

---

## 1. Read the contracts first, every session

Before writing a single line, read (in this order):
1. `docs/CONTRACT.md` — naming conventions, module ownership, glossary of canonical enum values.
2. The specific contract file for the module you've been asked to work on (`docs/API_CONTRACT.md`, `docs/DATABASE_CONTRACT.md`, or `docs/AI_SERVICE_CONTRACT.md`).
3. `docs/INTEGRATION_GUIDE.md` — the mock-first workflow you're expected to follow.

**Do not proceed on assumptions if a contract file answers the question.** If you find yourself about to invent an endpoint name, a field name, a status code, or a function signature — stop and check whether `docs/` already defines it. It almost certainly does.

## 2. You are scoped to one module. Stay inside it.

You will be told which module you own for a given task, e.g. "you are working on `ai_service/rsunivlm/`." Rules:

- Only create/edit files inside your assigned directory, **except**:
  - `ai_service/common/types.py` and `ai_service/common/errors.py` — additive changes only (new fields, new error codes), never rename or remove existing ones without flagging it explicitly to the user as a contract-breaking change.
  - `docs/*.md` — only if the user has explicitly asked you to propose a contract change (see §4). Never silently "fix" or "improve" a contract file while doing implementation work.
- Never edit another module's directory (`frontend/`, `backend/`, the other AI module) even if you can see a bug in it or think you could fix the integration faster by doing so. Flag it to the user instead — cross-module edits from an agent are exactly the kind of silent divergence this contract set exists to prevent.
- Never touch `docker-compose.yml`, `.env.example`, or CI config unless specifically asked.

## 3. Implement exactly the contracted interface — nothing more, nothing different

- Function/endpoint signatures, field names, casing, and enum values must match the relevant `docs/*.md` file **exactly** — not "close enough," not "a slightly cleaner version you thought of." If you genuinely believe the contract has a mistake or a gap, say so explicitly and propose a fix (§4) — do not just implement your preferred version and move on.
- If a contract file specifies a `TypedDict`/interface, your implementation's return values must satisfy it — including optional-vs-required fields. Don't add extra fields "for convenience" that aren't in the contract; downstream code isn't written to expect them and won't be updated to use them.
- Match the required mock (`mock.py`) alongside any real implementation, per `INTEGRATION_GUIDE.md` §2, unless one already exists and works — check before creating a duplicate.
- Match the confidence-score honesty rule in `AI_SERVICE_CONTRACT.md` §2 — never hardcode `confidence: 1.0` or fabricate a score; use the documented heuristic pattern and label it as such.

## 4. If the contract is wrong, missing, or ambiguous

Do not silently guess and do not silently "fix" the contract file yourself as part of an unrelated task. Instead:
1. Stop implementation on the ambiguous part.
2. Tell the user exactly what's missing/ambiguous and propose a specific, minimal addition (not a redesign).
3. Only edit `docs/*.md` if the user confirms — and when you do, bump the version number per `CONTRACT.md` §6 and keep the change additive/backward-compatible unless the user explicitly says a breaking change is acceptable.

## 5. Naming — no exceptions, no "your style" defaults

Follow `CONTRACT.md` §3 exactly:
- HTTP paths: kebab-case, versioned (`/api/v1/...`)
- JSON fields: snake_case
- Python: snake_case functions/vars, PascalCase classes
- TypeScript/React: camelCase vars, PascalCase components
- DB: snake_case, plural table names
- Enum-like strings: lowercase snake_case, must be one of the values already listed in `CONTRACT.md` §5

If your default code-generation style disagrees with any of the above (e.g. you'd normally camelCase JSON fields), override your default — the contract wins.

## 6. Testing expectation

Any function you implement against `AI_SERVICE_CONTRACT.md` must pass the shared conformance test suite referenced in `INTEGRATION_GUIDE.md` §4 before you consider the task done. Any endpoint you implement against `API_CONTRACT.md` must be manually or automatically checked against the example request/response pairs in that file. Don't report a task complete without having run these checks.

## 7. Commit / PR hygiene for agent-authored changes

- Keep contract-file changes and implementation changes in **separate commits/PRs**, even if you're doing both in one session — this preserves the review trail required by `CONTRACT.md` §6.
- Write commit messages that name the module and contract version you implemented against, e.g. `feat(rsunivlm): implement run_detection per AI_SERVICE_CONTRACT.md v1.0.0`.
- If you generated a `mock.py`, say so explicitly in the PR description — the human reviewer needs to know whether they're looking at real inference or a stand-in.

## 8. Multi-agent coordination (Codex / Claude / Antigravity working simultaneously)

- Assume other agents are concurrently editing other modules. Never assume a file outside your module is in its "final" state — read it fresh, don't cache assumptions about it across a long session.
- If you need something from another module (e.g. backend needs a function fusion hasn't implemented yet), use the mock (`INTEGRATION_GUIDE.md` §2) rather than blocking or improvising a fake inline version that isn't the real contract-conformant mock.
- Never rename, move, or refactor a file another module depends on (anything in `ai_service/common/`, any `docs/*.md`) as a side effect of an unrelated task, even if it seems like an obvious cleanup. Small "obvious" renames are exactly what breaks a parallel agent's in-flight work.

## 9. When in doubt

Prefer asking a clarifying question over shipping a guess when the ambiguity is about a cross-module interface (anything in `docs/`). Prefer proceeding with a clearly-stated assumption over asking when the ambiguity is purely internal to your own module's implementation details (things not covered by any contract file, e.g. internal variable names, which library to use for image resizing).
