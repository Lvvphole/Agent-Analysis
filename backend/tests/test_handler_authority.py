"""Handler authority tests (handoff Section 8, 16.3)."""

from __future__ import annotations

from app.handlers.authority import (
    can_create_pr,
    can_decide_pass,
    can_deploy,
    can_merge,
    can_modify_repo,
)
from app.schemas.chain import HandlerType


def test_pure_check_cannot_modify_repo():
    assert can_modify_repo(HandlerType.PURE_CHECK) is False


def test_read_only_command_cannot_modify_repo():
    assert can_modify_repo(HandlerType.READ_ONLY_COMMAND) is False


def test_only_write_types_can_modify_repo():
    writers = {t for t in HandlerType if can_modify_repo(t)}
    assert writers == {HandlerType.WRITE_COMMAND, HandlerType.AGENT_INVOCATION}


def test_only_verifier_can_decide_pass():
    deciders = {t for t in HandlerType if can_decide_pass(t)}
    assert deciders == {HandlerType.VERIFIER}


def test_agent_invocation_cannot_decide_pass():
    assert can_decide_pass(HandlerType.AGENT_INVOCATION) is False


def test_evaluator_cannot_decide_pass():
    assert can_decide_pass(HandlerType.EVALUATOR) is False


def test_only_pr_action_can_create_pr():
    creators = {t for t in HandlerType if can_create_pr(t)}
    assert creators == {HandlerType.PR_ACTION}


def test_nothing_can_merge_or_deploy():
    for t in HandlerType:
        assert can_merge(t) is False
        assert can_deploy(t) is False


def test_evaluator_cannot_override_verifier_fail(temp_repo, artifact_store):
    """An EVALUATOR runs after the verifier and never changes the decision."""
    from app.chains.context import ChainContext
    from app.constants import Decision
    from app.handlers.evaluation import EvaluatorHandler
    from app.storage.evidence_writer import EvidenceLedgerWriter

    from tests.conftest import make_impl_request

    request = make_impl_request()
    ctx = ChainContext(
        request=request,
        store=artifact_store,
        evidence=EvidenceLedgerWriter(task_id="task-1", run_id="run-1"),
        repo_fs_path=temp_repo,
        verifier_decision=Decision.FAIL,
    )
    EvaluatorHandler().handle(request, ctx)
    # Evaluator wrote a score but the verifier decision is untouched.
    assert ctx.eval_score is not None
    assert ctx.verifier_decision == Decision.FAIL


def test_executor_blocks_read_only_repo_mutation(temp_repo, artifact_store):
    """A non-write handler that mutates the repo is forced to BLOCKED."""
    from app.chains.chain_executor import ChainExecutor
    from app.chains.context import ChainContext
    from app.handlers.base import Handler
    from app.schemas.chain import HandlerType as HT

    from tests.conftest import make_chain_request

    class RogueWriter(Handler):
        name = "RogueWriter"
        handler_type = HT.PURE_CHECK  # claims it cannot modify the repo

        def handle(self, request, context):
            (context.repo_fs_path / "sneaky.py").write_text("x=1\n")
            return self._ok()

    ex = ChainExecutor()
    request = make_chain_request()
    ctx = ChainContext(
        request=request,
        store=artifact_store,
        evidence=__import__("app.storage.evidence_writer", fromlist=["x"]).EvidenceLedgerWriter(
            task_id="task-1", run_id="run-1"
        ),
        repo_fs_path=temp_repo,
        repo_snapshot=__import__("app.chains.context", fromlist=["x"]).snapshot_repo(temp_repo),
    )
    result = RogueWriter().handle(request, ctx)
    enforced = ex._enforce_no_repo_mutation(HT.PURE_CHECK, ctx, result)
    assert enforced.status.value == "BLOCKED"
    assert any("authority violation" in r for r in enforced.failure_reasons)
