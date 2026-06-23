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

This slice delivers the **deterministic core** (schemas, gates, state machines,
storage, the read-only analysis loop) **and the Chain of Responsibility routing
layer** built on top of it — all fully verifiable with `pytest`.

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
| Side-effecting git capture + allowlisted command runners (wired into the implementation chain) | done — `backend/app/runners/git_runner.py`, `command_runner.py` |
| Runtime execution spine (safe API execution of a registered chain: workspace policy, controlled provider, tool runtime, structured parsing) | done — `backend/app/runtime/`, `backend/app/agents/`, `backend/app/tools/`, `backend/app/parsing/` |
| Durable run persistence behind a port (in-memory default + PostgreSQL adapter, durable audit schema) | done — `backend/app/storage/run_repository.py`, `postgres_run_repository.py`, [`docs/persistence.md`](docs/persistence.md) |
| Per-attempt workspace isolation (server-owned attempt allocation, `base_commit` + `workspace_id` per attempt, per-attempt evidence scoping, production-mode rejection of caller paths) | done — `backend/app/runtime/workspace_allocator.py`, [`docs/workspace_isolation.md`](docs/workspace_isolation.md) |
| Tests covering every hard rule in Section 19 + the chain layer + runners + runtime spine + persistence + per-attempt isolation | done — `backend/tests/` (271; +9 Postgres-gated) |

## Chain of Responsibility (task routing inside the harness)

The harness stays the **outer authority**; a registered, immutable chain routes
each `task_type` through ordered, bounded handlers. Full reference:
[`docs/chain_of_responsibility.md`](docs/chain_of_responsibility.md).

- **Registry** (`backend/app/chains/registry.py`) — 9 task types mapped to ordered
  chains; unknown `task_type` → **BLOCKED**; a request cannot reorder a chain.
- **Executor** (`backend/app/chains/chain_executor.py`) — runs handlers in
  registered order only, routes every artifact through hashing → evidence ledger →
  checkpoint, enforces the authority matrix, and decides final status (PASS
  requires an independent `VERIFIER`).
- **Authority matrix** (`backend/app/handlers/authority.py`) — only `VERIFIER`
  decides PASS; only `PR_ACTION` creates a gated PR; `merge`/`deploy` are `false`
  for every handler type. Agent narrative is quarantined out of the evidence ledger.
- **Chains** — `AI_READINESS_AUDIT` runs end-to-end (read-only, hashed evidence,
  independent verifier); `IMPLEMENTATION` captures a real working-tree diff (git
  runner) and runs real allowlisted tests (command runner), gating the PR behind
  an independent verifier PASS.
- **Runtime execution spine** (`backend/app/runtime/`) — `POST /runs/{id}/chain/execute`
  actually *runs* the registered chain via the executor (not just plans it). It
  binds the request to **server-owned identity** (the URL `run_id` is authoritative:
  a body `run_id`/`task_id` that diverges from the URL or the registered manifest is
  rejected **422** and never executes; an empty `run_id` is adopted from the URL),
  validates the real filesystem path against a **workspace policy**
  (`runtime/workspace_policy.py`), runs read-only repo **tools** through policy with
  hashed output (`app/tools/`), invokes a **controlled model provider** built on the
  LLM layer (`app/agents/` — deterministic `fake`/`manual` adapters; no live
  provider in this slice), **quarantines** raw output and **schema-validates** the
  structured output (`app/parsing/`). The agent only *informs* analysis — it never
  decides PASS and never enters the evidence ledger as proof. A configured-but-
  unavailable provider → **BLOCKED**, never a fabricated PASS.
- **Per-attempt isolation** (`backend/app/runtime/workspace_allocator.py`) — every
  `execute` is a **server-owned attempt**: the server mints the `attempt_id`, captures
  the `base_commit` (real `git rev-parse HEAD`) and `workspace_id` it ran against, and
  scopes that attempt's evidence to `artifacts/{run_id}/{attempt_id}/`. A retry mints
  the next attempt. In **production mode** a caller-supplied `execution_path` is refused
  **422** (the server owns workspace allocation); dev keeps accepting it after the
  workspace policy validates it. Attempts persist into the `run_attempts` table.
  See [`docs/workspace_isolation.md`](docs/workspace_isolation.md).
- **API** — `GET /chains`, `GET /chains/{id}`, `POST /runs/{id}/chain` (plan),
  `POST /runs/{id}/chain/execute` (run), `GET /runs/{id}/chain/results`,
  `GET /runs/{id}/attempts` (no merge/deploy/complete/bypass/force-pass).

## Deferred to later phases (not yet built)

These are intentionally **not** claimed as done:

- Temporal workflow engine integration (the workflows are written as plain,
  Temporal-ready orchestration for now).
- Async worker execution, tenant isolation/auth, and object-backed artifact
  storage (Epics 4–6). Run persistence itself is **done**: runs live behind a
  `RunRepository` port with an in-memory default and a durable PostgreSQL adapter
  (`AGENT_ANALYSIS_DATABASE_URL`); see [`docs/persistence.md`](docs/persistence.md).
  The `runs`/`evidence_artifacts` schema reserves `tenant_id` for Epic 5.
- Docker sandbox runner and GitHub push/PR integration (the *policies* and
  *gates* that govern them exist; those side-effecting runners do not). The git
  runner (read-only working-tree capture) and allowlisted command runner *are*
  built.
- **Live model providers.** The runtime spine invokes models through a controlled
  provider abstraction, but ships only deterministic `fake`/`manual` adapters and
  the existing `stub` LLM adapter — **no** live Anthropic/OpenAI/Gemini/Claude
  Code/Codex calls. A real provider requires keys, network policy, rate limits,
  invocation recording, and tests before it is wired; until then a
  configured-but-unavailable provider returns **BLOCKED**.
- Live agent-driven `IMPLEMENTATION` execution beyond the read-only
  `AI_READINESS_AUDIT` runtime slice; the other chains remain plan-and-test only.
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
- Execute request whose body `run_id`/`task_id` diverges from the URL/registered
  identity -> **422**, chain never executes (no artifacts under a divergent id).
- Retry budget exhaustion -> `BLOCKED`.

## Running it

```bash
cd backend
python -m pip install -r requirements-dev.txt
python -m pytest -q                   # 262 tests (+6 Postgres-gated, skipped without a DB)
python scripts/generate_schemas.py    # regenerate ../schemas/*.schema.json
uvicorn app.main:app --reload         # control API on http://127.0.0.1:8000
```

## GitHub enforcement

The harness runs as a GitHub Actions workflow on every pull request to `main`:
[`.github/workflows/Agent-Analysis-Verification.yml`](.github/workflows/Agent-Analysis-Verification.yml).
It installs the backend dev dependencies, runs `python -m pytest -q`, and runs
`git diff --check` against the PR base. The job exposes a **stable required-check
name**: `agent-analysis-verification`.

> **Status: advisory until the check is required.** The workflow runs on every
> PR, but a workflow that merely *runs* does not block a merge. Agent-Analysis
> only becomes *enforcing* once `main` is configured with a branch ruleset that
> **requires** the `agent-analysis-verification` status check before merge.

Merge stays **human-controlled**. The workflow introduces **no** auto-merge,
auto-deploy, or force-pass behavior — it only reports PASS/FAIL on the PR. See
[`docs/github_enforcement.md`](docs/github_enforcement.md) for the exact branch
ruleset configuration that turns this advisory check into a required gate.

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
      storage/              # hashing, artifact store, ledger/checkpoint writers,
                            #   run repository port + in-memory & Postgres adapters, sql/
      runners/              # sandbox policy + git capture + command runner
      llm/                  # controlled LLM layer (adapter, router, recorder, stub)
      workflows/            # read-only analysis loop (Section 17.1)
      chains/               # CoR registry, executor, context (task routing)
      handlers/             # bounded handlers + authority matrix
      runtime/              # execution spine: workspace policy + runtime executor
      agents/               # controlled provider runtime (fake/manual adapters)
      tools/                # read-only tool registry + policy + executor
      parsing/              # structured output parser + agent-output quarantine
      api/                  # FastAPI routers (safe endpoints only)
      main.py               # FastAPI app
    scripts/generate_schemas.py
    tests/                  # 262 tests (+6 Postgres-gated)
    pyproject.toml
  schemas/                  # generated JSON Schemas (Section 10)
  docs/                     # chain_of_responsibility.md, github_enforcement.md, persistence.md
  artifacts/                # runtime evidence (git-ignored except .gitkeep)
  frontend/                 # Phase 6 control plane (planned — see README)
  docker-compose.yml
```
