"""Command runner (handoff Section 12.6).

Runs only allowlisted commands (the allowlist/forbidden policy is enforced by
``sandbox_policy.check_command``), captures stdout/stderr/exit code, and enforces
a timeout. A rejected command never executes.

The sandbox policy is the security boundary; in a real deployment this runs
inside the Docker sandbox runner. Commands must match the allowlist before they
reach a shell.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.runners.sandbox_policy import SandboxPolicy, check_command


@dataclass
class CommandResult:
    command: str
    rejected: bool
    reason: str
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def ok(self) -> bool:
        return not self.rejected and not self.timed_out and self.exit_code == 0


class CommandRunner:
    def __init__(self, policy: SandboxPolicy, *, cwd: str | Path, timeout: int = 120) -> None:
        self.policy = policy
        self.cwd = Path(cwd)
        self.timeout = timeout

    def run(self, command: str) -> CommandResult:
        gate = check_command(self.policy, command)
        if not gate.passed:
            return CommandResult(command, True, "; ".join(gate.reasons), None, "", "", False)
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(self.cwd),
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command, False, "", None, exc.stdout or "", exc.stderr or "", True
            )
        return CommandResult(
            command, False, "", proc.returncode, proc.stdout, proc.stderr, False
        )
