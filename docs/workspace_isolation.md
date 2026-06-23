# Per-Attempt Workspace Isolation (Epic 3)

Every execution of a run is an **attempt**, and the server — never the caller —
owns it. This layer makes attempts first-class: each `POST /runs/{id}/chain/execute`
allocates an attempt with a server-minted `attempt_id`, captures the `base_commit`
and `workspace_id` it ran against, scopes that attempt's evidence on disk, and
persists the attempt into the durable `run_attempts` table. A retry mints the next
attempt.

> Authority is unchanged. Allocation only records *what ran where* — audit
> metadata. It decides no PASS/FAIL/BLOCKED and relaxes no gate; the verifier
> remains the sole PASS authority and quarantined agent narrative is never
> evidence.

## What an attempt records

`RunAttempt` (`backend/app/storage/run_records.py`) mirrors the `run_attempts`
columns and is embedded in `RunRecord.attempts`, so it round-trips through the
snapshot with no new `RunRepository` port method:

| Field | Meaning |
| --- | --- |
| `attempt_id` | Server-owned, deterministic: `{run_id}-a{attempt_number}`. |
| `attempt_number` | 1-based; the next attempt is `len(record.attempts) + 1`. |
| `base_commit` | `git rev-parse HEAD` of the workspace, or `null` when it is not a git repo. |
| `workspace_id` | Opaque, server-owned identifier: `workspace-{run_id}-a{attempt_number}`. Never a host filesystem path — the resolved path stays internal so the audit surface cannot leak server layout. |
| `final_status` | Echo of the attempt's chain result (`PASS`/`FAIL`/`BLOCKED`). Audit only. |
| `created_at` | UTC ISO timestamp of allocation. |

## Allocation flow

`WorkspaceAllocator` (`backend/app/runtime/workspace_allocator.py`) holds a
`WorkspacePolicy` and mints the next attempt:

1. `policy.resolve(requested_path)` — reuses the existing workspace validation
   (empty / outside-root / nonexistent / nested-duplicate paths raise
   `WorkspacePolicyError`, and the endpoint blocks exactly as before, recording
   no attempt).
2. `base_commit = GitRunner(resolved).head_commit()` — reuses the read-only,
   capture-only git runner.
3. `attempt_id = f"{run_id}-a{attempt_number}"`; `workspace_id =
   f"workspace-{run_id}-a{attempt_number}"` (opaque — **not** the resolved path).

`allocate` returns a `WorkspaceAllocation(attempt, execution_path)`: the `attempt`
carries the opaque `workspace_id` (persisted and returned by the API), while the
validated `execution_path` (the resolved host path) stays in-process. The endpoint
runs the chain against `allocation.execution_path` with that attempt's `attempt_id`,
sets `final_status` from the result, appends the attempt to the record, and saves.
Because only the opaque id is ever persisted/returned, `GET /runs/{id}/attempts` and
the `run_attempts.workspace_id` column never expose the host filesystem layout.

## Production mode

`RuntimeSettings.production_mode` (default **False**) gates how a caller-supplied
`execution_path` is treated at `POST /runs/{id}/chain/execute`:

- **Production (`True`)** — a caller-supplied `execution_path` is refused **422**
  (`caller_execution_path_forbidden`); the server allocates the workspace from its
  own `workspace_root`. This closes the path-injection surface.
- **Dev/test (`False`)** — `execution_path` is still accepted, but only after the
  `WorkspacePolicy` validates it. Local development and the existing suite are
  unchanged.

## Evidence scoping

`ArtifactStore(root, attempt_id=...)` writes an attempt's artifacts to
`artifacts/{run_id}/{attempt_id}/` (vs. the flat `artifacts/{run_id}/` when no
`attempt_id` is given — every pre-existing caller is unaffected), so evidence from
different attempts of the same run never collides.

## Persistence

`PostgresRunRepository._project` upserts each `RunRecord.attempts` row into
`run_attempts` (`ON CONFLICT (attempt_id) DO UPDATE`). Upsert, not delete +
reinsert, so the `evidence_artifacts.attempt_id` foreign key is never nulled.
`runs.snapshot` stays the authoritative body; `run_attempts` is the queryable
projection, consistent with `handler_results` / `gate_results`.

## Read surface

`GET /runs/{id}/attempts` returns the recorded attempts for a run (404 if the run
is unknown) — an audit view, with no merge / deploy / complete / bypass / force-pass
anywhere on the surface.

## Deferred

The current runtime is the read-only `AI_READINESS_AUDIT` slice, so this layer is
*logical* allocation. A fresh per-attempt checkout/copy and reset-on-retry land
with live implementation execution; writing `evidence_artifacts` rows lands with
the object-backed artifact store (Epic 6).

## Tests

- `backend/tests/test_workspace_allocator.py` — deterministic `attempt_id`,
  `attempt_number` increment, `base_commit` from a real git repo (and `null`
  without one), opaque `workspace_id` (asserts it is not a host path), bad-path
  rejection.
- `backend/tests/test_runtime_execution_spine.py` — attempt recorded with a real
  `base_commit`; repeated execute increments the attempt number; production mode
  rejects a caller path (422) and allocates the server workspace without one;
  per-attempt artifact directory; `GET /runs/{id}/attempts`.
- `backend/tests/test_run_repository.py` — `attempts` round-trip (memory **and**
  Postgres) and the `run_attempts` projection (Postgres-gated).
