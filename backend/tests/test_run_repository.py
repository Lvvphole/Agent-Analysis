"""Run repository contract, serialization, and durability tests (Epic 2).

The contract tests run against the in-memory adapter always, and against the
Postgres adapter when ``AGENT_ANALYSIS_TEST_DATABASE_URL`` points at a database.
The serialization tests need no database. The restart/projection tests are
Postgres-only and skip without a database.
"""

from __future__ import annotations

import os

import pytest

from app.constants import Decision, RunType
from app.schemas.chain import (
    ChainExecutionResult,
    HandlerDecision,
    HandlerResult,
    HandlerStatus,
    HandlerType,
)
from app.schemas.gate_result import GateResult
from app.schemas.run_manifest import RunManifest
from app.schemas.verifier_report import VerifierReport
from app.storage.run_records import RunRecord
from app.storage.run_repository import InMemoryRunRepository
from app.storage.run_serialization import record_from_snapshot, record_to_snapshot

_PG_DSN = os.environ.get("AGENT_ANALYSIS_TEST_DATABASE_URL")


def _make_result(run_id: str = "run-1") -> ChainExecutionResult:
    return ChainExecutionResult(
        run_id=run_id,
        task_id="task-1",
        task_type="AI_READINESS_AUDIT",
        chain_id="ai_readiness_audit_chain",
        mode=RunType.READ_ONLY_ANALYSIS,
        handler_results=[
            HandlerResult(
                handler_name="AnalysisVerifier",
                handler_type=HandlerType.VERIFIER,
                status=HandlerStatus.PASS,
                decision=HandlerDecision.CONTINUE,
                gate_results=[GateResult.of("evidence_gate", [])],
            )
        ],
        final_status="PASS",
        verifier_decision=Decision.PASS,
    )


def _make_record(manifest: RunManifest, run_id: str = "run-1") -> RunRecord:
    return RunRecord(
        run_id=run_id,
        manifest=manifest,
        state="EXECUTE_CHAIN",
        verifier_report=VerifierReport(
            task_id="task-1",
            run_id=run_id,
            verifier_id="verifier-1",
            verifier_run_id="vr-1",
            coding_agent_run_id="car-1",
            decision=Decision.PASS,
        ),
        chain_execution_result=_make_result(run_id),
        llm_invocations=[{"role": "ANALYST", "hash": "abc"}],
    )


def _assert_same(a: RunRecord, b: RunRecord) -> None:
    assert a.run_id == b.run_id
    assert a.state == b.state
    assert a.manifest == b.manifest
    assert a.verifier_report == b.verifier_report
    assert a.chain_execution_result == b.chain_execution_result
    assert a.llm_invocations == b.llm_invocations
    assert a.tenant_id == b.tenant_id


# --- serialization (no database) --------------------------------------------


def test_snapshot_roundtrip_preserves_record(manifest):
    record = _make_record(manifest)
    rebuilt = record_from_snapshot(record_to_snapshot(record))
    _assert_same(record, rebuilt)


def test_snapshot_roundtrip_empty_record(manifest):
    record = RunRecord(run_id="run-9", manifest=manifest)
    rebuilt = record_from_snapshot(record_to_snapshot(record))
    _assert_same(record, rebuilt)
    assert rebuilt.verifier_report is None
    assert rebuilt.chain_execution_result is None


# --- repository contract (in-memory always; Postgres when configured) -------


def _pg_repo():
    from app.storage.postgres_run_repository import PostgresRunRepository

    repo = PostgresRunRepository(_PG_DSN)
    with repo._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "TRUNCATE runs, run_attempts, handler_results, "
                "gate_results, verifier_decisions, evidence_artifacts CASCADE"
            )
        conn.commit()
    return repo


@pytest.fixture(
    params=[
        "memory",
        pytest.param(
            "postgres",
            marks=pytest.mark.skipif(
                not _PG_DSN, reason="AGENT_ANALYSIS_TEST_DATABASE_URL not set"
            ),
        ),
    ]
)
def repo(request):
    if request.param == "memory":
        return InMemoryRunRepository()
    return _pg_repo()


def test_add_then_get_roundtrip(repo, manifest):
    record = _make_record(manifest)
    repo.add(record)
    _assert_same(record, repo.get("run-1"))


def test_get_missing_returns_none(repo):
    assert repo.get("does-not-exist") is None


def test_list_returns_added_runs(repo, manifest):
    repo.add(_make_record(manifest, run_id="run-1"))
    repo.add(_make_record(manifest.model_copy(update={"run_id": "run-2"}), run_id="run-2"))
    assert {r.run_id for r in repo.list()} == {"run-1", "run-2"}


def test_save_persists_mutation(repo, manifest):
    record = RunRecord(run_id="run-1", manifest=manifest, state="INTAKE")
    repo.add(record)
    record.state = "VERIFY"
    record.verifier_report = VerifierReport(
        task_id="task-1",
        run_id="run-1",
        verifier_id="verifier-1",
        verifier_run_id="vr-1",
        coding_agent_run_id="car-1",
        decision=Decision.FAIL,
    )
    repo.save(record)

    fetched = repo.get("run-1")
    assert fetched.state == "VERIFY"
    assert fetched.verifier_report.decision == Decision.FAIL


# --- durability + projection (Postgres only) --------------------------------


@pytest.mark.skipif(not _PG_DSN, reason="AGENT_ANALYSIS_TEST_DATABASE_URL not set")
def test_run_survives_process_restart(manifest):
    """A fresh repository object (new connections) retrieves a saved run."""
    from app.storage.postgres_run_repository import PostgresRunRepository

    writer = _pg_repo()
    writer.add(_make_record(manifest))

    # Simulate a restart: a brand new adapter instance, no schema re-apply.
    reader = PostgresRunRepository(_PG_DSN, apply_schema=False)
    _assert_same(_make_record(manifest), reader.get("run-1"))


@pytest.mark.skipif(not _PG_DSN, reason="AGENT_ANALYSIS_TEST_DATABASE_URL not set")
def test_save_projects_audit_rows(manifest):
    repo = _pg_repo()
    repo.add(_make_record(manifest))
    with repo._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM handler_results WHERE run_id = 'run-1'")
            handlers = cur.fetchone()[0]
            cur.execute("SELECT count(*) FROM gate_results WHERE run_id = 'run-1'")
            gates = cur.fetchone()[0]
            cur.execute(
                "SELECT decision FROM verifier_decisions WHERE run_id = 'run-1'"
            )
            decision = cur.fetchone()[0]
    assert handlers == 1
    assert gates == 1
    assert decision == "PASS"
