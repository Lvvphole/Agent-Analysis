"""WorkspaceAllocator tests (Epic 3 — per-attempt workspace isolation).

The server owns attempt identity. Allocation validates the workspace through the
existing policy, mints a deterministic attempt id, and records the base_commit +
workspace_id it ran against. It is audit metadata only — it decides nothing.
"""

from __future__ import annotations

import pytest

from app.runtime.workspace_allocator import WorkspaceAllocator
from app.runtime.workspace_policy import WorkspacePolicy, WorkspacePolicyError
from app.storage.run_records import RunRecord

from tests.conftest import make_manifest


def _record(run_id="run-1"):
    return RunRecord(run_id=run_id, manifest=make_manifest(run_id=run_id))


def test_allocate_records_base_commit_from_git(git_repo):
    record = _record()
    attempt = WorkspaceAllocator(WorkspacePolicy(git_repo)).allocate(record, str(git_repo))
    assert attempt.attempt_id == "run-1-a1"
    assert attempt.attempt_number == 1
    assert attempt.base_commit and len(attempt.base_commit) == 40
    assert attempt.workspace_id == str(git_repo.resolve())
    assert attempt.final_status is None
    assert attempt.created_at


def test_allocate_base_commit_none_when_not_a_repo(temp_repo):
    attempt = WorkspaceAllocator(WorkspacePolicy(temp_repo)).allocate(_record(), str(temp_repo))
    assert attempt.base_commit is None
    assert attempt.workspace_id == str(temp_repo.resolve())


def test_allocate_increments_attempt_number(temp_repo):
    allocator = WorkspaceAllocator(WorkspacePolicy(temp_repo))
    record = _record()
    first = allocator.allocate(record, str(temp_repo))
    record.attempts.append(first)
    second = allocator.allocate(record, str(temp_repo))
    assert (first.attempt_number, second.attempt_number) == (1, 2)
    assert (first.attempt_id, second.attempt_id) == ("run-1-a1", "run-1-a2")


def test_allocate_rejects_bad_path(temp_repo):
    allocator = WorkspaceAllocator(WorkspacePolicy(temp_repo))
    with pytest.raises(WorkspacePolicyError):
        allocator.allocate(_record(), str(temp_repo / "does_not_exist"))
