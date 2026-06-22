"""Sandboxed runners (Section 12.5-12.7).

This package holds the policy and (later) the Docker / command / git runners
that execute agent-influenced commands away from the host. For the MVP only the
sandbox *policy* — the part that decides what is permitted — is implemented.
"""

from app.runners.command_runner import CommandResult, CommandRunner
from app.runners.git_runner import GitCapture, GitRunner
from app.runners.sandbox_policy import (
    SandboxPolicy,
    build_policy,
    check_command,
    check_write,
)

__all__ = [
    "CommandResult",
    "CommandRunner",
    "GitCapture",
    "GitRunner",
    "SandboxPolicy",
    "build_policy",
    "check_command",
    "check_write",
]
