"""Shared test builders.

Factories return *valid* objects by default so each test can mutate exactly one
field and assert that the corresponding hard rule fires.
"""

from __future__ import annotations

import pytest

from app.constants import RunType
from app.schemas.evidence_ledger import EvidenceLedger, LedgerEntry
from app.schemas.run_manifest import RunManifest
from app.schemas.scrum_mapping import ScrumMapping
from app.schemas.strategic_programming import DesignOption, StrategicProgramming


def make_manifest(**overrides) -> RunManifest:
    base = dict(
        run_id="run-1",
        goal_id="goal-1",
        task_id="task-1",
        run_type=RunType.IMPLEMENTATION,
        model="claude-opus-4-8",
        prompt_hash="deadbeef",
        definition_of_done_version="dod-v1",
        executor_id="exec-1",
        coding_agent_id="agent-1",
        coding_agent_run_id="car-1",
        verifier_id="verifier-1",
        verifier_run_id="vr-1",
        files_in_scope=["backend/app/**"],
    )
    base.update(overrides)
    return RunManifest(**base)


def make_scrum(**overrides) -> ScrumMapping:
    base = dict(
        product_backlog_item_id="PBI-1",
        product_backlog_item_title="Add manifest gate",
        sprint_id="S-1",
        sprint_goal="Harden the deterministic harness",
        sprint_backlog_task_id="T-1",
        acceptance_criteria=["manifest gate must reject auto_merge true"],
        definition_of_done_version="dod-v1",
        increment_candidate=True,
    )
    base.update(overrides)
    return ScrumMapping(**base)


def make_strategic(**overrides) -> StrategicProgramming:
    base = dict(
        responsibility_owner="harness-core",
        design_options=[
            DesignOption(
                option_id="A",
                summary="Pure-function gates",
                tradeoffs="More modules, simpler testing",
                rejected_or_selected="selected",
            ),
            DesignOption(
                option_id="B",
                summary="One mega-validator",
                tradeoffs="Fewer files, harder to change",
                rejected_or_selected="rejected",
            ),
        ],
        selected_design="A",
        interface_contract="gate(input) -> GateResult",
    )
    base.update(overrides)
    return StrategicProgramming(**base)


def make_ledger(**overrides) -> EvidenceLedger:
    entries = overrides.pop(
        "ledger_entries",
        [
            LedgerEntry(
                entry_id="E0001",
                artifact_type="DIFF",
                artifact_path="artifacts/run-1/diff.patch",
                result="INFO",
                hash="a" * 64,
                recorded_by="executor",
            ),
            LedgerEntry(
                entry_id="E0002",
                artifact_type="TEST",
                artifact_path="artifacts/run-1/test_output.log",
                command="python -m pytest -q",
                result="PASS",
                hash="b" * 64,
                recorded_by="executor",
            ),
        ],
    )
    base = dict(task_id="task-1", run_id="run-1", ledger_entries=entries)
    base.update(overrides)
    return EvidenceLedger(**base)


@pytest.fixture
def manifest() -> RunManifest:
    return make_manifest()
