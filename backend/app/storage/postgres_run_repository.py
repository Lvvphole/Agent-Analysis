"""Postgres-backed :class:`RunRepository` adapter (Epic 2, PBI 2.4).

Persists each run as an authoritative JSON snapshot in ``runs.snapshot`` and
projects the queryable audit rows (handler results, gate results, verifier
decision) into their normalized tables. Reads reconstruct the record from the
snapshot, so the round-trip is lossless and independent of the projection.

The ``psycopg`` (v3) driver is imported lazily so the core install and the whole
in-memory test path never require a database driver. Install it for Postgres
mode with ``pip install -r backend/requirements-postgres.txt``.

Authority note: this adapter only stores and retrieves. It never decides
PASS/FAIL/BLOCKED and never relaxes a gate.
"""

from __future__ import annotations

from pathlib import Path

from app.storage.run_records import RunRecord
from app.storage.run_repository import RunRepository
from app.storage.run_serialization import record_from_snapshot, record_to_snapshot

_SCHEMA_PATH = Path(__file__).resolve().parent / "sql" / "0001_init.sql"


def _require_psycopg():
    try:
        import psycopg  # noqa: PLC0415
        from psycopg.types.json import Jsonb  # noqa: PLC0415
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        raise RuntimeError(
            "PostgresRunRepository requires the 'psycopg' driver. Install it with "
            "`pip install -r backend/requirements-postgres.txt`."
        ) from exc
    return psycopg, Jsonb


class PostgresRunRepository(RunRepository):
    """Durable run store backed by PostgreSQL."""

    def __init__(self, dsn: str, *, apply_schema: bool = True) -> None:
        self._psycopg, self._Jsonb = _require_psycopg()
        self._dsn = dsn
        if apply_schema:
            self.apply_schema()

    def _connect(self):
        return self._psycopg.connect(self._dsn)

    def apply_schema(self) -> None:
        """Apply the idempotent schema migration."""
        ddl = _SCHEMA_PATH.read_text()
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(ddl)
            conn.commit()

    # --- writes -------------------------------------------------------------

    def add(self, record: RunRecord) -> None:
        self.save(record)

    def save(self, record: RunRecord) -> None:
        Jsonb = self._Jsonb
        snapshot = record_to_snapshot(record)
        result = record.chain_execution_result
        # Derive both columns from a single source of truth so they can never
        # disagree (e.g. a later POST /verify must not leave final_status=PASS
        # next to verifier_decision=FAIL). The verifier report, when present, is
        # that source; otherwise fall back to the chain execution result.
        if record.verifier_report is not None:
            decision = record.verifier_report.decision.value
            final_status = decision
            verifier_decision = decision
        elif result is not None:
            final_status = result.final_status
            verifier_decision = result.verifier_decision.value
        else:
            final_status = None
            verifier_decision = None
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO runs
                        (run_id, tenant_id, state, final_status,
                         verifier_decision, manifest, snapshot, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (run_id) DO UPDATE SET
                        tenant_id = EXCLUDED.tenant_id,
                        state = EXCLUDED.state,
                        final_status = EXCLUDED.final_status,
                        verifier_decision = EXCLUDED.verifier_decision,
                        manifest = EXCLUDED.manifest,
                        snapshot = EXCLUDED.snapshot,
                        updated_at = now()
                    """,
                    (
                        record.run_id,
                        record.tenant_id,
                        record.state,
                        final_status,
                        verifier_decision,
                        Jsonb(snapshot["manifest"]),
                        Jsonb(snapshot),
                    ),
                )
                # Rewrite the projection rows for this run (idempotent).
                cur.execute("DELETE FROM handler_results WHERE run_id = %s", (record.run_id,))
                cur.execute("DELETE FROM gate_results WHERE run_id = %s", (record.run_id,))
                cur.execute("DELETE FROM verifier_decisions WHERE run_id = %s", (record.run_id,))
                self._project(cur, record)
            conn.commit()

    def _project(self, cur, record: RunRecord) -> None:
        """Project queryable audit rows from the record (write-side only)."""
        Jsonb = self._Jsonb
        # Per-attempt rows (Epic 3). Upsert rather than delete+reinsert so the
        # evidence_artifacts.attempt_id foreign key is never nulled.
        for attempt in record.attempts:
            cur.execute(
                """
                INSERT INTO run_attempts
                    (attempt_id, run_id, attempt_number, base_commit,
                     workspace_id, final_status)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (attempt_id) DO UPDATE SET
                    attempt_number = EXCLUDED.attempt_number,
                    base_commit = EXCLUDED.base_commit,
                    workspace_id = EXCLUDED.workspace_id,
                    final_status = EXCLUDED.final_status
                """,
                (
                    attempt.attempt_id,
                    record.run_id,
                    attempt.attempt_number,
                    attempt.base_commit,
                    attempt.workspace_id,
                    attempt.final_status,
                ),
            )

        result = record.chain_execution_result
        if result is not None:
            for seq, hr in enumerate(result.handler_results):
                cur.execute(
                    """
                    INSERT INTO handler_results
                        (run_id, seq, handler_name, handler_type, status,
                         decision, failure_reasons, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.run_id,
                        seq,
                        hr.handler_name,
                        hr.handler_type.value,
                        hr.status.value,
                        hr.decision.value,
                        Jsonb(list(hr.failure_reasons)),
                        Jsonb(dict(hr.metadata)),
                    ),
                )
                for gate in hr.gate_results:
                    cur.execute(
                        """
                        INSERT INTO gate_results
                            (run_id, handler_name, gate_name, status, passed, reasons)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            record.run_id,
                            hr.handler_name,
                            gate.gate_name,
                            gate.status.value,
                            gate.passed,
                            Jsonb(list(gate.reasons)),
                        ),
                    )

        report = record.verifier_report
        if report is not None:
            cur.execute(
                """
                INSERT INTO verifier_decisions
                    (run_id, task_id, verifier_run_id, coding_agent_run_id,
                     decision, failure_reasons)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    record.run_id,
                    report.task_id,
                    report.verifier_run_id,
                    report.coding_agent_run_id,
                    report.decision.value,
                    Jsonb(list(report.failure_reasons)),
                ),
            )
        elif result is not None:
            cur.execute(
                """
                INSERT INTO verifier_decisions (run_id, task_id, decision)
                VALUES (%s, %s, %s)
                """,
                (record.run_id, result.task_id, result.verifier_decision.value),
            )

    # --- reads --------------------------------------------------------------

    def get(self, run_id: str) -> RunRecord | None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT snapshot FROM runs WHERE run_id = %s", (run_id,))
                row = cur.fetchone()
        if row is None:
            return None
        return record_from_snapshot(row[0])

    def list(self) -> list[RunRecord]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT snapshot FROM runs ORDER BY created_at")
                rows = cur.fetchall()
        return [record_from_snapshot(row[0]) for row in rows]
