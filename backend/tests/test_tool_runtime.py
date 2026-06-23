"""Controlled tool runtime tests (runtime spine).

Read-only tools run through policy and produce hashed, ledgered artifacts. A tool
that is unregistered, forbidden, or mutating-in-read-only is BLOCKED with no
execution; a successful run always carries an artifact hash.
"""

from __future__ import annotations

import pytest

from app.chains.context import ChainContext
from app.constants import RunType
from app.storage.evidence_writer import EvidenceLedgerWriter
from app.tools.executor import ToolExecutor
from app.tools.policy import ToolPolicy
from app.tools.registry import FORBIDDEN_TOOL_NAMES, Tool, ToolRegistry, build_default_tool_registry

from tests.conftest import make_chain_request


def _ctx(repo, store):
    return ChainContext(
        request=make_chain_request(),
        store=store,
        evidence=EvidenceLedgerWriter(task_id="task-1", run_id="run-1"),
        repo_fs_path=repo,
    )


def _executor():
    registry = build_default_tool_registry()
    return ToolExecutor(registry, ToolPolicy(registry))


def test_registered_tool_runs_and_hashes(temp_repo, artifact_store):
    ctx = _ctx(temp_repo, artifact_store)
    res = _executor().run(ctx, "list_repo_tree", RunType.READ_ONLY_ANALYSIS)
    assert res.status == "OK"
    assert res.policy_decision == "ALLOWED"
    assert res.artifact_hash and res.output_hash == res.artifact_hash
    assert (artifact_store.run_dir("run-1") / "tool_list_repo_tree.log").exists()
    # The output was ledgered (hashed evidence), linked to the run.
    assert any(e.artifact_type == "COMMAND_OUTPUT" for e in ctx.evidence.ledger.ledger_entries)


def test_unregistered_tool_blocks(temp_repo, artifact_store):
    res = _executor().run(_ctx(temp_repo, artifact_store), "no_such_tool", RunType.READ_ONLY_ANALYSIS)
    assert res.status == "BLOCKED"
    assert res.policy_decision == "NOT_REGISTERED"
    assert not res.artifact_hash


def test_forbidden_tool_name_blocked_by_policy(temp_repo, artifact_store):
    # Even if a forbidden name reaches the policy, it is never allowed.
    res = _executor().run(_ctx(temp_repo, artifact_store), "deploy", RunType.READ_ONLY_ANALYSIS)
    assert res.status == "BLOCKED"
    assert res.policy_decision == "FORBIDDEN"


def test_forbidden_tool_cannot_be_registered():
    registry = ToolRegistry(tools=())
    for name in FORBIDDEN_TOOL_NAMES:
        with pytest.raises(ValueError):
            registry.register(Tool(name, lambda repo: ""))


def test_mutating_tool_blocked_in_read_only(temp_repo, artifact_store):
    registry = ToolRegistry(tools=())
    registry.register(Tool("write_thing", lambda repo: "x", mutating=True))
    executor = ToolExecutor(registry, ToolPolicy(registry))
    res = executor.run(_ctx(temp_repo, artifact_store), "write_thing", RunType.READ_ONLY_ANALYSIS)
    assert res.status == "BLOCKED"
    assert res.policy_decision == "NOT_ALLOWED_FOR_RUN_TYPE"


def test_all_default_tools_succeed(temp_repo, artifact_store):
    ctx = _ctx(temp_repo, artifact_store)
    executor = _executor()
    for name in ("list_repo_tree", "discover_commands", "inspect_ci_config", "inspect_dependencies"):
        res = executor.run(ctx, name, RunType.READ_ONLY_ANALYSIS)
        assert res.ok, (name, res.reason)
        assert res.artifact_hash
