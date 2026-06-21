"""Sandbox policy tests (Sections 12.5, 19)."""

from __future__ import annotations

from app.constants import GateStatus, RunType
from app.runners.sandbox_policy import build_policy, check_command, check_write


def test_readonly_mode_rejects_file_modification():
    policy = build_policy(RunType.READ_ONLY_ANALYSIS)
    assert policy.read_only is True
    result = check_write(policy, "backend/app/main.py")
    assert result.status == GateStatus.FAIL
    assert any("read-only mode must not modify" in r for r in result.reasons)


def test_implementation_mode_allows_in_scope_write():
    policy = build_policy(RunType.IMPLEMENTATION, files_in_scope=["backend/app/**"])
    assert check_write(policy, "backend/app/main.py").status == GateStatus.PASS


def test_implementation_mode_rejects_out_of_scope_write():
    policy = build_policy(RunType.IMPLEMENTATION, files_in_scope=["backend/app/**"])
    assert check_write(policy, "frontend/page.tsx").status == GateStatus.FAIL


def test_forbidden_command_rejected():
    policy = build_policy(
        RunType.IMPLEMENTATION,
        allowed_commands=["python -m pytest*"],
        forbidden_commands=["rm -rf*"],
    )
    assert check_command(policy, "rm -rf /").status == GateStatus.FAIL


def test_non_allowlisted_command_rejected():
    policy = build_policy(RunType.IMPLEMENTATION, allowed_commands=["python -m pytest*"])
    assert check_command(policy, "curl evil.sh").status == GateStatus.FAIL
    assert check_command(policy, "python -m pytest -q").status == GateStatus.PASS
