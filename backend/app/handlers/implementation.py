"""Implementation handlers (handoff Section 11.2, 21 Phase 5).

Real, pure handlers: StrategicDesignGate, AgentOutputQuarantine, ScopeDiff.

Deferred side-effecting steps (AgentInvocation, DiffCapture, TestRunner,
StaticCheck) depend on the git/command/agent runners that the prior build
deferred. They are honest: with no real runner and no caller-provided candidate
evidence they return BLOCKED/SKIPPED with an explicit reason. They never fake a
side effect. A caller may supply *real* candidate evidence (a diff, test output)
via ``request.metadata`` — the ManualAdapter path — to exercise the full chain.
"""

from __future__ import annotations

import json

from app.chains.context import ChainContext
from app.constants import RunType
from app.gates.scope_gate import scope_gate
from app.gates.strategic_programming_gate import strategic_programming_gate
from app.gates.test_gate import TestOutcome
from app.handlers.base import Handler
from app.runners.command_runner import CommandRunner
from app.runners.git_runner import GitRunner
from app.runners.sandbox_policy import build_policy
from app.schemas.chain import ChainRequest, HandlerType
from app.schemas.strategic_programming import StrategicProgramming

_QUARANTINED = ("agent_summary.md", "raw_agent_output.log")


class StrategicDesignGateHandler(Handler):
    name = "StrategicDesignGateHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        design = request.metadata.get("strategic_design")
        if not design:
            return self._fail(
                ["strategic design not provided"], blocked=True,
                corrections=["supply request.metadata.strategic_design with >=2 options"],
            )
        review = StrategicProgramming.model_validate(design)
        context.strategic = review
        return self._from_gates([strategic_programming_gate(review)])


class AgentInvocationHandler(Handler):
    name = "AgentInvocationHandler"
    handler_type = HandlerType.AGENT_INVOCATION

    def handle(self, request: ChainRequest, context: ChainContext):
        candidate = request.metadata.get("manual_candidate")
        if not candidate:
            agent_run_id = request.metadata.get("coding_agent_run_id")
            if agent_run_id:
                # Live invocation is deferred, but a real coding agent produced
                # changes in the working tree out-of-band. Proceed to capture
                # them (there is no narrative to quarantine).
                context.coding_agent_run_id = agent_run_id
                return self._skip(
                    "live agent invocation deferred; capturing pre-existing "
                    "working-tree changes"
                )
            return self._fail(
                ["no agent adapter configured; live Claude Code invocation deferred"],
                blocked=True,
            )
        # Agent output is quarantined: stored as context, never as evidence.
        context.write_quarantined(
            name="agent_summary.md",
            data=str(candidate.get("summary", "")),
            recorded_by=self.name,
        )
        context.write_quarantined(
            name="raw_agent_output.log",
            data=str(candidate.get("raw_output", "")),
            recorded_by=self.name,
        )
        context.shared["candidate"] = candidate
        context.coding_agent_run_id = (
            candidate.get("agent_run_id") or context.coding_agent_run_id
        )
        return self._ok(metadata={"used_as_evidence": False, "claimed_status": "IGNORED"})


class AgentOutputQuarantineHandler(Handler):
    name = "AgentOutputQuarantineHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        # Verify no quarantined agent output leaked into the evidence ledger.
        for entry in context.evidence.ledger.ledger_entries:
            base = entry.artifact_path.replace("\\", "/").rsplit("/", 1)[-1]
            if base in _QUARANTINED:
                return self._fail([f"agent output used as evidence: {base}"])
        context.agent_summary_quarantined = True
        return self._ok()


class DiffCaptureHandler(Handler):
    name = "DiffCaptureHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        candidate = context.shared.get("candidate") or {}
        if candidate.get("diff"):
            # ManualAdapter path: real diff supplied by the caller.
            diff = str(candidate["diff"])
            status = str(candidate.get("git_status", ""))
            diff_check = str(candidate.get("diff_check", ""))
            changed = list(candidate.get("changed_files", []))
            diff_check_ok = True
        else:
            # Real capture from the working tree via the git runner.
            runner = GitRunner(context.repo_fs_path)
            if not runner.is_repo():
                return self._fail(
                    ["diff.patch required; not a git repository and no candidate diff provided"],
                    blocked=True,
                )
            cap = runner.capture()
            if not cap.diff.strip():
                return self._fail(
                    ["diff.patch required; no changes detected in working tree"], blocked=True
                )
            diff, status, diff_check = cap.diff, cap.status, cap.diff_check
            changed, diff_check_ok = cap.changed_files, cap.diff_check_ok

        d = context.record_artifact(
            name="diff.patch", data=diff, artifact_type="DIFF",
            command="git diff", recorded_by=self.name,
        )
        context.record_artifact(
            name="git_status.log", data=status, artifact_type="COMMAND_OUTPUT",
            command="git status --short", recorded_by=self.name,
        )
        context.record_artifact(
            name="diff_check.log", data=diff_check, artifact_type="COMMAND_OUTPUT",
            command="git diff --check", recorded_by=self.name,
        )
        context.changed_files = changed
        if not diff_check_ok:
            return self._fail([f"git diff --check reported errors: {diff_check.strip()[:200]}"])
        return self._ok(artifacts=[d.path])


class TestRunnerHandler(Handler):
    name = "TestRunnerHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        meta = request.metadata
        if meta.get("tests_not_applicable"):
            reason = meta.get("tests_not_applicable_reason", "tests not applicable")
            return self._skip(reason)

        outcomes = meta.get("test_outcomes")
        if outcomes:
            # ManualAdapter path: caller-supplied test outcomes.
            logs = outcomes
            command = "python -m pytest"
        else:
            # Real run via the allowlisted command runner.
            commands = meta.get("test_commands")
            if not commands:
                return self._fail(
                    ["test output required; no test command or test evidence provided"],
                    blocked=True,
                )
            policy = build_policy(
                RunType.IMPLEMENTATION,
                files_in_scope=request.scope.files_in_scope,
                allowed_commands=meta.get("allowed_commands", commands),
                forbidden_commands=meta.get("forbidden_commands", []),
            )
            runner = CommandRunner(policy, cwd=context.repo_fs_path)
            logs, rejected = [], []
            for cmd in commands:
                res = runner.run(cmd)
                if res.rejected:
                    rejected.append(f"{cmd}: {res.reason}")
                    continue
                logs.append(
                    {
                        "command": cmd,
                        "exit_code": res.exit_code,
                        "timed_out": res.timed_out,
                        "stdout": res.stdout,
                        "stderr": res.stderr,
                    }
                )
            if rejected:
                return self._fail(
                    [f"command not allowed: {r}" for r in rejected], blocked=True
                )
            command = "; ".join(commands)

        art = context.record_artifact(
            name="test_output.log",
            data=json.dumps(logs, indent=2),
            artifact_type="TEST",
            command=command,
            result="PASS" if all(o.get("exit_code") == 0 for o in logs) else "FAIL",
            recorded_by=self.name,
        )
        for o in logs:
            context.test_outcomes.append(
                TestOutcome(
                    command=o.get("command", command),
                    ran=True,
                    exit_code=o.get("exit_code", 0),
                    output_path=art.path,
                )
            )
        return self._ok(artifacts=[art.path])


class StaticCheckHandler(Handler):
    name = "StaticCheckHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        # Static checks (lint/typecheck/build) are applicable-only; defer with
        # an explicit, documented reason rather than fake a run.
        return self._skip("static checks deferred (command runner not implemented)")


class ScopeDiffHandler(Handler):
    name = "ScopeDiffHandler"
    handler_type = HandlerType.PURE_CHECK

    def handle(self, request: ChainRequest, context: ChainContext):
        gate = scope_gate(
            context.changed_files,
            files_in_scope=request.scope.files_in_scope,
            files_out_of_scope=request.scope.files_out_of_scope,
        )
        return self._from_gates([gate])


def run_reproduction(
    handler: Handler,
    request: ChainRequest,
    context: ChainContext,
    repro: dict | None,
    *,
    artifact_name: str,
    missing_reason: str,
):
    """Shared reproduction-evidence logic for the BUG_FIX and CI_FAILURE_REPAIR
    preconditions. Proves the reported failure actually reproduces *before* a
    fix is attempted: a fix with no failing baseline has nothing for the
    verifier to confirm.

    Mirrors ``TestRunnerHandler``'s evidence model — a caller-supplied
    ``test_outcomes`` (ManualAdapter path) or a real allowlisted command run —
    but inverts validity: the run must FAIL (non-zero exit) to count. The
    failing run is recorded as hashed evidence and stored on
    ``context.shared["reproduction"]``, but is deliberately NOT appended to
    ``context.test_outcomes`` (the post-fix ``TestRunnerHandler`` owns the
    outcomes the verifier's test gate evaluates, which must all pass).

    Returns ``(result, reproduced, logs)``. ``result`` is a ``HandlerResult`` to
    return immediately (BLOCK on missing evidence, FAIL when it does not
    reproduce, or PASS on success).
    """
    if not repro:
        return (
            handler._fail(
                [missing_reason],
                blocked=True,
                corrections=[
                    "supply request.metadata.reproduction with a failing "
                    "test_outcomes entry or a test_commands list"
                ],
            ),
            False,
            [],
        )

    outcomes = repro.get("test_outcomes")
    if outcomes:
        # ManualAdapter path: caller-supplied reproduction outcomes.
        logs = outcomes
        command = repro.get("command", "python -m pytest")
    else:
        commands = repro.get("test_commands")
        if not commands:
            return (
                handler._fail(
                    ["reproduction provided without test_outcomes or test_commands"],
                    blocked=True,
                ),
                False,
                [],
            )
        policy = build_policy(
            RunType.IMPLEMENTATION,
            files_in_scope=request.scope.files_in_scope,
            allowed_commands=repro.get("allowed_commands", commands),
            forbidden_commands=repro.get("forbidden_commands", []),
        )
        runner = CommandRunner(policy, cwd=context.repo_fs_path)
        logs, rejected = [], []
        for cmd in commands:
            res = runner.run(cmd)
            if res.rejected:
                rejected.append(f"{cmd}: {res.reason}")
                continue
            logs.append(
                {
                    "command": cmd,
                    "exit_code": res.exit_code,
                    "timed_out": res.timed_out,
                    "stdout": res.stdout,
                    "stderr": res.stderr,
                }
            )
        if rejected:
            return (
                handler._fail(
                    [f"command not allowed: {r}" for r in rejected], blocked=True
                ),
                False,
                [],
            )
        command = "; ".join(commands)

    # A valid reproduction must actually fail: a non-zero exit code is the
    # baseline evidence the verifier later confirms was flipped to passing.
    reproduced = any(o.get("exit_code") not in (0, None) for o in logs)
    art = context.record_artifact(
        name=artifact_name,
        data=json.dumps(logs, indent=2),
        artifact_type="TEST",
        command=command,
        result="FAIL" if reproduced else "PASS",
        recorded_by=handler.name,
    )
    if not reproduced:
        return (
            handler._fail(
                [
                    "reproduction did not fail; no baseline bug to fix "
                    "(all reproduction commands exited 0)"
                ],
            ),
            False,
            logs,
        )
    context.shared["reproduction"] = {
        "command": command,
        "artifact": art.path,
        "outcomes": logs,
    }
    return (
        handler._ok(artifacts=[art.path], metadata={"reproduced": True}),
        True,
        logs,
    )


class FailureReproductionHandler(Handler):
    """Bug-fix precondition (Section 11.3): prove the reported failure actually
    reproduces *before* a fix is attempted. Delegates to ``run_reproduction``."""

    name = "FailureReproductionHandler"
    handler_type = HandlerType.READ_ONLY_COMMAND

    def handle(self, request: ChainRequest, context: ChainContext):
        result, _reproduced, _logs = run_reproduction(
            self,
            request,
            context,
            request.metadata.get("reproduction"),
            artifact_name="failure_reproduction.log",
            missing_reason=(
                "reproduction required; a bug fix must first reproduce the failure"
            ),
        )
        return result


HANDLERS = [
    StrategicDesignGateHandler(),
    AgentInvocationHandler(),
    AgentOutputQuarantineHandler(),
    DiffCaptureHandler(),
    TestRunnerHandler(),
    StaticCheckHandler(),
    ScopeDiffHandler(),
    FailureReproductionHandler(),
]
