# Agent-Analysis

> A deterministic control system around autonomous AI-generated code.

Agent-Analysis lets an engineer analyze a codebase for AI-generated-code
readiness, capture evidence-backed findings, convert them into Scrum backlog
items, and run **bounded** autonomous implementation through a deterministic
harness — where only **diff + passing tests + independent verifier approval**
can decide `PASS`.

## Core thesis (non-negotiable)

```text
AI narrative is not evidence.
The coding agent cannot self-certify.
Only diff + passing tests + verifier approval can decide PASS.
No auto-merge. No auto-deploy. No direct push to a protected branch.
The PR stays gated.
```

The system is designed so that this path is **impossible**:

```text
Agent says it is done → system marks PASS → PR auto-merges → deploy
```

…and this is the **only** valid path:

```text
Agent creates candidate diff → harness captures evidence → tests/static checks
run → independent verifier approves → PR remains gated → human controls merge
```

## What is implemented in this slice

This slice delivers the **deterministic core** (MVP Build Order Phase 1, plus
the storage primitives and the read-only analysis loop) — the part that can be
fully verified with `pytest`.

| Area | Status |
| --- | --- |
| Pydantic schemas (manifest, scrum, checkpoint, evidence ledger, verifier report, strategic programming, backlog, artifact) | done — `backend/app/schemas/` |
| Pure-function gates (manifest, scrum, evidence, test, scope, strategic-programming, no-self-certification, PR) | done — `backend/app/gates/` |
| State machines + transition guards (implementation + read-only analysis) | done — `backend/app/state_machine.py` |
| Storage: SHA-256 hashing, artifact store, append-only evidence ledger writer, checkpoint writer | done — `backend/app/storage/` |
| Sandbox policy (read-only enforcement, command allowlist) | done — `backend/app/runners/sandbox_policy.py` |
| Retry budget that moves to `BLOCKED` on exhaustion | done — `backend/app/retry_budget.py` |
| Read-only AI-readiness analysis workflow (no repo mutation, hashed evidence, findings) | done — `backend/app/workflows/analysis_workflow.py` |
| Control API (safe endpoints only — **no** merge/deploy/complete) | done — `backend/app/main.py`, `backend/app/api/` |
| JSON Schemas generated from the models | done — `schemas/*.schema.json` |
| Chain of Responsibility layer (router + executor + handlers, harness stays the authority) | done — `backend/app/chains/`, `backend/app/handlers/`, [`docs/chain_of_responsibility.md`](docs/chain_of_responsibility.md) |
| Tests covering every hard rule in Section 19 + the chain layer | done — `backend/tests/` (138) |

## Deferred to later phases (not yet built)

These are intentionally **not** claimed as done:

- Temporal workflow engine integration (the workflows are written as plain,
  Temporal-ready orchestration for now).
- PostgreSQL persistence (the API uses an in-memory registry for the MVP;
  `docker-compose.yml` provisions Postgres for the next phase).
- Docker sandbox runner, git runner, GitHub PR integration (the *policies* and
  *gates* that govern them exist; the side-effecting runners do not).
- Bounded implementation workflow end-to-end (the gates, diff/scope/test
  enforcement, verifier and PR gates it depends on are implemented and tested).
- The Next.js frontend control plane (Phase 6). See `frontend/README.md`.

## Hard gates (all enforced and unit-tested)

`manifest_gate`, `scrum_gate`, `evidence_gate`, `test_gate`, `scope_gate`,
`strategic_programming_gate`, `no_self_certification_gate`, `pr_gate`.

Notable invariants proven by the suite:

- `auto_merge: true` or `auto_deploy: true` -> manifest/PR gate **FAIL**.
- `coding_agent_run_id == verifier_run_id` -> **FAIL** (same-agent verifier ban).
- Unhashed or missing evidence -> **FAIL**.
- Agent summary used as proof -> **FAIL** (quarantine rule).
- Strategic Programming "works but harder to change" -> **FAIL** (blocks Done).
- Definition of Done changed mid-run -> **FAIL**.
- Read-only mode requires **no** `diff.patch`; implementation mode **requires**
  it. Read-only mode never modifies the repo.
- Incorrect canonical local path or GitHub repo URL -> **FAIL**.
- Retry budget exhaustion -> `BLOCKED`.

## Running it

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q                   # 95 tests
python scripts/generate_schemas.py    # regenerate ../schemas/*.schema.json
uvicorn app.main:app --reload         # control API on http://127.0.0.1:8000
```

## Canonical project identity

```text
Local path : C:\Users\Emory Harris\projects\agent-analysis
GitHub repo: https://github.com/Lvvphole/Agent-Analysis
```

These values are validated inside every run manifest and checkpoint
(`backend/app/constants.py`); a manifest that disagrees is rejected.

## Repository layout

```text
agent-analysis/
  backend/
    app/
      constants.py          # canonical identity, enums, state order
      state_machine.py      # state order + transition guards
      retry_budget.py       # bounded autonomy (Section 6.9)
      schemas/              # Pydantic contracts (Section 9)
      gates/                # pure-function gates (Section 13)
      storage/              # hashing, artifact store, ledger/checkpoint writers
      runners/              # sandbox policy (Section 12.5)
      workflows/            # read-only analysis loop (Section 17.1)
      api/                  # FastAPI routers (safe endpoints only)
      main.py               # FastAPI app
    scripts/generate_schemas.py
    tests/                  # 95 tests (Section 19)
    pyproject.toml
  schemas/                  # generated JSON Schemas (Section 10)
  artifacts/                # runtime evidence (git-ignored except .gitkeep)
  frontend/                 # Phase 6 control plane (planned — see README)
  docker-compose.yml
```
