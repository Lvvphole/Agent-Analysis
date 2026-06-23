-- Agent-Analysis durable run + evidence schema (Epic 2, PBI 2.1).
--
-- Design goals:
--   * Durable audit history of every run, its handler results, gate results,
--     and verifier decisions (the MVP in-memory registry kept none of this).
--   * A `runs.snapshot` JSONB column is the authoritative record body, so a run
--     reconstructs exactly across restarts without a lossy ORM mapping.
--   * Normalized projection tables make the audit queryable (which gate failed,
--     who decided PASS) without parsing JSON.
--   * `tenant_id` columns are present now so Epic 5 (multi-user) needs no
--     migration to become tenant-aware.
--
-- This file is idempotent (IF NOT EXISTS) so the adapter can apply it on start.
-- It introduces NO authority: nothing here can decide PASS or relax a gate.

CREATE TABLE IF NOT EXISTS runs (
    run_id            TEXT PRIMARY KEY,
    tenant_id         TEXT,
    state             TEXT NOT NULL DEFAULT 'INTAKE',
    final_status      TEXT,                 -- PASS | FAIL | BLOCKED | NULL
    verifier_decision TEXT,                 -- mirror of the verifier's decision
    manifest          JSONB NOT NULL,
    snapshot          JSONB NOT NULL,       -- authoritative RunRecord body
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_runs_tenant ON runs (tenant_id);

-- One execution attempt of a run. Epic 3 (per-attempt isolation) populates
-- base_commit / workspace_id; defined here so attempts are first-class in the
-- schema from the start.
CREATE TABLE IF NOT EXISTS run_attempts (
    attempt_id     TEXT PRIMARY KEY,
    run_id         TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    base_commit    TEXT,
    workspace_id   TEXT,
    final_status   TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (run_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_run_attempts_run ON run_attempts (run_id);

-- One row per handler in a chain execution (projection of
-- ChainExecutionResult.handler_results), ordered by `seq`.
CREATE TABLE IF NOT EXISTS handler_results (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    seq             INTEGER NOT NULL,
    handler_name    TEXT NOT NULL,
    handler_type    TEXT NOT NULL,
    status          TEXT NOT NULL,
    decision        TEXT NOT NULL,
    failure_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata        JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_handler_results_run ON handler_results (run_id);

-- One row per gate result emitted by a handler.
CREATE TABLE IF NOT EXISTS gate_results (
    id           BIGSERIAL PRIMARY KEY,
    run_id       TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    handler_name TEXT NOT NULL,
    gate_name    TEXT NOT NULL,
    status       TEXT NOT NULL,            -- PASS | FAIL | BLOCKED
    passed       BOOLEAN NOT NULL,
    reasons      JSONB NOT NULL DEFAULT '[]'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_gate_results_run ON gate_results (run_id);

-- The independent verifier's decision for a run. This is the durable audit of
-- *who* decided and whether the same-agent ban held — it never grants authority,
-- it records what the verifier already decided.
CREATE TABLE IF NOT EXISTS verifier_decisions (
    id                 BIGSERIAL PRIMARY KEY,
    run_id             TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    task_id            TEXT,
    verifier_run_id    TEXT,
    coding_agent_run_id TEXT,
    decision           TEXT NOT NULL,       -- PASS | FAIL | BLOCKED | PENDING
    failure_reasons    JSONB NOT NULL DEFAULT '[]'::jsonb,
    recorded_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_verifier_decisions_run ON verifier_decisions (run_id);

-- Content-addressed evidence artifacts. Populated by Epic 6 (object-backed
-- artifact store); defined here so the durable schema is complete. `used_as_
-- evidence` stays FALSE for quarantined LLM narrative — it is never proof.
CREATE TABLE IF NOT EXISTS evidence_artifacts (
    id              BIGSERIAL PRIMARY KEY,
    run_id          TEXT NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    attempt_id      TEXT REFERENCES run_attempts (attempt_id) ON DELETE SET NULL,
    tenant_id       TEXT,
    artifact_type   TEXT NOT NULL,
    sha256          TEXT NOT NULL,
    object_uri      TEXT,
    used_as_evidence BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_evidence_artifacts_run ON evidence_artifacts (run_id);
