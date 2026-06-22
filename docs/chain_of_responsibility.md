# Chain of Responsibility (inside the deterministic harness)

## Why it was added

Different task types need different ordered steps (analyze a repo, implement a
backlog item, review a diff for security). Hard-coding one workflow does not
scale and tempts an agent to invent its own order. The Chain of Responsibility
layer routes each `task_type` to a **registered, ordered** chain of bounded
handlers — without weakening any existing gate.

## The outer harness remains the authority

The harness, not the chain, is in control. The chain executor
(`backend/app/chains/chain_executor.py`):

- resolves the chain from the registry — a request **must not** invent, remove,
  or reorder handlers;
- runs handlers in registered order **only**;
- routes every artifact through hashing + the append-only evidence ledger +
  a checkpoint after each handler;
- enforces the handler authority matrix;
- decides the final status. **A handler result alone never advances or
  finalizes state.**

## Hard rules (must / must not)

- A chain **must not** auto-merge. A chain **must not** auto-deploy.
- An agent **must not** self-certify; agent narrative is context only and is
  **never** written to the evidence ledger (it is quarantined).
- Only a `VERIFIER` handler **may** decide PASS/FAIL/BLOCKED. The evaluator
  **must not** override the verifier.
- A `PR_ACTION` handler **may** report gated-PR readiness only after a verifier
  PASS; it **must not** merge or deploy. `auto_merge` / `auto_deploy` are always
  `false`.
- Handlers **must not** downgrade a gate FAIL to PASS or treat it as a warning.
- Unknown `task_type` **must** return BLOCKED.
- Read-only analysis **must not** modify the repository; the executor BLOCKS any
  non-write handler that mutates it.

## Handler types and authority matrix

Encoded in `backend/app/handlers/authority.py`.

| Handler Type      | Modify repo?      | Decide PASS? | Create PR?      | Merge? | Deploy? |
| ----------------- | ----------------- | ------------ | --------------- | ------ | ------- |
| PURE_CHECK        | No                | No           | No              | No     | No      |
| READ_ONLY_COMMAND | No                | No           | No              | No     | No      |
| WRITE_COMMAND     | Yes, inside scope | No           | No              | No     | No      |
| AGENT_INVOCATION  | Yes, inside scope | No           | No              | No     | No      |
| VERIFIER          | No                | Yes          | No              | No     | No      |
| PR_ACTION         | No                | No           | Yes, gated only | No     | No      |
| EVALUATOR         | No                | No           | No              | No     | No      |

`merge` and `deploy` are `False` for every type — by construction nothing here
can merge or deploy.

## Registered chains and routing

`backend/app/chains/registry.py` maps `task_type → chain_id` and defines each
chain as an immutable, ordered tuple of handler names:

| task_type | chain |
| --- | --- |
| AI_READINESS_AUDIT | `ai_readiness_audit_chain` (fully implemented, read-only) |
| IMPLEMENTATION / REFACTOR / TEST_COVERAGE_EXPANSION | `implementation_chain` (implemented; real git diff capture + allowlisted test runner; live agent invocation + GitHub push deferred) |
| BUG_FIX | `bug_fix_chain` (registered; execution deferred) |
| SECURITY_REVIEW | `security_review_chain` (registered; deferred) |
| DEPENDENCY_UPDATE | `dependency_update_chain` (registered; deferred) |
| DOCUMENTATION_UPDATE | `documentation_update_chain` (registered; deferred) |
| CI_FAILURE_REPAIR | `ci_failure_repair_chain` (registered; deferred) |

The five deferred chains are registered so routing is deterministic and
complete; executing them BLOCKS on the first unimplemented handler with an
explicit reason — no faked behavior.

## How the verifier stays independent

Verifier handlers (`backend/app/handlers/verification.py`) aggregate the
existing gates (`no_self_certification_gate`, `test_gate`, `evidence_gate`,
`strategic_programming_gate`, `scope_gate`). The executor maps only a `VERIFIER`
handler's status onto the run's verifier decision. The no-self-certification
gate fails when the coding-agent run id equals the verifier run id, so the same
agent can never create and certify the same work.

## How evaluation scores but cannot override the verifier

`EvaluatorHandler` writes an advisory `eval_score` and reads — but never
changes — the verifier decision. Final PASS requires an independent verifier
PASS; the evaluator cannot promote a FAIL.

## State machine integration

The chain runs as the internal `EXECUTE_CHAIN` phase, mapping onto the existing
states (read-only: `AGENT_INVOKE_READONLY → EVIDENCE_CAPTURE`; implementation:
`AGENT_INVOKE → DIFF_CAPTURE → TEST`). Existing transition guards in
`backend/app/state_machine.py` are unchanged.

## Implemented runners

`backend/app/runners/git_runner.py` (capture only: `git status --short`,
`git diff`, `git diff --check`, changed files — **no** merge, **no** push) and
`backend/app/runners/command_runner.py` (allowlisted-only via the sandbox
policy, captured stdout/stderr/exit code, enforced timeout) back the
`DiffCaptureHandler` and `TestRunnerHandler`. The implementation chain therefore
captures a real working-tree diff and runs real tests, then gates the PR behind
an independent verifier PASS. The `request.metadata` ManualAdapter path is kept
for environments without a working tree.

## Honestly deferred

Live Claude Code invocation, the Docker sandbox runner, the GitHub push/PR runner
(branch/commit/push/merge), Temporal, PostgreSQL persistence, the five non-core
chains' execution, security and license scanners, AST analysis, and the frontend
remain deferred.
