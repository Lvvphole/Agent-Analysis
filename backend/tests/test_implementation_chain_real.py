"""Implementation chain over real git + command runners (handoff Section 12, 16.5).

No ManualAdapter metadata: the diff is captured from a real working tree and the
tests run through the allowlisted command runner. This is the core thesis loop
running for real.
"""

from __future__ import annotations

from app.chains.chain_executor import ChainExecutor
from app.constants import Decision
from app.schemas.chain import PrStatus

from tests.conftest import STRATEGIC_DESIGN, make_impl_request

_PASS_CMD = "python -c \"import sys; sys.exit(0)\""
_FAIL_CMD = "python -c \"import sys; sys.exit(1)\""


def _meta(**extra):
    base = {
        "strategic_design": STRATEGIC_DESIGN,
        "coding_agent_run_id": "agent-real-1",
        "allowed_commands": ["python*"],
    }
    base.update(extra)
    return base


def _run(git_repo, store, metadata):
    request = make_impl_request(metadata=metadata)
    return ChainExecutor().execute(request, store=store, repo_fs_path=git_repo)


def test_real_diff_and_passing_tests_reach_gated_pr(git_repo, artifact_store):
    (git_repo / "backend" / "app" / "x.py").write_text("x = 2\n")  # in-scope change
    result = _run(git_repo, artifact_store, _meta(test_commands=[_PASS_CMD]))

    assert result.final_status == "PASS"
    assert result.verifier_decision == Decision.PASS
    assert result.pr_status == PrStatus.GATED
    assert result.auto_merge is False and result.auto_deploy is False
    diff = (artifact_store.run_dir("run-1") / "diff.patch").read_text()
    assert "x = 2" in diff  # captured from the real working tree


def test_real_failing_tests_block_pass(git_repo, artifact_store):
    (git_repo / "backend" / "app" / "x.py").write_text("x = 2\n")
    result = _run(git_repo, artifact_store, _meta(test_commands=[_FAIL_CMD]))
    assert result.verifier_decision == Decision.FAIL
    assert result.final_status != "PASS"


def test_forbidden_test_command_blocks(git_repo, artifact_store):
    (git_repo / "backend" / "app" / "x.py").write_text("x = 2\n")
    result = _run(git_repo, artifact_store, _meta(test_commands=["rm -rf /"]))
    assert result.final_status == "BLOCKED"
    test_handler = next(
        h for h in result.handler_results if h.handler_name == "TestRunnerHandler"
    )
    assert test_handler.status.value == "BLOCKED"
    assert any("not allowed" in r for r in test_handler.failure_reasons)


def test_no_changes_blocks_diff_capture(git_repo, artifact_store):
    # No working-tree change: diff capture must BLOCK (diff.patch required).
    result = _run(git_repo, artifact_store, _meta(test_commands=[_PASS_CMD]))
    assert result.final_status == "BLOCKED"
    diff_handler = next(
        h for h in result.handler_results if h.handler_name == "DiffCaptureHandler"
    )
    assert diff_handler.status.value == "BLOCKED"


def test_real_scope_violation_fails(git_repo, artifact_store):
    (git_repo / "other_pkg").mkdir()
    (git_repo / "other_pkg" / "y.py").write_text("y = 1\n")  # out of scope
    result = _run(git_repo, artifact_store, _meta(test_commands=[_PASS_CMD]))
    assert result.final_status != "PASS"
    scope = next(h for h in result.handler_results if h.handler_name == "ScopeDiffHandler")
    assert scope.status.value == "FAIL"


def test_real_same_agent_verifier_fails(git_repo, artifact_store):
    (git_repo / "backend" / "app" / "x.py").write_text("x = 2\n")
    # Coding agent run id collides with the verifier run id => self-certification.
    result = _run(
        git_repo, artifact_store,
        _meta(test_commands=[_PASS_CMD], coding_agent_run_id="impl-verifier"),
    )
    assert result.verifier_decision == Decision.FAIL
    assert result.final_status != "PASS"
