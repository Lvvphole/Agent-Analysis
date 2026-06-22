"""Command runner tests (handoff Section 12.6, 16)."""

from __future__ import annotations

from app.constants import RunType
from app.runners.command_runner import CommandRunner
from app.runners.sandbox_policy import build_policy


def _runner(tmp_path, timeout=30):
    policy = build_policy(
        RunType.IMPLEMENTATION,
        allowed_commands=["python*"],
        forbidden_commands=["rm -rf*"],
    )
    return CommandRunner(policy, cwd=tmp_path, timeout=timeout)


def test_allowlisted_command_runs_and_captures(tmp_path):
    res = _runner(tmp_path).run("python -c \"print(123)\"")
    assert res.rejected is False
    assert res.exit_code == 0
    assert "123" in res.stdout
    assert res.ok is True


def test_nonzero_exit_captured(tmp_path):
    res = _runner(tmp_path).run("python -c \"import sys; sys.exit(2)\"")
    assert res.exit_code == 2
    assert res.ok is False


def test_forbidden_command_rejected(tmp_path):
    res = _runner(tmp_path).run("rm -rf /tmp/whatever")
    assert res.rejected is True
    assert res.exit_code is None


def test_non_allowlisted_command_rejected(tmp_path):
    res = _runner(tmp_path).run("curl http://example.com")
    assert res.rejected is True


def test_timeout_enforced(tmp_path):
    res = _runner(tmp_path, timeout=1).run("python -c \"import time; time.sleep(5)\"")
    assert res.timed_out is True
    assert res.ok is False
