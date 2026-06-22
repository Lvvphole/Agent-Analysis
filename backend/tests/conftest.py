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


# --- Chain of Responsibility builders ---------------------------------------

STRATEGIC_DESIGN = {
    "responsibility_owner": "core",
    "design_options": [
        {"option_id": "A", "summary": "deep module", "tradeoffs": "simple",
         "rejected_or_selected": "selected"},
        {"option_id": "B", "summary": "mega validator", "tradeoffs": "complex",
         "rejected_or_selected": "rejected"},
    ],
    "selected_design": "A",
    "interface_contract": "handle(req, ctx) -> HandlerResult",
}

# A real candidate diff + passing test (the ManualAdapter evidence path).
MANUAL_CANDIDATE = {
    "agent_run_id": "agent-1",
    "summary": "implemented the change",
    "raw_output": "...agent narrative...",
    "diff": "--- a/backend/app/x.py\n+++ b/backend/app/x.py\n@@\n-x=1\n+x=2\n",
    "changed_files": ["backend/app/x.py"],
    "git_status": " M backend/app/x.py",
    "diff_check": "",
}


def make_chain_request(**overrides):
    from app.constants import RunType
    from app.schemas.chain import ChainRequest, TaskType

    task_type = overrides.pop("task_type", TaskType.AI_READINESS_AUDIT)
    mode = overrides.pop("mode", RunType.READ_ONLY_ANALYSIS)
    base = dict(
        run_id="run-1",
        task_id="task-1",
        task_type=task_type,
        mode=mode,
        scrum={
            "product_backlog_item_id": "PBI-1",
            "sprint_goal": "harden the harness",
            "sprint_backlog_task_id": "T-1",
            "definition_of_done_version": "dod-v1",
            "acceptance_criteria": ["analysis must produce hashed evidence"],
        },
    )
    base.update(overrides)
    return ChainRequest(**base)


def make_impl_request(**overrides):
    from app.constants import RunType
    from app.schemas.chain import TaskType

    base = dict(
        task_type=TaskType.IMPLEMENTATION,
        mode=RunType.IMPLEMENTATION,
        scope={"files_in_scope": ["backend/app/**"], "files_out_of_scope": []},
        metadata={"strategic_design": STRATEGIC_DESIGN},
    )
    base.update(overrides)
    base["scrum"] = overrides.get("scrum", {
        "product_backlog_item_id": "PBI-1",
        "sprint_goal": "add a bounded feature",
        "sprint_backlog_task_id": "T-1",
        "definition_of_done_version": "dod-v1",
        "acceptance_criteria": ["feature must return 200"],
    })
    return make_chain_request(**base)


@pytest.fixture
def temp_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "main.py").write_text("print('hi')\n")
    return repo


@pytest.fixture
def artifact_store(tmp_path):
    from app.storage.artifact_store import ArtifactStore

    return ArtifactStore(tmp_path / "artifacts")


@pytest.fixture
def git_repo(tmp_path):
    """An initialised git repo with one committed in-scope file."""
    import subprocess

    repo = tmp_path / "gitrepo"
    (repo / "backend" / "app").mkdir(parents=True)
    (repo / "backend" / "app" / "x.py").write_text("x = 1\n")

    def git(*args):
        subprocess.run(
            ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
            check=True,
            capture_output=True,
        )

    subprocess.run(["git", "init", "-q", str(repo)], check=True, capture_output=True)
    git("add", "-A")
    git("commit", "-q", "-m", "init")
    return repo
