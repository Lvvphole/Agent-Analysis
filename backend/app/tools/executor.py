"""Controlled tool executor.

Runs a registered, policy-approved tool against the run's working tree and
records its output as a hashed, ledgered artifact via the sanctioned
``ChainContext.record_artifact`` path. A tool that is unregistered, forbidden,
or not allowed for the run type is BLOCKED with no execution. A tool whose
recorded artifact has no hash is FAILED — output without an artifact hash is
never a success.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.constants import RunType
from app.storage.hashing import hash_bytes
from app.tools.policy import ALLOWED, ToolPolicy
from app.tools.registry import ToolRegistry
from app.tools.results import ToolResult

if TYPE_CHECKING:  # pragma: no cover
    from app.chains.context import ChainContext


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, policy: ToolPolicy) -> None:
        self.registry = registry
        self.policy = policy

    def run(self, context: "ChainContext", tool_name: str, run_type: RunType) -> ToolResult:
        decision, reason = self.policy.decide(tool_name, run_type)
        if decision != ALLOWED:
            return ToolResult(
                tool_name=tool_name,
                status="BLOCKED",
                policy_decision=decision,
                reason=reason,
            )

        tool = self.registry.get(tool_name)
        input_hash = hash_bytes(f"{tool_name}|{context.repo_fs_path}".encode("utf-8"))
        try:
            data = tool.run(context.repo_fs_path)
        except Exception as exc:  # noqa: BLE001 - report tool failure, never fake success
            return ToolResult(
                tool_name=tool_name,
                status="FAILED",
                policy_decision=decision,
                input_hash=input_hash,
                exit_code=1,
                reason=f"tool execution failed: {exc}",
            )

        if not isinstance(data, str):
            return ToolResult(
                tool_name=tool_name,
                status="FAILED",
                policy_decision=decision,
                input_hash=input_hash,
                exit_code=1,
                reason="tool did not return text output",
            )

        artifact = context.record_artifact(
            name=f"tool_{tool_name}.log",
            data=data,
            artifact_type="COMMAND_OUTPUT",
            command=f"tool:{tool_name}",
            recorded_by="tool_executor",
        )
        if not artifact.hash:
            return ToolResult(
                tool_name=tool_name,
                status="FAILED",
                policy_decision=decision,
                input_hash=input_hash,
                reason="tool output was not hashed",
            )

        return ToolResult(
            tool_name=tool_name,
            status="OK",
            policy_decision=decision,
            input_hash=input_hash,
            output_hash=artifact.hash,
            artifact_path=artifact.path,
            artifact_hash=artifact.hash,
            exit_code=0,
        )
