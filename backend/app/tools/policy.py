"""Tool execution policy.

Decides whether a named tool may run for a given run type. Read-only modes may
run read-only tools only; mutating tools are never allowed in read-only modes,
and a forbidden tool name is never allowed under any run type.
"""

from __future__ import annotations

from app.constants import RunType
from app.tools.registry import FORBIDDEN_TOOL_NAMES, Tool, ToolRegistry

# Policy decision codes (mirrored in ToolResult.policy_decision).
ALLOWED = "ALLOWED"
NOT_REGISTERED = "NOT_REGISTERED"
NOT_ALLOWED_FOR_RUN_TYPE = "NOT_ALLOWED_FOR_RUN_TYPE"
FORBIDDEN = "FORBIDDEN"


class ToolPolicy:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def decide(self, tool_name: str, run_type: RunType) -> tuple[str, str]:
        """Return (decision, reason)."""
        if tool_name in FORBIDDEN_TOOL_NAMES:
            return FORBIDDEN, f"tool '{tool_name}' is forbidden"
        tool: Tool | None = self.registry.get(tool_name)
        if tool is None:
            return NOT_REGISTERED, f"tool '{tool_name}' is not registered"
        if tool.mutating and run_type == RunType.READ_ONLY_ANALYSIS:
            return (
                NOT_ALLOWED_FOR_RUN_TYPE,
                f"mutating tool '{tool_name}' not allowed in read-only run",
            )
        return ALLOWED, ""
