"""Sandbox policy (Section 12.5).

Decides what a run is allowed to do inside the sandbox. The single most
important rule it encodes: READ_ONLY_ANALYSIS mode must not modify repository
files.
"""

from __future__ import annotations

from fnmatch import fnmatch

from pydantic import BaseModel, Field

from app.constants import RunType
from app.schemas.gate_result import GateResult

GATE_NAME = "sandbox_write_policy"


class SandboxPolicy(BaseModel):
    model_config = {"extra": "forbid"}

    read_only: bool
    workspace_path: str = ""
    network_enabled: bool = False
    allowed_commands: list[str] = Field(default_factory=list)
    forbidden_commands: list[str] = Field(default_factory=list)
    files_in_scope: list[str] = Field(default_factory=list)
    files_out_of_scope: list[str] = Field(default_factory=list)
    timeout_seconds: int = 600


def build_policy(
    run_type: RunType,
    *,
    files_in_scope: list[str] | None = None,
    files_out_of_scope: list[str] | None = None,
    allowed_commands: list[str] | None = None,
    forbidden_commands: list[str] | None = None,
    workspace_path: str = "",
) -> SandboxPolicy:
    """Build the policy for a run type.

    Read-only analysis is read-only by construction; implementation mode allows
    writes only inside the approved scope.
    """
    return SandboxPolicy(
        read_only=(run_type == RunType.READ_ONLY_ANALYSIS),
        workspace_path=workspace_path,
        allowed_commands=allowed_commands or [],
        forbidden_commands=forbidden_commands or [],
        files_in_scope=files_in_scope or [],
        files_out_of_scope=files_out_of_scope or [],
    )


def _matches_any(path: str, patterns: list[str]) -> bool:
    norm = path.replace("\\", "/")
    return any(fnmatch(norm, p.replace("\\", "/")) for p in patterns)


def check_write(policy: SandboxPolicy, path: str) -> GateResult:
    """Return PASS only if writing ``path`` is permitted under ``policy``."""
    reasons: list[str] = []
    if policy.read_only:
        reasons.append("read-only mode must not modify repository files")
    elif policy.files_in_scope and not _matches_any(path, policy.files_in_scope):
        reasons.append(f"write outside approved scope: {path}")
    elif _matches_any(path, policy.files_out_of_scope):
        reasons.append(f"write to out-of-scope file: {path}")
    return GateResult.of(GATE_NAME, reasons)


def check_command(policy: SandboxPolicy, command: str) -> GateResult:
    """Return PASS only if ``command`` is allowlisted and not forbidden."""
    reasons: list[str] = []
    if _matches_any(command, policy.forbidden_commands):
        reasons.append(f"forbidden command: {command}")
    elif policy.allowed_commands and not _matches_any(command, policy.allowed_commands):
        reasons.append(f"command not allowlisted: {command}")
    return GateResult.of(GATE_NAME, reasons)
