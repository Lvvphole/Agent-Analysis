"""WorkspaceAllocator tests (Epic 3 — per-attempt workspace isolation).

The server owns attempt identity. Allocation validates the workspace through the
existing policy, mints a deterministic attempt id, and records the base_commit +
workspace_id it ran against. It is audit metadata only — it decides nothing.
"""

from __future__ import annotations

import os

import pytest

from app.runtime.workspace_allocator import WorkspaceAllocator
from app.runtime.workspace_policy import WorkspacePolicy, WorkspacePolicyError
from app.storage.run_records import RunRecord

from tests.conftest import make_manifest


def _record(run_id="run-1"):
    return RunRecord(run_id=run_id, manifest=make_manifest(run_id=run_id))


def test_allocate_records_base_commit_from_git(git_repo):
    record = _record()
    alloc = WorkspaceAllocator(WorkspacePolicy(git_repo)).allocate(record, str(git_repo))
    attempt = alloc.attempt
    assert attempt.attempt_id == "run-1-a1"
    assert attempt.attempt_number == 1
    assert attempt.base_commit and len(attempt.base_commit) == 40
    assert attempt.workspace_id == "workspace-run-1-a1"
    assert attempt.final_status is None
    assert attempt.created_at
    # The validated host path travels on the allocation, not on the attempt.
    assert alloc.execution_path == git_repo.resolve()


def test_allocate_workspace_id_is_opaque_not_a_path(git_repo):
    """The public/persisted workspace_id must never carry the host filesystem path."""
    alloc = WorkspaceAllocator(WorkspacePolicy(git_repo)).allocate(_record(), str(git_repo))
    workspace_id = alloc.attempt.workspace_id
    assert workspace_id == "workspace-run-1-a1"
    assert not os.path.isabs(workspace_id)
    assert str(git_repo.resolve()) not in workspace_id


def test_allocate_base_commit_none_when_not_a_repo(temp_repo):
    alloc = WorkspaceAllocator(WorkspacePolicy(temp_repo)).allocate(_record(), str(temp_repo))
    assert alloc.attempt.base_commit is None
    assert alloc.attempt.workspace_id == "workspace-run-1-a1"
    assert alloc.execution_path == temp_repo.resolve()


def test_allocate_increments_attempt_number(temp_repo):
    allocator = WorkspaceAllocator(WorkspacePolicy(temp_repo))
    record = _record()
    first = allocator.allocate(record, str(temp_repo)).attempt
    record.attempts.append(first)
    second = allocator.allocate(record, str(temp_repo)).attempt
    assert (first.attempt_number, second.attempt_number) == (1, 2)
    assert (first.attempt_id, second.attempt_id) == ("run-1-a1", "run-1-a2")
    assert (first.workspace_id, second.workspace_id) == (
        "workspace-run-1-a1",
        "workspace-run-1-a2",
    )


def test_allocate_rejects_bad_path(temp_repo):
    allocator = WorkspaceAllocator(WorkspacePolicy(temp_repo))
    with pytest.raises(WorkspacePolicyError):
        allocator.allocate(_record(), str(temp_repo / "does_not_exist"))
