"""Tool execution result record.

Every controlled tool run produces one of these. A tool's output is only usable
once it is a hashed, ledgered artifact linked to the run/task; a result without
an ``artifact_hash`` is not a success.
"""

from __future__ import annotations

from pydantic import BaseModel


class ToolResult(BaseModel):
    model_config = {"extra": "forbid"}

    tool_name: str
    status: str  # OK | BLOCKED | FAILED
    policy_decision: str  # ALLOWED | NOT_REGISTERED | NOT_ALLOWED_FOR_RUN_TYPE | FORBIDDEN
    input_hash: str = ""
    output_hash: str = ""
    artifact_path: str = ""
    artifact_hash: str = ""
    exit_code: int = 0
    reason: str = ""

    @property
    def ok(self) -> bool:
        return self.status == "OK"
